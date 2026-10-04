# kinect-next

**kinect-next** is a modern, high-performance, hardware-synchronised and strictly
typed library for the **Microsoft Kinect for Windows v2** sensor on **Python
3.10+**, with full support for video, 3D point clouds and the **microphone array
(beamforming)**.

It is a from-scratch replacement for the long-unmaintained `pykinect2`, fixing its
architectural issues, memory leaks and incompatibilities with modern Python.

> 🇷🇺 Русская версия: [README.ru.md](README.ru.md)

---

## Highlights

* 🎙 **4-mic array & beamforming** — hardware sound-source localisation (SSL),
  speech azimuth tracking (−50°…+50°) and **gap-free** 16 kHz float32 / int16 PCM
  capture on a background thread; where the runtime supports it, the beam can be
  steered manually or locked onto a person's 3D joints (`audio.track_body`).
* 🎯 **Audio-visual fusion** — a built-in polar sound radar and automatic
  highlighting of the speaking person in OpenCV (`draw_audio_visual_overlay`).
* 🏎 **Lean frame handling** — each frame is copied exactly once, straight from
  the driver into a NumPy array; `BGR` / `RGB` are views of that array, and an
  opt-in buffer-reuse mode removes per-frame allocations in real-time loops.
* 💤 **Event-driven, thread-safe capture** — waits block on the SDK's
  frame-arrived events (≈0 % CPU while idle), `close()` may be called from any
  thread, and cancelling an `asyncio` task really aborts the wait.
* 🔒 **Deterministic COM cleanup (RAII)** — every `IUnknown` pointer is released
  as soon as a frame is consumed, not whenever the GC gets around to it.
* ⏱ **Hardware sync** — colour, depth, IR, skeleton and body-index of one sensor
  tick arrive together in a single `FrameSet`, timestamped on the sensor clock,
  along with all the audio captured since the previous one.
* ☁️ **Vectorised 3D point-cloud engine** — hundreds of thousands of coloured 3D
  points generated inside the native driver, off the Python GIL.
* 🧩 **Fully typed (PEP 561 / `py.typed`)** — passes `mypy --strict`.
* ⚡ **asyncio support** — `AsyncKinectSensor` async context manager and
  `async for` frame/audio generators.
* 📦 **No SDK needed to import** — `import kinect_next` has no side effects;
  `Kinect20.dll` is loaded lazily on the first `KinectSensor.open()`, so the
  package installs and imports anywhere, even without the SDK or a sensor
  (handy for CI, docs builds and unit tests). Opening a sensor is Windows-only
  and raises `KinectNotAvailableError` elsewhere.

---

## Requirements

| | |
|---|---|
| **OS** | Windows 10 / 11 (64-bit) — Kinect v2 is Windows-only |
| **Hardware** | Kinect v2 sensor + power adapter, on a **USB 3.0** port |
| **Driver** | [Kinect for Windows SDK 2.0](https://www.microsoft.com/en-us/download/details.aspx?id=44561) |
| **Python** | 3.10, 3.11, 3.12, 3.13 |

## Installation

```bash
pip install kinect-next              # core library
pip install "kinect-next[viz]"       # + OpenCV for the drawing helpers
pip install "kinect-next[open3d]"    # + Open3D for point-cloud conversion
pip install "kinect-next[all]"       # everything
```

From source:

```bash
git clone https://github.com/Liidioteee/kinect-next.git
cd kinect-next
pip install -e ".[dev]"
```

---

## Quickstart

### 1. Audio-visual fusion (skeletons + speaker in OpenCV)

```python
import cv2
from kinect_next import (
    KinectSensor,
    StreamType,
    draw_all_skeletons,
    draw_audio_visual_overlay,
)

streams = StreamType.COLOR | StreamType.BODY | StreamType.AUDIO

with KinectSensor(streams=streams) as kinect:
    for frames in kinect.poll_frames():
        if frames.color is None:
            continue

        display = frames.color.as_bgr().copy()          # BGR view -> own copy to draw on
        draw_all_skeletons(display, frames.bodies, kinect.mapper, target_space="color")
        draw_audio_visual_overlay(display, frames, kinect.mapper, target_space="color")

        cv2.imshow("Kinect v2 — Audio-Visual Fusion", cv2.resize(display, (1280, 720)))
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

### 2. Record 16 kHz microphone-array audio and track the beam

```python
from kinect_next import AudioFrame, KinectSensor, StreamType

recording = AudioFrame()

with KinectSensor(streams=StreamType.AUDIO) as kinect:
    for audio in kinect.poll_audio():
        print(f"voice azimuth: {audio.beam_angle_deg:+5.1f}°  loudness: {audio.dbfs:5.1f} dBFS")
        recording.subframes += audio.subframes          # consecutive frames join up gap-free
        if recording.duration_ms >= 5000:
            break

recording.save_wav("speech.wav", format_type="int16")   # 5 s, 16 kHz mono
```

Audio is captured continuously on a background thread, so nothing is lost while
your loop is busy: the next `AudioFrame` simply carries more 16 ms sub-frames. The
same holds for `FrameSet.audio` when audio is enabled next to video streams.

### 3. Generate a 3D point cloud and view it in Open3D

```python
import open3d as o3d
from kinect_next import KinectSensor, StreamType, save_point_cloud_ply, to_open3d_point_cloud

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH) as kinect:
    frames = kinect.wait_for_frames()

    cloud = kinect.mapper.generate_point_cloud(frames.depth, frames.color)
    print(f"points: {len(cloud.points):,}")

    save_point_cloud_ply("room_scan.ply", cloud)            # ASCII PLY
    save_point_cloud_ply("room_scan.bin.ply", cloud, binary=True)   # compact binary PLY

    o3d.visualization.draw_geometries([to_open3d_point_cloud(cloud)])
