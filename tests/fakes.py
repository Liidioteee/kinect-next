"""Duck-typed stand-ins for the native Kinect objects.

They mirror the Python-facing surface of ``kinect_next.native.interfaces`` closely
enough to drive :class:`KinectSensor` end to end without hardware. The readers use
*real* Win32 events with the SDK's semantics (the handle stays signalled until the
event data is fetched), so the sensor's wait logic is exercised for real.
"""

from __future__ import annotations

import ctypes
import threading
from collections import deque
from collections.abc import Sequence
from typing import Any

import numpy as np

from kinect_next.core.exceptions import COMOperationError
from kinect_next.native.types import (
    CameraIntrinsicsNative,
    CameraSpacePoint,
    ColorSpacePoint,
    DepthSpacePoint,
    JointNative,
    JointOrientationNative,
    PointF,
    Vector4Native,
)
from kinect_next.native.win32 import close_handle, create_event, reset_event, set_event

E_PENDING = -2147483638


class FakeCOM:
    """Base for fakes: tracks ``release()`` and works as a context manager."""

    def __init__(self) -> None:
        self.release_count = 0

    @property
    def released(self) -> bool:
        return self.release_count > 0

    def release(self) -> int:
        self.release_count += 1
        return 0

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _copy_out(data: np.ndarray, capacity: int, buffer_ptr: Any) -> None:
    src = np.ascontiguousarray(data)
    ctypes.memmove(buffer_ptr, src.ctypes.data, min(capacity * src.itemsize, src.nbytes))


# ---------------------------------------------------------------------------
# Video frames
# ---------------------------------------------------------------------------
class FakeColorSettings(FakeCOM):
    def __init__(self, exposure: int = 333_333, gain: float = 2.0, gamma: float = 2.2) -> None:
        super().__init__()
        self.exposure, self.gain, self.gamma = exposure, gain, gamma

    def get_exposure_time(self) -> int:
        return self.exposure

    def get_gain(self) -> float:
        return self.gain

    def get_gamma(self) -> float:
        return self.gamma


class FakeColorFrame(FakeCOM):
    def __init__(self, data: np.ndarray, ticks: int = 0, settings: FakeColorSettings | None = None) -> None:
        super().__init__()
        self.data, self.ticks, self.settings = data, ticks, settings
        self.requested_format: int | None = None

    def copy_converted_frame_data_to_array(self, capacity: int, buffer_ptr: Any, color_format: int) -> None:
        self.requested_format = color_format
        ctypes.memmove(buffer_ptr, np.ascontiguousarray(self.data).ctypes.data, capacity)

    def get_color_camera_settings(self) -> FakeColorSettings:
        if self.settings is None:
            raise COMOperationError("no camera settings", E_PENDING)
        return self.settings

    def get_relative_time(self) -> int:
        return self.ticks


class FakePlanarFrame(FakeCOM):
    """Depth / infrared / body-index frame."""

    def __init__(self, data: np.ndarray, ticks: int = 0, reliable: tuple[int, int] = (500, 4500)) -> None:
        super().__init__()
        self.data, self.ticks, self.reliable = data, ticks, reliable

    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        _copy_out(self.data, capacity, buffer_ptr)

    def get_relative_time(self) -> int:
        return self.ticks

    def get_min_reliable_distance(self) -> int:
        return self.reliable[0]

    def get_max_reliable_distance(self) -> int:
        return self.reliable[1]


class FakeBody(FakeCOM):
    def __init__(
        self,
        tracked: bool = True,
        tracking_id: int = 1,
        head: tuple[float, float, float] = (0.0, 0.5, 2.0),
        hands: tuple[int, int] = (2, 3),
        clipped: int = 0,
    ) -> None:
        super().__init__()
        self.tracked, self.tracking_id, self.head = tracked, tracking_id, head
        self.hands, self.clipped = hands, clipped

    def get_is_tracked(self) -> bool:
        return self.tracked

    def get_joints(self, count: int) -> Any:
        joints = (JointNative * count)()
        for i in range(count):
            joints[i].JointType = i
            joints[i].Position = CameraSpacePoint(0.01 * i, 0.02 * i, 2.0)
            joints[i].TrackingState = 2
        joints[3].Position = CameraSpacePoint(*self.head)  # JointType.HEAD
        return joints

    def get_joint_orientations(self, count: int) -> Any:
        orientations = (JointOrientationNative * count)()
        for i in range(count):
            orientations[i].JointType = i
            orientations[i].Orientation = Vector4Native(0.0, 0.0, 0.0, 1.0)
        return orientations

    def get_lean(self) -> PointF:
        return PointF(0.25, -0.5)

    def get_lean_tracking_state(self) -> int:
        return 2 if self.tracked else 0

    def get_tracking_id(self) -> int:
        return self.tracking_id if self.tracked else 0

    def get_is_restricted(self) -> bool:
        return False

    def get_hand_left_state(self) -> int:
        return self.hands[0]

    def get_hand_left_confidence(self) -> int:
        return 1

    def get_hand_right_state(self) -> int:
        return self.hands[1]

    def get_hand_right_confidence(self) -> int:
        return 0

    def get_clipped_edges(self) -> int:
        return self.clipped


