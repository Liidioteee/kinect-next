"""Vectorised coordinate mapper for 2D/3D conversions and point-cloud generation.

Kinect v2 works with three coordinate spaces:

* **camera space** -- metric 3D ``(x, y, z)`` in metres, origin at the IR camera;
* **depth space**  -- 2D pixel grid of the depth frame (512 x 424);
* **colour space** -- 2D pixel grid of the Full-HD colour frame (1920 x 1080).
"""

from __future__ import annotations

import ctypes
from typing import Final, NamedTuple

import numpy as np
import numpy.typing as npt

from kinect_next.models.color import ColorFrame
from kinect_next.models.depth import DepthFrame
from kinect_next.models.geometry import Point2D, Vector3
from kinect_next.native.interfaces import ICoordinateMapper
from kinect_next.native.types import CameraSpacePoint, DepthSpacePoint

_DEPTH_W: Final = 512
_DEPTH_H: Final = 424
_DEPTH_COUNT: Final = _DEPTH_W * _DEPTH_H
_COLOR_W: Final = 1920
_COLOR_H: Final = 1080
_COLOR_COUNT: Final = _COLOR_W * _COLOR_H

# Depth range (in metres) kept when filtering a generated point cloud.
_PCL_MIN_Z_M: Final = 0.4
_PCL_MAX_Z_M: Final = 8.0


class PointCloudData(NamedTuple):
    """A generated 3D point cloud.

    Attributes
    ----------
    points:
        ``(N, 3)`` float32 array of XYZ coordinates in metres.
    colors:
        ``(N, 3)`` float32 array of RGB values in ``[0, 1]``, or ``None`` when no
        colour frame was supplied.
    """

    points: npt.NDArray[np.float32]
    colors: npt.NDArray[np.float32] | None