```

### 4. Virtual green screen / background removal

```python
import cv2
import numpy as np
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH | StreamType.BODY_INDEX) as kinect:
    for frames in kinect.poll_frames():
        if not (frames.color and frames.depth and frames.body_index):
            continue

        color = frames.color.as_bgr()
        depth_coords = kinect.mapper.map_color_frame_to_depth_space(frames.depth)

        body_hd = cv2.remap(
            frames.body_index.data,
            depth_coords[:, :, 0], depth_coords[:, :, 1],
            interpolation=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT, borderValue=255,
        )
        mask = cv2.GaussianBlur((body_hd != 255).astype(np.uint8) * 255, (15, 15), 0)
        alpha = (mask.astype(np.float32) / 255.0)[:, :, None]

        green = np.full_like(color, (0, 255, 0))
        result = (color * alpha + green * (1.0 - alpha)).astype(np.uint8)

        cv2.imshow("Virtual Green Screen", cv2.resize(result, (1280, 720)))
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

### 5. Async streaming (asyncio)

```python
import asyncio
from kinect_next import AsyncKinectSensor, StreamType

async def main() -> None:
    streams = StreamType.DEPTH | StreamType.BODY | StreamType.AUDIO
    async with AsyncKinectSensor(streams=streams) as kinect:
        async for frames in kinect.stream():
            if frames.depth:
                d = frames.depth.distance_at(256, 212)
                print(f"[async] distance {d:.2f} m | people {len(frames.tracked_bodies)}")
            if frames.audio:
                print(f"[async audio] beam {frames.audio.beam_angle_deg:.1f}°")

asyncio.run(main())
```

### 6. Infrared (night vision)

```python
import cv2
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.INFRARED) as kinect:
    for frames in kinect.poll_frames():
        cv2.imshow("Kinect v2 — Infrared", frames.infrared.to_uint8())
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

---

## Architecture

```
kinect_next/
├── native/   # COM VTable dispatch, Win32 bindings, SDK C structs
├── core/     # KinectSensor, CoordinateMapper, AudioController, enums, exceptions
├── models/   # typed dataclasses: FrameSet, ColorFrame, DepthFrame, Body, ...
├── aio/      # AsyncKinectSensor
└── utils/    # OpenCV overlays and point-cloud export (opencv/open3d optional)
```

### `FrameSet`

One snapshot of every enabled stream. The video frames belong to the same sensor
tick; `audio` holds everything captured since the previous `FrameSet`. A field is
`None` when its stream is disabled or has no data for the current tick.

| Field | Type | Notes |
|---|---|---|
| `color` | `ColorFrame` | 1920×1080, `.as_bgr()` / `.as_rgb()` / `.as_bgra()` (views) |
| `depth` | `DepthFrame` | 512×424 mm, `.distance_at(x, y)`, `.to_normalized_uint8()` |
| `infrared` | `InfraredFrame` | 16-bit IR, `.to_uint8()` |
| `long_exposure_infrared` | `LongExposureInfraredFrame` | long-exposure IR |
| `body_index` | `BodyIndexFrame` | segmentation mask (`0..5` person, `255` background) |
| `bodies` / `tracked_bodies` | `list[Body]` | up to 6 skeletons |
| `audio` | `AudioFrame` | gap-free sub-frames; `.as_int16()`, `.save_wav()`, `.rms`, `.dbfs`, `.correlated_body_ids` |
| `floor_clip_plane` | `Vector4` | floor plane `Ax + By + Cz + D = 0` |
| `relative_time_ns` | `int` | sensor clock of this tick; every frame and audio sub-frame carries its own too |

### `Body`

`tracking_id`, `is_tracked`, `joints` (25 joints — `body.joints.head`,
`body.joints[JointType.HAND_LEFT]`, …), `hand_left` / `hand_right`
(`HandState.OPEN` / `CLOSED` / `LASSO` + confidence), `lean`, `clipped_edges`.

---

## Audio under load

The Kinect runtime only keeps the latest 1–3 audio sub-frames (16 ms each), so
kinect-next fetches them on a background thread the moment they appear. Measured
on a live sensor, audio stays gap-free while the application is idle, sleeps for
half a second per frame, builds a point cloud or runs heavy NumPy work on every
frame.

The capture thread still needs the GIL for a moment on each read. If other
threads run **CPU-bound pure-Python code** (tight loops that never release the
GIL), the hand-over can come too late and a sub-frame is missed — 1–7 % in a
stress test with 25 ms of pure-Python work per frame. Such gaps are never
silent: they are logged once and counted in `kinect.audio_subframes_lost`
(`0` means everything delivered so far is continuous).

If your application is like that, shorten the interpreter's switch interval
once at start-up; in the same stress test this brought the loss to zero:

```python
import sys
sys.setswitchinterval(0.0005)   # default is 0.005 s
```

## `AudioController` (`kinect.audio`)

```python
from kinect_next import AudioBeamMode, AudioStreamError

