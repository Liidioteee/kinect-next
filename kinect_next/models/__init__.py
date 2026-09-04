"""Typed data models returned by :mod:`kinect_next`."""

from kinect_next.models.audio import AudioBeamSubFrame, AudioFrame
from kinect_next.models.body import Body, Hand, Joint, JointCollection
from kinect_next.models.body_index import BodyIndexFrame
from kinect_next.models.color import ColorCameraSettings, ColorFrame
from kinect_next.models.depth import DepthFrame
from kinect_next.models.frameset import FrameSet
from kinect_next.models.geometry import Point2D, Quaternion, Vector3, Vector4
from kinect_next.models.infrared import InfraredFrame, LongExposureInfraredFrame

__all__ = [
    "AudioBeamSubFrame",
    "AudioFrame",
    "Body",
    "BodyIndexFrame",
    "ColorCameraSettings",
    "ColorFrame",
    "DepthFrame",
    "FrameSet",
    "Hand",
    "InfraredFrame",
    "Joint",
    "JointCollection",
    "LongExposureInfraredFrame",
    "Point2D",
    "Quaternion",
    "Vector3",
    "Vector4",
]
