"""``AsyncKinectSensor`` driven by fake native objects (no hardware)."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from kinect_next import (
    AsyncKinectSensor,
    AudioController,
    CoordinateMapper,
    KinectClosedError,
    KinectTimeoutError,
    StreamType,
)
from tests.conftest import make_multi_frame
from tests.fakes import FakeSensorNative, FakeSubFrame

_TICK = 160_000


def test_constructing_does_not_touch_the_hardware(native: FakeSensorNative) -> None:
    sensor = AsyncKinectSensor(StreamType.DEPTH)
    assert not sensor.is_open and native.opens == 0
    assert sensor.streams == StreamType.DEPTH
    assert sensor.is_available is False
    assert repr(sensor).startswith("<AsyncKinectSensor") and "closed" in repr(sensor)


def test_auto_open_is_gone_from_the_async_constructor() -> None:
    """Regression: the parameter existed but was silently ignored."""
    assert "auto_open" not in inspect.signature(AsyncKinectSensor).parameters


def test_async_context_manager_opens_and_closes(native: FakeSensorNative) -> None:
    async def run() -> None:
        async with AsyncKinectSensor(StreamType.DEPTH | StreamType.AUDIO) as sensor:
            assert sensor.is_open and sensor.is_available
            assert isinstance(sensor.mapper, CoordinateMapper)
            assert isinstance(sensor.audio, AudioController)
            assert sensor.sync_sensor.is_open
            assert sensor.audio_subframes_lost == 0
        assert not sensor.is_open

    asyncio.run(run())
    assert native.opens == 1 and native.closes == 1


def test_explicit_open_and_close_are_idempotent(native: FakeSensorNative) -> None:
    async def run() -> None:
        sensor = AsyncKinectSensor(StreamType.DEPTH)
        await sensor.open()
        await sensor.open()
        assert sensor.is_open
        await sensor.close()
        await sensor.close()
        assert not sensor.is_open

    asyncio.run(run())
    assert native.opens == 1 and native.closes == 1


def test_wait_for_frames(native: FakeSensorNative) -> None:
    async def run() -> int:
        async with AsyncKinectSensor(StreamType.DEPTH) as sensor:
            native.video.push(make_multi_frame(4))
            fs = await sensor.wait_for_frames(1000)
            assert fs.depth is not None
            return int(fs.depth.data[0, 0])

    assert asyncio.run(run()) == 1004


def test_wait_for_frames_times_out(native: FakeSensorNative) -> None:
    async def run() -> None:
        async with AsyncKinectSensor(StreamType.DEPTH) as sensor:
            with pytest.raises(KinectTimeoutError):
                await sensor.wait_for_frames(40)

    asyncio.run(run())


def test_stream_yields_frames_until_closed(native: FakeSensorNative) -> None:
    async def run() -> list[int]:
        seen: list[int] = []
        async with AsyncKinectSensor(StreamType.DEPTH) as sensor:
            native.video.push(make_multi_frame(1))
            async for fs in sensor.stream(timeout_ms=5000):
                assert fs.depth is not None
                seen.append(int(fs.depth.data[0, 0]))
                if len(seen) == 3:
                    asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(sensor.close()))
                else:
                    native.video.push(make_multi_frame(len(seen) + 1))
        return seen

    assert asyncio.run(run()) == [1001, 1002, 1003]


def test_stream_skips_timeouts(native: FakeSensorNative) -> None:
    async def run() -> int:
        async with AsyncKinectSensor(StreamType.DEPTH) as sensor:
            asyncio.get_running_loop().call_later(0.1, lambda: native.video.push(make_multi_frame(8)))
            async for fs in sensor.stream(timeout_ms=25):
                assert fs.depth is not None
                return int(fs.depth.data[0, 0])
        return -1

    assert asyncio.run(run()) == 1008


def test_audio_wait_and_audio_stream(native: FakeSensorNative) -> None:
    async def run() -> list[int]:
        counts: list[int] = []
        async with AsyncKinectSensor(StreamType.AUDIO) as sensor:
            native.audio.push(FakeSubFrame(_TICK), FakeSubFrame(2 * _TICK))
            frame = await sensor.wait_for_audio_frame(1000)
            counts.append(len(frame.subframes))

            native.audio.push(FakeSubFrame(3 * _TICK))
            async for frame in sensor.audio_stream(timeout_ms=5000):
                counts.append(len(frame.subframes))
                asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(sensor.close()))
        return counts

    assert asyncio.run(run()) == [2, 1]


def test_audio_stream_skips_timeouts(native: FakeSensorNative) -> None:
    async def run() -> int:
        async with AsyncKinectSensor(StreamType.AUDIO) as sensor:
            asyncio.get_running_loop().call_later(0.1, lambda: native.audio.push(FakeSubFrame(_TICK)))
            async for frame in sensor.audio_stream(timeout_ms=25):
                return len(frame.subframes)
        return -1

    assert asyncio.run(run()) == 1


def test_waiting_on_a_closed_async_sensor_raises(native: FakeSensorNative) -> None:
    async def run() -> None:
        sensor = AsyncKinectSensor(StreamType.DEPTH)
        with pytest.raises(KinectClosedError):
            await sensor.wait_for_frames(10)
        assert [fs async for fs in sensor.stream()] == []
        assert [fr async for fr in sensor.audio_stream()] == []

    asyncio.run(run())


def test_cancelling_the_task_aborts_the_worker_thread(native: FakeSensorNative) -> None:
    """Regression: a cancelled wait left a thread behind that swallowed the next frame."""

    async def run() -> int:
        async with AsyncKinectSensor(StreamType.DEPTH) as sensor:
            capture_lock = sensor.sync_sensor._lock
            for _ in range(5):
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(sensor.wait_for_frames(10_000), timeout=0.03)

            # The abandoned workers must let go of the capture, not sit in it for 10 s.
            released = False
            for _ in range(200):
                released = capture_lock.acquire(blocking=False)
                if released:
                    capture_lock.release()
                    break
                await asyncio.sleep(0.005)
            assert released, "a cancelled wait is still blocking inside the sensor"

            # ...and the next frame goes to the caller that is actually waiting.
            native.video.push(make_multi_frame(9))
            fs = await sensor.wait_for_frames(1000)
            assert fs.depth is not None
            assert sensor.is_open
            return int(fs.depth.data[0, 0])

    assert asyncio.run(run()) == 1009


def test_cancelling_an_audio_wait_aborts_the_worker_thread(native: FakeSensorNative) -> None:
    async def run() -> int:
        async with AsyncKinectSensor(StreamType.AUDIO) as sensor:
            task = asyncio.ensure_future(sensor.wait_for_audio_frame(10_000))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            native.audio.push(FakeSubFrame(_TICK))
            return len((await sensor.wait_for_audio_frame(1000)).subframes)

    assert asyncio.run(run()) == 1


def test_closing_while_a_wait_is_in_flight(native: FakeSensorNative) -> None:
    async def run() -> None:
        sensor = AsyncKinectSensor(StreamType.DEPTH)
        await sensor.open()
        pending = asyncio.ensure_future(sensor.wait_for_frames(10_000))
        await asyncio.sleep(0.05)
        await sensor.close()
        with pytest.raises(KinectClosedError):
            await pending

    asyncio.run(run())
