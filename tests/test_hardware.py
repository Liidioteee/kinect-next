"""Integration tests that talk to a real, connected Kinect v2.

Run with::

    pytest -m hardware --run-hardware

The sensor must be plugged in, powered and recognised by the SDK. No particular
scene content is required (nobody needs to be in frame). The Kinect delivers
sub-frames independently, so per-stream tests poll for a while before giving up.
"""

from __future__ import annotations

import asyncio
import threading
import time
import warnings
from collections.abc import Callable, Iterator
from itertools import pairwise

import numpy as np
import pytest

import kinect_next.core.sensor as sensor_mod
from kinect_next import (
    AsyncKinectSensor,
    AudioBeamMode,
    AudioStreamError,
    KinectClosedError,
    KinectSensor,
    StreamType,
    Vector3,
)
from kinect_next.core.exceptions import KinectError, KinectNotAvailableError
from kinect_next.models.frameset import FrameSet

pytestmark = pytest.mark.hardware

_VIDEO_STREAMS = (
    StreamType.COLOR | StreamType.DEPTH | StreamType.INFRARED | StreamType.BODY | StreamType.BODY_INDEX
)
_ALL_STREAMS = _VIDEO_STREAMS | StreamType.AUDIO

_WARMUP_S = 15.0
_SUBFRAME_NS = 16_000_000


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


def _audio_gaps(stamps: list[int]) -> list[int]:
    """Deltas between consecutive sub-frame timestamps that are not one sub-frame."""
    return [b - a for a, b in pairwise(stamps) if abs((b - a) - _SUBFRAME_NS) > 1_000_000]


def _settle_video(kinect: KinectSensor, budget_s: float = 12.0) -> None:
    """Wait until frames arrive steadily.

    A freshly (re)opened Kinect hands out a few frames and then pauses delivery
    once for 1-3 s while its pipeline spins up. That is sensor behaviour, measured
    with the raw SDK calls; anything timing-sensitive has to start after it.
    """
    deadline = time.monotonic() + budget_s
    steady = 0
    last = time.monotonic()
    while steady < 20:
        if time.monotonic() > deadline:
            pytest.skip("the sensor did not reach a steady frame rate")
        try:
            kinect.wait_for_frames(1000)
        except KinectError:
            steady = 0
            continue
        now = time.monotonic()
        steady = steady + 1 if now - last < 0.15 else 0
        last = now


def _settle_audio(kinect: KinectSensor, seconds: float = 4.0) -> None:
    """Let the audio pipeline get past its start-up hiccup, then discard the backlog.

    Shortly after opening, the runtime pauses audio delivery once for ~3 s. That
    is sensor behaviour; continuity is only meaningful after it.
    """
    stop = time.monotonic() + seconds
    while time.monotonic() < stop:
        try:
            kinect.wait_for_audio_frame(1000)
        except KinectError:
            pass


@pytest.fixture(scope="module")
def kinect() -> Iterator[KinectSensor]:
    try:
        sensor = KinectSensor(streams=_ALL_STREAMS)
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
    assert kinect.is_available
    assert kinect.streams == _ALL_STREAMS
    assert kinect.mapper is not None


def test_context_manager_opens_and_closes() -> None:
    with KinectSensor(streams=StreamType.DEPTH) as k:
        assert k.is_open
        _grab(k, lambda fs: fs.depth is not None, what="depth frame")
    assert not k.is_open


def test_first_frame_arrives_within_the_default_timeout() -> None:
    """Regression: a cold start used to overrun the old 1.5 s default."""
    with KinectSensor(streams=StreamType.DEPTH) as k:
        assert k.wait_for_frames().depth is not None
    with KinectSensor(streams=StreamType.AUDIO) as k:
        assert not k.wait_for_audio_frame().is_empty


def test_reopening_and_sharing_the_device(kinect: KinectSensor) -> None:
    refs = sensor_mod._shared_refcount
    for _ in range(2):
        with KinectSensor(streams=StreamType.DEPTH) as other:
            assert sensor_mod._shared_refcount == refs + 1
            _grab(other, lambda fs: fs.depth is not None, what="depth frame")
    assert sensor_mod._shared_refcount == refs
    # The long-lived fixture sensor must be unaffected by the others closing.
    _grab(kinect, lambda fs: fs.depth is not None, what="depth frame after sibling close")


def test_close_from_another_thread_ends_polling_cleanly() -> None:
    """Regression: this used to fail with 'Win32 wait ... failed (code 4294967295)'."""
    sensor = KinectSensor(streams=StreamType.DEPTH)
    _settle_video(sensor)
    outcome: dict[str, object] = {}

    def consume() -> None:
        try:
            outcome["frames"] = sum(1 for _ in sensor.poll_frames())
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    time.sleep(0.5)
    sensor.close()
    thread.join(5.0)

    assert not thread.is_alive()
    assert "error" not in outcome, outcome.get("error")
    assert isinstance(outcome["frames"], int) and outcome["frames"] > 3
    with pytest.raises(KinectClosedError):
        sensor.wait_for_frames(100)


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
    assert fs.color.settings is not None and fs.color.settings.exposure_time > 0


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
    assert fs.floor_clip_plane is not None


