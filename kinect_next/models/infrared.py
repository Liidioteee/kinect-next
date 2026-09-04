"""Infrared frame data models (``InfraredFrame`` and ``LongExposureInfraredFrame``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

IR_WIDTH: Final = 512
IR_HEIGHT: Final = 424


@dataclass(slots=True)
class InfraredFrame:
    """A 512 x 424 infrared frame with a 16-bit dynamic range (``uint16``)."""

    data: npt.NDArray[np.uint16]  # shape (424, 512)
    relative_time_ns: int = 0

    @property
    def width(self) -> int:
        """Frame width in pixels (512)."""
        return IR_WIDTH

    @property
    def height(self) -> int:
        """Frame height in pixels (424)."""
        return IR_HEIGHT

    def to_uint8(self) -> npt.NDArray[np.uint8]:
        """Scale the 16-bit IR frame to 8-bit by a ``>> 6`` bit-shift and clamp.

        This is a cheap linear reduction that keeps the informative low end of the
        Kinect IR range visible in the dark; it is not a logarithmic tone curve.
        """
        out: npt.NDArray[np.uint8] = np.clip(self.data >> 6, 0, 255).astype(np.uint8)
        return out


@dataclass(slots=True)
class LongExposureInfraredFrame(InfraredFrame):
    """A long-exposure infrared frame, better suited to static scenes."""