class FakeBodyFrame(FakeCOM):
    def __init__(self, bodies: Sequence[FakeBody], ticks: int = 0) -> None:
        super().__init__()
        self.bodies, self.ticks = list(bodies), ticks

    def get_bodies(self, count: int) -> list[FakeBody]:
        return self.bodies[:count]

    def get_floor_clip_plane(self) -> Vector4Native:
        return Vector4Native(0.0, 1.0, 0.0, 0.75)

    def get_relative_time(self) -> int:
        return self.ticks


class FakeReference(FakeCOM):
    def __init__(self, frame: FakeCOM | None) -> None:
        super().__init__()
        self.frame = frame

    def acquire_frame(self) -> Any:
        return self.frame


class FakeMultiFrame(FakeCOM):
    def __init__(
        self,
        *,
        color: FakeColorFrame | None = None,
        depth: FakePlanarFrame | None = None,
        infrared: FakePlanarFrame | None = None,
        long_exposure_infrared: FakePlanarFrame | None = None,
        body_index: FakePlanarFrame | None = None,
        body: FakeBodyFrame | None = None,
    ) -> None:
        super().__init__()
        self._frames = {
            "color": color,
            "depth": depth,
            "infrared": infrared,
            "long_exposure_infrared": long_exposure_infrared,
            "body_index": body_index,
            "body": body,
        }
        self.references: list[FakeReference] = []

    def _reference(self, name: str) -> FakeReference:
        ref = FakeReference(self._frames[name])
        self.references.append(ref)
        return ref

    def get_color_frame_reference(self) -> FakeReference:
        return self._reference("color")

    def get_depth_frame_reference(self) -> FakeReference:
        return self._reference("depth")

    def get_infrared_frame_reference(self) -> FakeReference:
        return self._reference("infrared")

    def get_long_exposure_infrared_frame_reference(self) -> FakeReference:
        return self._reference("long_exposure_infrared")

    def get_body_index_frame_reference(self) -> FakeReference:
        return self._reference("body_index")

    def get_body_frame_reference(self) -> FakeReference:
        return self._reference("body")

    def everything(self) -> list[FakeCOM]:
        """This frame plus every reference and sub-frame handed out from it."""
        frames = [f for f in self._frames.values() if f is not None]
        nested = [b for f in frames if isinstance(f, FakeBodyFrame) for b in f.bodies]
        return [self, *self.references, *frames, *nested]


class _FakeEventReader(FakeCOM):
    """Shared event plumbing: a manual-reset Win32 event with SDK semantics."""

    def __init__(self) -> None:
        super().__init__()
        self.event = 0
        self.unsubscribed = False
        self.cleared = 0
        self.subscribe_error: Exception | None = None
        self._pending: deque[Any] = deque()
        self._guard = threading.Lock()

    def subscribe_frame_arrived(self) -> int:
        if self.subscribe_error is not None:
            raise self.subscribe_error
        self.event = create_event(manual_reset=True)
        return self.event

    def unsubscribe_frame_arrived(self, handle: int) -> None:
        assert handle == self.event
        self.unsubscribed = True
        close_handle(handle)
        self.event = 0

    def clear_frame_arrived(self, handle: int) -> None:
        with self._guard:
            self.cleared += 1
            if self.event:
                reset_event(handle)

    def signal(self) -> None:
        """Fire the frame-arrived event without making a frame available (E_PENDING)."""
        with self._guard:
            if self.event:
                set_event(self.event)

    def _push(self, item: Any) -> None:
        with self._guard:
            self._pending.append(item)
            if self.event:
                set_event(self.event)

    def _pop_latest(self) -> Any:
        """Like the SDK: only the newest item is ever retrievable."""
        with self._guard:
            if not self._pending:
                return None
            item = self._pending.pop()
            self._pending.clear()
            return item


class FakeMultiSourceReader(_FakeEventReader):
    def __init__(self, flags: int) -> None:
        super().__init__()
        self.flags = flags

    def push(self, frame: FakeMultiFrame) -> FakeMultiFrame:
        self._push(frame)
        return frame

    def acquire_latest_frame(self) -> FakeMultiFrame | None:
        frame: FakeMultiFrame | None = self._pop_latest()
        return frame


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
class FakeCorrelation(FakeCOM):
    def __init__(self, tracking_id: int) -> None:
        super().__init__()
        self.tracking_id = tracking_id

    def get_body_tracking_id(self) -> int:
        return self.tracking_id


