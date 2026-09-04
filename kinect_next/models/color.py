"""Colour frame data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

COLOR_WIDTH: Final = 1920
COLOR_HEIGHT: Final = 1080


@dataclass(slots=True)
class ColorCameraSettings:
    """Auto-exposure state reported by the colour camera."""

    exposure_time: int
    gain: float
    gamma: float


@dataclass(slots=True)
class ColorFrame:
    """A Full-HD (1920 x 1080) colour frame stored as a native BGRA ``uint8`` buffer."""

    data: npt.NDArray[np.uint8]  # shape (1080, 1920, 4)
    settings: ColorCameraSettings | None = None
    relative_time_ns: int = 0

    @property
    def width(self) -> int:
        """Frame width in pixels (1920)."""
        return COLOR_WIDTH

    @property
    def height(self) -> int:
        """Frame height in pixels (1080)."""
        return COLOR_HEIGHT

    def as_bgra(self) -> npt.NDArray[np.uint8]:
        """Return the native ``(1080, 1920, 4)`` BGRA array (no copy)."""
        return self.data

    def as_bgr(self) -> npt.NDArray[np.uint8]:
        """Return a ``(1080, 1920, 3)`` BGR **view** for OpenCV (no copy)."""
        return self.data[:, :, :3]

    def as_rgb(self) -> npt.NDArray[np.uint8]:
        """Return a ``(1080, 1920, 3)`` RGB **view** for PIL / Matplotlib / Open3D (no copy)."""
        return self.data[:, :, 2::-1]
