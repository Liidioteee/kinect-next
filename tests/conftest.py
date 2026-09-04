"""Shared pytest configuration.

Hardware tests (``@pytest.mark.hardware``) are skipped unless ``--run-hardware``
is passed, so the default suite runs anywhere without a Kinect v2 attached.
"""

from __future__ import annotations

import pytest


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
