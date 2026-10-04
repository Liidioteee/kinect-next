"""Tests for the COM interop base class against a real in-process VTable."""

from __future__ import annotations

import ctypes
import gc
from ctypes import c_float, c_int, c_ubyte, c_void_p

import pytest

from kinect_next.core.exceptions import COMOperationError, KinectError
from kinect_next.native.com_base import HRESULT, COMBase
from kinect_next.native.types import Vector4Native
from tests.fake_com import E_FAIL, E_PENDING, FakeCOMObject, write


class _Demo(COMBase):
    _vtable_ = ("First", "Second", "Third")


# ---------------------------------------------------------------------------
# NULL handling and error formatting
# ---------------------------------------------------------------------------
def test_null_wrapper_is_invalid() -> None:
    for raw in (None, 0, c_void_p(None)):
        obj = COMBase(raw, owned=False)
        assert obj.is_valid is False
        assert not obj
        assert obj.ptr == 0
        assert obj.add_ref() == 0
        assert obj.release() == 0


def test_calling_a_method_on_null_raises() -> None:
    obj = _Demo(None)
    with pytest.raises(COMOperationError, match="_Demo::First"):
        obj._call("First", ())


def test_com_operation_error_formats_hresult() -> None:
    err = COMOperationError("boom", hresult=-2147024809)
    assert "0x80070057" in str(err)
    assert err.hresult == -2147024809
    assert isinstance(err, KinectError)


def test_com_operation_error_without_hresult() -> None:
    err = COMOperationError("plain message")
    assert str(err) == "plain message"
    assert err.hresult is None


def test_hresult_is_the_windows_type() -> None:
    assert HRESULT is ctypes.HRESULT


# ---------------------------------------------------------------------------
# VTable layout
# ---------------------------------------------------------------------------
def test_slots_are_derived_from_the_vtable_order() -> None:
    assert _Demo._slots_ == {
        "QueryInterface": 0,
        "AddRef": 1,
        "Release": 2,
        "First": 3,
        "Second": 4,
        "Third": 5,
    }


def test_call_dispatches_to_the_named_slot() -> None:
    fake = FakeCOMObject()
    obj = _Demo(fake.address, owned=False)
    obj._call("Third", ())
    obj._call("First", ())
    assert fake.calls == [5, 3]


def test_unknown_method_name_is_a_programming_error() -> None:
    obj = _Demo(FakeCOMObject().address, owned=False)
    with pytest.raises(KeyError):
        obj._call("Nope", ())


def test_thunks_are_cached_per_instance() -> None:
    fake = FakeCOMObject()
    obj = _Demo(fake.address, owned=False)
    obj._call("First", ())
    thunk = obj._thunks["First"]
    obj._call("First", ())
    assert obj._thunks["First"] is thunk


def test_arguments_reach_the_native_method() -> None:
    fake = FakeCOMObject()
    seen: list[tuple[int, int, int]] = []
    fake.on(4, lambda a1, a2, a3: seen.append((a1, a2, a3)) or 0)
    _Demo(fake.address, owned=False)._call("Second", (c_int, c_int, c_int), 7, 8, 9)
    assert seen == [(7, 8, 9)]


# ---------------------------------------------------------------------------
# Failure HRESULTs
# ---------------------------------------------------------------------------
def test_failure_hresult_becomes_com_operation_error() -> None:
    fake = FakeCOMObject()
    fake.on(3, lambda *_: E_PENDING)
    obj = _Demo(fake.address, owned=False)
    with pytest.raises(COMOperationError) as excinfo:
        obj._call("First", ())
    assert excinfo.value.hresult == E_PENDING
    assert "0x8000000A" in str(excinfo.value)
    assert "_Demo::First" in str(excinfo.value)


def test_non_hresult_return_type_still_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """On the portable fallback (plain ``c_long``) the sign check does the work."""
    import kinect_next.native.com_base as com_base

    monkeypatch.setattr(com_base, "HRESULT", ctypes.c_long)
    fake = FakeCOMObject()
    fake.on(3, lambda *_: E_FAIL)
    obj = _Demo(fake.address, owned=False)
    with pytest.raises(COMOperationError) as excinfo:
        obj._call("First", ())
    assert excinfo.value.hresult == E_FAIL


# ---------------------------------------------------------------------------
# Out-parameter helpers
# ---------------------------------------------------------------------------
def test_get_int_float_bool() -> None:
    fake = FakeCOMObject()
    fake.on(3, lambda a1, *_: write(a1, c_int(-42)) or 0)
    fake.on(4, lambda a1, *_: write(a1, c_float(1.5)) or 0)
    fake.on(5, lambda a1, *_: write(a1, c_ubyte(1)) or 0)
    obj = _Demo(fake.address, owned=False)
    assert obj._get_int("First", c_int) == -42
    assert obj._get_float("Second") == 1.5
    assert obj._get_bool("Third") is True


