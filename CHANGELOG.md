# Changelog

All notable changes to **kinect-next** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2026-10-04

A correctness and robustness release driven by a full code review with a live
sensor. It contains breaking API changes (see **Changed** / **Removed**).

### Fixed

- **Six audio COM methods called the wrong VTable slot.** `IAudioSource.get_is_active`,
  `IAudioBeam.get_relative_time`, `IAudioBeamFrame.get_audio_beam` /
  `get_relative_time_start` and `IAudioBeamSubFrame.get_audio_body_correlation_count` /
  `get_audio_body_correlation` were off by one or more slots. In practice
  `correlated_body_ids` was always empty (the beam *mode* was read as the count),
  and `get_is_active` wrote an 8-byte pointer into a 1-byte buffer. VTable
  layouts are now declared by method name in SDK-header order and verified
  against `Kinect.h`.
- **Audio in `FrameSet` was lossy.** The SDK only exposes the latest 1-2 audio
  sub-frames, so sampling audio once per video frame dropped 30-60 % of it. Audio
  is now captured continuously by a background thread; `FrameSet.audio` and
  `wait_for_audio_frame()` return gap-free audio however slowly they are read.
- **`wait_for_audio_frame()` burned a full CPU core** and `wait_for_frames()`
  degenerated into a 1 ms poll, because the frame-arrived event was never
  re-armed. Waits now fetch the event data and genuinely block (audio-only
  capture: ~100 % -> ~2 % of a core).
- **Closing a sensor while another thread was waiting** failed with
  `KinectError: Win32 wait ... failed (code 4294967295)` and could release COM
  objects that were in use. `KinectSensor` is now thread-safe: `close()`
  interrupts waits, which raise `KinectClosedError`, and `poll_frames()` /
  `poll_audio()` / `stream()` / `audio_stream()` end cleanly.
- **Manual beam steering failed silently.** Some Kinect runtimes accept
  `MANUAL` mode with `S_OK` and stay in `AUTOMATIC`; `set_beam_angle()` /
  `track_joint()` / `track_body()` then did nothing. Every mode change is now
  verified and raises `AudioStreamError` when it is not applied.
- **`CoordinateMapper` silently returned wrong results** for non-contiguous depth
  views (e.g. `depth[:, ::-1]`) and non-`uint16` arrays, and would read out of
  bounds for undersized ones. Inputs are now validated (`ValueError` /
  `TypeError`) and views are copied to a contiguous buffer.
- `generate_point_cloud(..., remove_invalid=False)` no longer emits
  `RuntimeWarning: invalid value encountered in cast`.
- `draw_audio_visual_overlay()` no longer crashes with `OverflowError` when the
  speaker's head cannot be projected; `Point2D.as_int_tuple()` raises a
  descriptive `ValueError` for non-finite coordinates.
- `relative_time_ns` is now populated on every frame and on `FrameSet` (it was
  always `0`), and `AudioBeamSubFrame.mode` reports the real beam mode.
- A failed `open()` now releases everything it had acquired and leaves the
  object reusable.
- An asyncio task cancelled while awaiting `wait_for_frames()` /
  `wait_for_audio_frame()` no longer leaves a worker thread behind that consumes
  the next frame.

### Added

- `KinectClosedError` (a `KinectError`) for waits on a closed sensor.
- `AudioController.supports_manual_steering`, plus `repr()` for the controller
  and both sensor classes; `set_beam_angle()` / `track_joint()` / `track_body()`
  return the angle that was applied.
- `KinectSensor(..., audio_buffer_seconds=10.0)` bounds the background audio queue.
- `KinectSensor.audio_subframes_lost` counts audio sub-frames that were missed
  (capture thread starved of the GIL) or discarded (buffer overflow); the first
  gap is also logged. See "Audio under load" in the README.
- `CoordinateMapper` whole-frame methods accept a raw `(424, 512)` `uint16`
  array as well as a `DepthFrame`.
- `find_speaking_body(..., correlated_body_ids=...)`: the sensor's own
  audio-body correlation now takes precedence over the azimuth heuristic, and
  `draw_audio_visual_overlay()` uses it.
- `COMBase` is a context manager; native layer gained the missing timestamp,
  beam-mode, event-data and calibration-state accessors.
- `import kinect_next` works on non-Windows platforms (opening a sensor raises
  `KinectNotAvailableError`).
- `open3d` and `all` extras; `viz` now only pulls in OpenCV.
- Test suite grown from 45 to 458 hardware-free tests (100 % line coverage) and
  from 15 to 27 hardware tests, including a snapshot of the SDK header's VTable
  layouts (`tests/data/kinect_vtables.json`).

### Changed

- **BREAKING:** the default `timeout_ms` of every wait is 5000 ms (was 1500). A
  freshly opened Kinect routinely needs longer than 1.5 s to deliver data.
- **BREAKING:** `KinectSensor`'s `auto_open` is keyword-only; so is
  `generate_point_cloud`'s `remove_invalid`.
- **BREAKING:** waits on a closed sensor raise `KinectClosedError` instead of a
  bare `KinectError` (still a subclass).
- **BREAKING (native layer):** `COMBase._call_method(index, ...)` is replaced by
  `COMBase._call("HeaderMethodName", ...)`; `COMBase.ptr` is an `int`;
  `create_event()` returns an `int`; `IBodyFrame.get_and_refresh_body_data` is
  replaced by `get_bodies()`, and `IBody.get_joints()` /
  `get_joint_orientations()` return the filled arrays.
- `AudioFrame` now holds all audio captured since the previous read rather than
  "the latest couple of sub-frames".
- README no longer claims zero-copy frames: frames are copied once from the
  driver into NumPy; `as_bgr()` / `as_rgb()` are views of that array.
- Packaging: SPDX `license = "MIT"` (PEP 639) with `setuptools>=77`.

### Removed

- **BREAKING:** `AsyncKinectSensor(auto_open=...)` — the argument was accepted and
  ignored. Open the sensor with `async with` or `await sensor.open()`.
- **BREAKING:** `AudioController.set_mode()` — assign `controller.mode` instead.

## [2.0.0] - 2026-09-04

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
