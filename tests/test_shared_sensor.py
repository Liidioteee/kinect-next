"""The process-wide shared IKinectSensor is reference-counted (no hardware)."""

from __future__ import annotations

import pytest

import kinect_next.core.sensor as sensor_mod


class _FakeNative:
    opens = 0
    closes = 0
    releases = 0

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def open(self) -> None:
        type(self).opens += 1

    def close(self) -> None:
        type(self).closes += 1

    def release(self) -> int:
        type(self).releases += 1
        return 0


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeNative.opens = _FakeNative.closes = _FakeNative.releases = 0
    monkeypatch.setattr(sensor_mod, "get_default_kinect_sensor", lambda: 0x1000)
    monkeypatch.setattr(sensor_mod, "IKinectSensorNative", _FakeNative)
    monkeypatch.setattr(sensor_mod, "_shared_sensor", None)
    monkeypatch.setattr(sensor_mod, "_shared_refcount", 0)


def test_shared_sensor_is_opened_once_and_closed_last() -> None:
    a = sensor_mod._acquire_shared_sensor()
    b = sensor_mod._acquire_shared_sensor()
    assert a is b
    assert _FakeNative.opens == 1

    sensor_mod._release_shared_sensor()
    assert _FakeNative.closes == 0  # still one holder

    sensor_mod._release_shared_sensor()
    assert _FakeNative.closes == 1
    assert _FakeNative.releases == 1


def test_reacquire_after_full_release_reopens() -> None:
    sensor_mod._acquire_shared_sensor()
    sensor_mod._release_shared_sensor()
    sensor_mod._acquire_shared_sensor()
    assert _FakeNative.opens == 2


def test_extra_release_is_a_no_op() -> None:
    sensor_mod._release_shared_sensor()
    sensor_mod._release_shared_sensor()
    assert _FakeNative.closes == 0
