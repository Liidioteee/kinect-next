"""Save and export 3D point clouds."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from kinect_next.core.mapper import PointCloudData

if TYPE_CHECKING:
    import open3d  # noqa: F401


def save_point_cloud_ply(filename: str | Path, pcd: PointCloudData, *, binary: bool = False) -> None:
    """Write a point cloud to a PLY file (MeshLab / Blender / CloudCompare / Open3D).

    Parameters
    ----------
    filename:
        Destination path. Parent directories are created if missing.
    pcd:
        The point cloud to write.
    binary:
        Write ``binary_little_endian`` PLY (compact, fastest). The default writes
        ASCII PLY, which is the most portable.
    """
    points = np.ascontiguousarray(pcd.points, dtype=np.float32)
    colors = pcd.colors
    has_colors = colors is not None and len(colors) == len(points)
    count = len(points)

    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    fmt = "binary_little_endian 1.0" if binary else "ascii 1.0"
    header = [
        "ply",
        f"format {fmt}",
        f"element vertex {count}",
        "property float x",
        "property float y",
        "property float z",
    ]
    if has_colors:
        header += ["property uchar red", "property uchar green", "property uchar blue"]
    header += ["end_header", ""]
    header_bytes = ("\n".join(header)).encode("ascii")

    if has_colors:
        assert colors is not None
        rgb = (np.clip(colors, 0.0, 1.0) * 255.0).round().astype(np.uint8)

    if binary:
        with path.open("wb") as fh:
            fh.write(header_bytes)
            if has_colors:
                rec = np.zeros(
                    count,
                    dtype=[("xyz", "<f4", 3), ("rgb", "u1", 3)],
                )
                rec["xyz"] = points
                rec["rgb"] = rgb
                fh.write(rec.tobytes())
            else:
                fh.write(points.tobytes())
        return

    with path.open("wb") as fh:
        fh.write(header_bytes)
        if has_colors:
            rows = np.concatenate([points, rgb.astype(np.float32)], axis=1)
            np.savetxt(fh, rows, fmt="%.4f %.4f %.4f %d %d %d")
        else:
            np.savetxt(fh, points, fmt="%.4f %.4f %.4f")


def to_open3d_point_cloud(pcd: PointCloudData) -> Any:
    """Convert to an ``open3d.geometry.PointCloud`` (requires ``open3d``)."""
    try:
        import open3d as o3d
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            'open3d is required for this conversion. Install it with: pip install "kinect-next[open3d]"'
        ) from exc

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(pcd.points.astype(np.float64))
    if pcd.colors is not None:
        cloud.colors = o3d.utility.Vector3dVector(pcd.colors.astype(np.float64))
    return cloud
