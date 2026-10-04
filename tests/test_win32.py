"""Win32 event helpers and the lazy ``Kinect20.dll`` binding (no hardware)."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
import time
from ctypes import c_void_p

import pytest

import kinect_next.native.win32 as win32
from kinect_next import KinectNotAvailableError
from kinect_next.native.win32 import (
    WAIT_FAILED,
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    close_handle,
    create_event,
    reset_event,
    set_event,
    wait_for_multiple_objects,
    wait_for_single_object,
)


def test_manual_reset_event_stays_signalled_until_reset() -> None:
    event = create_event(manual_reset=True)
    try:
        assert isinstance(event, int) and event != 0
        assert wait_for_single_object(event, 0) == WAIT_TIMEOUT
        set_event(event)
        assert wait_for_single_object(event, 0) == WAIT_OBJECT_0
        assert wait_for_single_object(event, 0) == WAIT_OBJECT_0
        reset_event(event)
        assert wait_for_single_object(event, 0) == WAIT_TIMEOUT
    finally:
        close_handle(event)


def test_auto_reset_event_is_consumed_by_one_wait() -> None:
    event = create_event()
    try:
        set_event(event)
        assert wait_for_single_object(event, 0) == WAIT_OBJECT_0
        assert wait_for_single_object(event, 0) == WAIT_TIMEOUT
    finally:
        close_handle(event)


def test_event_can_start_signalled() -> None:
    event = create_event(manual_reset=True, initial_state=True)
    try:
        assert wait_for_single_object(event, 0) == WAIT_OBJECT_0
    finally:
        close_handle(event)


def test_wait_blocks_until_another_thread_signals() -> None:
    event = create_event()
    try:
        threading.Timer(0.1, set_event, args=(event,)).start()
        started = time.monotonic()
        assert wait_for_single_object(event, 2000) == WAIT_OBJECT_0
        assert 0.08 <= time.monotonic() - started < 1.5
    finally:
        close_handle(event)


def test_wait_for_multiple_objects_reports_which_handle_fired() -> None:
    first, second = create_event(), create_event()
    try:
        assert wait_for_multiple_objects([first, second], timeout_ms=0) == WAIT_TIMEOUT
        set_event(second)
        assert wait_for_multiple_objects((first, second), timeout_ms=0) == WAIT_OBJECT_0 + 1
        set_event(first)
        set_event(second)
        assert wait_for_multiple_objects([first, second], wait_all=True, timeout_ms=0) == WAIT_OBJECT_0
    finally:
        close_handle(first)
        close_handle(second)


def test_handles_may_be_passed_as_c_void_p() -> None:
    event = create_event(manual_reset=True, initial_state=True)
    try:
        assert wait_for_multiple_objects([c_void_p(event)], timeout_ms=0) == WAIT_OBJECT_0
    finally:
        close_handle(c_void_p(event))


def test_waiting_on_an_invalid_handle_fails() -> None:
    assert wait_for_single_object(0xDEAD0, 0) == WAIT_FAILED


@pytest.mark.parametrize("func", [close_handle, set_event, reset_event])
def test_null_handles_are_ignored(func: object) -> None:
    func(None)  # type: ignore[operator]
    func(0)  # type: ignore[operator]


def test_create_event_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(win32, "_CreateEventW", lambda *_a: None)
    with pytest.raises(OSError, match="event handle"):
        create_event()


# ---------------------------------------------------------------------------
# Kinect20.dll
# ---------------------------------------------------------------------------
class _FakeDll:
    def __init__(self, hresult: int, pointer: int) -> None:
        self.hresult, self.pointer = hresult, pointer
        self.GetDefaultKinectSensor = self._get  # ctypes sets argtypes/restype on this

    class _Func:
        argtypes: object = None
        restype: object = None

    def _get(self, out: object) -> int:
        ctypes.cast(out, ctypes.POINTER(c_void_p)).contents.value = self.pointer  # type: ignore[arg-type]
        return self.hresult


def _use_dll(monkeypatch: pytest.MonkeyPatch, hresult: int, pointer: int) -> None:
    dll = _FakeDll(hresult, pointer)
    monkeypatch.setattr(win32, "_kinect20", dll)
    monkeypatch.setattr(win32, "_get_default_kinect_sensor", dll.GetDefaultKinectSensor)


def test_get_default_kinect_sensor_returns_the_pointer(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_dll(monkeypatch, 0, 0x1234)
    assert win32.get_default_kinect_sensor().value == 0x1234


def test_a_failure_hresult_means_the_sensor_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_dll(monkeypatch, -2147467259, 0)
    with pytest.raises(KinectNotAvailableError, match="0x80004005"):
        win32.get_default_kinect_sensor()


def test_a_null_sensor_pointer_means_the_sensor_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_dll(monkeypatch, 0, 0)
    with pytest.raises(KinectNotAvailableError):
        win32.get_default_kinect_sensor()


def test_a_missing_sdk_is_reported_with_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> object:
        raise OSError("Could not find module 'Kinect20'")

    monkeypatch.setattr(win32, "_kinect20", None)
    monkeypatch.setattr(win32, "_get_default_kinect_sensor", None)
    monkeypatch.setattr(ctypes, "WinDLL", missing)
    with pytest.raises(KinectNotAvailableError, match=r"SDK 2\.0 is installed"):
        win32.get_default_kinect_sensor()


def test_the_dll_binding_is_configured_once(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[str] = []

    class Dll:
        def __init__(self, name: str) -> None:
            loads.append(name)
            self.GetDefaultKinectSensor = _FakeDll._Func()

    monkeypatch.setattr(win32, "_kinect20", None)
    monkeypatch.setattr(win32, "_get_default_kinect_sensor", None)
    monkeypatch.setattr(ctypes, "WinDLL", Dll)
    win32._ensure_kinect_dll()
    win32._ensure_kinect_dll()
    assert loads == ["Kinect20"]
    assert win32._get_default_kinect_sensor.restype is ctypes.HRESULT


# ---------------------------------------------------------------------------
# Portability
# ---------------------------------------------------------------------------
def test_the_package_imports_without_the_windows_only_ctypes_api() -> None:
    """``import kinect_next`` must work where ``ctypes`` has no Win32 support.

    A fresh interpreter has the Windows-only names removed from ``ctypes`` before
    the import, which is what Linux / macOS look like. Opening a sensor there
    must fail with ``KinectNotAvailableError``, not an ``AttributeError``.
    """
    code = """
import ctypes
for name in ("HRESULT", "WINFUNCTYPE", "WinDLL", "windll", "OleDLL", "oledll", "WinError"):
    if hasattr(ctypes, name):
        delattr(ctypes, name)

import kinect_next
from kinect_next import KinectNotAvailableError, KinectSensor, StreamType

sensor = KinectSensor(StreamType.DEPTH, auto_open=False)
try:
    sensor.open()
except KinectNotAvailableError as exc:
    assert "Windows" in str(exc), exc
else:
    raise SystemExit("open() unexpectedly succeeded")
assert not sensor.is_open
print("ok")
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"
