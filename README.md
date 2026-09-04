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
  speech azimuth tracking (−50°…+50°), 16 kHz float32 / int16 PCM capture, and
  locking the beam onto a person's 3D joints (`audio.track_body`).
* 🎯 **Audio-visual fusion** — a built-in polar sound radar and automatic
  highlighting of the speaking person in OpenCV (`draw_audio_visual_overlay`).
* 🏎 **Zero-copy frames** — NumPy views over the native driver buffers
  (`BGRA`, `BGR`, `RGB`, `uint16`, `float32`) with no redundant copies, plus an
  opt-in buffer-reuse mode for allocation-free real-time loops.
* 🔒 **Deterministic COM cleanup (RAII)** — every `IUnknown` pointer is released
  as soon as a frame is consumed, not whenever the GC gets around to it.
* ⏱ **Hardware sync** — colour, depth, IR, skeleton, body-index and audio arrive
  together in a single `FrameSet`.
* ☁️ **Vectorised 3D point-cloud engine** — hundreds of thousands of coloured 3D
  points generated inside the native driver, off the Python GIL.
* 🧩 **Fully typed (PEP 561 / `py.typed`)** — passes `mypy --strict`.
* ⚡ **asyncio support** — `AsyncKinectSensor` async context manager and
  `async for` frame/audio generators.
* 📦 **No SDK needed to import** — `import kinect_next` has no side effects;
  `Kinect20.dll` is loaded lazily on the first `KinectSensor.open()`, so the
  package installs and imports on Windows even without the SDK or a sensor
  (handy for CI and unit tests). Kinect v2 itself is Windows-only.

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
pip install kinect-next            # core library
pip install "kinect-next[viz]"     # + OpenCV / Open3D for the drawing helpers
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

        display = frames.color.as_bgr().copy()          # zero-copy (1080, 1920, 3)
        draw_all_skeletons(display, frames.bodies, kinect.mapper, target_space="color")
        draw_audio_visual_overlay(display, frames, kinect.mapper, target_space="color")

        cv2.imshow("Kinect v2 — Audio-Visual Fusion", cv2.resize(display, (1280, 720)))
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

### 2. Record 16 kHz microphone-array audio and track the beam

```python
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.AUDIO) as kinect:
    for audio in kinect.poll_audio():
        print(f"voice azimuth: {audio.beam_angle_deg:+5.1f}°  loudness: {audio.dbfs:5.1f} dBFS")
        audio.save_wav("speech.wav", format_type="int16")   # 16 kHz mono
        break
```

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

One hardware-synchronised snapshot. A field is `None` when its stream is disabled
or has no data for the current tick.

| Field | Type | Notes |
|---|---|---|
| `color` | `ColorFrame` | 1920×1080, `.as_bgr()` / `.as_rgb()` / `.as_bgra()` (views) |
| `depth` | `DepthFrame` | 512×424 mm, `.distance_at(x, y)`, `.to_normalized_uint8()` |
| `infrared` | `InfraredFrame` | 16-bit IR, `.to_uint8()` |
| `long_exposure_infrared` | `LongExposureInfraredFrame` | long-exposure IR |
| `body_index` | `BodyIndexFrame` | segmentation mask (`0..5` person, `255` background) |
| `bodies` / `tracked_bodies` | `list[Body]` | up to 6 skeletons |
| `audio` | `AudioFrame` | `.as_int16()`, `.save_wav()`, `.rms`, `.dbfs` |
| `floor_clip_plane` | `Vector4` | floor plane `Ax + By + Cz + D = 0` |

### `Body`

`tracking_id`, `is_tracked`, `joints` (25 joints — `body.joints.head`,
`body.joints[JointType.HAND_LEFT]`, …), `hand_left` / `hand_right`
(`HandState.OPEN` / `CLOSED` / `LASSO` + confidence), `lean`, `clipped_edges`.

---

## `AudioController` (`kinect.audio`)

```python
from kinect_next import AudioBeamMode

kinect.audio.set_mode(AudioBeamMode.AUTOMATIC)   # DSP tracks the loudest source
kinect.audio.set_beam_angle(-20.0)               # steer manually, −50°…+50°

for body in frames.tracked_bodies:
    kinect.audio.track_body(body)                 # aim at a person's head
```

## `CoordinateMapper` (`kinect.mapper`)

Kinect v2 uses three spaces: **camera space** (metric 3D), **depth space**
(512×424) and **colour space** (1920×1080).

```python
p_depth = joint.to_depth_space(kinect.mapper)     # Point2D
p_color = joint.to_color_space(kinect.mapper)     # Point2D

cam = kinect.mapper.map_depth_frame_to_camera_space(frames.depth)   # (424, 512, 3) f32
col = kinect.mapper.map_depth_frame_to_color_space(frames.depth)    # (424, 512, 2) f32
```

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

The test suite runs without a sensor. See [dev.md](dev.md) / [guide.md](guide.md)
for internal architecture notes, and [CHANGELOG.md](CHANGELOG.md) for release
history.

## License

[MIT](LICENSE). Commercial and non-commercial use, modification and
distribution are permitted.