class FakeSubFrame(FakeCOM):
    def __init__(
        self,
        ticks: int,
        *,
        value: float = 0.1,
        angle: float = 0.2,
        confidence: float = 0.9,
        mode: int = 0,
        correlated: Sequence[int] = (),
        samples: int = 256,
    ) -> None:
        super().__init__()
        self.ticks, self.angle, self.confidence, self.mode = ticks, angle, confidence, mode
        self.pcm = np.full(samples, value, dtype=np.float32)
        self.correlations = [FakeCorrelation(i) for i in correlated]

    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        ctypes.memmove(buffer_ptr, self.pcm.ctypes.data, min(capacity, self.pcm.nbytes))

    def get_audio_body_correlation_count(self) -> int:
        return len(self.correlations)

    def get_audio_body_correlation(self, index: int) -> FakeCorrelation | None:
        return self.correlations[index] if index < len(self.correlations) else None

    def get_beam_angle(self) -> float:
        return self.angle

    def get_beam_angle_confidence(self) -> float:
        return self.confidence

    def get_audio_beam_mode(self) -> int:
        return self.mode

    def get_duration(self) -> int:
        return 160_000  # 16 ms in 100 ns ticks

    def get_relative_time(self) -> int:
        return self.ticks


class FakeBeamFrame(FakeCOM):
    def __init__(self, subframes: Sequence[FakeSubFrame | None]) -> None:
        super().__init__()
        self.subframes = list(subframes)

    def get_sub_frame_count(self) -> int:
        return len(self.subframes)

    def get_sub_frame(self, index: int) -> FakeSubFrame | None:
        return self.subframes[index]


class FakeBeamFrameList(FakeCOM):
    def __init__(self, frames: Sequence[FakeBeamFrame | None]) -> None:
        super().__init__()
        self.frames = list(frames)
        self.count_error: Exception | None = None

    def get_count(self) -> int:
        if self.count_error is not None:
            raise self.count_error
        return len(self.frames)

    def open_audio_beam_frame(self, index: int) -> FakeBeamFrame | None:
        return self.frames[index]


class FakeAudioReader(_FakeEventReader):
    def push(self, *subframes: FakeSubFrame) -> FakeBeamFrameList:
        frame_list = FakeBeamFrameList([FakeBeamFrame(subframes)])
        self._push(frame_list)
        return frame_list

    def push_list(self, frame_list: FakeBeamFrameList) -> None:
        self._push(frame_list)

    def acquire_latest_beam_frames(self) -> FakeBeamFrameList | None:
        frame_list: FakeBeamFrameList | None = self._pop_latest()
        return frame_list


class FakeBeam(FakeCOM):
    """An audio beam; ``honours_manual=False`` mimics runtimes that ignore MANUAL."""

    def __init__(self, honours_manual: bool = True) -> None:
        super().__init__()
        self.honours_manual = honours_manual
        self.mode = 0
        self.angle = 0.0
        self.confidence = 0.5
        self.mode_requests: list[int] = []

    def get_audio_beam_mode(self) -> int:
        return self.mode

    def put_audio_beam_mode(self, mode: int) -> None:
        self.mode_requests.append(mode)
        if mode == 0 or self.honours_manual:
            self.mode = mode

    def get_beam_angle(self) -> float:
        return self.angle

    def put_beam_angle(self, angle_radians: float) -> None:
        self.angle = angle_radians

    def get_beam_angle_confidence(self) -> float:
        return self.confidence


class FakeBeamList(FakeCOM):
    def __init__(self, beams: Sequence[FakeBeam]) -> None:
        super().__init__()
        self.beams = list(beams)

    def get_beam_count(self) -> int:
        return len(self.beams)

    def open_audio_beam(self, index: int) -> FakeBeam:
        return self.beams[index]


class FakeAudioSource(FakeCOM):
    def __init__(self, reader: FakeAudioReader, beams: Sequence[FakeBeam]) -> None:
        super().__init__()
        self.reader, self.beam_list = reader, FakeBeamList(beams)

    def get_audio_beams(self) -> FakeBeamList:
        return self.beam_list

    def open_reader(self) -> FakeAudioReader:
        return self.reader

    def get_sub_frame_length_in_bytes(self) -> int:
        return 1024


# ---------------------------------------------------------------------------
# Coordinate mapper
# ---------------------------------------------------------------------------
def _as_array(pointer: Any, ctype: Any, count: int) -> np.ndarray:
    address = pointer.value if hasattr(pointer, "value") else int(pointer)
    return np.ctypeslib.as_array((ctype * count).from_address(address))


