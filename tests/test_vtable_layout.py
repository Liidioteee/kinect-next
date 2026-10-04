"""The COM VTable layouts must match the Kinect SDK header exactly.

A wrong slot does not fail loudly -- it calls a *different* native method with
the wrong arguments -- so the layouts are pinned three ways:

* every ``_vtable_`` equals the checked-in snapshot of ``Kinect.h``;
* the snapshot equals the real header whenever the SDK is installed;
* every Python method dispatches to the header method it claims to wrap
  (see ``test_interfaces.py``).
"""

from __future__ import annotations

import pytest

from kinect_next.native.com_base import COMBase
from tests.kinect_header import find_header, load_snapshot, parse_vtable, wrapped_interfaces

_INTERFACES = wrapped_interfaces()
_SNAPSHOT = load_snapshot()


def test_every_wrapped_interface_is_in_the_snapshot() -> None:
    assert sorted(_INTERFACES) == sorted(_SNAPSHOT)


@pytest.mark.parametrize("name", sorted(_INTERFACES))
def test_vtable_matches_header_snapshot(name: str) -> None:
    assert list(_INTERFACES[name]._vtable_) == _SNAPSHOT[name]


@pytest.mark.parametrize("name", sorted(_INTERFACES))
def test_slots_follow_iunknown(name: str) -> None:
    cls = _INTERFACES[name]
    assert cls._slots_["QueryInterface"] == 0
    assert cls._slots_["AddRef"] == 1
    assert cls._slots_["Release"] == 2
    for offset, method in enumerate(cls._vtable_):
        assert cls._slots_[method] == 3 + offset


def test_snapshot_matches_the_installed_sdk_header() -> None:
    header = find_header()
    if header is None:
        pytest.skip("Kinect for Windows SDK 2.0 (Kinect.h) is not installed")
    text = header.read_text(encoding="latin-1")
    for name, expected in _SNAPSHOT.items():
        assert parse_vtable(text, name) == expected, f"{name} drifted from {header}"


def test_duplicate_vtable_entries_are_rejected() -> None:
    with pytest.raises(TypeError, match="duplicate"):

        class _Broken(COMBase):
            _vtable_ = ("Foo", "Foo")