def test_get_bool_only_touches_one_byte() -> None:
    """``BOOLEAN`` is one byte; the helper must not hand out a wider buffer."""
    fake = FakeCOMObject()
    fake.on(3, lambda a1, *_: write(a1, c_ubyte(0)) or 0)
    assert _Demo(fake.address, owned=False)._get_bool("First") is False


def test_get_struct() -> None:
    fake = FakeCOMObject()
    fake.on(3, lambda a1, *_: write(a1, Vector4Native(1.0, 2.0, 3.0, 4.0)) or 0)
    vec = _Demo(fake.address, owned=False)._get_struct("First", Vector4Native)
    assert (vec.x, vec.y, vec.z, vec.w) == (1.0, 2.0, 3.0, 4.0)


def test_get_interface_wraps_and_owns_the_returned_pointer() -> None:
    fake, child = FakeCOMObject(), FakeCOMObject()
    fake.on(3, lambda a1, *_: write(a1, c_void_p(child.address)) or 0)
    wrapped = _Demo(fake.address, owned=False)._get_interface("First", _Demo)
    assert wrapped.ptr == child.address
    assert child.refcount == 1
    wrapped.release()
    assert child.refcount == 0


def test_get_interface_passes_leading_arguments() -> None:
    fake, child = FakeCOMObject(), FakeCOMObject()
    seen: list[int] = []

    def handler(index: int, out: int, _a3: int) -> int:
        seen.append(index)
        write(out, c_void_p(child.address))
        return 0

    fake.on(3, handler)
    wrapped = _Demo(fake.address, owned=False)._get_interface("First", _Demo, (ctypes.c_uint,), 5)
    assert seen == [5]
    assert wrapped.ptr == child.address
    wrapped.release()


def test_get_interface_rejects_a_null_result() -> None:
    obj = _Demo(FakeCOMObject().address, owned=False)
    with pytest.raises(COMOperationError, match="NULL interface pointer"):
        obj._get_interface("First", _Demo)


def test_try_get_interface_returns_none_when_nothing_is_available() -> None:
    fake = FakeCOMObject()
    obj = _Demo(fake.address, owned=False)
    assert obj._try_get_interface("First", _Demo) is None  # NULL out-pointer
    fake.on(3, lambda *_: E_PENDING)
    assert obj._try_get_interface("First", _Demo) is None  # failure HRESULT


# ---------------------------------------------------------------------------
# Reference counting
# ---------------------------------------------------------------------------
def test_add_ref_and_release_reach_iunknown() -> None:
    fake = FakeCOMObject()
    obj = COMBase(fake.address)
    assert obj.add_ref() == 2
    assert obj.release() == 1
    assert fake.refcount == 1
    assert not obj.is_valid


def test_release_is_idempotent() -> None:
    fake = FakeCOMObject()
    obj = COMBase(fake.address)
    obj.release()
    assert obj.release() == 0
    assert fake.refcount == 0


def test_context_manager_releases() -> None:
    fake = FakeCOMObject()
    with COMBase(fake.address) as obj:
        assert obj.is_valid
    assert fake.refcount == 0
    assert not obj.is_valid


def test_owned_wrapper_releases_on_garbage_collection() -> None:
    fake = FakeCOMObject()
    obj = COMBase(fake.address)
    del obj
    gc.collect()
    assert fake.refcount == 0


def test_borrowed_wrapper_does_not_release_on_garbage_collection() -> None:
    fake = FakeCOMObject()
    obj = COMBase(fake.address, owned=False)
    del obj
    gc.collect()
    assert fake.refcount == 1


def test_calls_after_release_raise_instead_of_crashing() -> None:
    fake = FakeCOMObject()
    obj = _Demo(fake.address)
    obj.release()
    with pytest.raises(COMOperationError, match="released or NULL"):
        obj._call("First", ())


def test_repr_shows_type_and_address() -> None:
    fake = FakeCOMObject()
    assert repr(_Demo(fake.address, owned=False)) == f"<_Demo at 0x{fake.address:X}>"


def test_an_oserror_without_a_windows_code_falls_back_to_errno() -> None:
    obj = _Demo(FakeCOMObject().address, owned=False)

    def raise_plain(*_args: object) -> None:
        raise OSError(22, "invalid argument")

    obj._thunks["First"] = raise_plain
    with pytest.raises(COMOperationError) as excinfo:
        obj._call("First", ())
    assert excinfo.value.hresult == 22


def test_gil_holding_interfaces_dispatch_and_release_correctly() -> None:
    """``_hold_gil_`` only changes whether the GIL is released around the call."""

    class _Hot(_Demo):
        _hold_gil_ = True

    fake = FakeCOMObject()
    fake.on(3, lambda a1, *_: write(a1, c_int(7)) or 0)
    fake.on(4, lambda *_: E_PENDING)
    obj = _Hot(fake.address)
    assert obj._get_int("First", c_int) == 7
    with pytest.raises(COMOperationError) as excinfo:
        obj._call("Second", ())
    assert excinfo.value.hresult == E_PENDING
    assert obj.add_ref() == 2
    assert obj.release() == 1
