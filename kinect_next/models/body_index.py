"""Body-index (per-person segmentation mask) frame data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

BODY_INDEX_WIDTH: Final = 512
BODY_INDEX_HEIGHT: Final = 424
BACKGROUND_VALUE: Final = 255


@dataclass(slots=True)
class BodyIndexFrame:
    """A 512 x 424 segmentation mask: ``0..5`` is a tracked body index, ``255`` is background."""

    data: npt.NDArray[np.uint8]  # shape (424, 512)
    relative_time_ns: int = 0  # sensor clock at capture, in nanoseconds

    @property
    def width(self) -> int:
        """Frame width in pixels (512)."""
        return BODY_INDEX_WIDTH

    @property
    def height(self) -> int:
        """Frame height in pixels (424)."""
        return BODY_INDEX_HEIGHT

    def get_body_mask(self, body_index: int) -> npt.NDArray[np.bool_]:
        """Boolean mask that is ``True`` where person ``body_index`` is present."""
        mask: npt.NDArray[np.bool_] = self.data == body_index
        return mask

    def get_all_bodies_mask(self) -> npt.NDArray[np.bool_]:
        """Boolean mask that is ``True`` for any person and ``False`` for background."""
        mask: npt.NDArray[np.bool_] = self.data != BACKGROUND_VALUE
        return mask
