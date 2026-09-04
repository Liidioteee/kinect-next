"""Smoke tests for the public API surface. These require no Kinect hardware."""

from __future__ import annotations

import importlib

import kinect_next


def test_version_is_a_string() -> None:
    assert isinstance(kinect_next.__version__, str)
    assert kinect_next.__version__.count(".") >= 2


def test_version_matches_package_metadata() -> None:
    meta = importlib.metadata.version("kinect-next")
    assert meta == kinect_next.__version__


def test_all_names_are_importable() -> None:
    for name in kinect_next.__all__:
        assert hasattr(kinect_next, name), f"{name} listed in __all__ but missing"


def test_all_has_no_duplicates() -> None:
    assert len(kinect_next.__all__) == len(set(kinect_next.__all__))


def test_all_covers_every_public_name() -> None:
    exported = set(kinect_next.__all__)
    public = {
        name
        for name in vars(kinect_next)
        if not name.startswith("_")
        and name not in {"aio", "core", "models", "native", "utils", "annotations"}
    }
    assert public <= exported


def test_key_symbols_present() -> None:
    from kinect_next import (
        AsyncKinectSensor,
        COMOperationError,
        KinectSensor,
        StreamType,
    )

    assert issubclass(COMOperationError, kinect_next.KinectError)
    assert hasattr(KinectSensor, "wait_for_frames")
    assert hasattr(AsyncKinectSensor, "stream")
    assert StreamType.COLOR in StreamType.ALL


def test_importing_does_not_load_the_kinect_dll() -> None:
    # Run in a pristine interpreter: opening a sensor elsewhere in this test
    # session would otherwise have loaded the DLL already.
    import subprocess
    import sys

    code = (
        "import kinect_next, kinect_next.native.win32 as w;"
        "assert w._kinect20 is None, 'Kinect20.dll loaded at import time'"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