class FakeMapper(FakeCOM):
    """A deterministic pin-hole-free mapper: easy to predict, easy to assert on.

    * depth pixel ``(col, row)`` with depth ``d`` mm -> camera ``(col/100, row/100, d/1000)``
    * depth pixel ``(col, row)`` -> colour pixel ``(col * 3, row * 2)``
    * a depth of ``0`` is "invalid" and maps to ``-inf`` everywhere
    """

    WIDTH, HEIGHT = 512, 424

    def map_camera_point_to_depth_space(self, point: CameraSpacePoint) -> DepthSpacePoint:
        if point.z <= 0:
            return DepthSpacePoint(float("-inf"), float("-inf"))
        return DepthSpacePoint(point.x * 100.0, point.y * 100.0)

    def map_camera_point_to_color_space(self, point: CameraSpacePoint) -> ColorSpacePoint:
        if point.z <= 0:
            return ColorSpacePoint(float("-inf"), float("-inf"))
        return ColorSpacePoint(point.x * 300.0, point.y * 200.0)

    def map_depth_point_to_camera_space(self, point: DepthSpacePoint, depth: int) -> CameraSpacePoint:
        return CameraSpacePoint(point.x / 100.0, point.y / 100.0, depth / 1000.0)

    def map_depth_point_to_color_space(self, point: DepthSpacePoint, depth: int) -> ColorSpacePoint:
        return ColorSpacePoint(point.x * 3.0, point.y * 2.0)

    def _grid(self, depth_ptr: Any, count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        assert count == self.WIDTH * self.HEIGHT
        depth = _as_array(depth_ptr, ctypes.c_uint16, count).astype(np.float32)
        index = np.arange(count)
        return depth, (index % self.WIDTH).astype(np.float32), (index // self.WIDTH).astype(np.float32)

    def map_depth_frame_to_camera_space(self, count: int, depth_ptr: Any, out_ptr: Any) -> None:
        depth, cols, rows = self._grid(depth_ptr, count)
        out = _as_array(out_ptr, ctypes.c_float, count * 3).reshape(count, 3)
        out[:, 0], out[:, 1], out[:, 2] = cols / 100.0, rows / 100.0, depth / 1000.0
        out[depth == 0] = -np.inf

    def map_depth_frame_to_color_space(self, count: int, depth_ptr: Any, out_ptr: Any) -> None:
        depth, cols, rows = self._grid(depth_ptr, count)
        out = _as_array(out_ptr, ctypes.c_float, count * 2).reshape(count, 2)
        out[:, 0], out[:, 1] = cols * 3.0, rows * 2.0
        out[depth == 0] = -np.inf

    def map_color_frame_to_depth_space(
        self, count: int, depth_ptr: Any, color_count: int, out_ptr: Any
    ) -> None:
        depth, _cols, _rows = self._grid(depth_ptr, count)
        out = _as_array(out_ptr, ctypes.c_float, color_count * 2).reshape(color_count, 2)
        out[:] = float(depth[0])  # lets tests see which depth buffer was read

    def get_depth_camera_intrinsics(self) -> CameraIntrinsicsNative:
        return CameraIntrinsicsNative(366.0, 366.5, 255.5, 206.0, 0.09, -0.27, 0.1)


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------
class FakeSensorNative(FakeCOM):
    """Stand-in for ``IKinectSensorNative``; hands out the fakes above."""

    def __init__(self, beams: Sequence[FakeBeam] | None = None) -> None:
        super().__init__()
        self.opens = 0
        self.closes = 0
        self.available = True
        self.mapper = FakeMapper()
        self.beams = [FakeBeam()] if beams is None else list(beams)
        self.video_readers: list[FakeMultiSourceReader] = []
        self.audio_readers: list[FakeAudioReader] = []
        self.audio_sources: list[FakeAudioSource] = []
        self.next_subscribe_error: Exception | None = None

    def open(self) -> None:
        self.opens += 1

    def close(self) -> None:
        self.closes += 1

    def is_available(self) -> bool:
        return self.available

    def get_coordinate_mapper(self) -> FakeMapper:
        return self.mapper

    def open_multi_source_frame_reader(self, flags: int) -> FakeMultiSourceReader:
        reader = FakeMultiSourceReader(flags)
        reader.subscribe_error, self.next_subscribe_error = self.next_subscribe_error, None
        self.video_readers.append(reader)
        return reader

    def get_audio_source(self) -> FakeAudioSource:
        reader = FakeAudioReader()
        self.audio_readers.append(reader)
        source = FakeAudioSource(reader, self.beams)
        self.audio_sources.append(source)
        return source

    # Convenience accessors for the most recently opened readers.
    @property
    def video(self) -> FakeMultiSourceReader:
        return self.video_readers[-1]

    @property
    def audio(self) -> FakeAudioReader:
        return self.audio_readers[-1]
