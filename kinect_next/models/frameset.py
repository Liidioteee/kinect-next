"""``FrameSet`` -- one hardware-synchronised snapshot of every enabled stream."""

from __future__ import annotations

from dataclasses import dataclass, field

from kinect_next.models.audio import AudioFrame
from kinect_next.models.body import Body
from kinect_next.models.body_index import BodyIndexFrame
from kinect_next.models.color import ColorFrame
from kinect_next.models.depth import DepthFrame
from kinect_next.models.geometry import Vector4
from kinect_next.models.infrared import InfraredFrame, LongExposureInfraredFrame


@dataclass(slots=True)
class FrameSet:
    """A single point-in-time snapshot of every stream enabled on the sensor.

    All frames in one ``FrameSet`` are hardware-synchronised. A field is ``None``
    when its stream was not enabled or no data was ready for this tick.
    """

    color: ColorFrame | None = None
    depth: DepthFrame | None = None
    infrared: InfraredFrame | None = None
    long_exposure_infrared: LongExposureInfraredFrame | None = None
    body_index: BodyIndexFrame | None = None
    bodies: list[Body] = field(default_factory=list)
    audio: AudioFrame | None = None
    floor_clip_plane: Vector4 | None = None
    relative_time_ns: int = 0

    @property
    def tracked_bodies(self) -> list[Body]:
        """Only the bodies that are actively tracked this frame."""
        return [b for b in self.bodies if b.is_tracked]