def test_poll_frames_yields_a_stream(kinect: KinectSensor) -> None:
    assert _drain(kinect.poll_frames(timeout_ms=2000), 5) == 5


def test_frames_carry_sensor_timestamps(kinect: KinectSensor) -> None:
    """Regression: every ``relative_time_ns`` used to be 0."""
    first = _grab(kinect, lambda fs: fs.depth is not None and fs.color is not None, what="colour+depth")
    second = _grab(kinect, lambda fs: fs.depth is not None and fs.color is not None, what="colour+depth")
    assert first.depth is not None and second.depth is not None
    assert first.color is not None and first.infrared is not None

    assert first.relative_time_ns == first.depth.relative_time_ns > 0
    assert second.depth.relative_time_ns > first.depth.relative_time_ns
    step_ms = (second.depth.relative_time_ns - first.depth.relative_time_ns) / 1e6
    assert 20 < step_ms < 500, f"implausible frame interval {step_ms:.1f} ms"
    # Frames of one tick are within a frame period of each other.
    assert abs(first.color.relative_time_ns - first.depth.relative_time_ns) < 100_000_000
    assert abs(first.infrared.relative_time_ns - first.depth.relative_time_ns) < 100_000_000


def test_waiting_blocks_instead_of_polling() -> None:
    """Regression: the frame event was never re-armed, so waits degenerated into a 1 ms poll."""
    with KinectSensor(streams=StreamType.DEPTH) as k:
        _settle_video(k)

        waits = 0
        real_wait = sensor_mod.wait_for_multiple_objects

        def counting(handles: object, wait_all: bool = False, timeout_ms: int = 0) -> int:
            nonlocal waits
            waits += 1
            return real_wait(handles, wait_all, timeout_ms)  # type: ignore[arg-type]

        sensor_mod.wait_for_multiple_objects = counting  # type: ignore[assignment]
        try:
            cpu, wall = time.process_time(), time.perf_counter()
            frames = 60
            for _ in range(frames):
                k.wait_for_frames()
            cpu, wall = time.process_time() - cpu, time.perf_counter() - wall
        finally:
            sensor_mod.wait_for_multiple_objects = real_wait

    assert waits / frames < 4, f"{waits / frames:.1f} waits per frame - the event is not blocking"
    assert cpu / wall < 0.25, f"capture loop used {cpu / wall:.0%} of a core"


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


def test_mapper_handles_views_and_rejects_bad_input(kinect: KinectSensor) -> None:
    """Regression: mirrored views and float arrays produced silently wrong results."""
    fs = _grab(kinect, lambda fs: fs.depth is not None, what="depth frame")
    assert fs.depth is not None
    mirrored = fs.depth.data[:, ::-1]
    from_view = kinect.mapper.map_depth_frame_to_camera_space(mirrored)
    from_copy = kinect.mapper.map_depth_frame_to_camera_space(np.ascontiguousarray(mirrored))
    assert np.array_equal(from_view, from_copy, equal_nan=True)

    with pytest.raises(TypeError):
        kinect.mapper.map_depth_frame_to_camera_space(fs.depth.data.astype(np.float32))
    with pytest.raises(ValueError):
        kinect.mapper.map_depth_frame_to_camera_space(fs.depth.data[:100])


def test_generate_point_cloud(kinect: KinectSensor) -> None:
    fs = _grab(
        kinect,
        lambda fs: fs.depth is not None and fs.color is not None,
        what="colour+depth frame",
    )
    assert fs.depth is not None
    cloud = kinect.mapper.generate_point_cloud(fs.depth, fs.color)
    assert cloud.points.ndim == 2 and cloud.points.shape[1] == 3
    assert cloud.points.shape[0] > 0
    assert cloud.colors is not None
    assert cloud.colors.shape == cloud.points.shape
    assert np.isfinite(cloud.points).all()
    assert (cloud.points[:, 2] > 0).all()

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # regression: -inf used to be cast to int
        full = kinect.mapper.generate_point_cloud(fs.depth, fs.color, remove_invalid=False)
    assert full.points.shape == (424 * 512, 3)


def test_single_point_projection_roundtrip(kinect: KinectSensor) -> None:
    p = kinect.mapper.map_camera_point_to_depth_space(Vector3(0.1, -0.2, 1.5))
    assert 0 <= p.x <= 512
    assert 0 <= p.y <= 424
    back = kinect.mapper.map_depth_point_to_camera_space(p, 1500)
    assert back.as_tuple() == pytest.approx((0.1, -0.2, 1.5), abs=0.01)
    assert not kinect.mapper.map_camera_point_to_depth_space(Vector3(0.0, 0.0, 0.0)).is_valid()


