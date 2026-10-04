"""``KinectSensor`` lifecycle and video capture, driven by fake native objects."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np
import pytest

import kinect_next.core.sensor as sensor_mod
from kinect_next import (
    COMOperationError,
    FrameEdges,
    HandState,
    JointType,
    KinectClosedError,
    KinectError,
    KinectSensor,
    KinectTimeoutError,
    StreamNotEnabledError,
    StreamType,
    TrackingConfidence,
    TrackingState,
)
from kinect_next.core._cancel import CancelToken, WaitCancelledError
from kinect_next.core.enums import ColorImageFormat
from kinect_next.native.win32 import WAIT_FAILED
from tests.conftest import VIDEO_STREAMS, make_multi_frame, wait_until
from tests.fakes import FakeSensorNative

SensorFactory = Callable[..., KinectSensor]


def _in_thread(func: Callable[[], object]) -> tuple[threading.Thread, dict[str, object]]:
    """Run ``func`` in a thread, capturing its result or exception."""
    outcome: dict[str, object] = {}

    def runner() -> None:
        try:
            outcome["result"] = func()
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread, outcome


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def test_open_subscribes_and_close_releases_everything(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(StreamType.DEPTH | StreamType.BODY)
    assert sensor.is_open
    assert native.opens == 1
    reader = native.video
    assert reader.event != 0

    sensor.close()
    assert not sensor.is_open
    assert reader.unsubscribed and reader.released
    assert native.closes == 1 and native.released
    assert sensor_mod._shared_refcount == 0


def test_only_video_bits_reach_the_multi_source_reader(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    make_sensor(StreamType.COLOR | StreamType.DEPTH | StreamType.AUDIO)
    assert native.video.flags == int(StreamType.COLOR | StreamType.DEPTH)


def test_audio_only_sensor_opens_no_video_reader(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    make_sensor(StreamType.AUDIO)
    assert native.video_readers == []
    assert len(native.audio_readers) == 1


def test_auto_open_false_defers_to_the_context_manager(native: FakeSensorNative) -> None:
    sensor = KinectSensor(StreamType.DEPTH, auto_open=False)
    assert not sensor.is_open and native.opens == 0
    with sensor as entered:
        assert entered is sensor and sensor.is_open
    assert not sensor.is_open


def test_open_and_close_are_idempotent(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    sensor.open()
    assert len(native.video_readers) == 1
    sensor.close()
    sensor.close()
    assert native.closes == 1


def test_a_closed_sensor_can_be_reopened(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    sensor.close()
    sensor.open()
    native.video.push(make_multi_frame(5))
    assert sensor.wait_for_frames(500).depth is not None
    assert native.opens == 2


def test_two_sensors_share_one_native_device(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    first, second = make_sensor(StreamType.DEPTH), make_sensor(StreamType.COLOR)
    assert native.opens == 1
    first.close()
    assert native.closes == 0, "the device must stay open for the other instance"
    native.video.push(make_multi_frame())
    assert second.wait_for_frames(500).color is not None
    second.close()
    assert native.closes == 1


def test_a_failed_open_releases_what_it_acquired(native: FakeSensorNative) -> None:
    native.next_subscribe_error = COMOperationError("subscribe failed", -1)
    with pytest.raises(COMOperationError):
        KinectSensor(StreamType.DEPTH)
    assert native.video.released
    assert native.closes == 1
    assert sensor_mod._shared_refcount == 0


def test_a_failed_open_leaves_the_sensor_reusable(native: FakeSensorNative) -> None:
    sensor = KinectSensor(StreamType.DEPTH, auto_open=False)
    native.next_subscribe_error = COMOperationError("subscribe failed", -1)
    with pytest.raises(COMOperationError):
        sensor.open()
    assert not sensor.is_open
    sensor.open()
    assert sensor.is_open
    sensor.close()


def test_properties_and_repr(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.DEPTH | StreamType.BODY)
    assert sensor.streams == StreamType.DEPTH | StreamType.BODY
    assert sensor.is_available is True
    assert "open" in repr(sensor) and "DEPTH" in repr(sensor)
    native.available = False
    assert sensor.is_available is False
    sensor.close()
    assert sensor.is_available is False
    assert "closed" in repr(sensor)


def test_is_available_is_false_when_the_native_call_fails(
    native: FakeSensorNative, make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensor = make_sensor()

    def boom() -> bool:
        raise COMOperationError("device lost", -1)

    monkeypatch.setattr(native, "is_available", boom)
    assert sensor.is_available is False


def test_mapper_is_only_available_while_open(make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    assert sensor.mapper is not None
    sensor.close()
    with pytest.raises(KinectClosedError):
        _ = sensor.mapper


def test_audio_buffer_seconds_must_be_positive(native: FakeSensorNative) -> None:
    with pytest.raises(ValueError, match="audio_buffer_seconds"):
        KinectSensor(StreamType.AUDIO, audio_buffer_seconds=0)


# ---------------------------------------------------------------------------
# Capture: content
# ---------------------------------------------------------------------------
def test_frameset_carries_every_enabled_stream(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(VIDEO_STREAMS)
    native.video.push(make_multi_frame(tick=7))
    fs = sensor.wait_for_frames(500)

    assert fs.color is not None and fs.color.data.shape == (1080, 1920, 4)
    assert fs.color.data.dtype == np.uint8 and (fs.color.data == 7).all()
    assert fs.color.settings is not None
    assert (fs.color.settings.exposure_time, fs.color.settings.gain) == (333_333, 2.0)

    assert fs.depth is not None and fs.depth.data.shape == (424, 512)
    assert fs.depth.data.dtype == np.uint16 and (fs.depth.data == 1007).all()
    assert (fs.depth.min_reliable_distance, fs.depth.max_reliable_distance) == (500, 4500)

    assert fs.infrared is not None and (fs.infrared.data == 2007).all()
    assert fs.long_exposure_infrared is not None and (fs.long_exposure_infrared.data == 3007).all()
    assert fs.body_index is not None and fs.body_index.data.dtype == np.uint8
    assert (fs.body_index.data == 255).all()

    assert fs.floor_clip_plane is not None and fs.floor_clip_plane.as_tuple() == (0.0, 1.0, 0.0, 0.75)
    assert fs.audio is None


def test_colour_is_requested_as_bgra(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.COLOR)
    frame = native.video.push(make_multi_frame())
    sensor.wait_for_frames(500)
    color = frame._frames["color"]
    assert color is not None and color.requested_format == int(ColorImageFormat.BGRA)  # type: ignore[union-attr]


def test_relative_times_are_reported_in_nanoseconds(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(VIDEO_STREAMS)
    native.video.push(make_multi_frame(tick=3))
    fs = sensor.wait_for_frames(500)
    assert fs.depth is not None and fs.depth.relative_time_ns == 30 * 100
    assert fs.infrared is not None and fs.infrared.relative_time_ns == 31 * 100
    assert fs.long_exposure_infrared is not None
    assert fs.long_exposure_infrared.relative_time_ns == 32 * 100
    assert fs.body_index is not None and fs.body_index.relative_time_ns == 33 * 100
    assert fs.color is not None and fs.color.relative_time_ns == 36 * 100
    assert fs.relative_time_ns == fs.depth.relative_time_ns


@pytest.mark.parametrize(
    ("streams", "expected_ticks"),
    [
        (StreamType.COLOR, 16),
        (StreamType.BODY, 14),
        (StreamType.COLOR | StreamType.BODY_INDEX, 13),
        (StreamType.COLOR | StreamType.INFRARED, 11),
    ],
)
def test_frameset_time_falls_back_when_depth_is_absent(
    native: FakeSensorNative, make_sensor: SensorFactory, streams: StreamType, expected_ticks: int
) -> None:
    sensor = make_sensor(streams)
    native.video.push(make_multi_frame(tick=1))
    assert sensor.wait_for_frames(500).relative_time_ns == expected_ticks * 100


def test_bodies_are_parsed_into_typed_models(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.BODY)
    native.video.push(make_multi_frame())
    fs = sensor.wait_for_frames(500)

    assert len(fs.bodies) == 2
    tracked, untracked = fs.bodies
    assert fs.tracked_bodies == [tracked]

    assert tracked.is_tracked and tracked.tracking_id == 77
    assert len(tracked.joints) == 25
    assert tracked.joints.head.joint_type is JointType.HEAD
    assert tracked.joints.head.position.as_tuple() == (0.0, 0.5, 2.0)
    assert tracked.joints[JointType.SPINE_BASE].tracking_state is TrackingState.TRACKED
    assert tracked.joints.head.orientation.as_tuple() == (0.0, 0.0, 0.0, 1.0)
    assert tracked.hand_left.state is HandState.OPEN
    assert tracked.hand_left.confidence is TrackingConfidence.HIGH
    assert tracked.hand_right.state is HandState.CLOSED
    assert tracked.hand_right.confidence is TrackingConfidence.LOW
    assert tracked.lean.as_tuple() == (0.25, -0.5)
    assert tracked.lean_tracking_state is TrackingState.TRACKED
    assert tracked.clipped_edges is FrameEdges.NONE

    assert not untracked.is_tracked and untracked.tracking_id == 0
    assert len(untracked.joints) == 25
    assert all(j.tracking_state is TrackingState.NOT_TRACKED for j in untracked.joints)


def test_streams_without_data_are_none(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(VIDEO_STREAMS)
    native.video.push(
        make_multi_frame(
            color=None, depth=None, infrared=None, long_exposure_infrared=None, body_index=None, body=None
        )
    )
    fs = sensor.wait_for_frames(500)
    assert fs.color is None and fs.depth is None and fs.infrared is None
    assert fs.long_exposure_infrared is None and fs.body_index is None
    assert fs.bodies == [] and fs.floor_clip_plane is None
    assert fs.relative_time_ns == 0


def test_disabled_streams_are_not_touched(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.DEPTH)
    frame = native.video.push(make_multi_frame())
    fs = sensor.wait_for_frames(500)
    assert fs.depth is not None and fs.color is None and fs.infrared is None
    assert len(frame.references) == 1


def test_camera_settings_are_optional(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    from tests.fakes import FakeColorFrame

    sensor = make_sensor(StreamType.COLOR)
    bare = FakeColorFrame(np.zeros((1080, 1920, 4), dtype=np.uint8), ticks=1, settings=None)
    native.video.push(make_multi_frame(color=bare))
    fs = sensor.wait_for_frames(500)
    assert fs.color is not None and fs.color.settings is None


def test_every_native_object_is_released_after_capture(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(VIDEO_STREAMS)
    frame = native.video.push(make_multi_frame())
    sensor.wait_for_frames(500)
    leaked = [type(obj).__name__ for obj in frame.everything() if not obj.released]
    assert leaked == []


def test_native_objects_are_released_even_when_a_copy_fails(
    native: FakeSensorNative, make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensor = make_sensor(StreamType.DEPTH | StreamType.INFRARED)
    frame = make_multi_frame()
    infrared = frame._frames["infrared"]
    assert infrared is not None

    def boom(*_args: object) -> None:
        raise COMOperationError("copy failed", -1)

    monkeypatch.setattr(infrared, "copy_frame_data_to_array", boom)
    native.video.push(frame)
    with pytest.raises(COMOperationError, match="copy failed"):
        sensor.wait_for_frames(500)
    assert frame.released and infrared.released
    assert all(ref.released for ref in frame.references)


def test_frames_own_their_data_by_default(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.DEPTH)
    native.video.push(make_multi_frame(tick=1))
    first = sensor.wait_for_frames(500)
    native.video.push(make_multi_frame(tick=2))
    second = sensor.wait_for_frames(500)
    assert first.depth is not None and second.depth is not None
    assert not np.shares_memory(first.depth.data, second.depth.data)
    assert (first.depth.data == 1001).all() and (second.depth.data == 1002).all()


def test_reuse_buffers_recycles_the_arrays(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.DEPTH | StreamType.COLOR, reuse_buffers=True)
    native.video.push(make_multi_frame(tick=1))
    first = sensor.wait_for_frames(500)
    native.video.push(make_multi_frame(tick=2))
    second = sensor.wait_for_frames(500)
    assert first.depth is not None and second.depth is not None
    assert first.depth.data is second.depth.data
    assert first.color is not None and second.color is not None
    assert first.color.data is second.color.data
    assert (first.depth.data == 1002).all(), "the earlier frame is overwritten, as documented"


# ---------------------------------------------------------------------------
# Capture: waiting
# ---------------------------------------------------------------------------
def test_wait_times_out_when_no_frame_arrives(make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    started = time.monotonic()
    with pytest.raises(KinectTimeoutError, match="60 ms"):
        sensor.wait_for_frames(60)
    assert 0.05 <= time.monotonic() - started < 1.0


def test_zero_timeout_polls_without_blocking(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    with pytest.raises(KinectTimeoutError):
        sensor.wait_for_frames(0)
    native.video.push(make_multi_frame())
    assert sensor.wait_for_frames(0).depth is not None


def test_wait_blocks_on_the_event_instead_of_spinning(
    native: FakeSensorNative, make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the event was never re-armed, so every wait returned at once."""
    sensor = make_sensor()
    for tick in (1, 2):  # leave the event in its post-capture state
        native.video.push(make_multi_frame(tick))
        sensor.wait_for_frames(500)

    waits: list[int] = []
    real_wait = sensor_mod.wait_for_multiple_objects

    def counting_wait(handles: object, wait_all: bool = False, timeout_ms: int = 0) -> int:
        waits.append(timeout_ms)
        return real_wait(handles, wait_all, timeout_ms)  # type: ignore[arg-type]

    monkeypatch.setattr(sensor_mod, "wait_for_multiple_objects", counting_wait)
    threading.Timer(0.15, lambda: native.video.push(make_multi_frame(3))).start()

    started = time.monotonic()
    fs = sensor.wait_for_frames(2000)
    elapsed = time.monotonic() - started

    assert fs.depth is not None and (fs.depth.data == 1003).all()
    assert elapsed >= 0.1, "returned before the frame existed"
    assert len(waits) == 1, f"expected one blocking wait, saw {len(waits)}"
    assert native.video.cleared >= 3, "the event data must be fetched to re-arm the handle"


