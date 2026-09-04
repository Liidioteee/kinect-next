# Changelog

All notable changes to **kinect-next** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-09-03

First fully production-hardened release. This version contains breaking changes
relative to the unreleased `1.x` line, hence the major version bump.

### Added

- `kinect_next.AsyncKinectSensor` is now re-exported from the top-level package.
- `COMOperationError` is now part of the public top-level API.
- `KinectSensor(..., reuse_buffers=False)` opt-in flag that reuses internal
  NumPy frame buffers across `wait_for_frames()` calls to eliminate per-frame
  allocation churn in real-time loops.
- `KinectSensor.streams` read-only property exposing the configured
  `StreamType` mask.
- `save_point_cloud_ply(..., binary=False)` option to write a compact
  binary-little-endian PLY; the ASCII writer is now fully vectorized.
- Package metadata: `project.urls`, SPDX license classifier, `dev` extra,
  single-sourced version, `ruff`/`mypy`/`pytest` configuration.
- `LICENSE`, `CHANGELOG.md`, `MANIFEST.in`, `.gitignore`, `tests/` suite and a
  GitHub Actions CI workflow.
- Hardware integration suite (`tests/test_hardware.py`), opt-in via
  `pytest --run-hardware`; skipped by default so the normal suite needs no sensor.
- English `README.md`; the Russian manual is preserved as `README.ru.md`.

### Changed

- **BREAKING:** `import kinect_next` no longer fails on a Windows machine that
  does not have the Kinect for Windows SDK installed. `Kinect20.dll` is now
  loaded lazily on the first `KinectSensor.open()`; a missing DLL raises
  `KinectNotAvailableError` at that point instead of at import time. This makes
  the package installable and importable for CI and unit tests without the SDK
  or a sensor. (Kinect v2 remains Windows-only.)
- **BREAKING:** `Joint.to_depth_space()` / `Joint.to_color_space()` now accept a
  `CoordinateMapper` (previously typed as `Any`).
- All docstrings, comments and identifiers translated to English.
- COM VTable dispatch now caches per-interface method thunks, removing repeated
  `WINFUNCTYPE` / `ctypes.cast` work from the per-frame hot path.
- Frame references and native frames are now released deterministically inside
  `wait_for_frames()` instead of relying on garbage-collection timing.
- Silent `except Exception: pass` blocks replaced with narrow exception handling
  and `logging` at `DEBUG` level.

### Fixed

- COM calls now raise `COMOperationError` for **every** failure `HRESULT`,
  including the ones `ctypes` surfaces as a bare `OSError` (e.g. `E_PENDING`
  "frame not ready yet"). `_acquire_pending_audio()` / `acquire_latest_frame()`
  swallow that transient case again instead of crashing the capture loop.
- The native `IKinectSensor` is now reference-counted across `KinectSensor`
  instances in one process. Previously, closing one instance called
  `IKinectSensor::Close()` on the shared device and broke every other live
  instance; the hardware is now closed only when the last one releases it.
- `wait_for_frames()` no longer aborts with `KinectTimeoutError` on the first
  transient `NULL` / `E_PENDING` from `acquire_latest_frame()` (common with many
  streams enabled). It retries within the `timeout_ms` budget, as
  `wait_for_audio_frame()` already did.
- `readme = "readme.md"` vs. the actual `README.md` filename mismatch that broke
  source builds on case-sensitive filesystems.
- `InfraredFrame.to_uint8()` docstring now accurately describes the bit-shift
  scaling (previously claimed a logarithmic curve).
- `CoordinateMapper` method spacing / formatting.
