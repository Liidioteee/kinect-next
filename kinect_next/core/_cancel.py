"""Cooperative cancellation of blocking waits (used by the asyncio wrapper)."""

from __future__ import annotations

from kinect_next.core.exceptions import KinectError


class CancelToken:
    """A flag a blocked wait re-checks whenever the sensor is woken up."""

    __slots__ = ("cancelled",)

    def __init__(self) -> None:
        self.cancelled = False


class WaitCancelledError(KinectError):
    """The wait was abandoned by its caller (e.g. the awaiting task was cancelled)."""
