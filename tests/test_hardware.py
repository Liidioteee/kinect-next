"""Integration tests that talk to a real, connected Kinect v2.

Run with::

    pytest -m hardware --run-hardware

The sensor must be plugged in, powered and recognised by the SDK. No particular
scene content is required (nobody needs to be in frame). The Kinect delivers
sub-frames independently, so per-stream tests poll for a while before giving up.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator

import numpy as np
import pytest

from kinect_next import AsyncKinectSensor, KinectSensor, StreamType
from kinect_next.core.exceptions import KinectError, KinectNotAvailableError
from kinect_next.models.frameset import FrameSet

pytestmark = pytest.mark.hardware

_VIDEO_STREAMS = (
    StreamType.COLOR | StreamType.DEPTH | StreamType.INFRARED | StreamType.BODY | StreamType.BODY_INDEX
)
_ALL_STREAMS = _VIDEO_STREAMS | StreamType.AUDIO

_WARMUP_S = 15.0


def _grab(
    kinect: KinectSensor,
    predicate: Callable[[FrameSet], bool],
    *,
    what: str,
    budget_s: float = _WARMUP_S,
) -> FrameSet:
    """Poll ``wait_for_frames`` until ``predicate`` holds, or skip after ``budget_s``."""
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        try:
            fs = kinect.wait_for_frames(timeout_ms=2000)
        except KinectError:
            continue
        if predicate(fs):
            return fs
    pytest.skip(f"sensor produced no usable {what} within {budget_s:.0f}s")


def _drain(gen: object, count: int, deadline_s: float = 40.0) -> int:
    """Pull ``count`` items from a generator, bounded by a wall-clock deadline."""
    stop = time.monotonic() + deadline_s
    seen = 0
    for _item in gen:  # type: ignore[attr-defined]
        seen += 1
        if seen >= count or time.monotonic() > stop:
            break
    return seen


@pytest.fixture(scope="module")
def kinect() -> Iterator[KinectSensor]:
    try:
        sensor = KinectSensor(streams=_ALL_STREAMS, auto_open=True)
    except KinectNotAvailableError as exc:
        pytest.skip(f"Kinect v2 not available: {exc}")

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and not sensor.is_available:
        time.sleep(0.2)

    yield sensor
    sensor.close()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def test_sensor_reports_open(kinect: KinectSensor) -> None:
    assert kinect.is_open
    assert kinect.streams == _ALL_STREAMS
    assert kinect.mapper is not None


def test_context_manager_opens_and_closes() -> None:
    with KinectSensor(streams=StreamType.DEPTH) as k:
        assert k.is_open
        _grab(k, lambda fs: fs.depth is not None, what="depth frame")
    assert not k.is_open


# ---------------------------------------------------------------------------
# Video frames
# ---------------------------------------------------------------------------
def test_color_frame_shape_and_dtype(kinect: KinectSensor) -> None:
    fs = _grab(kinect, lambda fs: fs.color is not None, what="colour frame")
    assert fs.color is not None
    assert fs.color.data.shape == (1080, 1920, 4)
    assert fs.color.data.dtype == np.uint8
    assert np.shares_memory(fs.color.as_bgr(), fs.color.data)
    assert fs.color.as_bgr().shape == (1080, 1920, 3)


def test_depth_frame_is_plausible(kinect: KinectSensor) -> None:
    fs = _grab(kinect, lambda fs: fs.depth is not None, what="depth frame")
    assert fs.depth is not None
    assert fs.depth.data.shape == (424, 512)
    assert fs.depth.data.dtype == np.uint16
    valid = fs.depth.data[(fs.depth.data > 0) & (fs.depth.data < 8000)]
    assert valid.size > 512, "depth frame looks empty - is the sensor blocked?"
    assert fs.depth.min_reliable_distance > 0
    assert fs.depth.max_reliable_distance > fs.depth.min_reliable_distance


def test_infrared_frame(kinect: KinectSensor) -> None:
    fs = _grab(kinect, lambda fs: fs.infrared is not None, what="infrared frame")
    assert fs.infrared is not None
    assert fs.infrared.data.shape == (424, 512)
    assert fs.infrared.data.dtype == np.uint16
    assert fs.infrared.data.max() > 0
    assert fs.infrared.to_uint8().dtype == np.uint8


def test_body_index_frame(kinect: KinectSensor) -> None:
    fs = _grab(kinect, lambda fs: fs.body_index is not None, what="body-index frame")
    assert fs.body_index is not None
    assert fs.body_index.data.shape == (424, 512)
    uniq = set(np.unique(fs.body_index.data).tolist())
    assert uniq <= {0, 1, 2, 3, 4, 5, 255}


def test_bodies_present_with_25_joints(kinect: KinectSensor) -> None:
    fs = _grab(kinect, lambda fs: bool(fs.bodies), what="body data")
    assert len(fs.bodies) <= 6
    for body in fs.bodies:
        assert len(body.joints) == 25
        assert isinstance(body.tracking_id, int)
    assert all(b.is_tracked for b in fs.tracked_bodies)


def test_poll_frames_yields_a_stream(kinect: KinectSensor) -> None:
    assert _drain(kinect.poll_frames(timeout_ms=2000), 5) == 5


# ---------------------------------------------------------------------------
# Coordinate mapper / point cloud
# ---------------------------------------------------------------------------
def test_map_depth_frame_to_camera_space(kinect: KinectSensor) -> None:
    fs = _grab(kinect, lambda fs: fs.depth is not None, what="depth frame")
    assert fs.depth is not None
    cam = kinect.mapper.map_depth_frame_to_camera_space(fs.depth)
    assert cam.shape == (424, 512, 3)
    assert cam.dtype == np.float32
    assert np.isfinite(cam).any()


def test_generate_point_cloud(kinect: KinectSensor) -> None:
    fs = _grab(
        kinect,
        lambda fs: fs.depth is not None and fs.color is not None,
        what="colour+depth frame",
    )
    cloud = kinect.mapper.generate_point_cloud(fs.depth, fs.color)
    assert cloud.points.ndim == 2 and cloud.points.shape[1] == 3
    assert cloud.points.shape[0] > 0
    assert cloud.colors is not None
    assert cloud.colors.shape == cloud.points.shape
    assert np.isfinite(cloud.points).all()
    assert (cloud.points[:, 2] > 0).all()


def test_single_point_projection_roundtrip(kinect: KinectSensor) -> None:
    from kinect_next.models.geometry import Vector3

    p = kinect.mapper.map_camera_point_to_depth_space(Vector3(0.0, 0.0, 1.5))
    assert 0 <= p.x <= 512
    assert 0 <= p.y <= 424


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
def test_wait_for_audio_frame(kinect: KinectSensor) -> None:
    frame = kinect.wait_for_audio_frame(timeout_ms=5000)
    assert not frame.is_empty
    assert frame.sample_rate == 16000
    assert frame.data.dtype == np.float32
    assert frame.data.size > 0
    assert -60.0 <= frame.beam_angle_deg <= 60.0
    assert frame.as_int16().dtype == np.int16


def test_poll_audio_yields_frames(kinect: KinectSensor) -> None:
    assert _drain(kinect.poll_audio(timeout_ms=5000), 3) == 3


# ---------------------------------------------------------------------------
# Buffer reuse
# ---------------------------------------------------------------------------
def test_reuse_buffers_recycles_the_same_array() -> None:
    with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH, reuse_buffers=True) as k:
        first = _grab(k, lambda fs: fs.color is not None, what="colour frame")
        assert first.color is not None
        first_ptr = first.color.data.ctypes.data
        second = _grab(k, lambda fs: fs.color is not None, what="second colour frame")
        assert second.color is not None
        assert second.color.data.ctypes.data == first_ptr


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------
def test_async_sensor_streams() -> None:
    async def _run() -> int:
        seen = 0
        async with AsyncKinectSensor(streams=StreamType.DEPTH | StreamType.BODY) as k:
            async for fs in k.stream(timeout_ms=2000):
                assert isinstance(fs, FrameSet)
                seen += 1
                if seen >= 3:
                    break
        return seen

    assert asyncio.run(_run()) == 3
