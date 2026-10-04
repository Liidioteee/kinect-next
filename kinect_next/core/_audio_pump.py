"""Background capture of the microphone-array stream.

The Kinect runtime only ever exposes the *latest* audio beam frame (one to three
16 ms sub-frames); anything not picked up within a frame period is gone. Reading
audio from the video loop therefore drops most of it. :class:`AudioPump` owns a
small daemon thread that blocks on the reader's frame-arrived event, copies every
sub-frame as it appears and queues it, so consumers get gap-free audio no matter
how slowly they poll.

The thread still needs the GIL for a few hundred microseconds per read. If other
threads keep the GIL busy with CPU-bound pure-Python code, the hand-over can
arrive too late and a sub-frame is missed; such gaps are counted in
:attr:`AudioPump.missed_subframes` and logged, never hidden.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections import deque
from typing import Final

import numpy as np

from kinect_next.core._cancel import CancelToken, WaitCancelledError
from kinect_next.core.enums import AudioBeamMode
from kinect_next.core.exceptions import (
    AudioStreamError,
    COMOperationError,
    KinectClosedError,
    KinectTimeoutError,
)
from kinect_next.models.audio import AudioBeamSubFrame
from kinect_next.native.interfaces import IAudioBeamFrameReader, IAudioBeamSubFrame
from kinect_next.native.win32 import (
    WAIT_OBJECT_0,
    close_handle,
    create_event,
    set_event,
    wait_for_multiple_objects,
)

_log = logging.getLogger("kinect_next")

_TICKS_PER_MS: Final = 10_000.0
_NS_PER_TICK: Final = 100
_BYTES_PER_SAMPLE: Final = 4  # float32
# A timestamp at or before the newest queued one, but within this window, is a
# repeat of a sub-frame that was already captured.
_DUPLICATE_WINDOW_NS: Final = 1_000_000_000
# A forward jump shorter than this is audio we failed to fetch in time; a longer
# one is the sensor itself restarting its audio pipeline (it does so once,
# shortly after being opened).
_STREAM_RESTART_NS: Final = 1_000_000_000
_JOIN_TIMEOUT_S: Final = 2.0


def parse_subframe(native: IAudioBeamSubFrame, subframe_bytes: int) -> AudioBeamSubFrame:
    """Copy a native ``IAudioBeamSubFrame`` into a typed :class:`AudioBeamSubFrame`."""
    pcm = np.empty(subframe_bytes // _BYTES_PER_SAMPLE, dtype=np.float32)
    native.copy_frame_data_to_array(pcm.nbytes, pcm.ctypes.data_as(ctypes.c_void_p))

    correlated: list[int] = []
    for index in range(native.get_audio_body_correlation_count()):
        correlation = native.get_audio_body_correlation(index)
        if correlation is not None:
            with correlation:
                correlated.append(correlation.get_body_tracking_id())

    return AudioBeamSubFrame(
        data=pcm,
        beam_angle=native.get_beam_angle(),
        beam_angle_confidence=native.get_beam_angle_confidence(),
        mode=AudioBeamMode(native.get_audio_beam_mode()),
        duration_ms=native.get_duration() / _TICKS_PER_MS,
        relative_time_ns=native.get_relative_time() * _NS_PER_TICK,
        correlated_body_ids=tuple(correlated),
    )


class AudioPump:
    """Continuously drains an ``IAudioBeamFrameReader`` into a bounded queue.

    Parameters
    ----------
    reader:
        The audio reader to drain. The pump takes ownership and releases it in
        :meth:`stop`.
    subframe_bytes:
        Payload size of one sub-frame (``IAudioSource::get_SubFrameLengthInBytes``).
    max_subframes:
        Queue capacity. When a consumer falls further behind than this, the
        oldest sub-frames are discarded.
    """

    def __init__(self, reader: IAudioBeamFrameReader, subframe_bytes: int, max_subframes: int) -> None:
        self._reader = reader
        self._subframe_bytes = subframe_bytes
        self._queue: deque[AudioBeamSubFrame] = deque(maxlen=max(1, max_subframes))
        self._cond = threading.Condition()
        self._closed = False
        self._error: BaseException | None = None
        self._last_time_ns: int | None = None
        self._overflowing = False
        self._warned_missed = False
        #: Sub-frames discarded because the queue was full (the consumer is too slow).
        self.dropped_subframes = 0
        #: Sub-frames the capture thread could not fetch before the SDK replaced them.
        self.missed_subframes = 0

        self._stop_event = create_event(manual_reset=True)
        try:
            self._frame_event = reader.subscribe_frame_arrived()
        except BaseException:
            close_handle(self._stop_event)
            raise
        self._thread = threading.Thread(target=self._run, name="kinect-next-audio", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Capture thread
    # ------------------------------------------------------------------
    def _run(self) -> None:
        handles = (self._frame_event, self._stop_event)
        try:
            while wait_for_multiple_objects(handles) == WAIT_OBJECT_0:
                self._reader.clear_frame_arrived(self._frame_event)
                try:
                    subframes = self._read_latest()
                except COMOperationError as exc:
                    _log.debug("Skipped an unreadable audio frame: %s", exc)
                    subframes = []
                if subframes:
                    self._enqueue(subframes)
                else:
                    # Events without a fresh frame are routine; yield briefly so a
                    # handle that fails to re-arm can never turn into a hot spin.
                    time.sleep(0.001)
        except BaseException as exc:
            _log.exception("The Kinect audio capture thread stopped unexpectedly.")
            with self._cond:
                self._error = exc
                self._cond.notify_all()

    def _read_latest(self) -> list[AudioBeamSubFrame]:
        frame_list = self._reader.acquire_latest_beam_frames()
        if frame_list is None:
            return []
        subframes: list[AudioBeamSubFrame] = []
        with frame_list:
            for beam_index in range(frame_list.get_count()):
                frame = frame_list.open_audio_beam_frame(beam_index)
                if frame is None:
                    continue
                with frame:
                    for sub_index in range(frame.get_sub_frame_count()):
                        native = frame.get_sub_frame(sub_index)
                        if native is None:
                            continue
                        with native:
                            subframes.append(parse_subframe(native, self._subframe_bytes))
        return subframes

    def _enqueue(self, subframes: list[AudioBeamSubFrame]) -> None:
        with self._cond:
            added = False
            for subframe in subframes:
                last = self._last_time_ns
                stamp = subframe.relative_time_ns
                if last is not None and 0 <= last - stamp < _DUPLICATE_WINDOW_NS:
                    continue
                if last is not None:
                    self._note_gap(stamp - last, subframe.duration_ms)
                self._last_time_ns = stamp
                if len(self._queue) == self._queue.maxlen:
                    self.dropped_subframes += 1
                    if not self._overflowing:
                        self._overflowing = True
                        _log.warning(
                            "Kinect audio buffer is full (%d sub-frames); dropping the oldest audio. "
                            "Read audio more often or raise audio_buffer_seconds.",
                            self._queue.maxlen,
                        )
                self._queue.append(subframe)
                added = True
            if added:
                self._cond.notify_all()

    def _note_gap(self, delta_ns: int, duration_ms: float) -> None:
        """Account for sub-frames that went missing between two captured ones."""
        step_ns = duration_ms * 1e6
        if step_ns <= 0 or not 1.5 * step_ns < delta_ns < _STREAM_RESTART_NS:
            return
        missed = round(delta_ns / step_ns) - 1
        self.missed_subframes += missed
        if not self._warned_missed:
            self._warned_missed = True
            _log.warning(
                "Kinect audio capture fell behind and missed %d sub-frame(s) (%.0f ms). "
                "Other threads are holding the GIL for too long; see 'Audio under load' "
                "in the README. Further gaps are only counted (KinectSensor.audio_subframes_lost).",
                missed,
                missed * duration_ms,
            )

    # ------------------------------------------------------------------
    # Consumer side
    # ------------------------------------------------------------------
    def drain(self) -> list[AudioBeamSubFrame]:
        """Return and remove everything captured so far (possibly nothing)."""
        with self._cond:
            return self._take()

    def wait(
        self, deadline: float, timeout_ms: int, cancel: CancelToken | None = None
    ) -> list[AudioBeamSubFrame]:
        """Block until at least one sub-frame is queued, then return all of them.

        ``deadline`` is a :func:`time.monotonic` timestamp.
        """
        with self._cond:
            while True:
                if self._queue:
                    return self._take()
                if self._closed:
                    raise KinectClosedError("The sensor was closed while waiting for audio.")
                if self._error is not None:
                    raise AudioStreamError("The audio capture thread stopped.") from self._error
                if cancel is not None and cancel.cancelled:
                    raise WaitCancelledError("The wait for audio was cancelled.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise KinectTimeoutError(f"Timed out waiting for an audio frame ({timeout_ms} ms).")
                self._cond.wait(remaining)

    def _take(self) -> list[AudioBeamSubFrame]:
        items = list(self._queue)
        self._queue.clear()
        self._overflowing = False
        return items

    def interrupt(self) -> None:
        """Wake every blocked :meth:`wait` so it re-checks its cancel token."""
        with self._cond:
            self._cond.notify_all()

    def stop(self) -> None:
        """Stop the capture thread and release the reader (idempotent)."""
        with self._cond:
            if self._closed:
                return
            self._closed = True
            self._cond.notify_all()

        set_event(self._stop_event)
        if self._thread is not threading.current_thread():
            self._thread.join(_JOIN_TIMEOUT_S)
        if self._frame_event:
            try:
                self._reader.unsubscribe_frame_arrived(self._frame_event)
            except (COMOperationError, OSError) as exc:  # pragma: no cover - teardown best effort
                _log.debug("Ignored error while unsubscribing the audio event: %s", exc)
        self._reader.release()
        close_handle(self._stop_event)
        self._frame_event = 0
        self._stop_event = 0
