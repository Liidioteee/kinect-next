"""The :class:`KinectSensor` facade: frame capture, hardware sync, video and audio."""

from __future__ import annotations

import contextlib
import ctypes
import logging
import threading
import time
from collections.abc import Generator
from typing import Any, Final, Protocol

import numpy as np
import numpy.typing as npt

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
    KinectError,
    KinectTimeoutError,
    StreamNotEnabledError,
)
from kinect_next.core.mapper import CoordinateMapper
from kinect_next.models.audio import AudioBeamSubFrame, AudioFrame
from kinect_next.models.body import Body, Hand, Joint, JointCollection
from kinect_next.models.body_index import BodyIndexFrame
from kinect_next.models.color import ColorCameraSettings, ColorFrame
from kinect_next.models.depth import DepthFrame
from kinect_next.models.frameset import FrameSet
from kinect_next.models.geometry import Point2D, Quaternion, Vector3, Vector4
from kinect_next.models.infrared import InfraredFrame, LongExposureInfraredFrame
from kinect_next.native.interfaces import (
    IAudioBeamFrameReader,
    IAudioBeamSubFrame,
    IAudioSource,
    IBody,
    IBodyFrame,
    IKinectSensorNative,
    IMultiSourceFrameReader,
)
from kinect_next.native.types import JointNative, JointOrientationNative
from kinect_next.native.win32 import (
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    get_default_kinect_sensor,
    wait_for_single_object,
)

_log = logging.getLogger("kinect_next")

MAX_BODY_COUNT: Final = 6

_COLOR_SHAPE: Final = (1080, 1920, 4)
_DEPTH_SHAPE: Final = (424, 512)
_COLOR_BYTES: Final = 1080 * 1920 * 4
_DEPTH_PIXELS: Final = 512 * 424

_AUDIO_SUBFRAME_SAMPLES: Final = 256
_AUDIO_SUBFRAME_BYTES: Final = _AUDIO_SUBFRAME_SAMPLES * 4  # float32
_TICKS_PER_MS: Final = 10_000.0
_NS_PER_TICK: Final = 100


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


class _PlanarRef(Protocol):
    """A frame reference yielding a :class:`_PlanarFrame`."""

    def acquire_frame(self) -> _PlanarFrame | None: ...


def _parse_subframe(native_subframe: IAudioBeamSubFrame) -> AudioBeamSubFrame:
    """Convert a native ``IAudioBeamSubFrame`` into a typed :class:`AudioBeamSubFrame`."""
    pcm_buffer = np.empty(_AUDIO_SUBFRAME_SAMPLES, dtype=np.float32)
    native_subframe.copy_frame_data_to_array(
        _AUDIO_SUBFRAME_BYTES, pcm_buffer.ctypes.data_as(ctypes.c_void_p)
    )

    corr_ids: list[int] = []
    for c_idx in range(native_subframe.get_audio_body_correlation_count()):
        corr = native_subframe.get_audio_body_correlation(c_idx)
        if corr:
            corr_ids.append(corr.get_body_tracking_id())

    return AudioBeamSubFrame(
        data=pcm_buffer,
        beam_angle=native_subframe.get_beam_angle(),
        beam_angle_confidence=native_subframe.get_beam_angle_confidence(),
        duration_ms=native_subframe.get_duration() / _TICKS_PER_MS,
        relative_time_ns=native_subframe.get_relative_time() * _NS_PER_TICK,
        correlated_body_ids=tuple(corr_ids),
    )


