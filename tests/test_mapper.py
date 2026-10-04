"""``CoordinateMapper``: projections, input validation and point clouds (no hardware)."""

from __future__ import annotations

import ctypes
import warnings

import numpy as np
import pytest

from kinect_next import ColorFrame, CoordinateMapper, DepthFrame, Point2D, Vector3
from tests.fakes import FakeMapper, _as_array


@pytest.fixture
def mapper() -> CoordinateMapper:
    return CoordinateMapper(FakeMapper())  # type: ignore[arg-type]


def _depth(value: int = 1500) -> np.ndarray:
    return np.full((424, 512), value, dtype=np.uint16)


def _color() -> ColorFrame:
    """A colour frame whose pixel encodes its own position: B = x % 256, G = y % 256."""
    data = np.zeros((1080, 1920, 4), dtype=np.uint8)
    data[:, :, 0] = (np.arange(1920) % 256)[None, :]
    data[:, :, 1] = (np.arange(1080) % 256)[:, None]
    data[:, :, 2] = 200
    data[:, :, 3] = 255
    return ColorFrame(data=data)


# ---------------------------------------------------------------------------
# Single points
# ---------------------------------------------------------------------------
def test_single_point_projections(mapper: CoordinateMapper) -> None:
    assert mapper.map_camera_point_to_depth_space(Vector3(1.0, 2.0, 1.5)) == Point2D(100.0, 200.0)
    assert mapper.map_camera_point_to_color_space(Vector3(1.0, 2.0, 1.5)) == Point2D(300.0, 400.0)
    assert mapper.map_depth_point_to_camera_space(Point2D(100.0, 200.0), 1500) == Vector3(1.0, 2.0, 1.5)
    assert mapper.map_depth_point_to_color_space(Point2D(10.0, 20.0), 1500) == Point2D(30.0, 40.0)


def test_an_unprojectable_point_is_reported_as_invalid(mapper: CoordinateMapper) -> None:
    point = mapper.map_camera_point_to_depth_space(Vector3(0.0, 0.0, 0.0))
    assert not point.is_valid()
    with pytest.raises(ValueError, match="could not be projected"):
        point.as_int_tuple()


def test_depth_camera_intrinsics(mapper: CoordinateMapper) -> None:
    assert mapper.get_depth_camera_intrinsics() == (366.0, 366.5, 255.5, 206.0)


# ---------------------------------------------------------------------------
# Whole frames
# ---------------------------------------------------------------------------
def test_depth_frame_to_camera_space(mapper: CoordinateMapper) -> None:
    cam = mapper.map_depth_frame_to_camera_space(DepthFrame(data=_depth(2000)))
    assert cam.shape == (424, 512, 3) and cam.dtype == np.float32
    assert tuple(cam[0, 0]) == (0.0, 0.0, 2.0)
    assert tuple(cam[100, 300]) == pytest.approx((3.0, 1.0, 2.0))


def test_depth_frame_to_color_space(mapper: CoordinateMapper) -> None:
    pts = mapper.map_depth_frame_to_color_space(DepthFrame(data=_depth()))
    assert pts.shape == (424, 512, 2) and pts.dtype == np.float32
    assert tuple(pts[10, 20]) == (60.0, 20.0)


def test_color_frame_to_depth_space(mapper: CoordinateMapper) -> None:
    pts = mapper.map_color_frame_to_depth_space(DepthFrame(data=_depth(777)))
    assert pts.shape == (1080, 1920, 2) and pts.dtype == np.float32
    assert (pts == 777.0).all()


def test_raw_arrays_are_accepted_directly(mapper: CoordinateMapper) -> None:
    depth = _depth(1200)
    from_array = mapper.map_depth_frame_to_camera_space(depth)
    from_frame = mapper.map_depth_frame_to_camera_space(DepthFrame(data=depth))
    assert np.array_equal(from_array, from_frame)


# ---------------------------------------------------------------------------
# Input validation (these used to produce silently wrong results)
# ---------------------------------------------------------------------------
def test_a_mirrored_view_gives_the_same_result_as_its_copy(mapper: CoordinateMapper) -> None:
    """Regression: non-contiguous views were read as if they were contiguous."""
    depth = np.arange(424 * 512, dtype=np.uint32).reshape(424, 512).astype(np.uint16)
    depth[depth == 0] = 1
    mirrored = depth[:, ::-1]
    assert not mirrored.flags.c_contiguous

    from_view = mapper.map_depth_frame_to_camera_space(mirrored)
    from_copy = mapper.map_depth_frame_to_camera_space(np.ascontiguousarray(mirrored))
    assert np.array_equal(from_view, from_copy)
    assert from_view[0, 0, 2] == pytest.approx(mirrored[0, 0] / 1000.0)


