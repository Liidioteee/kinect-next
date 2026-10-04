"""Library core: sensor, coordinate mapper, audio controller, enums and exceptions."""

from kinect_next.core.audio import AudioController
from kinect_next.core.enums import (
    Activity,
    Appearance,
    AudioBeamMode,
    ColorImageFormat,
    DetectionResult,
    Expression,
    FrameEdges,
    HandState,
    JointType,
    KinectAudioCalibrationState,
    StreamType,
    TrackingConfidence,
    TrackingState,
)
from kinect_next.core.exceptions import (
    AudioStreamError,
    COMOperationError,
    KinectClosedError,
    KinectError,
    KinectNotAvailableError,
    KinectTimeoutError,
    StreamNotEnabledError,
)
from kinect_next.core.mapper import CoordinateMapper, PointCloudData
from kinect_next.core.sensor import KinectSensor

__all__ = [
    "Activity",
    "Appearance",
    "AudioBeamMode",
    "AudioController",
    "AudioStreamError",
    "COMOperationError",
    "ColorImageFormat",
    "CoordinateMapper",
    "DetectionResult",
    "Expression",
    "FrameEdges",
    "HandState",
    "JointType",
    "KinectAudioCalibrationState",
    "KinectClosedError",
    "KinectError",
    "KinectNotAvailableError",
    "KinectSensor",
    "KinectTimeoutError",
    "PointCloudData",
    "StreamNotEnabledError",
    "StreamType",
    "TrackingConfidence",
    "TrackingState",
]