audio = kinect.audio
print(audio.mode, audio.beam_angle_deg, audio.beam_angle_confidence)

if audio.supports_manual_steering:
    audio.set_beam_angle(-20.0)                   # steer manually, −50°…+50°
    for body in frames.tracked_bodies:
        audio.track_body(body)                    # aim at a person's head
    audio.mode = AudioBeamMode.AUTOMATIC          # hand control back to the DSP
```

> **Manual steering depends on the Kinect runtime.** Some SDK / firmware
> combinations accept the switch to `MANUAL` and silently stay in `AUTOMATIC`
> (Microsoft's own managed API behaves the same on such machines). kinect-next
> verifies every mode change: `set_beam_angle()`, `track_joint()`, `track_body()`
> and `audio.mode = AudioBeamMode.MANUAL` raise `AudioStreamError` instead of
> pretending to work. In `AUTOMATIC` mode the beam angle, its confidence and
> `AudioFrame.correlated_body_ids` are always available.

## `CoordinateMapper` (`kinect.mapper`)

Kinect v2 uses three spaces: **camera space** (metric 3D), **depth space**
(512×424) and **colour space** (1920×1080).

```python
p_depth = joint.to_depth_space(kinect.mapper)     # Point2D
p_color = joint.to_color_space(kinect.mapper)     # Point2D

cam = kinect.mapper.map_depth_frame_to_camera_space(frames.depth)   # (424, 512, 3) f32
col = kinect.mapper.map_depth_frame_to_color_space(frames.depth)    # (424, 512, 2) f32
```

The whole-frame methods take a `DepthFrame` or a raw `(424, 512)` `uint16` array.
Views with any strides (mirrored, sliced) are handled; a wrong shape or dtype
raises `ValueError` / `TypeError` rather than being misread by the native code.
A point that cannot be projected comes back as `-inf` — check `Point2D.is_valid()`
before `as_int_tuple()`.

## Waiting, timeouts and shutdown

```python
frames = kinect.wait_for_frames()            # default timeout: 5 s
frames = kinect.wait_for_frames(timeout_ms=0)  # poll: KinectTimeoutError if nothing is ready
```

* **Start-up.** A freshly opened Kinect needs 1–3 s before data flows, and it
  typically pauses delivery once more for a couple of seconds right after the
  first frames. The 5 s default covers both; `poll_frames()` / `poll_audio()`
  skip timeouts on their own.
* **Thread safety.** Captures are serialised, so several threads may call
  `wait_for_frames()`. `close()` can be called from any thread: waits in
  progress raise `KinectClosedError` and the `poll_*` / `stream()` generators
  just finish.
* **asyncio.** Cancelling a task that awaits `AsyncKinectSensor.wait_for_frames()`
  (e.g. via `asyncio.wait_for`) aborts the underlying wait as well.
* **Several sensor objects.** All `KinectSensor` instances in a process share the
  one physical device; it is closed when the last instance closes.

## Real-time loops: `reuse_buffers`

```python
# Reuse the internal colour/depth/IR NumPy buffers across calls — no per-frame
# allocation. The arrays from one wait_for_frames() call are overwritten by the
# next, so copy anything you need to keep.
with KinectSensor(StreamType.COLOR | StreamType.DEPTH, reuse_buffers=True) as kinect:
    for frames in kinect.poll_frames():
        ...
```

---

## Development

```bash
pip install -e ".[dev]"
ruff check kinect_next tests
ruff format --check kinect_next tests
mypy kinect_next
pytest
```

The default suite runs without a sensor: the capture logic is driven by fakes
and the COM dispatcher by a real in-process VTable. With a Kinect v2 attached,
add the integration tests:

```bash
pytest --run-hardware
```

The COM VTable layouts are pinned to the SDK header: `tests/data/kinect_vtables.json`
is a snapshot of `Kinect.h` (regenerate it with `python tests/kinect_header.py`),
and it is re-checked against the installed header whenever the SDK is present.

See [dev.md](dev.md) / [guide.md](guide.md) for internal architecture notes, and
[CHANGELOG.md](CHANGELOG.md) for release history.

## License

[MIT](LICENSE). Commercial and non-commercial use, modification and
distribution are permitted.