def test_color_frame_to_depth_space(kinect: KinectSensor) -> None:
    fs = _grab(kinect, lambda fs: fs.depth is not None, what="depth frame")
    assert fs.depth is not None
    pts = kinect.mapper.map_color_frame_to_depth_space(fs.depth)
    assert pts.shape == (1080, 1920, 2) and pts.dtype == np.float32
    fx, fy, cx, cy = kinect.mapper.get_depth_camera_intrinsics()
    assert 300 < fx < 450 and 300 < fy < 450 and 200 < cx < 320 and 150 < cy < 260


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
def test_wait_for_audio_frame(kinect: KinectSensor) -> None:
    frame = kinect.wait_for_audio_frame(timeout_ms=5000)
    assert not frame.is_empty
    assert frame.sample_rate == 16000
    assert frame.data.dtype == np.float32
    assert frame.data.size > 0 and frame.data.size % 256 == 0
    assert -60.0 <= frame.beam_angle_deg <= 60.0
    assert frame.as_int16().dtype == np.int16
    sub = frame.subframes[0]
    assert sub.duration_ms == pytest.approx(16.0)
    assert sub.relative_time_ns > 0
    assert sub.mode in (AudioBeamMode.AUTOMATIC, AudioBeamMode.MANUAL)


def test_poll_audio_yields_frames(kinect: KinectSensor) -> None:
    assert _drain(kinect.poll_audio(timeout_ms=5000), 3) == 3


def test_audio_in_framesets_is_gap_free(kinect: KinectSensor) -> None:
    """Regression: reading audio from the video loop used to drop 30-60 % of it."""
    _settle_audio(kinect)
    stamps: list[int] = []
    started = time.monotonic()
    while time.monotonic() - started < 4.0:
        fs = kinect.wait_for_frames()
        if fs.audio is not None:
            stamps += [sf.relative_time_ns for sf in fs.audio.subframes]
    elapsed = time.monotonic() - started

    assert _audio_gaps(stamps) == []
    captured_s = len(stamps) * 0.016
    assert captured_s == pytest.approx(elapsed, abs=0.25), f"{captured_s:.2f}s of audio in {elapsed:.2f}s"


def test_audio_survives_a_slow_consumer(kinect: KinectSensor) -> None:
    _settle_audio(kinect, seconds=1.0)
    before = kinect.wait_for_audio_frame().subframes[-1].relative_time_ns
    time.sleep(1.0)  # the application is busy; the capture thread is not
    frame = kinect.wait_for_audio_frame()
    stamps = [before, *(sf.relative_time_ns for sf in frame.subframes)]
    assert _audio_gaps(stamps) == []
    assert len(frame.subframes) >= 55


def test_audio_only_capture_does_not_burn_a_core() -> None:
    """Regression: the audio wait loop used to spin at ~100 % of one core."""
    with KinectSensor(streams=StreamType.AUDIO) as k:
        k.wait_for_audio_frame()
        cpu, wall = time.process_time(), time.perf_counter()
        for _ in range(60):
            k.wait_for_audio_frame()
        cpu, wall = time.process_time() - cpu, time.perf_counter() - wall
    assert cpu / wall < 0.25, f"audio capture used {cpu / wall:.0%} of a core"


def test_beam_steering_works_or_fails_loudly(kinect: KinectSensor) -> None:
    """Some runtimes ignore MANUAL mode; the library must never pretend otherwise."""
    audio = kinect.audio
    if audio.supports_manual_steering:
        assert audio.set_beam_angle(-20.0) == -20.0
        assert audio.mode is AudioBeamMode.MANUAL
        audio.mode = AudioBeamMode.AUTOMATIC
    else:
        with pytest.raises(AudioStreamError, match="MANUAL"):
            audio.set_beam_angle(-20.0)
    assert audio.mode is AudioBeamMode.AUTOMATIC
    assert -60.0 <= audio.beam_angle_deg <= 60.0
    assert 0.0 <= audio.beam_angle_confidence <= 1.0


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


def test_async_cancellation_and_close() -> None:
    def audio_threads() -> int:
        return sum(1 for t in threading.enumerate() if t.name == "kinect-next-audio")

    before = audio_threads()  # the module-wide fixture sensor may own one

    async def _run() -> None:
        async with AsyncKinectSensor(streams=StreamType.DEPTH | StreamType.AUDIO) as k:
            await k.wait_for_frames()
            for i in range(20):
                try:
                    await asyncio.wait_for(k.wait_for_frames(), timeout=0.002 * (i % 4))
                except asyncio.TimeoutError:
                    pass
            # Cancelled waits must not leave workers behind that eat frames.
            for _ in range(10):
                assert (await k.wait_for_frames()).depth is not None
            assert not (await k.wait_for_audio_frame()).is_empty
            pending = asyncio.ensure_future(k.wait_for_audio_frame(10_000))
            await asyncio.sleep(0)
        try:
            await pending
        except KinectClosedError:
            pass

    asyncio.run(_run())
    assert audio_threads() == before, "closing must stop the sensor's audio capture thread"
