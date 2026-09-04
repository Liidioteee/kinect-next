"""``AsyncKinectSensor`` -- an asyncio-friendly wrapper for FastAPI / WebSockets."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from kinect_next.core.audio import AudioController
from kinect_next.core.enums import StreamType
from kinect_next.core.exceptions import KinectTimeoutError
from kinect_next.core.mapper import CoordinateMapper
from kinect_next.core.sensor import KinectSensor
from kinect_next.models.audio import AudioFrame
from kinect_next.models.frameset import FrameSet


class AsyncKinectSensor:
    """Asynchronous controller for a Kinect v2.

    Blocking SDK calls run in a worker thread, so the event loop is never stalled::

        async with AsyncKinectSensor(StreamType.DEPTH | StreamType.BODY) as kinect:
            async for frames in kinect.stream():
                ...
    """

    def __init__(
        self,
        streams: StreamType = StreamType.COLOR | StreamType.DEPTH | StreamType.BODY,
        auto_open: bool = True,
        *,
        reuse_buffers: bool = False,
    ) -> None:
        self._sync_sensor = KinectSensor(streams=streams, auto_open=False, reuse_buffers=reuse_buffers)
        self._auto_open = auto_open

    @property
    def sync_sensor(self) -> KinectSensor:
        """The underlying synchronous :class:`KinectSensor`."""
        return self._sync_sensor

    @property
    def streams(self) -> StreamType:
        """The stream bitmask this sensor was configured with."""
        return self._sync_sensor.streams

    @property
    def mapper(self) -> CoordinateMapper:
        """The vectorised coordinate mapper (sensor must be open)."""
        return self._sync_sensor.mapper

    @property
    def audio(self) -> AudioController:
        """The microphone-array beam controller (requires ``StreamType.AUDIO``)."""
        return self._sync_sensor.audio

    @property
    def is_available(self) -> bool:
        """Whether the sensor hardware is connected and ready."""
        return self._sync_sensor.is_available

    @property
    def is_open(self) -> bool:
        """Whether the sensor is currently open."""
        return self._sync_sensor.is_open

    async def open(self) -> None:
        """Open the sensor without blocking the event loop."""
        await asyncio.to_thread(self._sync_sensor.open)

    async def close(self) -> None:
        """Close the sensor without blocking the event loop."""
        await asyncio.to_thread(self._sync_sensor.close)

    async def __aenter__(self) -> AsyncKinectSensor:
        if not self._sync_sensor.is_open:
            await self.open()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        await self.close()

    async def wait_for_frames(self, timeout_ms: int = 1500) -> FrameSet:
        """Await one synchronised :class:`FrameSet` from a worker thread."""
        return await asyncio.to_thread(self._sync_sensor.wait_for_frames, timeout_ms)

    async def wait_for_audio_frame(self, timeout_ms: int = 1500) -> AudioFrame:
        """Await one :class:`AudioFrame` from a worker thread."""
        return await asyncio.to_thread(self._sync_sensor.wait_for_audio_frame, timeout_ms)

    async def stream(self, timeout_ms: int = 1500) -> AsyncGenerator[FrameSet, None]:
        """Yield synchronised :class:`FrameSet` objects until the sensor closes."""
        while self._sync_sensor.is_open:
            try:
                yield await self.wait_for_frames(timeout_ms)
            except KinectTimeoutError:
                continue

    async def audio_stream(self, timeout_ms: int = 1500) -> AsyncGenerator[AudioFrame, None]:
        """Yield :class:`AudioFrame` objects at the microphone frame rate (~60 Hz)."""
        while self._sync_sensor.is_open:
            try:
                yield await self.wait_for_audio_frame(timeout_ms)
            except KinectTimeoutError:
                continue
