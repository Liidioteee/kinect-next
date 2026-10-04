"""A real in-process COM-style object for exercising the VTable dispatcher.

``FakeCOMObject`` builds a genuine VTable out of ``ctypes`` callbacks, so
``COMBase`` talks to it exactly as it talks to ``Kinect20.dll`` -- through raw
function pointers. Every slot records that it was called; individual slots can be
given a handler that writes out-parameters or returns a failure ``HRESULT``.

Slot callbacks take ``this`` plus three pointer-sized arguments. On x64 Windows
those are exactly the register-passed arguments, so one prototype safely serves
methods of any arity (the caller owns the stack).
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import c_long, c_ulong, c_void_p

S_OK = 0
E_PENDING = -2147483638  # 0x8000000A
E_FAIL = -2147467259  # 0x80004005

Handler = Callable[[int, int, int], int]

_SLOT_PROTO = ctypes.WINFUNCTYPE(c_long, c_void_p, c_void_p, c_void_p, c_void_p)
_REFCOUNT_PROTO = ctypes.WINFUNCTYPE(c_ulong, c_void_p)


class FakeCOMObject:
    """An object whose VTable slots are Python callbacks."""

    def __init__(self, slots: int = 32) -> None:
        self.calls: list[int] = []
        self.refcount = 1
        self.handlers: dict[int, Handler] = {}

        callbacks: list[object] = [
            _SLOT_PROTO(self._make_slot(0)),
            _REFCOUNT_PROTO(self._add_ref),
            _REFCOUNT_PROTO(self._release),
        ]
        callbacks += [_SLOT_PROTO(self._make_slot(i)) for i in range(3, slots)]
        self._callbacks = callbacks  # keep the thunks alive
        self._vtable = (c_void_p * slots)(*(ctypes.cast(cb, c_void_p) for cb in callbacks))  # type: ignore[arg-type]
        self._object = c_void_p(ctypes.addressof(self._vtable))
        self.address = ctypes.addressof(self._object)

    def _make_slot(self, index: int) -> Callable[[int, int, int, int], int]:
        def slot(_this: int, a1: int, a2: int, a3: int) -> int:
            self.calls.append(index)
            handler = self.handlers.get(index)
            return handler(a1 or 0, a2 or 0, a3 or 0) if handler else S_OK

        return slot

    def _add_ref(self, _this: int) -> int:
        self.refcount += 1
        return self.refcount

    def _release(self, _this: int) -> int:
        self.refcount -= 1
        return self.refcount

    def on(self, slot: int, handler: Handler) -> None:
        """Install ``handler(a1, a2, a3) -> HRESULT`` for VTable slot ``slot``."""
        self.handlers[slot] = handler


def write(address: int, value: object) -> None:
    """Store a ctypes ``value`` at ``address`` (an out-parameter)."""
    ctypes.memmove(address, ctypes.byref(value), ctypes.sizeof(value))  # type: ignore[arg-type]
