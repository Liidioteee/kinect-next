"""Tests for the COM interop base class that do not need a real COM object."""

from __future__ import annotations

import ctypes

import pytest

from kinect_next.core.exceptions import COMOperationError, KinectError
from kinect_next.native.com_base import COMBase

E_PENDING = -2147483638  # 0x8000000A -- "data not yet available"


def test_null_wrapper_is_invalid() -> None:
    for raw in (None, 0):
        obj = COMBase(raw, owned=False)
        assert obj.is_valid is False
        assert obj.add_ref() == 0
        assert obj.release() == 0


def test_calling_a_method_on_null_raises() -> None:
    obj = COMBase(None, owned=False)
    with pytest.raises(COMOperationError):
        obj._call_method(3, [])


def test_com_operation_error_formats_hresult() -> None:
    err = COMOperationError("boom", hresult=-2147024809)
    assert "0x80070057" in str(err)
    assert err.hresult == -2147024809
    assert isinstance(err, KinectError)


def test_com_operation_error_without_hresult() -> None:
    err = COMOperationError("plain message")
    assert str(err) == "plain message"
    assert err.hresult is None


def test_ctypes_oserror_is_normalised_to_com_operation_error() -> None:
    """ctypes raises OSError directly for failure HRESULTs (e.g. E_PENDING).

    ``_call_method`` must translate that into a ``COMOperationError`` so callers
    such as ``IAudioBeamFrameReader.acquire_latest_beam_frames`` can swallow the
    "frame not ready yet" case with a single ``except COMOperationError``.
    """
    obj = COMBase(0x1000, owned=False)  # non-NULL: passes the is_valid guard

    def _raise_pending(*_args: object) -> object:
        exc = OSError("not yet available")
        exc.winerror = E_PENDING  # type: ignore[attr-defined]
        raise exc

    obj._thunks[(6, ctypes.HRESULT, ())] = _raise_pending

    with pytest.raises(COMOperationError) as excinfo:
        obj._call_method(6, [], ctypes.HRESULT)
    assert excinfo.value.hresult == E_PENDING
    assert "0x8000000A" in str(excinfo.value)
