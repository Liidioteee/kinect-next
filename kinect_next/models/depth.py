"""Depth frame data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

DEPTH_WIDTH: Final = 512
DEPTH_HEIGHT: Final = 424


@dataclass(slots=True)
class DepthFrame:
    """A 512 x 424 depth frame; pixel values are distances in millimetres (``uint16``)."""

    data: npt.NDArray[np.uint16]  # shape (424, 512)
    min_reliable_distance: int = 500  # 0.5 m
    max_reliable_distance: int = 4500  # 4.5 m
    relative_time_ns: int = 0  # sensor clock at capture, in nanoseconds

    @property
    def width(self) -> int:
        """Frame width in pixels (512)."""
        return DEPTH_WIDTH

    @property
    def height(self) -> int:
        """Frame height in pixels (424)."""
        return DEPTH_HEIGHT

    def distance_at(self, x: int, y: int) -> float:
        """Distance to pixel ``(x, y)`` in metres, or ``0.0`` if out of bounds."""
        if 0 <= x < DEPTH_WIDTH and 0 <= y < DEPTH_HEIGHT:
            return float(self.data[y, x]) / 1000.0
        return 0.0

    def to_normalized_uint8(self) -> npt.NDArray[np.uint8]:
        """Map the reliable depth range to ``0..255`` for display (near = bright)."""
        valid = (self.data >= self.min_reliable_distance) & (self.data <= self.max_reliable_distance)
        out = np.zeros(self.data.shape, dtype=np.uint8)
        if valid.any():
            span = max(1, self.max_reliable_distance - self.min_reliable_distance)
            clipped = np.clip(self.data, self.min_reliable_distance, self.max_reliable_distance)
            scaled = 255.0 - ((clipped - self.min_reliable_distance) / span * 255.0)
            out[valid] = scaled[valid].astype(np.uint8)
        return out
