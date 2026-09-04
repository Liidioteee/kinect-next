"""Minimal, fast COM interop base class with deterministic ``IUnknown`` cleanup.

``COMBase`` dispatches directly against the object's VTable by slot index, which
avoids the overhead (and TLB generation) of ``comtypes``. Per-instance thunk
caching keeps repeated calls on the frame hot path allocation-free.
"""

from __future__ import annotations

import ctypes
from ctypes import HRESULT, c_ulong, c_void_p
from typing import Any

from kinect_next.core.exceptions import COMOperationError

# ``IUnknown`` VTable layout.
_QUERY_INTERFACE = 0
_ADD_REF = 1
_RELEASE = 2

_PPVOID = ctypes.POINTER(ctypes.POINTER(c_void_p))
# ``AddRef`` / ``Release`` share one signature; build the prototype once.
_IUNKNOWN_PROTO = ctypes.WINFUNCTYPE(c_ulong, c_void_p) if hasattr(ctypes, "WINFUNCTYPE") else None

_ThunkKey = tuple[int, Any, tuple[Any, ...]]


class COMBase:
    """Wrapper around a raw ``IUnknown*`` pointer.

    The wrapper owns the reference by default and calls ``IUnknown::Release`` when
    it is garbage-collected. Pass ``owned=False`` for borrowed pointers whose
    lifetime is managed elsewhere.
    """

    __slots__ = ("_owned", "_ptr", "_thunks", "_vtable")

    def __init__(self, raw_ptr: c_void_p | int | None, owned: bool = True) -> None:
        if isinstance(raw_ptr, int):
            self._ptr: c_void_p = c_void_p(raw_ptr)
        elif raw_ptr is None:
            self._ptr = c_void_p(None)
        else:
            self._ptr = raw_ptr
        self._owned = owned
        self._vtable: Any = None
        self._thunks: dict[_ThunkKey, Any] = {}

    # ------------------------------------------------------------------
    # Pointer introspection
    # ------------------------------------------------------------------
    @property
    def ptr(self) -> c_void_p:
        """The underlying raw pointer."""
        return self._ptr

    @property
    def is_valid(self) -> bool:
        """``True`` while the wrapper holds a non-NULL pointer."""
        return bool(self._ptr) and bool(self._ptr.value)

    # ------------------------------------------------------------------
    # IUnknown
    # ------------------------------------------------------------------
    def _get_vtable(self) -> Any:
        vt = self._vtable
        if vt is None:
            vt = ctypes.cast(self._ptr, _PPVOID).contents
            self._vtable = vt
        return vt

    def add_ref(self) -> int:
        """Call ``IUnknown::AddRef`` and return the new reference count."""
        if not self.is_valid or _IUNKNOWN_PROTO is None:
            return 0
        return int(_IUNKNOWN_PROTO(self._get_vtable()[_ADD_REF])(self._ptr))

    def release(self) -> int:
        """Call ``IUnknown::Release``, NULL the pointer, and return the count."""
        if self.is_valid and _IUNKNOWN_PROTO is not None:
            count = int(_IUNKNOWN_PROTO(self._get_vtable()[_RELEASE])(self._ptr))
            self._ptr = c_void_p(None)
            self._vtable = None
            self._thunks.clear()
            return count
        return 0

    def __del__(self) -> None:
        # Never raise from a finaliser (interpreter shutdown, partial init, ...).
        try:
            if self._owned:
                self.release()
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------
    # VTable dispatch
    # ------------------------------------------------------------------
    def _call_method(
        self,
        index: int,
        argtypes: list[Any],
        restype: Any = HRESULT,
        *args: Any,
    ) -> Any:
        """Invoke the VTable slot ``index`` with ``args``.

        The compiled thunk is cached per instance and per signature; subsequent
        calls skip all ``ctypes`` prototype construction.
        """
        if not self.is_valid:
            raise COMOperationError(
                "Attempted to call a method on an uninitialised COM object (NULL pointer)."
            )

        key: _ThunkKey = (index, restype, tuple(argtypes))
        func = self._thunks.get(key)
        if func is None:
            proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
            func = proto(self._get_vtable()[index])
            self._thunks[key] = func

        try:
            hr = func(self._ptr, *args)
        except OSError as exc:
            # ctypes raises OSError directly for failure HRESULTs when
            # ``restype is ctypes.HRESULT`` (e.g. E_PENDING when a frame is not
            # ready yet). Normalise it so callers only ever see COMOperationError.
            code = getattr(exc, "winerror", None)
            if code is None:
                code = exc.errno
            raise COMOperationError(f"COM method (VTable slot {index}) failed", code) from exc
        if restype is HRESULT and hr is not None and hr < 0:
            raise COMOperationError(f"COM method (VTable slot {index}) failed", hr)
        return hr
