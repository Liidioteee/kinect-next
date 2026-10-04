"""Tests for point-cloud export helpers."""

from __future__ import annotations

import numpy as np

from kinect_next.core.mapper import PointCloudData
from kinect_next.utils.point_cloud import save_point_cloud_ply

_POINTS = np.array([[0.0, 0.0, 1.0], [1.0, -1.0, 2.0], [0.5, 0.25, 1.5]], dtype=np.float32)


def _read_header(path) -> list[str]:
    lines: list[str] = []
    with path.open("rb") as fh:
        for raw in fh:
            line = raw.decode("ascii").strip()
            lines.append(line)
            if line == "end_header":
                break
    return lines


def test_ascii_ply_without_colors(tmp_path) -> None:
    out = tmp_path / "cloud.ply"
    save_point_cloud_ply(out, PointCloudData(points=_POINTS, colors=None))
    header = _read_header(out)
    assert header[0] == "ply"
    assert "format ascii 1.0" in header
    assert "element vertex 3" in header
    assert "property uchar red" not in header
    body = out.read_text().splitlines()[len(header) :]
    assert len(body) == 3
    assert body[1].split()[:3] == ["1.0000", "-1.0000", "2.0000"]


def test_ascii_ply_with_colors(tmp_path) -> None:
    colors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [2.0, -1.0, 0.5]], dtype=np.float32)
    out = tmp_path / "cloud_rgb.ply"
    save_point_cloud_ply(out, PointCloudData(points=_POINTS, colors=colors))
    header = _read_header(out)
    assert "property uchar red" in header
    last = out.read_text().splitlines()[-1].split()
    # colours are clamped to [0, 1] then scaled to 0..255
    assert last[3:] == ["255", "0", "128"]


def test_binary_ply_roundtrip(tmp_path) -> None:
    colors = np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], dtype=np.float32)
    out = tmp_path / "cloud.bin.ply"
    save_point_cloud_ply(out, PointCloudData(points=_POINTS, colors=colors), binary=True)

    header = _read_header(out)
    assert "format binary_little_endian 1.0" in header

    raw = out.read_bytes()
    payload = raw.split(b"end_header\n", 1)[1]
    rec = np.frombuffer(payload, dtype=[("xyz", "<f4", 3), ("rgb", "u1", 3)])
    assert rec.shape == (3,)
    np.testing.assert_allclose(rec["xyz"], _POINTS)
    assert tuple(rec["rgb"][0]) == (255, 255, 255)
    assert tuple(rec["rgb"][2]) == (128, 128, 128)


def test_creates_parent_directory(tmp_path) -> None:
    out = tmp_path / "a" / "b" / "cloud.ply"
    save_point_cloud_ply(out, PointCloudData(points=_POINTS, colors=None))
    assert out.is_file()


def test_mismatched_colours_are_ignored(tmp_path) -> None:
    out = tmp_path / "cloud.ply"
    save_point_cloud_ply(out, PointCloudData(points=_POINTS, colors=np.ones((2, 3), dtype=np.float32)))
    header = _read_header(out)
    assert "property uchar red" not in header
    assert "element vertex 3" in header


def test_binary_ply_without_colors(tmp_path) -> None:
    out = tmp_path / "cloud.ply"
    save_point_cloud_ply(out, PointCloudData(points=_POINTS, colors=None), binary=True)
    raw = out.read_bytes()
    body = raw[raw.index(b"end_header\n") + len(b"end_header\n") :]
    assert np.array_equal(np.frombuffer(body, dtype="<f4").reshape(-1, 3), _POINTS)


def test_colours_are_clipped_to_the_byte_range(tmp_path) -> None:
    out = tmp_path / "cloud.ply"
    colors = np.array([[2.0, -1.0, 0.5]] * 3, dtype=np.float32)
    save_point_cloud_ply(out, PointCloudData(points=_POINTS, colors=colors))
    first_vertex = out.read_text().split("end_header\n")[1].splitlines()[0].split()
    assert first_vertex[3:] == ["255", "0", "128"]


def test_to_open3d_point_cloud_converts_points_and_colours(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from kinect_next import to_open3d_point_cloud

    class _Cloud:
        points = None
        colors = None

    fake_o3d = SimpleNamespace(
        geometry=SimpleNamespace(PointCloud=_Cloud),
        utility=SimpleNamespace(Vector3dVector=lambda arr: ("vec", arr)),
    )
    monkeypatch.setitem(sys.modules, "open3d", fake_o3d)

    colors = np.full((3, 3), 0.5, dtype=np.float32)
    cloud = to_open3d_point_cloud(PointCloudData(points=_POINTS, colors=colors))
    assert cloud.points[0] == "vec" and cloud.points[1].dtype == np.float64
    assert np.array_equal(cloud.points[1], _POINTS.astype(np.float64))
    assert cloud.colors[1].dtype == np.float64

    plain = to_open3d_point_cloud(PointCloudData(points=_POINTS, colors=None))
    assert plain.colors is None


def test_to_open3d_point_cloud_without_open3d(monkeypatch) -> None:
    import builtins

    import pytest

    from kinect_next import to_open3d_point_cloud

    real_import = builtins.__import__

    def no_open3d(name, *args, **kwargs):
        if name == "open3d":
            raise ImportError("No module named 'open3d'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_open3d)
    with pytest.raises(ImportError, match="open3d is required"):
        to_open3d_point_cloud(PointCloudData(points=_POINTS, colors=None))
