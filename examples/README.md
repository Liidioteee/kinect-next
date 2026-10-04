# Examples

Runnable scripts that need a physically connected Kinect v2 and the `viz` extra:

```bash
pip install "kinect-next[viz]"
```

| Script | What it shows |
|---|---|
| `skeleton_opencv.py` | Colour + depth preview with skeleton overlay |
| `background_removal.py` | Virtual green screen via colour→depth remap of the body-index mask |
| `async_streaming.py` | Non-blocking capture with `AsyncKinectSensor` |
| `hardware_probes/` | Low-level step-by-step bring-up scripts used during development (`test_step5_deb.py` is a historical brute-force VTable scanner; the layouts are now taken from `Kinect.h` and verified by `tests/test_vtable_layout.py`) |

These are illustrative and are **not** shipped in the published package.