def test_an_event_without_a_frame_is_retried(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    native.video.signal()  # event fires, AcquireLatestFrame still says E_PENDING
    threading.Timer(0.05, lambda: native.video.push(make_multi_frame(9))).start()
    fs = sensor.wait_for_frames(2000)
    assert fs.depth is not None and (fs.depth.data == 1009).all()


def test_events_without_frames_still_respect_the_deadline(
    native: FakeSensorNative, make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensor = make_sensor()
    # A handle that never re-arms: every wait reports "signalled", no frame ever comes.
    monkeypatch.setattr(native.video, "clear_frame_arrived", lambda _handle: None)
    native.video.signal()
    started = time.monotonic()
    with pytest.raises(KinectTimeoutError):
        sensor.wait_for_frames(80)
    assert time.monotonic() - started < 1.0


def test_a_failed_win32_wait_is_reported(make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    sensor = make_sensor()
    monkeypatch.setattr(sensor_mod, "wait_for_multiple_objects", lambda *_a, **_k: WAIT_FAILED)
    with pytest.raises(KinectError, match="code 4294967295"):
        sensor.wait_for_frames(100)


def test_waiting_on_a_closed_sensor_raises(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = KinectSensor(StreamType.DEPTH, auto_open=False)
    with pytest.raises(KinectClosedError):
        sensor.wait_for_frames(10)
    opened = make_sensor()
    opened.close()
    with pytest.raises(KinectClosedError):
        opened.wait_for_frames(10)


def test_waiting_with_no_stream_enabled_is_an_error(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.NONE)
    with pytest.raises(KinectError, match="No data stream"):
        sensor.wait_for_frames(10)


def test_audio_api_requires_the_audio_stream(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.DEPTH)
    with pytest.raises(StreamNotEnabledError):
        _ = sensor.audio
    with pytest.raises(StreamNotEnabledError):
        sensor.wait_for_audio_frame(10)


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------
def test_close_interrupts_a_blocked_wait(make_sensor: SensorFactory) -> None:
    """Regression: closing during a wait used to fail with an opaque Win32 error."""
    sensor = make_sensor()
    thread, outcome = _in_thread(lambda: sensor.wait_for_frames(10_000))
    time.sleep(0.1)

    started = time.monotonic()
    sensor.close()
    thread.join(2.0)

    assert not thread.is_alive()
    assert time.monotonic() - started < 1.0
    assert isinstance(outcome.get("error"), KinectClosedError)


def test_poll_frames_ends_cleanly_when_closed(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    seen: list[int] = []

    def consume() -> None:
        for fs in sensor.poll_frames(timeout_ms=10_000):
            assert fs.depth is not None
            seen.append(int(fs.depth.data[0, 0]))

    thread, outcome = _in_thread(consume)
    for tick in (1, 2, 3):
        native.video.push(make_multi_frame(tick))
        wait_until(lambda t=tick: seen and seen[-1] == 1000 + t, what=f"frame {tick}")
    sensor.close()
    thread.join(2.0)

    assert not thread.is_alive()
    assert "error" not in outcome
    assert seen == [1001, 1002, 1003]


def test_poll_frames_skips_timeouts(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    threading.Timer(0.12, lambda: native.video.push(make_multi_frame(4))).start()
    fs = next(sensor.poll_frames(timeout_ms=30))  # several timeouts happen first
    assert fs.depth is not None and (fs.depth.data == 1004).all()


def test_poll_frames_on_a_closed_sensor_yields_nothing() -> None:
    sensor = KinectSensor(StreamType.DEPTH, auto_open=False)
    assert list(sensor.poll_frames()) == []
    assert list(sensor.poll_audio()) == []


def test_concurrent_waiters_each_get_a_distinct_frame(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor()
    results: list[int] = []
    guard = threading.Lock()

    def grab() -> None:
        fs = sensor.wait_for_frames(5000)
        assert fs.depth is not None
        with guard:
            results.append(int(fs.depth.data[0, 0]))

    threads = [threading.Thread(target=grab, daemon=True) for _ in range(2)]
    for thread in threads:
        thread.start()
    time.sleep(0.05)
    native.video.push(make_multi_frame(1))
    wait_until(lambda: len(results) == 1, what="first waiter")
    native.video.push(make_multi_frame(2))
    for thread in threads:
        thread.join(2.0)
    assert sorted(results) == [1001, 1002]


def test_a_queued_waiter_times_out_while_another_holds_the_capture(make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    thread, _outcome = _in_thread(lambda: sensor.wait_for_frames(10_000))
    time.sleep(0.1)
    with pytest.raises(KinectTimeoutError):
        sensor.wait_for_frames(50)
    sensor.close()
    thread.join(2.0)


def test_cancelling_a_token_aborts_the_wait(make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    cancel = CancelToken()
    thread, outcome = _in_thread(lambda: sensor._wait_for_frames(10_000, cancel))
    time.sleep(0.1)

    cancel.cancelled = True
    sensor._interrupt()
    thread.join(2.0)

    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), WaitCancelledError)
    assert sensor.is_open, "cancelling one wait must not close the sensor"


def test_a_spurious_wake_up_keeps_waiting(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    thread, outcome = _in_thread(lambda: sensor.wait_for_frames(5000))
    time.sleep(0.05)
    sensor._interrupt()  # nobody cancelled, nobody closed
    time.sleep(0.05)
    assert thread.is_alive()
    native.video.push(make_multi_frame(6))
    thread.join(2.0)
    assert "error" not in outcome


def test_a_pre_cancelled_token_never_waits(make_sensor: SensorFactory) -> None:
    sensor = make_sensor()
    cancel = CancelToken()
    cancel.cancelled = True
    with pytest.raises(WaitCancelledError):
        sensor._wait_for_frames(10_000, cancel)


def test_close_completes_even_if_unsubscribing_fails(
    native: FakeSensorNative, make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensor = make_sensor()
    reader = native.video

    def boom(_handle: int) -> None:
        raise COMOperationError("device already gone", -1)

    monkeypatch.setattr(reader, "unsubscribe_frame_arrived", boom)
    sensor.close()
    assert not sensor.is_open and reader.released
    assert sensor_mod._shared_refcount == 0


def test_a_reader_torn_down_mid_wait_reads_as_closed(make_sensor: SensorFactory) -> None:
    """The guard behind the lock-free ``is_open`` check."""
    sensor = make_sensor()
    reader, sensor._reader = sensor._reader, None
    try:
        with pytest.raises(KinectClosedError):
            sensor.wait_for_frames(50)
    finally:
        sensor._reader = reader


def test_a_wait_cancelled_as_a_frame_arrives_leaves_the_frame(
    native: FakeSensorNative, make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: when a frame and a cancellation are signalled together the
    Win32 wait reports the frame; the abandoned wait must not consume it."""
    sensor = make_sensor()
    cancel = CancelToken()
    real_wait = sensor_mod.wait_for_multiple_objects

    def cancelled_during_wait(handles: object, wait_all: bool = False, timeout_ms: int = 0) -> int:
        result = real_wait(handles, wait_all, timeout_ms)  # type: ignore[arg-type]
        cancel.cancelled = True  # the awaiting task was cancelled while we were blocked
        return result

    native.video.push(make_multi_frame(7))
    monkeypatch.setattr(sensor_mod, "wait_for_multiple_objects", cancelled_during_wait)
    with pytest.raises(WaitCancelledError):
        sensor._wait_for_frames(1000, cancel)
    monkeypatch.undo()

    fs = sensor.wait_for_frames(1000)
    assert fs.depth is not None and (fs.depth.data == 1007).all()


def test_a_wait_closed_as_a_frame_arrives_reports_closed(
    native: FakeSensorNative, make_sensor: SensorFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensor = make_sensor()
    real_wait = sensor_mod.wait_for_multiple_objects

    def closing_during_wait(handles: object, wait_all: bool = False, timeout_ms: int = 0) -> int:
        result = real_wait(handles, wait_all, timeout_ms)  # type: ignore[arg-type]
        sensor._closing = True
        return result

    frame = native.video.push(make_multi_frame(1))
    monkeypatch.setattr(sensor_mod, "wait_for_multiple_objects", closing_during_wait)
    try:
        with pytest.raises(KinectClosedError):
            sensor.wait_for_frames(1000)
    finally:
        sensor._closing = False
    assert not frame.released, "the frame must not have been acquired"
