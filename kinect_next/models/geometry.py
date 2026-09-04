"""Geometric primitives: 2D points, 3D/4D vectors and quaternions."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Point2D:
    """A 2D point in a frame plane (colour- or depth-space coordinates)."""

    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        """Return ``(x, y)`` as floats."""
        return self.x, self.y

    def as_int_tuple(self) -> tuple[int, int]:
        """Return ``(x, y)`` rounded to the nearest integers (pixel coordinates)."""
        return round(self.x), round(self.y)

    def is_valid(self) -> bool:
        """``True`` unless a coordinate is NaN or +/-infinity (out of view)."""
        return math.isfinite(self.x) and math.isfinite(self.y)


@dataclass(slots=True, frozen=True)
class Vector3:
    """A 3D vector / point in camera space (metres)."""

    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        """Return ``(x, y, z)`` as floats."""
        return self.x, self.y, self.z

    def length(self) -> float:
        """Euclidean length (distance from the sensor origin)."""
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def distance_to(self, other: Vector3) -> float:
        """Euclidean distance to ``other`` in metres."""
        dx = self.x - other.x
        dy = self.y - other.y
        dz = self.z - other.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def is_valid(self) -> bool:
        """``True`` unless a coordinate is NaN or +/-infinity."""
        return math.isfinite(self.x) and math.isfinite(self.y) and math.isfinite(self.z)


@dataclass(slots=True, frozen=True)
class Vector4:
    """A 4D vector, e.g. the floor-plane equation ``Ax + By + Cz + D = 0``."""

    x: float
    y: float
    z: float
    w: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Return ``(x, y, z, w)`` as floats."""
        return self.x, self.y, self.z, self.w


@dataclass(slots=True, frozen=True)
class Quaternion:
    """A joint orientation expressed as a unit quaternion ``(x, y, z, w)``."""

    x: float
    y: float
    z: float
    w: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Return ``(x, y, z, w)`` as floats."""
        return self.x, self.y, self.z, self.w

    def to_euler_angles(self) -> tuple[float, float, float]:
        """Convert to intrinsic ``(roll, pitch, yaw)`` Euler angles in radians."""
        sinr_cosp = 2.0 * (self.w * self.x + self.y * self.z)
        cosr_cosp = 1.0 - 2.0 * (self.x * self.x + self.y * self.y)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        sinp = 2.0 * (self.w * self.y - self.z * self.x)
        pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)

        siny_cosp = 2.0 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1.0 - 2.0 * (self.y * self.y + self.z * self.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return roll, pitch, yaw

    def to_rotation_matrix(self) -> tuple[tuple[float, float, float], ...]:
        """Return the equivalent 3x3 rotation matrix as nested tuples."""
        xx = self.x * self.x
        xy = self.x * self.y
        xz = self.x * self.z
        xw = self.x * self.w
        yy = self.y * self.y
        yz = self.y * self.z
        yw = self.y * self.w
        zz = self.z * self.z
        zw = self.z * self.w

        return (
            (1.0 - 2.0 * (yy + zz), 2.0 * (xy - zw), 2.0 * (xz + yw)),
            (2.0 * (xy + zw), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - xw)),
            (2.0 * (xz - yw), 2.0 * (yz + xw), 1.0 - 2.0 * (xx + yy)),
        )
