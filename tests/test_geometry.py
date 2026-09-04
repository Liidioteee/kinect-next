"""Tests for the geometry primitives."""

from __future__ import annotations

import math

import pytest

from kinect_next.models.geometry import Point2D, Quaternion, Vector3, Vector4


def test_vector3_length_and_distance() -> None:
    assert Vector3(3.0, 4.0, 0.0).length() == pytest.approx(5.0)
    assert Vector3(0.0, 0.0, 0.0).distance_to(Vector3(1.0, 2.0, 2.0)) == pytest.approx(3.0)


def test_vector3_validity() -> None:
    assert Vector3(1.0, 2.0, 3.0).is_valid()
    assert not Vector3(math.inf, 0.0, 0.0).is_valid()
    assert not Vector3(0.0, math.nan, 0.0).is_valid()


def test_point2d_rounding_and_validity() -> None:
    assert Point2D(1.4, 2.6).as_int_tuple() == (1, 3)
    assert Point2D(0.0, 0.0).is_valid()
    assert not Point2D(math.inf, 0.0).is_valid()


def test_quaternion_identity() -> None:
    q = Quaternion(0.0, 0.0, 0.0, 1.0)
    assert q.to_euler_angles() == (0.0, 0.0, 0.0)
    assert q.to_rotation_matrix() == (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )


def test_quaternion_90deg_about_z() -> None:
    half = math.sqrt(0.5)
    roll, pitch, yaw = Quaternion(0.0, 0.0, half, half).to_euler_angles()
    assert roll == pytest.approx(0.0, abs=1e-9)
    assert pitch == pytest.approx(0.0, abs=1e-9)
    assert yaw == pytest.approx(math.pi / 2, abs=1e-9)


def test_vector4_tuple() -> None:
    assert Vector4(1.0, 2.0, 3.0, 4.0).as_tuple() == (1.0, 2.0, 3.0, 4.0)
