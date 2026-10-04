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
    assert issubclass(kinect_next.KinectClosedError, kinect_next.KinectError)
    assert hasattr(KinectSensor, "wait_for_audio_frame")
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


def test_every_library_exception_derives_from_kinect_error() -> None:
    from kinect_next.core import exceptions
    from kinect_next.core._cancel import WaitCancelledError

    errors = [
        obj for obj in vars(exceptions).values() if isinstance(obj, type) and issubclass(obj, Exception)
    ]
    assert len(errors) >= 7
    assert all(issubclass(err, kinect_next.KinectError) for err in [*errors, WaitCancelledError])


def test_native_layer_exports_are_importable() -> None:
    import kinect_next.native as native

    for name in native.__all__:
        assert hasattr(native, name), f"{name} listed in kinect_next.native.__all__ but missing"
    assert len(native.__all__) == len(set(native.__all__))


def test_default_timeout_covers_sensor_start_up() -> None:
    """A cold sensor needs 1-3 s before its first frame; the default must exceed that."""
    import inspect

    from kinect_next import AsyncKinectSensor, KinectSensor
    from kinect_next.core.sensor import DEFAULT_TIMEOUT_MS

    assert DEFAULT_TIMEOUT_MS >= 3000
    for cls, names in (
        (KinectSensor, ("wait_for_frames", "wait_for_audio_frame", "poll_frames", "poll_audio")),
        (AsyncKinectSensor, ("wait_for_frames", "wait_for_audio_frame", "stream", "audio_stream")),
    ):
        for name in names:
            default = inspect.signature(getattr(cls, name)).parameters["timeout_ms"].default
            assert default == DEFAULT_TIMEOUT_MS, f"{cls.__name__}.{name}"
