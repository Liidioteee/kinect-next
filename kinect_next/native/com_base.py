"""Minimal, fast COM interop base class with deterministic ``IUnknown`` cleanup.

``COMBase`` dispatches directly against the object's VTable, which avoids the
overhead (and TLB generation) of ``comtypes``. Interfaces declare their VTable
layout *by method name* in ``_vtable_`` -- in the exact order of the SDK header --
and call methods by that name, so a slot index is never written by hand.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_ulong, c_void_p
from types import TracebackType
from typing import Any, ClassVar, TypeVar

from typing_extensions import Self

from kinect_next.core.exceptions import COMOperationError

# ``HRESULT`` / ``WINFUNCTYPE`` only exist on Windows. Fall back to portable
# equivalents so that ``import kinect_next`` works everywhere (docs builds, type
# checking, CI); nothing here is ever *called* without the Kinect runtime.
HRESULT: Any = getattr(ctypes, "HRESULT", ctypes.c_long)
_FUNCTYPE: Any = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
# Same ABI (x64 Windows has a single calling convention), but the interpreter
# lock stays held for the duration of the call. See ``COMBase._hold_gil_``.
_GIL_HELD_FUNCTYPE: Any = ctypes.PYFUNCTYPE

_IUNKNOWN: tuple[str, ...] = ("QueryInterface", "AddRef", "Release")
_ADD_REF = 1
_RELEASE = 2

_PPVOID = POINTER(POINTER(c_void_p))
# ``AddRef`` / ``Release`` share one signature; build the prototypes once.
_IUNKNOWN_PROTO = _FUNCTYPE(c_ulong, c_void_p)
_IUNKNOWN_GIL_HELD_PROTO = _GIL_HELD_FUNCTYPE(c_ulong, c_void_p)

_T = TypeVar("_T")
_I = TypeVar("_I", bound="COMBase")


class COMBase:
    """Wrapper around a raw ``IUnknown*`` pointer.

    The wrapper owns the reference by default and calls ``IUnknown::Release`` when
    it is closed, leaves a ``with`` block or is garbage-collected. Pass
    ``owned=False`` for borrowed pointers whose lifetime is managed elsewhere.

    Subclasses list the interface's own methods (everything after ``IUnknown``)
    in ``_vtable_``, in header order.
    """

    __slots__ = ("_owned", "_ptr", "_thunks")

    #: Methods of the interface after ``IUnknown``, in SDK header order.
    _vtable_: ClassVar[tuple[str, ...]] = ()
    #: Keep the GIL while calling into this interface.
    #:
    #: ``ctypes`` normally releases the GIL around every foreign call. That is
    #: right for calls that block or copy megabytes, but for an object whose
    #: methods are all sub-microsecond getters it means re-queueing for the GIL
    #: dozens of times per frame -- under load each round trip can cost a full
    #: switch interval (5 ms). The audio capture path must finish a read within
    #: one 16 ms sub-frame or the audio is gone, so its interfaces set this.
    _hold_gil_: ClassVar[bool] = False
    #: ``method name -> VTable slot``, derived from ``_vtable_``.
    _slots_: ClassVar[dict[str, int]] = {name: i for i, name in enumerate(_IUNKNOWN)}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        names = _IUNKNOWN + tuple(cls._vtable_)
        if len(set(names)) != len(names):
            raise TypeError(f"{cls.__name__}._vtable_ contains duplicate method names")
        cls._slots_ = {name: i for i, name in enumerate(names)}

    def __init__(self, raw_ptr: c_void_p | int | None, owned: bool = True) -> None:
        if isinstance(raw_ptr, c_void_p):
            raw_ptr = raw_ptr.value
        self._ptr: int = raw_ptr or 0
        self._owned = owned
        self._thunks: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Pointer introspection
    # ------------------------------------------------------------------
    @property
    def ptr(self) -> int:
        """The underlying raw pointer as an integer address (``0`` once released)."""
        return self._ptr

    @property
    def is_valid(self) -> bool:
        """``True`` while the wrapper holds a non-NULL pointer."""
        return self._ptr != 0

    def __bool__(self) -> bool:
        return self._ptr != 0

    def __repr__(self) -> str:
        return f"<{type(self).__name__} at 0x{self._ptr:X}>"

    # ------------------------------------------------------------------
    # IUnknown
    # ------------------------------------------------------------------
    def _method_address(self, slot: int) -> int:
        vtable = ctypes.cast(self._ptr, _PPVOID).contents
        return int(vtable[slot] or 0)

    def add_ref(self) -> int:
        """Call ``IUnknown::AddRef`` and return the new reference count."""
        if not self._ptr:
            return 0
        proto = _IUNKNOWN_GIL_HELD_PROTO if self._hold_gil_ else _IUNKNOWN_PROTO
        return int(proto(self._method_address(_ADD_REF))(self._ptr))

    def release(self) -> int:
        """Call ``IUnknown::Release``, NULL the pointer, and return the count.

        Safe to call more than once; later calls are no-ops.
        """
        if not self._ptr:
            return 0
        ptr, self._ptr = self._ptr, 0
        self._thunks.clear()
        proto = _IUNKNOWN_GIL_HELD_PROTO if self._hold_gil_ else _IUNKNOWN_PROTO
        return int(proto(ctypes.cast(ptr, _PPVOID).contents[_RELEASE])(ptr))

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()

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
    def _call(self, method: str, argtypes: tuple[Any, ...], *args: Any) -> None:
        """Invoke the ``HRESULT``-returning VTable method ``method`` with ``args``.

        The compiled thunk is cached per instance, so repeated calls on long-lived
        objects (sensor, readers, mapper) skip all prototype construction.

        Raises
        ------
        COMOperationError
            If the pointer is NULL or the method returns a failure ``HRESULT``.
        """
        name = f"{type(self).__name__}::{method}"
        if not self._ptr:
            raise COMOperationError(f"{name} called on a released or NULL COM object.")

        func = self._thunks.get(method)
        if func is None:
            functype = _GIL_HELD_FUNCTYPE if self._hold_gil_ else _FUNCTYPE
            proto = functype(HRESULT, c_void_p, *argtypes)
            func = proto(self._method_address(self._slots_[method]))
            self._thunks[method] = func

        try:
            hr = func(self._ptr, *args)
        except OSError as exc:
            # ctypes raises OSError directly for failure HRESULTs (e.g. E_PENDING
            # when a frame is not ready yet). Normalise it so callers only ever
            # see COMOperationError.
            code = getattr(exc, "winerror", None)
            if code is None:
                code = exc.errno
            raise COMOperationError(f"{name} failed", code) from exc
        if hr is not None and hr < 0:
            raise COMOperationError(f"{name} failed", hr)

    # -- typed out-parameter helpers -----------------------------------
    def _get_int(self, method: str, ctype: Any) -> int:
        out = ctype()
        self._call(method, (POINTER(ctype),), byref(out))
        return int(out.value)

    def _get_float(self, method: str) -> float:
        out = ctypes.c_float()
        self._call(method, (POINTER(ctypes.c_float),), byref(out))
        return float(out.value)

    def _get_bool(self, method: str) -> bool:
        # The SDK's BOOLEAN is one byte.
        out = ctypes.c_ubyte()
        self._call(method, (POINTER(ctypes.c_ubyte),), byref(out))
        return out.value != 0

    def _get_struct(self, method: str, struct_type: type[_T]) -> _T:
        out = struct_type()
        self._call(method, (POINTER(struct_type),), byref(out))  # type: ignore[arg-type]
        return out

    def _get_interface(
        self, method: str, interface: type[_I], argtypes: tuple[Any, ...] = (), *args: Any
    ) -> _I:
        """Call a method whose last parameter is an interface out-pointer."""
        out = c_void_p()
        self._call(method, (*argtypes, POINTER(c_void_p)), *args, byref(out))
        if not out.value:
            raise COMOperationError(f"{type(self).__name__}::{method} returned a NULL interface pointer.")
        return interface(out.value)

    def _try_get_interface(
        self, method: str, interface: type[_I], argtypes: tuple[Any, ...] = (), *args: Any
    ) -> _I | None:
        """Like :meth:`_get_interface`, but return ``None`` when nothing is available.

        Used for the "acquire" family, where a failure ``HRESULT`` (``E_PENDING``,
        an expired frame reference) simply means "no data this time".
        """
        try:
            return self._get_interface(method, interface, argtypes, *args)
        except COMOperationError:
            return None
