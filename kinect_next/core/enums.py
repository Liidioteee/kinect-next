"""Strictly-typed enumerations for every Kinect v2 mode and constant."""

from __future__ import annotations

from enum import IntEnum, IntFlag

JOINT_COUNT = 25
"""Number of skeleton joints tracked per body by the Kinect SDK 2.0."""


class StreamType(IntFlag):
    """Sensor data streams. Combine with bitwise OR, e.g. ``COLOR | DEPTH``."""

    NONE = 0
    COLOR = 1
    INFRARED = 2
    LONG_EXPOSURE_INFRARED = 4
    DEPTH = 8
    BODY_INDEX = 16
    BODY = 32
    AUDIO = 64
    ALL = COLOR | INFRARED | LONG_EXPOSURE_INFRARED | DEPTH | BODY_INDEX | BODY | AUDIO


class JointType(IntEnum):
    """The 25 skeleton joints tracked by the Kinect SDK 2.0."""

    SPINE_BASE = 0
    SPINE_MID = 1
    NECK = 2
    HEAD = 3
    SHOULDER_LEFT = 4
    ELBOW_LEFT = 5
    WRIST_LEFT = 6
    HAND_LEFT = 7
    SHOULDER_RIGHT = 8
    ELBOW_RIGHT = 9
    WRIST_RIGHT = 10
    HAND_RIGHT = 11
    HIP_LEFT = 12
    KNEE_LEFT = 13
    ANKLE_LEFT = 14
    FOOT_LEFT = 15
    HIP_RIGHT = 16
    KNEE_RIGHT = 17
    ANKLE_RIGHT = 18
    FOOT_RIGHT = 19
    SPINE_SHOULDER = 20
    HAND_TIP_LEFT = 21
    THUMB_LEFT = 22
    HAND_TIP_RIGHT = 23
    THUMB_RIGHT = 24

    @classmethod
    def count(cls) -> int:
        """Return the number of joint types (always 25)."""
        return JOINT_COUNT


class TrackingState(IntEnum):
    """Tracking state of a joint or body."""

    NOT_TRACKED = 0
    INFERRED = 1
    TRACKED = 2


class HandState(IntEnum):
    """Recognised state of a hand."""

    UNKNOWN = 0
    NOT_TRACKED = 1
    OPEN = 2
    CLOSED = 3
    LASSO = 4


class TrackingConfidence(IntEnum):
    """Confidence level of a hand-state detection."""

    LOW = 0
    HIGH = 1


class DetectionResult(IntEnum):
    """Result of an activity / face-expression detector."""

    UNKNOWN = 0
    NO = 1
    MAYBE = 2
    YES = 3


class Activity(IntEnum):
    """Face activity categories (Kinect Face SDK)."""

    EYE_LEFT_CLOSED = 0
    EYE_RIGHT_CLOSED = 1
    MOUTH_OPEN = 2
    MOUTH_MOVED = 3
    LOOKING_AWAY = 4
    COUNT = 5


class Expression(IntEnum):
    """Face expression categories (Kinect Face SDK)."""

    NEUTRAL = 0
    HAPPY = 1
    COUNT = 2


class Appearance(IntEnum):
    """Face appearance categories (Kinect Face SDK)."""

    WEARING_GLASSES = 0
    COUNT = 1


class FrameEdges(IntFlag):
    """Which frame edges a body is clipped by (body partially out of view)."""

    NONE = 0
    RIGHT = 1
    LEFT = 2
    TOP = 4
    BOTTOM = 8


class ColorImageFormat(IntEnum):
    """Colour image pixel formats supported by the SDK."""

    NONE = 0
    RGBA = 1
    YUV = 2
    BGRA = 3
    BAYER = 4
    YUY2 = 5


class AudioBeamMode(IntEnum):
    """Microphone-array beam steering mode."""

    AUTOMATIC = 0
    MANUAL = 1


class KinectAudioCalibrationState(IntEnum):
    """Calibration state of the audio subsystem."""

    UNKNOWN = 0
    CALIBRATION_REQUIRED = 1
    CALIBRATED = 2
