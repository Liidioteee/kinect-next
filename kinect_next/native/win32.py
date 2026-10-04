"""Win32 kernel synchronisation primitives and lazy bindings to ``Kinect20.dll``.

Importing this module never touches the Kinect runtime. ``Kinect20.dll`` is
resolved on first use (see :func:`get_default_kinect_sensor`) so that
``import kinect_next`` works on a Windows box without the Kinect for Windows SDK
installed -- useful for CI and unit tests.
"""

from __future__ import annotations

import ctypes
from collections.abc import Sequence
from ctypes import POINTER, c_bool, c_uint32, c_void_p, c_wchar_p
from typing import Any, Final

from kinect_next.core.exceptions import KinectNotAvailableError
from kinect_next.native.com_base import HRESULT

INFINITE: Final = 0xFFFFFFFF
WAIT_OBJECT_0: Final = 0x00000000
WAIT_TIMEOUT: Final = 0x00000102
WAIT_FAILED: Final = 0xFFFFFFFF

# ``WinDLL`` only exists on Windows; guard the attribute access so that the
# module still imports on other platforms (see ``com_base`` for the ``HRESULT``
# fallback). There, every entry point raises ``KinectNotAvailableError``.
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if hasattr(ctypes, "WinDLL") else None


def _bind(name: str, argtypes: list[Any], restype: Any) -> Any:
    if _kernel32 is None:  # pragma: no cover - non-Windows fallback
        raise KinectNotAvailableError("Win32 kernel32 API is only available on Windows.")
    func = getattr(_kernel32, name)
    func.argtypes = argtypes
    func.restype = restype
    return func


def _unavailable(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover - non-Windows
    raise KinectNotAvailableError("Win32 kernel32 API is only available on Windows.")


if _kernel32 is not None:
    _CreateEventW = _bind("CreateEventW", [c_void_p, c_bool, c_bool, c_wchar_p], c_void_p)
    _CloseHandle = _bind("CloseHandle", [c_void_p], c_bool)
    _SetEvent = _bind("SetEvent", [c_void_p], c_bool)
    _ResetEvent = _bind("ResetEvent", [c_void_p], c_bool)
    _WaitForSingleObject = _bind("WaitForSingleObject", [c_void_p, c_uint32], c_uint32)
    _WaitForMultipleObjects = _bind(
        "WaitForMultipleObjects", [c_uint32, POINTER(c_void_p), c_bool, c_uint32], c_uint32
    )
else:  # pragma: no cover - non-Windows fallback
    _CreateEventW = _CloseHandle = _SetEvent = _unavailable
    _ResetEvent = _WaitForSingleObject = _WaitForMultipleObjects = _unavailable


def create_event(manual_reset: bool = False, initial_state: bool = False) -> int:
    """Create an unnamed Win32 event object and return its handle."""
    handle = _CreateEventW(None, manual_reset, initial_state, None)
    if not handle:
        raise OSError(ctypes.get_last_error(), "Failed to create a Win32 event handle.")
    return int(handle)


def close_handle(handle: c_void_p | int | None) -> None:
    """Close a Win32 handle, ignoring NULL."""
    if handle:
        _CloseHandle(handle)


def set_event(handle: c_void_p | int | None) -> None:
    """Signal a Win32 event object."""
    if handle:
        _SetEvent(handle)


def reset_event(handle: c_void_p | int | None) -> None:
    """Reset a Win32 event object to the non-signalled state."""
    if handle:
        _ResetEvent(handle)


def wait_for_single_object(handle: c_void_p | int, timeout_ms: int = INFINITE) -> int:
    """Block until ``handle`` is signalled or ``timeout_ms`` elapses."""
    return int(_WaitForSingleObject(handle, timeout_ms))


def wait_for_multiple_objects(
    handles: Sequence[c_void_p | int], wait_all: bool = False, timeout_ms: int = INFINITE
) -> int:
    """Block until one/all of ``handles`` are signalled or ``timeout_ms`` elapses.

    Returns ``WAIT_OBJECT_0 + i`` for the first signalled handle ``i``,
    ``WAIT_TIMEOUT`` or ``WAIT_FAILED``.
    """
    count = len(handles)
    arr = (c_void_p * count)(*handles)
    return int(_WaitForMultipleObjects(count, arr, wait_all, timeout_ms))


# ---------------------------------------------------------------------------
# Lazy Kinect20.dll binding
# ---------------------------------------------------------------------------

_kinect20: Any = None
_get_default_kinect_sensor: Any = None

_SDK_HINT = (
    "Kinect20.dll could not be loaded. Make sure the Microsoft Kinect for "
    "Windows SDK 2.0 is installed and that you are running 64-bit Python on "
    "Windows. Download: https://www.microsoft.com/en-us/download/details.aspx?id=44561"
)


def _ensure_kinect_dll() -> None:
    global _kinect20, _get_default_kinect_sensor
    if _kinect20 is not None:
        return
    if not hasattr(ctypes, "WinDLL"):  # pragma: no cover - non-Windows
        raise KinectNotAvailableError("Kinect v2 is only supported on 64-bit Windows.")
    try:
        _kinect20 = ctypes.WinDLL("Kinect20")
    except OSError as exc:
        raise KinectNotAvailableError(_SDK_HINT) from exc

    fn = _kinect20.GetDefaultKinectSensor
    fn.argtypes = [POINTER(c_void_p)]
    fn.restype = HRESULT
    _get_default_kinect_sensor = fn


def get_default_kinect_sensor() -> c_void_p:
    """Return a raw ``IKinectSensor*`` from ``Kinect20.dll::GetDefaultKinectSensor``.

    Raises
    ------
    KinectNotAvailableError
        If the SDK runtime cannot be loaded or the sensor cannot be acquired.
    """
    _ensure_kinect_dll()
    assert _get_default_kinect_sensor is not None
    raw_ptr = c_void_p()
    hr = _get_default_kinect_sensor(ctypes.byref(raw_ptr))
    if hr < 0 or not raw_ptr.value:
        raise KinectNotAvailableError(f"GetDefaultKinectSensor failed (HRESULT: 0x{hr & 0xFFFFFFFF:08X}).")
    return raw_ptr
