"""Shared pytest configuration and fixtures.

Hardware tests (``@pytest.mark.hardware``) are skipped unless ``--run-hardware``
is passed, so the default suite runs anywhere without a Kinect v2 attached.
Everything else drives :class:`KinectSensor` through the fakes in ``fakes.py``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
import pytest

import kinect_next.core.sensor as sensor_mod
from kinect_next import KinectSensor, StreamType
from tests.fakes import (
    FakeBody,
    FakeBodyFrame,
    FakeColorFrame,
    FakeColorSettings,
    FakeMultiFrame,
    FakePlanarFrame,
    FakeSensorNative,
)

VIDEO_STREAMS = (
    StreamType.COLOR
    | StreamType.DEPTH
    | StreamType.INFRARED
    | StreamType.LONG_EXPOSURE_INFRARED
    | StreamType.BODY_INDEX
    | StreamType.BODY
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="run tests that require a physically connected Kinect v2 sensor",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-hardware"):
        return
    skip = pytest.mark.skip(reason="needs a Kinect v2; pass --run-hardware to enable")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)


def wait_until(predicate: Callable[[], object], timeout: float = 2.0, what: str = "condition") -> None:
    """Poll ``predicate`` until it is truthy; fail the test after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        time.sleep(0.002)


def make_multi_frame(tick: int = 1, **overrides: Any) -> FakeMultiFrame:
    """A fully populated multi-source frame whose pixels encode ``tick``.

    Pass e.g. ``color=None`` to simulate a stream with no data for this tick.
    """
    frames: dict[str, Any] = {
        "color": FakeColorFrame(
            np.full((1080, 1920, 4), tick % 251, dtype=np.uint8),
            ticks=tick * 10 + 6,
            settings=FakeColorSettings(),
        ),
        "depth": FakePlanarFrame(np.full((424, 512), 1000 + tick, dtype=np.uint16), ticks=tick * 10),
        "infrared": FakePlanarFrame(np.full((424, 512), 2000 + tick, dtype=np.uint16), ticks=tick * 10 + 1),
        "long_exposure_infrared": FakePlanarFrame(
            np.full((424, 512), 3000 + tick, dtype=np.uint16), ticks=tick * 10 + 2
        ),
        "body_index": FakePlanarFrame(np.full((424, 512), 255, dtype=np.uint8), ticks=tick * 10 + 3),
        "body": FakeBodyFrame(
            [FakeBody(tracked=True, tracking_id=77), FakeBody(tracked=False)], ticks=tick * 10 + 4
        ),
    }
    frames.update(overrides)
    return FakeMultiFrame(**frames)


@pytest.fixture
def native(monkeypatch: pytest.MonkeyPatch) -> FakeSensorNative:
    """Replace the process-wide native sensor with a :class:`FakeSensorNative`."""
    fake = FakeSensorNative()
    monkeypatch.setattr(sensor_mod, "get_default_kinect_sensor", lambda: 0x1000)
    monkeypatch.setattr(sensor_mod, "IKinectSensorNative", lambda _ptr: fake)
    monkeypatch.setattr(sensor_mod, "_shared_sensor", None)
    monkeypatch.setattr(sensor_mod, "_shared_refcount", 0)
    return fake


@pytest.fixture
def make_sensor(native: FakeSensorNative) -> Iterator[Callable[..., KinectSensor]]:
    """Factory for sensors backed by the fake; everything is closed at teardown."""
    created: list[KinectSensor] = []

    def factory(streams: StreamType = StreamType.DEPTH, **kwargs: Any) -> KinectSensor:
        sensor = KinectSensor(streams, **kwargs)
        created.append(sensor)
        return sensor

    yield factory
    for sensor in created:
        sensor.close()
