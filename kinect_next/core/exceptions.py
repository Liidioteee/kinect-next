"""Exception hierarchy for :mod:`kinect_next`.

All exceptions raised by the library derive from :class:`KinectError`, so callers
can guard an entire capture loop with a single ``except KinectError``.
"""

from __future__ import annotations


class KinectError(Exception):
    """Base class for every error raised by :mod:`kinect_next`."""


class KinectNotAvailableError(KinectError):
    """The Kinect v2 sensor (or its SDK runtime) is missing, busy or not ready."""


class KinectTimeoutError(KinectError):
    """A frame did not arrive from the sensor within the requested timeout."""


class KinectClosedError(KinectError):
    """The sensor is closed, or was closed while a wait was in progress."""


class StreamNotEnabledError(KinectError):
    """A stream was requested that was not enabled when the sensor was opened."""


class AudioStreamError(KinectError):
    """Audio subsystem / microphone-array beamforming error."""


class COMOperationError(KinectError):
    """A native Win32/COM call into the Kinect SDK returned a failure ``HRESULT``."""

    def __init__(self, message: str, hresult: int | None = None) -> None:
        if hresult is not None:
            message = f"{message} (HRESULT: 0x{hresult & 0xFFFFFFFF:08X})"
        super().__init__(message)
        self.hresult = hresult
