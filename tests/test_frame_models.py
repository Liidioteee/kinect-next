"""Tests for the image-like frame data models."""

from __future__ import annotations

import numpy as np

from kinect_next.models.body_index import BodyIndexFrame
from kinect_next.models.color import ColorFrame
from kinect_next.models.depth import DepthFrame
from kinect_next.models.infrared import InfraredFrame, LongExposureInfraredFrame


def test_depth_distance_at() -> None:
    data = np.zeros((424, 512), dtype=np.uint16)
    data[10, 20] = 1500
    frame = DepthFrame(data)
    assert frame.distance_at(20, 10) == 1.5
    assert frame.distance_at(-1, 0) == 0.0
    assert frame.distance_at(0, 999) == 0.0


def test_depth_normalized_near_is_brighter_than_far() -> None:
    data = np.zeros((424, 512), dtype=np.uint16)
    data[0, 0] = 600  # near
    data[0, 1] = 4400  # far
    out = DepthFrame(data).to_normalized_uint8()
    assert out.dtype == np.uint8
    assert out[0, 0] > out[0, 1]
    assert out[0, 2] == 0  # outside reliable range -> stays 0


def test_infrared_to_uint8() -> None:
    data = np.array([[0, 64, 4096, 65535]], dtype=np.uint16)
    out = InfraredFrame(data).to_uint8()
    assert out.dtype == np.uint8
    assert out[0, 0] == 0
    assert out[0, 1] == 1
    assert out[0, 3] == 255  # 65535 >> 6 == 1023, clipped to 255


def test_long_exposure_ir_is_an_infrared_frame() -> None:
    frame = LongExposureInfraredFrame(np.zeros((424, 512), dtype=np.uint16))
    assert isinstance(frame, InfraredFrame)
    assert frame.to_uint8().shape == (424, 512)


def test_body_index_masks() -> None:
    data = np.full((424, 512), 255, dtype=np.uint8)
    data[0, :10] = 0
    data[0, 10:20] = 3
    frame = BodyIndexFrame(data)
    assert frame.get_body_mask(0).sum() == 10
    assert frame.get_body_mask(3).sum() == 10
    assert frame.get_all_bodies_mask().sum() == 20


def test_color_views_share_memory_and_channel_order() -> None:
    data = np.zeros((1080, 1920, 4), dtype=np.uint8)
    data[0, 0] = (10, 20, 30, 255)  # B, G, R, A
    frame = ColorFrame(data)

    assert np.shares_memory(frame.as_bgr(), data)
    assert tuple(frame.as_bgr()[0, 0]) == (10, 20, 30)
    assert tuple(frame.as_rgb()[0, 0]) == (30, 20, 10)
    assert frame.width == 1920 and frame.height == 1080
