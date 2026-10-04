"""The :class:`KinectSensor` facade: frame capture, hardware sync, video and audio."""

from __future__ import annotations

import contextlib
import ctypes
import logging
import math
import threading
import time
from collections.abc import Callable, Generator
from types import TracebackType
from typing import Any, Final, Protocol

import numpy as np
import numpy.typing as npt
from typing_extensions import Self

from kinect_next.core._audio_pump import AudioPump
from kinect_next.core._cancel import CancelToken, WaitCancelledError
from kinect_next.core.audio import AudioController
from kinect_next.core.enums import (
    JOINT_COUNT,
    ColorImageFormat,
    FrameEdges,
    HandState,
    JointType,
    StreamType,
    TrackingConfidence,
    TrackingState,
)
from kinect_next.core.exceptions import (
    COMOperationError,
    KinectClosedError,
    KinectError,
    KinectTimeoutError,
    StreamNotEnabledError,
)
from kinect_next.core.mapper import CoordinateMapper
from kinect_next.models.audio import AudioFrame
from kinect_next.models.body import Body, Hand, Joint, JointCollection
from kinect_next.models.body_index import BodyIndexFrame
from kinect_next.models.color import ColorCameraSettings, ColorFrame
from kinect_next.models.depth import DepthFrame
from kinect_next.models.frameset import FrameSet
from kinect_next.models.geometry import Point2D, Quaternion, Vector3, Vector4
from kinect_next.models.infrared import InfraredFrame, LongExposureInfraredFrame
from kinect_next.native.interfaces import (
    IBody,
    IBodyFrame,
    IKinectSensorNative,
    IMultiSourceFrame,
    IMultiSourceFrameReader,
)
from kinect_next.native.win32 import (
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    close_handle,
    create_event,
    get_default_kinect_sensor,
    set_event,
    wait_for_multiple_objects,
)

_log = logging.getLogger("kinect_next")

MAX_BODY_COUNT: Final = 6

DEFAULT_TIMEOUT_MS: Final = 5000
"""Default wait budget. Generous on purpose: after a cold :meth:`KinectSensor.open`
the runtime needs 1-3 s before the first video and audio frames appear."""

_COLOR_SHAPE: Final = (1080, 1920, 4)
_DEPTH_SHAPE: Final = (424, 512)
_COLOR_BYTES: Final = 1080 * 1920 * 4
_DEPTH_PIXELS: Final = 512 * 424

_AUDIO_SUBFRAME_MS: Final = 16.0
_NS_PER_TICK: Final = 100
_WAIT_WOKEN: Final = WAIT_OBJECT_0 + 1


# ---------------------------------------------------------------------------
# Process-wide shared IKinectSensor
#
# ``GetDefaultKinectSensor`` returns the one physical device. Several
# ``KinectSensor`` objects in the same process must therefore share a single
# native ``IKinectSensor`` and only ``Close()`` it once the last one is done --
# otherwise closing one instance tears the hardware out from under the others.
# ---------------------------------------------------------------------------
_shared_lock = threading.Lock()
_shared_sensor: IKinectSensorNative | None = None
_shared_refcount = 0


def _acquire_shared_sensor() -> IKinectSensorNative:
    global _shared_sensor, _shared_refcount
    with _shared_lock:
        if _shared_sensor is None:
            sensor = IKinectSensorNative(get_default_kinect_sensor())
            sensor.open()
            _shared_sensor = sensor
        _shared_refcount += 1
        return _shared_sensor


def _release_shared_sensor() -> None:
    global _shared_sensor, _shared_refcount
    with _shared_lock:
        if _shared_refcount == 0:
            return
        _shared_refcount -= 1
        if _shared_refcount == 0 and _shared_sensor is not None:
            with contextlib.suppress(COMOperationError, OSError):
                _shared_sensor.close()
            _shared_sensor.release()
            _shared_sensor = None


class _PlanarFrame(Protocol):
    """Any single-plane frame that copies straight into a buffer."""

    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None: ...
    def get_relative_time(self) -> int: ...
    def release(self) -> int: ...