@pytest.mark.parametrize("dtype", [np.float32, np.int16, np.uint8, np.uint32])
def test_the_wrong_dtype_is_rejected(mapper: CoordinateMapper, dtype: type) -> None:
    with pytest.raises(TypeError, match="uint16"):
        mapper.map_depth_frame_to_camera_space(_depth().astype(dtype))


@pytest.mark.parametrize("shape", [(212, 256), (424, 512, 1), (512, 424), (217088,)])
def test_the_wrong_shape_is_rejected(mapper: CoordinateMapper, shape: tuple[int, ...]) -> None:
    """A smaller buffer would make the native code read out of bounds."""
    with pytest.raises(ValueError, match="shape"):
        mapper.map_depth_frame_to_color_space(np.zeros(shape, dtype=np.uint16))


def test_non_arrays_are_rejected(mapper: CoordinateMapper) -> None:
    with pytest.raises(TypeError, match="NumPy array"):
        mapper.map_color_frame_to_depth_space([[1, 2], [3, 4]])  # type: ignore[arg-type]


def test_validation_applies_to_every_whole_frame_method(mapper: CoordinateMapper) -> None:
    bad = _depth().astype(np.float32)
    for method in (
        mapper.map_depth_frame_to_camera_space,
        mapper.map_depth_frame_to_color_space,
        mapper.map_color_frame_to_depth_space,
        mapper.generate_point_cloud,
    ):
        with pytest.raises(TypeError):
            method(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Point clouds
# ---------------------------------------------------------------------------
def test_point_cloud_without_colour(mapper: CoordinateMapper) -> None:
    cloud = mapper.generate_point_cloud(DepthFrame(data=_depth(1500)))
    assert cloud.points.shape == (424 * 512, 3) and cloud.points.dtype == np.float32
    assert cloud.colors is None
    assert (cloud.points[:, 2] == 1.5).all()


def test_point_cloud_drops_invalid_and_out_of_range_depth(mapper: CoordinateMapper) -> None:
    depth = _depth(1500)
    depth[0, :10] = 0  # no depth  -> -inf
    depth[1, :10] = 300  # too close (< 0.4 m)
    depth[2, :10] = 9000  # too far   (> 8 m)
    cloud = mapper.generate_point_cloud(depth)
    assert cloud.points.shape[0] == 424 * 512 - 30
    assert np.isfinite(cloud.points).all()


def test_point_cloud_colours_are_sampled_from_the_mapped_pixel(mapper: CoordinateMapper) -> None:
    cloud = mapper.generate_point_cloud(_depth(1500), _color())
    assert cloud.colors is not None and cloud.colors.shape == cloud.points.shape
    assert cloud.colors.dtype == np.float32

    # depth pixel (col=20, row=10) -> colour pixel (60, 20): B=60, G=20, R=200 -> RGB
    index = 10 * 512 + 20
    assert tuple(cloud.colors[index]) == pytest.approx((200 / 255, 20 / 255, 60 / 255))


def test_points_outside_the_colour_frame_are_black() -> None:
    class Overshooting(FakeMapper):
        def map_depth_frame_to_color_space(self, count: int, depth_ptr: object, out_ptr: object) -> None:
            super().map_depth_frame_to_color_space(count, depth_ptr, out_ptr)
            out = _as_array(out_ptr, ctypes.c_float, count * 2).reshape(count, 2)
            out[:512] = (5000.0, 5000.0)  # first row: beyond 1920x1080
            out[512:1024] = (-3.0, 10.0)  # second row: negative x

    cloud = CoordinateMapper(Overshooting()).generate_point_cloud(_depth(1500), _color())  # type: ignore[arg-type]
    assert cloud.colors is not None
    assert (cloud.colors[:1024] == 0.0).all()
    assert (cloud.colors[1024:, 0] > 0.0).all()


def test_keeping_invalid_points_does_not_emit_numpy_warnings(mapper: CoordinateMapper) -> None:
    """Regression: -inf colour coordinates were cast to int (RuntimeWarning)."""
    depth = _depth(1500)
    depth[:100] = 0
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        cloud = mapper.generate_point_cloud(depth, _color(), remove_invalid=False)

    assert cloud.points.shape == (424 * 512, 3)
    assert cloud.colors is not None and cloud.colors.shape == (424 * 512, 3)
    assert np.isneginf(cloud.points[: 100 * 512]).all()
    assert (cloud.colors[: 100 * 512] == 0.0).all()
    assert np.isfinite(cloud.points[100 * 512 :]).all()


def test_point_cloud_reads_through_a_non_contiguous_view(mapper: CoordinateMapper) -> None:
    depth = _depth(1500)
    depth[:, :256] = 2500
    cloud = mapper.generate_point_cloud(depth[:, ::-1], _color())
    assert cloud.colors is not None
    assert cloud.points[0, 2] == 1.5  # the mirrored view starts with the 1.5 m half
    assert cloud.points[511, 2] == 2.5
