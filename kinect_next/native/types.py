"""Low-level Kinect SDK 2.0 C structures for :mod:`ctypes`."""

from ctypes import Structure, c_float, c_int


class CameraSpacePoint(Structure):
    _fields_ = [
        ("x", c_float),
        ("y", c_float),
        ("z", c_float),
    ]


class ColorSpacePoint(Structure):
    _fields_ = [
        ("x", c_float),
        ("y", c_float),
    ]


class DepthSpacePoint(Structure):
    _fields_ = [
        ("x", c_float),
        ("y", c_float),
    ]


class PointF(Structure):
    _fields_ = [
        ("x", c_float),
        ("y", c_float),
    ]


class Vector4Native(Structure):
    _fields_ = [
        ("x", c_float),
        ("y", c_float),
        ("z", c_float),
        ("w", c_float),
    ]


class JointNative(Structure):
    _fields_ = [
        ("JointType", c_int),
        ("Position", CameraSpacePoint),
        ("TrackingState", c_int),
    ]


class JointOrientationNative(Structure):
    _fields_ = [
        ("JointType", c_int),
        ("Orientation", Vector4Native),
    ]


class CameraIntrinsicsNative(Structure):
    _fields_ = [
        ("FocalLengthX", c_float),
        ("FocalLengthY", c_float),
        ("PrincipalPointX", c_float),
        ("PrincipalPointY", c_float),
        ("RadialDistortionSecondOrder", c_float),
        ("RadialDistortionFourthOrder", c_float),
        ("RadialDistortionSixthOrder", c_float),
    ]
