"""Background audio capture: continuity, buffering, shutdown (no hardware)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import numpy as np
import pytest

from kinect_next import (
    AudioBeamMode,
    AudioController,
    AudioStreamError,
    COMOperationError,
    KinectClosedError,
    KinectSensor,
    KinectTimeoutError,
    StreamNotEnabledError,
    StreamType,
)
from kinect_next.core._audio_pump import AudioPump, parse_subframe
from kinect_next.core._cancel import CancelToken, WaitCancelledError
from kinect_next.models.audio import AudioBeamSubFrame
from tests.conftest import make_multi_frame, wait_until
from tests.fakes import FakeAudioReader, FakeBeamFrame, FakeBeamFrameList, FakeSensorNative, FakeSubFrame

SensorFactory = Callable[..., KinectSensor]

_TICK = 160_000  # one 16 ms sub-frame in 100 ns ticks


def _pump(sensor: KinectSensor) -> AudioPump:
    pump = sensor._audio_pump
    assert pump is not None
    return pump


def _deliver(native: FakeSensorNative, sensor: KinectSensor, *subframes: FakeSubFrame) -> None:
    """Hand one beam frame to the reader and wait until the pump has queued it."""
    pump = _pump(sensor)
    if not hasattr(pump, "enqueue_calls"):
        original = pump._enqueue

        def counting(batch: list[AudioBeamSubFrame]) -> None:
            original(batch)
            pump.enqueue_calls += 1  # type: ignore[attr-defined]

        pump.enqueue_calls = 0  # type: ignore[attr-defined]
        pump._enqueue = counting  # type: ignore[method-assign]

    before = pump.enqueue_calls  # type: ignore[attr-defined]
    native.audio.push(*subframes)
    wait_until(lambda: pump.enqueue_calls > before, what="the audio pump to queue the frame")  # type: ignore[attr-defined]


def _subframes(start: int, count: int) -> list[FakeSubFrame]:
    return [FakeSubFrame((start + i) * _TICK, value=(start + i) / 1000.0) for i in range(count)]


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
def test_subframe_fields_are_decoded(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    native.audio.push(
        FakeSubFrame(5 * _TICK, value=0.25, angle=-0.5, confidence=0.75, mode=1, correlated=(11, 22))
    )
    frame = sensor.wait_for_audio_frame(1000)

    assert len(frame.subframes) == 1
    sub = frame.subframes[0]
    assert sub.data.dtype == np.float32 and sub.data.shape == (256,)
    assert np.allclose(sub.data, 0.25)
    assert sub.beam_angle == -0.5 and sub.beam_angle_confidence == 0.75
    assert sub.mode is AudioBeamMode.MANUAL
    assert sub.duration_ms == 16.0
    assert sub.relative_time_ns == 5 * _TICK * 100
    assert sub.correlated_body_ids == (11, 22)
    assert sorted(frame.correlated_body_ids) == [11, 22]


def test_correlations_are_released(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    source = FakeSubFrame(_TICK, correlated=(1, 2))
    _deliver(native, sensor, source)
    assert source.released
    assert all(c.released for c in source.correlations)


def test_subframe_size_follows_the_audio_source() -> None:
    native_sub = FakeSubFrame(_TICK, value=0.5, samples=128)
    parsed = parse_subframe(native_sub, subframe_bytes=512)  # type: ignore[arg-type]
    assert parsed.data.shape == (128,) and np.allclose(parsed.data, 0.5)


# ---------------------------------------------------------------------------
# Continuity (the regression this design exists for)
# ---------------------------------------------------------------------------
def test_a_slow_consumer_loses_no_audio(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    """Regression: audio used to be sampled once per video frame, dropping ~60 %."""
    sensor = make_sensor(StreamType.AUDIO)
    for start in range(0, 20, 2):  # the SDK hands out 1-2 sub-frames at a time
        _deliver(native, sensor, *_subframes(start, 2))

    frame = sensor.wait_for_audio_frame(1000)
    stamps = [sf.relative_time_ns // (_TICK * 100) for sf in frame.subframes]
    assert stamps == list(range(20))
    assert frame.duration_ms == pytest.approx(320.0)
    assert frame.data.shape == (20 * 256,)


def test_frameset_audio_holds_everything_since_the_previous_frameset(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(StreamType.DEPTH | StreamType.AUDIO)

    native.video.push(make_multi_frame(1))
    assert sensor.wait_for_frames(1000).audio is None  # nothing captured yet

    for start in (0, 2, 4):
        _deliver(native, sensor, *_subframes(start, 2))
    native.video.push(make_multi_frame(2))
    fs = sensor.wait_for_frames(1000)
    assert fs.depth is not None and fs.audio is not None
    assert [sf.relative_time_ns // (_TICK * 100) for sf in fs.audio.subframes] == [0, 1, 2, 3, 4, 5]

    _deliver(native, sensor, *_subframes(6, 1))
    native.video.push(make_multi_frame(3))
    fs = sensor.wait_for_frames(1000)
    assert fs.audio is not None
    assert [sf.relative_time_ns // (_TICK * 100) for sf in fs.audio.subframes] == [6]


def test_audio_only_frameset(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    native.audio.push(*_subframes(0, 2))
    fs = sensor.wait_for_frames(1000)
    assert fs.audio is not None and len(fs.audio.subframes) == 2
    assert fs.depth is None and fs.color is None and fs.bodies == []


def test_repeated_subframes_are_not_queued_twice(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    _deliver(native, sensor, *_subframes(0, 2))
    _deliver(native, sensor, *_subframes(1, 2))  # sub-frame 1 again, then 2
    _deliver(native, sensor, *_subframes(0, 1))  # an old one
    frame = sensor.wait_for_audio_frame(1000)
    assert [sf.relative_time_ns // (_TICK * 100) for sf in frame.subframes] == [0, 1, 2]


def test_a_restarted_audio_clock_is_accepted(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    late = 10_000_000_000 // 100  # 10 s in ticks
    _deliver(native, sensor, FakeSubFrame(late))
    _deliver(native, sensor, FakeSubFrame(_TICK))  # the clock started over
    frame = sensor.wait_for_audio_frame(1000)
    assert [sf.relative_time_ns for sf in frame.subframes] == [late * 100, _TICK * 100]


def test_missing_frames_and_subframes_are_skipped(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    frame_list = FakeBeamFrameList([None, FakeBeamFrame([None, FakeSubFrame(3 * _TICK)])])
    native.audio.push_list(frame_list)
    frame = sensor.wait_for_audio_frame(1000)
    assert [sf.relative_time_ns for sf in frame.subframes] == [3 * _TICK * 100]


# ---------------------------------------------------------------------------
# Buffer bounds
# ---------------------------------------------------------------------------
def test_buffer_overflow_drops_the_oldest_audio_and_warns_once(
    native: FakeSensorNative, make_sensor: SensorFactory, caplog: pytest.LogCaptureFixture
) -> None:
    sensor = make_sensor(StreamType.AUDIO, audio_buffer_seconds=0.064)  # 4 sub-frames
    with caplog.at_level(logging.WARNING, logger="kinect_next"):
        for start in range(0, 10, 2):
            _deliver(native, sensor, *_subframes(start, 2))

    frame = sensor.wait_for_audio_frame(1000)
    assert [sf.relative_time_ns // (_TICK * 100) for sf in frame.subframes] == [6, 7, 8, 9]
    assert _pump(sensor).dropped_subframes == 6
    warnings = [r for r in caplog.records if "audio buffer is full" in r.getMessage()]
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Waiting and errors
# ---------------------------------------------------------------------------
def test_audio_wait_times_out(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    started = time.monotonic()
    with pytest.raises(KinectTimeoutError, match="60 ms"):
        sensor.wait_for_audio_frame(60)
    assert 0.05 <= time.monotonic() - started < 1.0


def test_audio_wait_blocks_until_audio_arrives(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    threading.Timer(0.1, lambda: native.audio.push(*_subframes(0, 1))).start()
    started = time.monotonic()
    frame = sensor.wait_for_audio_frame(2000)
    assert time.monotonic() - started >= 0.08
    assert not frame.is_empty


def test_the_capture_thread_idles_without_spinning(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    """Regression: the audio wait loop used to burn a full core."""
    sensor = make_sensor(StreamType.AUDIO)
    _deliver(native, sensor, *_subframes(0, 1))
    cleared = native.audio.cleared
    started = time.process_time()
    time.sleep(0.3)
    assert native.audio.cleared == cleared, "the pump woke up with no event pending"
    assert time.process_time() - started < 0.15
    assert sensor.wait_for_audio_frame(100).subframes


def test_audio_wait_on_a_closed_sensor(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    sensor.close()
    with pytest.raises(KinectClosedError):
        sensor.wait_for_audio_frame(10)


def test_close_interrupts_a_blocked_audio_wait(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    errors: list[BaseException] = []

    def waiter() -> None:
        try:
            sensor.wait_for_audio_frame(10_000)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=waiter, daemon=True)
    thread.start()
    time.sleep(0.1)
    sensor.close()
    thread.join(2.0)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], KinectClosedError)


def test_poll_audio_ends_cleanly_when_closed(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    counts: list[int] = []
    done = threading.Event()

    def consume() -> None:
        for frame in sensor.poll_audio(timeout_ms=10_000):
            counts.append(len(frame.subframes))
        done.set()

    threading.Thread(target=consume, daemon=True).start()
    _deliver(native, sensor, *_subframes(0, 2))
    wait_until(lambda: counts == [2], what="the first audio frame")
    sensor.close()
    assert done.wait(2.0)


def test_poll_audio_skips_timeouts(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    threading.Timer(0.12, lambda: native.audio.push(*_subframes(0, 1))).start()
    frame = next(sensor.poll_audio(timeout_ms=30))
    assert len(frame.subframes) == 1


def test_cancelling_a_token_aborts_the_audio_wait(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    cancel = CancelToken()
    errors: list[BaseException] = []

    def waiter() -> None:
        try:
            sensor._wait_for_audio_frame(10_000, cancel)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=waiter, daemon=True)
    thread.start()
    time.sleep(0.1)
    cancel.cancelled = True
    sensor._interrupt()
    thread.join(2.0)
    assert len(errors) == 1 and isinstance(errors[0], WaitCancelledError)


def test_an_unreadable_frame_does_not_stop_capture(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    broken = FakeBeamFrameList([])
    broken.count_error = COMOperationError("frame expired", -1)
    native.audio.push_list(broken)
    wait_until(lambda: broken.released, what="the broken frame to be discarded")

    native.audio.push(*_subframes(0, 1))
    assert len(sensor.wait_for_audio_frame(1000).subframes) == 1


def test_a_crashed_capture_thread_surfaces_as_an_error(
    native: FakeSensorNative, make_sensor: SensorFactory, caplog: pytest.LogCaptureFixture
) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    broken = FakeBeamFrameList([])
    broken.count_error = RuntimeError("unexpected")
    with caplog.at_level(logging.CRITICAL, logger="kinect_next"):
        native.audio.push_list(broken)
        with pytest.raises(AudioStreamError, match="capture thread stopped"):
            sensor.wait_for_audio_frame(2000)


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------
def test_close_stops_the_thread_and_releases_the_reader(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    pump, reader = _pump(sensor), native.audio
    assert pump._thread.is_alive()
    sensor.close()
    assert not pump._thread.is_alive()
    assert reader.unsubscribed and reader.released
    assert native.audio_sources[-1].released and native.audio_sources[-1].beam_list.released
    pump.stop()  # idempotent
    assert reader.release_count == 1


def test_a_failed_subscription_does_not_leak_the_stop_event() -> None:
    reader = FakeAudioReader()
    reader.subscribe_error = COMOperationError("no audio", -1)
    with pytest.raises(COMOperationError):
        AudioPump(reader, 1024, 8)  # type: ignore[arg-type]


def test_reopening_starts_a_fresh_capture(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    sensor.close()
    sensor.open()
    assert len(native.audio_readers) == 2
    native.audio.push(*_subframes(0, 1))
    assert len(sensor.wait_for_audio_frame(1000).subframes) == 1


# ---------------------------------------------------------------------------
# The controller exposed by the sensor
# ---------------------------------------------------------------------------
def test_sensor_exposes_the_audio_controller(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    assert isinstance(sensor.audio, AudioController)
    sensor.audio.set_beam_angle(10.0)
    assert native.beams[0].mode == 1
    sensor.close()
    with pytest.raises(KinectClosedError):
        _ = sensor.audio


def test_a_sensor_without_beams_still_captures_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    import kinect_next.core.sensor as sensor_mod

    native = FakeSensorNative(beams=[])
    monkeypatch.setattr(sensor_mod, "get_default_kinect_sensor", lambda: 0x1000)
    monkeypatch.setattr(sensor_mod, "IKinectSensorNative", lambda _ptr: native)
    monkeypatch.setattr(sensor_mod, "_shared_sensor", None)
    monkeypatch.setattr(sensor_mod, "_shared_refcount", 0)

    with KinectSensor(StreamType.AUDIO) as sensor:
        with pytest.raises(StreamNotEnabledError, match="no audio beam"):
            _ = sensor.audio
        native.audio.push(*_subframes(0, 1))
        assert len(sensor.wait_for_audio_frame(1000).subframes) == 1


def test_an_audio_event_without_a_frame_is_harmless(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    cleared = native.audio.cleared
    native.audio.signal()  # event fires, AcquireLatestBeamFrames has nothing
    wait_until(lambda: native.audio.cleared > cleared, what="the pump to consume the event")
    native.audio.push(*_subframes(0, 1))
    assert len(sensor.wait_for_audio_frame(1000).subframes) == 1


def test_a_pump_torn_down_mid_wait_reads_as_closed(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO)
    pump, sensor._audio_pump = sensor._audio_pump, None
    try:
        with pytest.raises(KinectClosedError):
            sensor.wait_for_audio_frame(50)
    finally:
        sensor._audio_pump = pump


# ---------------------------------------------------------------------------
# Loss accounting
# ---------------------------------------------------------------------------
def test_missed_subframes_are_counted_and_reported_once(
    native: FakeSensorNative, make_sensor: SensorFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """If the capture thread is starved, the gap must be visible, not silent."""
    sensor = make_sensor(StreamType.AUDIO)
    assert sensor.audio_subframes_lost == 0
    with caplog.at_level(logging.WARNING, logger="kinect_next"):
        _deliver(native, sensor, *_subframes(0, 2))
        _deliver(native, sensor, *_subframes(4, 1))  # sub-frames 2 and 3 never seen
        _deliver(native, sensor, *_subframes(6, 1))  # sub-frame 5 never seen

    assert _pump(sensor).missed_subframes == 3
    assert sensor.audio_subframes_lost == 3
    warnings = [r for r in caplog.records if "fell behind" in r.getMessage()]
    assert len(warnings) == 1 and "missed 2 sub-frame(s) (32 ms)" in warnings[0].getMessage()
    frame = sensor.wait_for_audio_frame(1000)
    assert [sf.relative_time_ns // (_TICK * 100) for sf in frame.subframes] == [0, 1, 4, 6]


def test_a_sensor_side_audio_restart_is_not_counted_as_loss(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    """The Kinect pauses audio for ~3 s once after opening; that is not our gap."""
    sensor = make_sensor(StreamType.AUDIO)
    _deliver(native, sensor, *_subframes(0, 2))
    _deliver(native, sensor, *_subframes(200, 2))  # 3.2 s later on the sensor clock
    assert sensor.audio_subframes_lost == 0


def test_lost_count_includes_buffer_overflow(native: FakeSensorNative, make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.AUDIO, audio_buffer_seconds=0.032)  # 2 sub-frames
    for start in (0, 2, 4):
        _deliver(native, sensor, *_subframes(start, 2))
    assert sensor.audio_subframes_lost == 4


def test_lost_count_without_audio_is_zero(make_sensor: SensorFactory) -> None:
    sensor = make_sensor(StreamType.DEPTH)
    assert sensor.audio_subframes_lost == 0
    sensor.close()
    assert sensor.audio_subframes_lost == 0


def test_a_cancelled_wait_leaves_queued_audio_for_the_next_reader(
    native: FakeSensorNative, make_sensor: SensorFactory
) -> None:
    """Regression: audio that arrived together with a cancellation was taken by
    the abandoned wait and thrown away, leaving a gap for the real consumer."""
    sensor = make_sensor(StreamType.AUDIO)
    _deliver(native, sensor, *_subframes(0, 2))

    cancel = CancelToken()
    cancel.cancelled = True
    with pytest.raises(WaitCancelledError):
        sensor._wait_for_audio_frame(1000, cancel)

    frame = sensor.wait_for_audio_frame(1000)
    assert [sf.relative_time_ns // (_TICK * 100) for sf in frame.subframes] == [0, 1]