class CoordinateMapper:
    """Wrapper around the native ``ICoordinateMapper`` with NumPy batch helpers."""

    __slots__ = ("_native",)

    def __init__(self, native_mapper: ICoordinateMapper) -> None:
        self._native = native_mapper

    # ------------------------------------------------------------------
    # Single-point projections
    # ------------------------------------------------------------------
    def map_camera_point_to_depth_space(self, point: Vector3) -> Point2D:
        """Camera-space metres -> depth-frame pixel (512 x 424)."""
        res = self._native.map_camera_point_to_depth_space(CameraSpacePoint(point.x, point.y, point.z))
        return Point2D(res.x, res.y)

    def map_camera_point_to_color_space(self, point: Vector3) -> Point2D:
        """Camera-space metres -> colour-frame pixel (1920 x 1080)."""
        res = self._native.map_camera_point_to_color_space(CameraSpacePoint(point.x, point.y, point.z))
        return Point2D(res.x, res.y)

    def map_depth_point_to_camera_space(self, point: Point2D, depth_mm: int) -> Vector3:
        """Depth-frame pixel + distance (mm) -> camera-space metres."""
        res = self._native.map_depth_point_to_camera_space(DepthSpacePoint(point.x, point.y), depth_mm)
        return Vector3(res.x, res.y, res.z)

    def map_depth_point_to_color_space(self, point: Point2D, depth_mm: int) -> Point2D:
        """Depth-frame pixel + distance (mm) -> colour-frame pixel (1920 x 1080)."""
        res = self._native.map_depth_point_to_color_space(DepthSpacePoint(point.x, point.y), depth_mm)
        return Point2D(res.x, res.y)

    # ------------------------------------------------------------------
    # Whole-frame (vectorised) projections
    # ------------------------------------------------------------------
    def map_depth_frame_to_camera_space(self, depth_frame: DepthFrame) -> npt.NDArray[np.float32]:
        """Project the whole depth frame into camera space.

        Returns a ``(424, 512, 3)`` float32 array of ``(x, y, z)`` metres.
        """
        camera_points = np.empty((_DEPTH_H, _DEPTH_W, 3), dtype=np.float32)
        self._native.map_depth_frame_to_camera_space(
            _DEPTH_COUNT,
            depth_frame.data.ctypes.data_as(ctypes.c_void_p),
            camera_points.ctypes.data_as(ctypes.c_void_p),
        )
        return camera_points

    def map_depth_frame_to_color_space(self, depth_frame: DepthFrame) -> npt.NDArray[np.float32]:
        """Find the colour-frame ``(x, y)`` for every depth pixel.

        Returns a ``(424, 512, 2)`` float32 array.
        """
        color_points = np.empty((_DEPTH_H, _DEPTH_W, 2), dtype=np.float32)
        self._native.map_depth_frame_to_color_space(
            _DEPTH_COUNT,
            depth_frame.data.ctypes.data_as(ctypes.c_void_p),
            color_points.ctypes.data_as(ctypes.c_void_p),
        )
        return color_points

    def map_color_frame_to_depth_space(self, depth_frame: DepthFrame) -> npt.NDArray[np.float32]:
        """Find the depth-frame ``(x, y)`` for every Full-HD colour pixel.

        Returns a ``(1080, 1920, 2)`` float32 array.
        """
        depth_points = np.empty((_COLOR_H, _COLOR_W, 2), dtype=np.float32)
        self._native.map_color_frame_to_depth_space(
            _DEPTH_COUNT,
            depth_frame.data.ctypes.data_as(ctypes.c_void_p),
            _COLOR_COUNT,
            depth_points.ctypes.data_as(ctypes.c_void_p),
        )
        return depth_points

    # ------------------------------------------------------------------
    # Point cloud
    # ------------------------------------------------------------------
    def generate_point_cloud(
        self,
        depth_frame: DepthFrame,
        color_frame: ColorFrame | None = None,
        remove_invalid: bool = True,
    ) -> PointCloudData:
        """Generate a dense 3D point cloud, optionally textured with colour.

        Parameters
        ----------
        depth_frame:
            The depth frame to unproject.
        color_frame:
            Optional colour frame; when given, each point receives an RGB value.
        remove_invalid:
            Drop points with a non-finite or out-of-range depth
            (``z`` outside ``[0.4, 8.0]`` m).
        """
        flat_points = self.map_depth_frame_to_camera_space(depth_frame).reshape(-1, 3)

        valid_mask: npt.NDArray[np.bool_] | slice
        if remove_invalid:
            z = flat_points[:, 2]
            valid_mask = np.isfinite(z) & (z > _PCL_MIN_Z_M) & (z < _PCL_MAX_Z_M)
            valid_points = flat_points[valid_mask]
        else:
            valid_mask = slice(None)
            valid_points = flat_points

        valid_colors: npt.NDArray[np.float32] | None = None
        if color_frame is not None:
            color_coords = self.map_depth_frame_to_color_space(depth_frame).reshape(-1, 2)
            color_coords = color_coords[valid_mask]

            cx = np.rint(color_coords[:, 0]).astype(np.intp)
            cy = np.rint(color_coords[:, 1]).astype(np.intp)
            in_bounds = (cx >= 0) & (cx < _COLOR_W) & (cy >= 0) & (cy < _COLOR_H)

            rgb_img = color_frame.as_rgb()
            valid_colors = np.zeros((cx.shape[0], 3), dtype=np.float32)
            valid_colors[in_bounds] = rgb_img[cy[in_bounds], cx[in_bounds]] / np.float32(255.0)

        return PointCloudData(points=valid_points, colors=valid_colors)

    # ------------------------------------------------------------------
    def get_depth_camera_intrinsics(self) -> tuple[float, float, float, float]:
        """Return the depth camera intrinsics ``(fx, fy, cx, cy)`` in pixels."""
        k = self._native.get_depth_camera_intrinsics()
        return (k.FocalLengthX, k.FocalLengthY, k.PrincipalPointX, k.PrincipalPointY)