class KinectSensor:
    """High-level controller for a Microsoft Kinect v2.

    Supports use as a context manager and frame-synchronised streaming::

        with KinectSensor(StreamType.COLOR | StreamType.BODY) as kinect:
            for frames in kinect.poll_frames():
                ...

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
    """

    __slots__ = (
        "_audio_controller",
        "_audio_event_handle",
        "_audio_reader",
        "_audio_source",
        "_buffers",
        "_event_handle",
        "_is_open",
        "_mapper",
        "_reader",
        "_reuse_buffers",
        "_sensor_ptr",
        "_streams",
    )

    def __init__(
        self,
        streams: StreamType = StreamType.COLOR | StreamType.DEPTH | StreamType.BODY,
        auto_open: bool = True,
        *,
        reuse_buffers: bool = False,
    ) -> None:
        self._streams = streams
        self._reuse_buffers = reuse_buffers
        self._sensor_ptr: IKinectSensorNative | None = None
        self._reader: IMultiSourceFrameReader | None = None
        self._event_handle: int = 0
        self._mapper: CoordinateMapper | None = None
        self._is_open: bool = False
        self._buffers: dict[str, npt.NDArray[np.generic]] = {}

        self._audio_source: IAudioSource | None = None
        self._audio_reader: IAudioBeamFrameReader | None = None
        self._audio_event_handle: int = 0
        self._audio_controller: AudioController | None = None

        if auto_open:
            self.open()

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
        if self._mapper is None:
            raise KinectError("Sensor is not open; CoordinateMapper is unavailable.")
        return self._mapper

    @property
    def audio(self) -> AudioController:
        """The microphone-array beam controller (requires ``StreamType.AUDIO``)."""
        if self._audio_controller is None:
            raise StreamNotEnabledError("StreamType.AUDIO was not enabled for this sensor.")
        return self._audio_controller

    @property
    def is_available(self) -> bool:
        """Whether the sensor hardware is connected and ready."""
        return self._sensor_ptr.is_available() if self._sensor_ptr else False

    @property
    def is_open(self) -> bool:
        """Whether :meth:`open` has completed and :meth:`close` has not run."""
        return self._is_open

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def open(self) -> None:
        """Open the sensor and its video / audio readers (idempotent)."""
        if self._is_open:
            return

        # Borrowed reference to the process-wide sensor (do not release here).
        self._sensor_ptr = _acquire_shared_sensor()
        try:
            self._mapper = CoordinateMapper(self._sensor_ptr.get_coordinate_mapper())

            video_flags = int(self._streams & ~StreamType.AUDIO)
            if video_flags != 0:
                self._reader = self._sensor_ptr.open_multi_source_frame_reader(video_flags)
                self._event_handle = self._reader.subscribe_frame_arrived()

            if self._streams & StreamType.AUDIO:
                self._audio_source = self._sensor_ptr.get_audio_source()
                beams = self._audio_source.get_audio_beams()
                if beams.get_beam_count() > 0:
                    self._audio_controller = AudioController(beams.open_audio_beam(0))
                self._audio_reader = self._audio_source.open_reader()
                self._audio_event_handle = self._audio_reader.subscribe_frame_arrived()
        except BaseException:
            self._sensor_ptr = None
            _release_shared_sensor()
            raise

        self._is_open = True

    def close(self) -> None:
        """Release every Win32 handle and COM resource held by the sensor."""
        if not self._is_open:
            return

        if self._audio_reader is not None and self._audio_event_handle:
            self._safe(self._audio_reader.unsubscribe_frame_arrived, self._audio_event_handle)
        self._audio_event_handle = 0
        self._audio_reader = None
        self._audio_source = None
        self._audio_controller = None

        if self._reader is not None and self._event_handle:
            self._safe(self._reader.unsubscribe_frame_arrived, self._event_handle)
        self._event_handle = 0
        self._reader = None
        self._mapper = None
        self._buffers.clear()

        if self._sensor_ptr is not None:
            # Borrowed reference: drop our share; the hardware is only closed
            # once the last live KinectSensor releases it.
            self._sensor_ptr = None
            _release_shared_sensor()

        self._is_open = False

    def __enter__(self) -> KinectSensor:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - finaliser
        with contextlib.suppress(Exception):
            self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe(func: object, *args: object) -> None:
        """Call ``func(*args)`` swallowing COM errors during teardown."""
        try:
            func(*args)  # type: ignore[operator]
        except (COMOperationError, OSError) as exc:  # pragma: no cover - teardown best effort
            _log.debug("Ignored error during cleanup: %s", exc)

    def _buffer(self, name: str, shape: tuple[int, ...], dtype: npt.DTypeLike) -> npt.NDArray[Any]:
        """Return a scratch array, reused between calls when ``reuse_buffers`` is set."""
        if not self._reuse_buffers:
            return np.empty(shape, dtype=dtype)
        buf = self._buffers.get(name)
        if buf is None or buf.shape != shape or buf.dtype != np.dtype(dtype):
            buf = np.empty(shape, dtype=dtype)
            self._buffers[name] = buf
        return buf

    def _copy_planar(
        self, ref: _PlanarRef, name: str, dtype: npt.DTypeLike, acquired: list[Any]
    ) -> npt.NDArray[Any] | None:
        """Acquire a single-plane frame, copy it into a (reusable) buffer, return it."""
        acquired.append(ref)
        frame = ref.acquire_frame()
        if frame is None:
            return None
        acquired.append(frame)
        arr = self._buffer(name, _DEPTH_SHAPE, dtype)
        frame.copy_frame_data_to_array(_DEPTH_PIXELS, arr.ctypes.data_as(ctypes.c_void_p))
        return arr

    def _acquire_pending_audio(self) -> AudioFrame | None:
        """Non-blocking poll of any queued audio sub-frames."""
        if self._audio_reader is None:
            return None
        frame_list = self._audio_reader.acquire_latest_beam_frames()
        if not frame_list:
            return None

        subframes: list[AudioBeamSubFrame] = []
        try:
            for b_idx in range(frame_list.get_count()):
                a_frame = frame_list.open_audio_beam_frame(b_idx)
                if not a_frame:
                    continue
                try:
                    for sf_idx in range(a_frame.get_sub_frame_count()):
                        sf = a_frame.get_sub_frame(sf_idx)
                        if sf:
                            try:
                                subframes.append(_parse_subframe(sf))
                            finally:
                                sf.release()
                finally:
                    a_frame.release()
        finally:
            frame_list.release()

        return AudioFrame(subframes=subframes) if subframes else None

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def wait_for_audio_frame(self, timeout_ms: int = 1500) -> AudioFrame:
        """Block until an audio frame is available (~62.5 Hz, 16 ms sub-frames)."""
        if not self._is_open or self._audio_reader is None or not self._audio_event_handle:
            raise StreamNotEnabledError("Sensor is not open or StreamType.AUDIO is not enabled.")

        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            remaining_ms = int((deadline - time.monotonic()) * 1000.0)
            if remaining_ms <= 0:
                raise KinectTimeoutError(f"Timed out waiting for an audio frame ({timeout_ms} ms).")

            wait_res = wait_for_single_object(self._audio_event_handle, remaining_ms)
            if wait_res == WAIT_TIMEOUT:
                raise KinectTimeoutError(f"Timed out waiting for an audio frame ({timeout_ms} ms).")
            if wait_res != WAIT_OBJECT_0:
                raise KinectError(f"Win32 wait on the audio event failed (code {wait_res}).")

            audio_frame = self._acquire_pending_audio()
            if audio_frame is not None and not audio_frame.is_empty:
                return audio_frame

    def wait_for_frames(self, timeout_ms: int = 1500) -> FrameSet:
        """Wait for and return one hardware-synchronised :class:`FrameSet`.

        Parameters
        ----------
        timeout_ms:
            Maximum time to wait for the next frame.

        Raises
        ------
        KinectTimeoutError
            If no frame arrives within ``timeout_ms``.
        KinectError
            If no stream is enabled or the Win32 wait fails.
        """
        if not self._is_open:
            raise KinectError("Sensor is not open.")

        frameset = FrameSet()

        if self._reader is None:
            if self._streams & StreamType.AUDIO:
                frameset.audio = self.wait_for_audio_frame(timeout_ms)
                return frameset
            raise KinectError("No data stream is enabled.")

        # The frame-arrived event can fire before the multi-source frame is
        # actually retrievable (E_PENDING), which is common when many streams are
        # enabled. Keep waiting until we get one or the timeout budget runs out.
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            remaining_ms = int((deadline - time.monotonic()) * 1000.0)
            if remaining_ms <= 0:
                raise KinectTimeoutError(f"Timed out waiting for a frame ({timeout_ms} ms).")

            wait_res = wait_for_single_object(self._event_handle, remaining_ms)
            if wait_res == WAIT_TIMEOUT:
                raise KinectTimeoutError(f"Timed out waiting for a frame ({timeout_ms} ms).")
            if wait_res != WAIT_OBJECT_0:
                raise KinectError(f"Win32 wait on the frame event failed (code {wait_res}).")

            multi_frame = self._reader.acquire_latest_frame()
            if multi_frame:
                break
            time.sleep(0.001)  # avoid a hot spin if the event stays signalled

        acquired: list[Any] = [multi_frame]
        try:
            streams = self._streams

            if streams & StreamType.COLOR:
                c_ref = multi_frame.get_color_frame_reference()
                acquired.append(c_ref)
                c_frame = c_ref.acquire_frame()
                if c_frame is not None:
                    acquired.append(c_frame)
                    arr = self._buffer("color", _COLOR_SHAPE, np.uint8)
                    c_frame.copy_converted_frame_data_to_array(
                        _COLOR_BYTES,
                        arr.ctypes.data_as(ctypes.c_void_p),
                        int(ColorImageFormat.BGRA),
                    )
                    settings: ColorCameraSettings | None = None
                    try:
                        cs = c_frame.get_color_camera_settings()
                        settings = ColorCameraSettings(
                            exposure_time=cs.get_exposure_time(),
                            gain=cs.get_gain(),
                            gamma=cs.get_gamma(),
                        )
                    except COMOperationError:  # camera settings are optional
                        pass
                    frameset.color = ColorFrame(data=arr, settings=settings)

            if streams & StreamType.DEPTH:
                d_ref = multi_frame.get_depth_frame_reference()
                acquired.append(d_ref)
                d_frame = d_ref.acquire_frame()
                if d_frame is not None:
                    acquired.append(d_frame)
                    arr = self._buffer("depth", _DEPTH_SHAPE, np.uint16)
                    d_frame.copy_frame_data_to_array(_DEPTH_PIXELS, arr.ctypes.data_as(ctypes.c_void_p))
                    frameset.depth = DepthFrame(
                        data=arr,
                        min_reliable_distance=d_frame.get_min_reliable_distance(),
                        max_reliable_distance=d_frame.get_max_reliable_distance(),
                    )

            if streams & StreamType.INFRARED:
                planar = self._copy_planar(
                    multi_frame.get_infrared_frame_reference(), "infrared", np.uint16, acquired
                )
                if planar is not None:
                    frameset.infrared = InfraredFrame(data=planar)

            if streams & StreamType.LONG_EXPOSURE_INFRARED:
                planar = self._copy_planar(
                    multi_frame.get_long_exposure_infrared_frame_reference(),
                    "le_infrared",
                    np.uint16,
                    acquired,
                )
                if planar is not None:
                    frameset.long_exposure_infrared = LongExposureInfraredFrame(data=planar)

            if streams & StreamType.BODY_INDEX:
                planar = self._copy_planar(
                    multi_frame.get_body_index_frame_reference(), "body_index", np.uint8, acquired
                )
                if planar is not None:
                    frameset.body_index = BodyIndexFrame(data=planar)

            if streams & StreamType.BODY:
                b_ref = multi_frame.get_body_frame_reference()
                acquired.append(b_ref)
                b_frame = b_ref.acquire_frame()
                if b_frame is not None:
                    acquired.append(b_frame)
                    floor = b_frame.get_floor_clip_plane()
                    frameset.floor_clip_plane = Vector4(floor.x, floor.y, floor.z, floor.w)
                    frameset.bodies = self._parse_bodies(b_frame)

            if streams & StreamType.AUDIO:
                frameset.audio = self._acquire_pending_audio()
        finally:
            for obj in reversed(acquired):
                with contextlib.suppress(COMOperationError):
                    obj.release()

        return frameset

    @staticmethod
    def _parse_bodies(body_frame: IBodyFrame) -> list[Body]:
        """Parse the 6-slot native body array into typed :class:`Body` objects."""
        bodies_native = (ctypes.c_void_p * MAX_BODY_COUNT)()
        body_frame.get_and_refresh_body_data(MAX_BODY_COUNT, bodies_native)

        parsed: list[Body] = []
        for ptr in bodies_native:
            if not ptr:
                continue

            native_body = IBody(ptr, owned=True)
            is_tracked = native_body.get_is_tracked()

            joints: dict[JointType, Joint] = {}
            if is_tracked:
                joints_arr = (JointNative * JOINT_COUNT)()
                orient_arr = (JointOrientationNative * JOINT_COUNT)()
                native_body.get_joints(JOINT_COUNT, joints_arr)
                native_body.get_joint_orientations(JOINT_COUNT, orient_arr)
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
            parsed.append(
                Body(
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
            )
        return parsed

    # ------------------------------------------------------------------
    # Generators
    # ------------------------------------------------------------------
    def poll_frames(self, timeout_ms: int = 1500) -> Generator[FrameSet, None, None]:
        """Yield synchronised :class:`FrameSet` objects until the sensor closes."""
        while self._is_open:
            try:
                yield self.wait_for_frames(timeout_ms)
            except KinectTimeoutError:
                continue

    def poll_audio(self, timeout_ms: int = 1500) -> Generator[AudioFrame, None, None]:
        """Yield :class:`AudioFrame` objects at the microphone frame rate (~60 Hz)."""
        while self._is_open:
            try:
                yield self.wait_for_audio_frame(timeout_ms)
            except KinectTimeoutError:
                continue