class _PlanarRef(Protocol):
    """A frame reference yielding a :class:`_PlanarFrame`."""

    def acquire_frame(self) -> _PlanarFrame | None: ...
    def release(self) -> int: ...


def _safe(func: Callable[..., object], *args: object) -> None:
    """Call ``func(*args)`` swallowing COM errors during teardown."""
    try:
        func(*args)
    except (COMOperationError, OSError) as exc:
        _log.debug("Ignored error during cleanup: %s", exc)


class KinectSensor:
    """High-level controller for a Microsoft Kinect v2.

    Supports use as a context manager and frame-synchronised streaming::

        with KinectSensor(StreamType.COLOR | StreamType.BODY) as kinect:
            for frames in kinect.poll_frames():
                ...

    A ``KinectSensor`` is thread-safe: captures are serialised, and
    :meth:`close` may be called from any thread -- it interrupts waits that are
    in progress (they raise :class:`KinectClosedError`, and the ``poll_*``
    generators simply finish).

    Parameters
    ----------
    streams:
        Bitmask of :class:`StreamType` values to enable.
    auto_open:
        Open the sensor immediately (default). Set ``False`` to defer to
        :meth:`open` / the context manager.
    reuse_buffers:
        When ``True`` the NumPy arrays backing colour / depth / infrared /
        body-index frames are allocated once and reused on every
        :meth:`wait_for_frames` call. This removes per-frame allocation churn in
        real-time loops, but the arrays returned by one call are overwritten by
        the next -- copy anything you need to keep.
    audio_buffer_seconds:
        How much audio the background capture thread may queue between reads
        before it starts discarding the oldest sub-frames.
    """

    __slots__ = (
        "_audio_controller",
        "_audio_pump",
        "_audio_subframes",
        "_buffers",
        "_closing",
        "_event_handle",
        "_is_open",
        "_lock",
        "_mapper",
        "_reader",
        "_reuse_buffers",
        "_sensor_ptr",
        "_streams",
        "_wake_event",
    )

    def __init__(
        self,
        streams: StreamType = StreamType.COLOR | StreamType.DEPTH | StreamType.BODY,
        *,
        auto_open: bool = True,
        reuse_buffers: bool = False,
        audio_buffer_seconds: float = 10.0,
    ) -> None:
        if audio_buffer_seconds <= 0:
            raise ValueError("audio_buffer_seconds must be positive.")

        self._streams = StreamType(streams)
        self._reuse_buffers = reuse_buffers
        self._audio_subframes = math.ceil(audio_buffer_seconds * 1000.0 / _AUDIO_SUBFRAME_MS)
        self._lock = threading.RLock()
        self._closing = False
        self._is_open = False

        self._sensor_ptr: IKinectSensorNative | None = None
        self._reader: IMultiSourceFrameReader | None = None
        self._event_handle: int = 0
        self._wake_event: int = 0
        self._mapper: CoordinateMapper | None = None
        self._buffers: dict[str, npt.NDArray[np.generic]] = {}
        self._audio_pump: AudioPump | None = None
        self._audio_controller: AudioController | None = None

        if auto_open:
            self.open()

    def __repr__(self) -> str:
        state = "open" if self._is_open else "closed"
        return f"<KinectSensor {self._streams!r} {state}>"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def streams(self) -> StreamType:
        """The stream bitmask this sensor was configured with."""
        return self._streams

    @property
    def mapper(self) -> CoordinateMapper:
        """The vectorised :class:`CoordinateMapper` for this sensor."""
        mapper = self._mapper
        if mapper is None:
            raise KinectClosedError("Sensor is not open; CoordinateMapper is unavailable.")
        return mapper

    @property
    def audio(self) -> AudioController:
        """The microphone-array beam controller (requires ``StreamType.AUDIO``)."""
        if not self._streams & StreamType.AUDIO:
            raise StreamNotEnabledError("StreamType.AUDIO was not enabled for this sensor.")
        controller = self._audio_controller
        if controller is None:
            if not self._is_open:
                raise KinectClosedError("Sensor is not open; the audio controller is unavailable.")
            raise StreamNotEnabledError("The sensor reported no audio beam to control.")
        return controller

    @property
    def audio_subframes_lost(self) -> int:
        """Audio sub-frames (16 ms each) lost since the sensor was opened.

        Counts sub-frames the capture thread could not fetch in time (other
        threads hogging the GIL) plus those discarded because the audio buffer
        overflowed (nobody read audio for ``audio_buffer_seconds``). ``0`` means
        the audio delivered so far is gap-free.
        """
        pump = self._audio_pump
        return 0 if pump is None else pump.missed_subframes + pump.dropped_subframes

    @property
    def is_available(self) -> bool:
        """Whether the sensor hardware is connected and ready."""
        sensor = self._sensor_ptr
        if sensor is None:
            return False
        try:
            return sensor.is_available()
        except COMOperationError:
            return False

    @property
    def is_open(self) -> bool:
        """Whether :meth:`open` has completed and :meth:`close` has not run."""
        return self._is_open

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def open(self) -> None:
        """Open the sensor and its video / audio readers (idempotent)."""
        with self._lock:
            if self._is_open:
                return

            # Borrowed reference to the process-wide sensor (never released here).
            sensor = _acquire_shared_sensor()
            self._sensor_ptr = sensor
            try:
                self._mapper = CoordinateMapper(sensor.get_coordinate_mapper())
                self._wake_event = create_event()

                video_flags = int(self._streams & ~StreamType.AUDIO)
                if video_flags:
                    self._reader = sensor.open_multi_source_frame_reader(video_flags)
                    self._event_handle = self._reader.subscribe_frame_arrived()

                if self._streams & StreamType.AUDIO:
                    with sensor.get_audio_source() as source:
                        with source.get_audio_beams() as beams:
                            if beams.get_beam_count() > 0:
                                self._audio_controller = AudioController(beams.open_audio_beam(0))
                        self._audio_pump = AudioPump(
                            source.open_reader(),
                            source.get_sub_frame_length_in_bytes(),
                            self._audio_subframes,
                        )
            except BaseException:
                self._teardown()
                raise

            self._closing = False
            self._is_open = True

    def close(self) -> None:
        """Release every Win32 handle and COM resource held by the sensor.

        Idempotent and safe to call from any thread. Waits that are in progress
        on other threads are interrupted and raise :class:`KinectClosedError`.
        """
        if not self._is_open:
            return

        # Wake blocked waiters first so they let go of the capture lock.
        self._closing = True
        self._interrupt()
        with self._lock:
            if self._is_open:
                self._teardown()
                self._is_open = False
            self._closing = False

    def _teardown(self) -> None:
        """Release everything acquired by :meth:`open`; tolerant of partial state."""
        pump, self._audio_pump = self._audio_pump, None
        if pump is not None:
            pump.stop()
        self._audio_controller = None

        reader, self._reader = self._reader, None
        handle, self._event_handle = self._event_handle, 0
        if reader is not None:
            if handle:
                _safe(reader.unsubscribe_frame_arrived, handle)
            reader.release()

        wake, self._wake_event = self._wake_event, 0
        close_handle(wake)
        self._mapper = None
        self._buffers.clear()

        if self._sensor_ptr is not None:
            # Borrowed reference: drop our share; the hardware is only closed
            # once the last live KinectSensor releases it.
            self._sensor_ptr = None
            _release_shared_sensor()

    def _interrupt(self) -> None:
        """Wake every blocked wait so it re-checks the close / cancel flags."""
        set_event(self._wake_event)
        pump = self._audio_pump
        if pump is not None:
            pump.interrupt()

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - finaliser
        with contextlib.suppress(Exception):
            self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _check(self, cancel: CancelToken | None) -> None:
        if self._closing or not self._is_open:
            raise KinectClosedError("Sensor is not open.")
        if cancel is not None and cancel.cancelled:
            raise WaitCancelledError("The wait was cancelled.")

    def _buffer(self, name: str, shape: tuple[int, ...], dtype: npt.DTypeLike) -> npt.NDArray[Any]:
        """Return a scratch array, reused between calls when ``reuse_buffers`` is set."""
        if not self._reuse_buffers:
            return np.empty(shape, dtype=dtype)
        buf = self._buffers.get(name)
        if buf is None or buf.shape != shape or buf.dtype != np.dtype(dtype):
            buf = np.empty(shape, dtype=dtype)
            self._buffers[name] = buf
        return buf

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def wait_for_audio_frame(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> AudioFrame:
        """Block until audio is available and return everything captured so far.

        Audio is captured continuously in the background (16 ms sub-frames), so
        consecutive calls return gap-free audio regardless of how often you call.

        Raises
        ------
        StreamNotEnabledError
            If ``StreamType.AUDIO`` was not enabled.
        KinectTimeoutError
            If no audio arrives within ``timeout_ms``.
        KinectClosedError
            If the sensor is closed (possibly while waiting).
        """
        return self._wait_for_audio_frame(timeout_ms, None)

    def _wait_for_audio_frame(self, timeout_ms: int, cancel: CancelToken | None) -> AudioFrame:
        if not self._streams & StreamType.AUDIO:
            raise StreamNotEnabledError("StreamType.AUDIO was not enabled for this sensor.")
        self._check(cancel)
        pump = self._audio_pump
        if pump is None:
            raise KinectClosedError("Sensor is not open.")
        deadline = time.monotonic() + timeout_ms / 1000.0
        return AudioFrame(subframes=pump.wait(deadline, timeout_ms, cancel))

    def wait_for_frames(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> FrameSet:
        """Wait for and return one hardware-synchronised :class:`FrameSet`.

        The video frames in a ``FrameSet`` belong to the same sensor tick.
        ``FrameSet.audio`` carries all audio captured since the previous call.

        Parameters
        ----------
        timeout_ms:
            Maximum time to wait for the next frame. ``0`` polls without blocking.

        Raises
        ------
        KinectTimeoutError
            If no frame arrives within ``timeout_ms``.
        KinectClosedError
            If the sensor is closed (possibly while waiting).
        KinectError
            If no stream is enabled or the Win32 wait fails.
        """
        return self._wait_for_frames(timeout_ms, None)

    def _wait_for_frames(self, timeout_ms: int, cancel: CancelToken | None) -> FrameSet:
        self._check(cancel)
        if not self._streams & ~StreamType.AUDIO:
            if self._streams & StreamType.AUDIO:
                return FrameSet(audio=self._wait_for_audio_frame(timeout_ms, cancel))
            raise KinectError("No data stream is enabled.")

        deadline = time.monotonic() + timeout_ms / 1000.0
        if not self._lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            raise KinectTimeoutError(f"Timed out waiting for a frame ({timeout_ms} ms).")
        try:
            with self._next_multi_frame(deadline, timeout_ms, cancel) as multi_frame:
                frameset = self._read_frameset(multi_frame)
            pump = self._audio_pump
        finally:
            self._lock.release()

        if pump is not None:
            subframes = pump.drain()
            if subframes:
                frameset.audio = AudioFrame(subframes=subframes)
        return frameset

    def _next_multi_frame(
        self, deadline: float, timeout_ms: int, cancel: CancelToken | None
    ) -> IMultiSourceFrame:
        """Block on the frame-arrived event until a multi-source frame can be acquired."""
        while True:
            self._check(cancel)
            reader = self._reader
            if reader is None:
                raise KinectClosedError("Sensor is not open.")
            handle = self._event_handle

            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000.0))
            result = wait_for_multiple_objects((handle, self._wake_event), timeout_ms=remaining_ms)
            if result == _WAIT_WOKEN:
                continue  # close() or a cancellation: re-check the flags
            if result == WAIT_TIMEOUT:
                raise KinectTimeoutError(f"Timed out waiting for a frame ({timeout_ms} ms).")
            if result != WAIT_OBJECT_0:
                raise KinectError(f"Win32 wait on the frame event failed (code {result}).")

            # Fetching the event data is what re-arms the handle; without it the
            # next wait would return immediately instead of blocking.
            reader.clear_frame_arrived(handle)
            multi_frame = reader.acquire_latest_frame()
            if multi_frame is not None:
                return multi_frame

            # The event can fire before the frame is retrievable (E_PENDING),
            # which is common when many streams are enabled. Keep waiting.
            if time.monotonic() >= deadline:
                raise KinectTimeoutError(f"Timed out waiting for a frame ({timeout_ms} ms).")
            time.sleep(0.001)

    def _read_frameset(self, multi_frame: IMultiSourceFrame) -> FrameSet:
        """Copy every enabled stream out of ``multi_frame`` into a :class:`FrameSet`."""
        streams = self._streams
        frameset = FrameSet()

        if streams & StreamType.COLOR:
            frameset.color = self._read_color(multi_frame)

        if streams & StreamType.DEPTH:
            frameset.depth = self._read_depth(multi_frame)

        if streams & StreamType.INFRARED:
            planar = self._read_planar(multi_frame.get_infrared_frame_reference(), "infrared", np.uint16)
            if planar is not None:
                frameset.infrared = InfraredFrame(data=planar[0], relative_time_ns=planar[1])

        if streams & StreamType.LONG_EXPOSURE_INFRARED:
            planar = self._read_planar(
                multi_frame.get_long_exposure_infrared_frame_reference(), "le_infrared", np.uint16
            )
            if planar is not None:
                frameset.long_exposure_infrared = LongExposureInfraredFrame(
                    data=planar[0], relative_time_ns=planar[1]
                )

        if streams & StreamType.BODY_INDEX:
            planar = self._read_planar(multi_frame.get_body_index_frame_reference(), "body_index", np.uint8)
            if planar is not None:
                frameset.body_index = BodyIndexFrame(data=planar[0], relative_time_ns=planar[1])

        body_time_ns = 0
        if streams & StreamType.BODY:
            with multi_frame.get_body_frame_reference() as b_ref:
                b_frame = b_ref.acquire_frame()
                if b_frame is not None:
                    with b_frame:
                        floor = b_frame.get_floor_clip_plane()
                        frameset.floor_clip_plane = Vector4(floor.x, floor.y, floor.z, floor.w)
                        frameset.bodies = self._parse_bodies(b_frame)
                        body_time_ns = b_frame.get_relative_time() * _NS_PER_TICK

        # All frames of one tick share (to within the exposure offset) the same
        # timestamp; report the depth clock when available.
        for stamp in (
            frameset.depth.relative_time_ns if frameset.depth else 0,
            frameset.infrared.relative_time_ns if frameset.infrared else 0,
            frameset.body_index.relative_time_ns if frameset.body_index else 0,
            body_time_ns,
            frameset.long_exposure_infrared.relative_time_ns if frameset.long_exposure_infrared else 0,
            frameset.color.relative_time_ns if frameset.color else 0,
        ):
            if stamp:
                frameset.relative_time_ns = stamp
                break
        return frameset

    def _read_color(self, multi_frame: IMultiSourceFrame) -> ColorFrame | None:
        with multi_frame.get_color_frame_reference() as ref:
            frame = ref.acquire_frame()
            if frame is None:
                return None
            with frame:
                arr = self._buffer("color", _COLOR_SHAPE, np.uint8)
                frame.copy_converted_frame_data_to_array(
                    _COLOR_BYTES, arr.ctypes.data_as(ctypes.c_void_p), int(ColorImageFormat.BGRA)
                )
                settings: ColorCameraSettings | None = None
                try:
                    with frame.get_color_camera_settings() as cs:
                        settings = ColorCameraSettings(
                            exposure_time=cs.get_exposure_time(),
                            gain=cs.get_gain(),
                            gamma=cs.get_gamma(),
                        )
                except COMOperationError:  # camera settings are optional
                    pass
                return ColorFrame(
                    data=arr, settings=settings, relative_time_ns=frame.get_relative_time() * _NS_PER_TICK
                )

    def _read_depth(self, multi_frame: IMultiSourceFrame) -> DepthFrame | None:
        with multi_frame.get_depth_frame_reference() as ref:
            frame = ref.acquire_frame()
            if frame is None:
                return None
            with frame:
                arr = self._buffer("depth", _DEPTH_SHAPE, np.uint16)
                frame.copy_frame_data_to_array(_DEPTH_PIXELS, arr.ctypes.data_as(ctypes.c_void_p))
                return DepthFrame(
                    data=arr,
                    min_reliable_distance=frame.get_min_reliable_distance(),
                    max_reliable_distance=frame.get_max_reliable_distance(),
                    relative_time_ns=frame.get_relative_time() * _NS_PER_TICK,
                )

    def _read_planar(
        self, ref: _PlanarRef, name: str, dtype: npt.DTypeLike
    ) -> tuple[npt.NDArray[Any], int] | None:
        """Acquire a 512 x 424 single-plane frame; return ``(array, relative_time_ns)``."""
        try:
            frame = ref.acquire_frame()
            if frame is None:
                return None
            try:
                arr = self._buffer(name, _DEPTH_SHAPE, dtype)
                frame.copy_frame_data_to_array(_DEPTH_PIXELS, arr.ctypes.data_as(ctypes.c_void_p))
                return arr, frame.get_relative_time() * _NS_PER_TICK
            finally:
                frame.release()
        finally:
            ref.release()

    @staticmethod
    def _parse_bodies(body_frame: IBodyFrame) -> list[Body]:
        """Parse the 6-slot native body array into typed :class:`Body` objects."""
        natives = body_frame.get_bodies(MAX_BODY_COUNT)
        try:
            return [KinectSensor._parse_body(native) for native in natives]
        finally:
            for native in natives:
                native.release()

    @staticmethod
    def _parse_body(native_body: IBody) -> Body:
        is_tracked = native_body.get_is_tracked()

        joints: dict[JointType, Joint] = {}
        if is_tracked:
            joints_arr = native_body.get_joints(JOINT_COUNT)
            orient_arr = native_body.get_joint_orientations(JOINT_COUNT)
            for j_idx in range(JOINT_COUNT):
                jn = joints_arr[j_idx]
                on = orient_arr[j_idx]
                jt = JointType(jn.JointType)
                joints[jt] = Joint(
                    joint_type=jt,
                    position=Vector3(jn.Position.x, jn.Position.y, jn.Position.z),
                    tracking_state=TrackingState(jn.TrackingState),
                    orientation=Quaternion(
                        on.Orientation.x, on.Orientation.y, on.Orientation.z, on.Orientation.w
                    ),
                )
        else:
            for jt in JointType:
                joints[jt] = Joint(
                    jt, Vector3(0.0, 0.0, 0.0), TrackingState.NOT_TRACKED, Quaternion(0, 0, 0, 1)
                )

        lean_pt = native_body.get_lean()
        return Body(
            tracking_id=native_body.get_tracking_id(),
            is_tracked=is_tracked,
            is_restricted=native_body.get_is_restricted(),
            joints=JointCollection(joints),
            hand_left=Hand(
                state=HandState(native_body.get_hand_left_state()),
                confidence=TrackingConfidence(native_body.get_hand_left_confidence()),
            ),
            hand_right=Hand(
                state=HandState(native_body.get_hand_right_state()),
                confidence=TrackingConfidence(native_body.get_hand_right_confidence()),
            ),
            lean=Point2D(lean_pt.x, lean_pt.y),
            lean_tracking_state=TrackingState(native_body.get_lean_tracking_state()),
            clipped_edges=FrameEdges(native_body.get_clipped_edges()),
        )

    # ------------------------------------------------------------------
    # Generators
    # ------------------------------------------------------------------
    def poll_frames(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Generator[FrameSet, None, None]:
        """Yield synchronised :class:`FrameSet` objects until the sensor closes."""
        while self._is_open:
            try:
                yield self.wait_for_frames(timeout_ms)
            except KinectTimeoutError:
                continue
            except KinectClosedError:
                return

    def poll_audio(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Generator[AudioFrame, None, None]:
        """Yield gap-free :class:`AudioFrame` objects until the sensor closes."""
        while self._is_open:
            try:
                yield self.wait_for_audio_frame(timeout_ms)
            except KinectTimeoutError:
                continue
            except KinectClosedError:
                return
