"""``AsyncKinectSensor`` -- an asyncio-friendly wrapper for FastAPI / WebSockets."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from types import TracebackType
from typing import TypeVar

from typing_extensions import Self

from kinect_next.core._cancel import CancelToken
from kinect_next.core.audio import AudioController
from kinect_next.core.enums import StreamType
from kinect_next.core.exceptions import KinectClosedError, KinectTimeoutError
from kinect_next.core.mapper import CoordinateMapper
from kinect_next.core.sensor import DEFAULT_TIMEOUT_MS, KinectSensor
from kinect_next.models.audio import AudioFrame
from kinect_next.models.frameset import FrameSet

_T = TypeVar("_T")


class AsyncKinectSensor:
    """Asynchronous controller for a Kinect v2.

    Blocking SDK calls run in a worker thread, so the event loop is never stalled::

        async with AsyncKinectSensor(StreamType.DEPTH | StreamType.BODY) as kinect:
            async for frames in kinect.stream():
                ...

    The sensor is opened by ``async with`` (or an explicit ``await open()``);
    constructing the object never touches the hardware. Cancelling an awaiting
    task (``asyncio.wait_for``, ``task.cancel()``) also aborts the underlying
    wait, so no worker thread is left behind consuming frames.
    """

    __slots__ = ("_sync_sensor",)

    def __init__(
        self,
        streams: StreamType = StreamType.COLOR | StreamType.DEPTH | StreamType.BODY,
        *,
        reuse_buffers: bool = False,
        audio_buffer_seconds: float = 10.0,
    ) -> None:
        self._sync_sensor = KinectSensor(
            streams=streams,
            auto_open=False,
            reuse_buffers=reuse_buffers,
            audio_buffer_seconds=audio_buffer_seconds,
        )

    def __repr__(self) -> str:
        return f"<Async{repr(self._sync_sensor)[1:]}"

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
    def audio_subframes_lost(self) -> int:
        """Audio sub-frames lost since opening (see :attr:`KinectSensor.audio_subframes_lost`)."""
        return self._sync_sensor.audio_subframes_lost

    @property
    def is_available(self) -> bool:
        """Whether the sensor hardware is connected and ready."""
        return self._sync_sensor.is_available

    @property
    def is_open(self) -> bool:
        """Whether the sensor is currently open."""
        return self._sync_sensor.is_open

    async def open(self) -> None:
        """Open the sensor without blocking the event loop (idempotent)."""
        await asyncio.to_thread(self._sync_sensor.open)

    async def close(self) -> None:
        """Close the sensor without blocking the event loop (idempotent)."""
        await asyncio.to_thread(self._sync_sensor.close)

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def _run_cancellable(self, wait: Callable[[int, CancelToken], _T], timeout_ms: int) -> _T:
        """Run a blocking wait in a worker thread, aborting it if we are cancelled."""
        cancel = CancelToken()
        try:
            return await asyncio.to_thread(wait, timeout_ms, cancel)
        except asyncio.CancelledError:
            cancel.cancelled = True
            self._sync_sensor._interrupt()
            raise

    async def wait_for_frames(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> FrameSet:
        """Await one synchronised :class:`FrameSet` from a worker thread."""
        return await self._run_cancellable(self._sync_sensor._wait_for_frames, timeout_ms)

    async def wait_for_audio_frame(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> AudioFrame:
        """Await one gap-free :class:`AudioFrame` from a worker thread."""
        return await self._run_cancellable(self._sync_sensor._wait_for_audio_frame, timeout_ms)

    async def stream(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> AsyncGenerator[FrameSet, None]:
        """Yield synchronised :class:`FrameSet` objects until the sensor closes."""
        while self._sync_sensor.is_open:
            try:
                yield await self.wait_for_frames(timeout_ms)
            except KinectTimeoutError:
                continue
            except KinectClosedError:
                return

    async def audio_stream(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> AsyncGenerator[AudioFrame, None]:
        """Yield gap-free :class:`AudioFrame` objects until the sensor closes."""
        while self._sync_sensor.is_open:
            try:
                yield await self.wait_for_audio_frame(timeout_ms)
            except KinectTimeoutError:
                continue
            except KinectClosedError:
                return
