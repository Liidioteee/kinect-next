"""Typed COM interface definitions for the Kinect SDK 2.0.

Each class lists the interface's methods in ``_vtable_`` in the exact order of the
SDK header (``Kinect.h``); VTable slots are derived from that order and methods
are invoked by their header name. ``tests/test_vtable_layout.py`` checks every
``_vtable_`` against a snapshot of the header (and against the header itself when
the SDK is installed), so the layouts cannot silently drift.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    POINTER,
    byref,
    c_float,
    c_int,
    c_longlong,
    c_uint,
    c_ulong,
    c_ulonglong,
    c_ushort,
    c_void_p,
)
from typing import Any

from kinect_next.core.exceptions import COMOperationError
from kinect_next.native.com_base import COMBase
from kinect_next.native.types import (
    CameraIntrinsicsNative,
    CameraSpacePoint,
    ColorSpacePoint,
    DepthSpacePoint,
    JointNative,
    JointOrientationNative,
    PointF,
    Vector4Native,
)

# ``WAITABLE_HANDLE`` is an ``INT_PTR``.
_WAITABLE_HANDLE = c_void_p


def _pop_event_data(obj: COMBase, method: str, handle: int) -> None:
    """Fetch and release the event args queued on ``handle``.

    The SDK keeps a waitable handle signalled until its event data has been
    retrieved; this is what re-arms the handle for the next blocking wait.
    """
    out = c_void_p()
    try:
        obj._call(method, (_WAITABLE_HANDLE, POINTER(c_void_p)), handle, byref(out))
    except COMOperationError:
        return
    if out.value:
        COMBase(out.value).release()


# ==============================================================================
# Frame descriptions and colour camera settings
# ==============================================================================


class IFrameDescription(COMBase):
    __slots__ = ()
    _vtable_ = (
        "get_Width",
        "get_Height",
        "get_HorizontalFieldOfView",
        "get_VerticalFieldOfView",
        "get_DiagonalFieldOfView",
        "get_LengthInPixels",
        "get_BytesPerPixel",
    )

    def get_width(self) -> int:
        return self._get_int("get_Width", c_int)

    def get_height(self) -> int:
        return self._get_int("get_Height", c_int)

    def get_length_in_pixels(self) -> int:
        return self._get_int("get_LengthInPixels", c_uint)

    def get_bytes_per_pixel(self) -> int:
        return self._get_int("get_BytesPerPixel", c_uint)


class IColorCameraSettings(COMBase):
    __slots__ = ()
    _vtable_ = ("get_ExposureTime", "get_FrameInterval", "get_Gain", "get_Gamma")

    def get_exposure_time(self) -> int:
        """Exposure time in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_ExposureTime", c_longlong)

    def get_frame_interval(self) -> int:
        """Frame interval in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_FrameInterval", c_longlong)

    def get_gain(self) -> float:
        return self._get_float("get_Gain")

    def get_gamma(self) -> float:
        return self._get_float("get_Gamma")


# ==============================================================================
# Video frames
# ==============================================================================


class IColorFrame(COMBase):
    __slots__ = ()
    _vtable_ = (
        "get_RawColorImageFormat",
        "get_FrameDescription",
        "CopyRawFrameDataToArray",
        "AccessRawUnderlyingBuffer",
        "CopyConvertedFrameDataToArray",
        "CreateFrameDescription",
        "get_ColorCameraSettings",
        "get_RelativeTime",
        "get_ColorFrameSource",
    )

    def copy_converted_frame_data_to_array(self, capacity: int, buffer_ptr: Any, color_format: int) -> None:
        self._call(
            "CopyConvertedFrameDataToArray", (c_uint, c_void_p, c_int), capacity, buffer_ptr, color_format
        )

    def get_color_camera_settings(self) -> IColorCameraSettings:
        return self._get_interface("get_ColorCameraSettings", IColorCameraSettings)

    def get_relative_time(self) -> int:
        """Timestamp in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_RelativeTime", c_longlong)


class _PlanarFrame(COMBase):
    """Shared implementation of the single-plane frames (depth, IR, body index).

    These interfaces have identical layouts for the methods used here.
    """

    __slots__ = ()

    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        self._call("CopyFrameDataToArray", (c_uint, c_void_p), capacity, buffer_ptr)

    def get_relative_time(self) -> int:
        """Timestamp in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_RelativeTime", c_longlong)


class IDepthFrame(_PlanarFrame):
    __slots__ = ()
    _vtable_ = (
        "CopyFrameDataToArray",
        "AccessUnderlyingBuffer",
        "get_FrameDescription",
        "get_RelativeTime",
        "get_DepthFrameSource",
        "get_DepthMinReliableDistance",
        "get_DepthMaxReliableDistance",
    )

    def get_min_reliable_distance(self) -> int:
        return self._get_int("get_DepthMinReliableDistance", c_ushort)

    def get_max_reliable_distance(self) -> int:
        return self._get_int("get_DepthMaxReliableDistance", c_ushort)


class IInfraredFrame(_PlanarFrame):
    __slots__ = ()
    _vtable_ = (
        "CopyFrameDataToArray",
        "AccessUnderlyingBuffer",
        "get_FrameDescription",
        "get_RelativeTime",
        "get_InfraredFrameSource",
    )


class ILongExposureInfraredFrame(_PlanarFrame):
    __slots__ = ()
    _vtable_ = (
        "CopyFrameDataToArray",
        "AccessUnderlyingBuffer",
        "get_FrameDescription",
        "get_RelativeTime",
        "get_LongExposureInfraredFrameSource",
    )


class IBodyIndexFrame(_PlanarFrame):
    __slots__ = ()
    _vtable_ = (
        "CopyFrameDataToArray",
        "AccessUnderlyingBuffer",
        "get_FrameDescription",
        "get_RelativeTime",
        "get_BodyIndexFrameSource",
    )


# ==============================================================================
# Bodies
# ==============================================================================


class IBody(COMBase):
    __slots__ = ()
    _vtable_ = (
        "GetJoints",
        "GetJointOrientations",
        "get_Engaged",
        "GetExpressionDetectionResults",
        "GetActivityDetectionResults",
        "GetAppearanceDetectionResults",
        "get_HandLeftState",
        "get_HandLeftConfidence",
        "get_HandRightState",
        "get_HandRightConfidence",
        "get_ClippedEdges",
        "get_TrackingId",
        "get_IsTracked",
        "get_IsRestricted",
        "get_Lean",
        "get_LeanTrackingState",
    )

    def get_joints(self, count: int) -> ctypes.Array[JointNative]:
        joints = (JointNative * count)()
        self._call("GetJoints", (c_uint, c_void_p), count, joints)
        return joints

    def get_joint_orientations(self, count: int) -> ctypes.Array[JointOrientationNative]:
        orientations = (JointOrientationNative * count)()
        self._call("GetJointOrientations", (c_uint, c_void_p), count, orientations)
        return orientations

    def get_hand_left_state(self) -> int:
        return self._get_int("get_HandLeftState", c_int)

    def get_hand_left_confidence(self) -> int:
        return self._get_int("get_HandLeftConfidence", c_int)

    def get_hand_right_state(self) -> int:
        return self._get_int("get_HandRightState", c_int)

    def get_hand_right_confidence(self) -> int:
        return self._get_int("get_HandRightConfidence", c_int)

    def get_clipped_edges(self) -> int:
        return self._get_int("get_ClippedEdges", c_ulong)

    def get_tracking_id(self) -> int:
        return self._get_int("get_TrackingId", c_ulonglong)

    def get_is_tracked(self) -> bool:
        return self._get_bool("get_IsTracked")

    def get_is_restricted(self) -> bool:
        return self._get_bool("get_IsRestricted")

    def get_lean(self) -> PointF:
        return self._get_struct("get_Lean", PointF)

    def get_lean_tracking_state(self) -> int:
        return self._get_int("get_LeanTrackingState", c_int)


class IBodyFrame(COMBase):
    __slots__ = ()
    _vtable_ = ("GetAndRefreshBodyData", "get_FloorClipPlane", "get_RelativeTime", "get_BodyFrameSource")

    def get_bodies(self, count: int) -> list[IBody]:
        """Return an owned :class:`IBody` for every populated body slot."""
        slots = (c_void_p * count)()
        self._call("GetAndRefreshBodyData", (c_uint, c_void_p), count, slots)
        return [IBody(ptr) for ptr in slots if ptr]

    def get_floor_clip_plane(self) -> Vector4Native:
        return self._get_struct("get_FloorClipPlane", Vector4Native)

    def get_relative_time(self) -> int:
        """Timestamp in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_RelativeTime", c_longlong)


# ==============================================================================
# Frame references and the multi-source reader
# ==============================================================================

_FRAME_REFERENCE_VTABLE = ("AcquireFrame", "get_RelativeTime")


class IColorFrameReference(COMBase):
    __slots__ = ()
    _vtable_ = _FRAME_REFERENCE_VTABLE

    def acquire_frame(self) -> IColorFrame | None:
        return self._try_get_interface("AcquireFrame", IColorFrame)


class IDepthFrameReference(COMBase):
    __slots__ = ()
    _vtable_ = _FRAME_REFERENCE_VTABLE

    def acquire_frame(self) -> IDepthFrame | None:
        return self._try_get_interface("AcquireFrame", IDepthFrame)


class IBodyFrameReference(COMBase):
    __slots__ = ()
    _vtable_ = _FRAME_REFERENCE_VTABLE

    def acquire_frame(self) -> IBodyFrame | None:
        return self._try_get_interface("AcquireFrame", IBodyFrame)


class IBodyIndexFrameReference(COMBase):
    __slots__ = ()
    _vtable_ = _FRAME_REFERENCE_VTABLE

    def acquire_frame(self) -> IBodyIndexFrame | None:
        return self._try_get_interface("AcquireFrame", IBodyIndexFrame)


class IInfraredFrameReference(COMBase):
    __slots__ = ()
    _vtable_ = _FRAME_REFERENCE_VTABLE

    def acquire_frame(self) -> IInfraredFrame | None:
        return self._try_get_interface("AcquireFrame", IInfraredFrame)


class ILongExposureInfraredFrameReference(COMBase):
    __slots__ = ()
    _vtable_ = _FRAME_REFERENCE_VTABLE

    def acquire_frame(self) -> ILongExposureInfraredFrame | None:
        return self._try_get_interface("AcquireFrame", ILongExposureInfraredFrame)


class IMultiSourceFrame(COMBase):
    __slots__ = ()
    _vtable_ = (
        "get_ColorFrameReference",
        "get_DepthFrameReference",
        "get_BodyFrameReference",
        "get_BodyIndexFrameReference",
        "get_InfraredFrameReference",
        "get_LongExposureInfraredFrameReference",
    )

    def get_color_frame_reference(self) -> IColorFrameReference:
        return self._get_interface("get_ColorFrameReference", IColorFrameReference)

    def get_depth_frame_reference(self) -> IDepthFrameReference:
        return self._get_interface("get_DepthFrameReference", IDepthFrameReference)

    def get_body_frame_reference(self) -> IBodyFrameReference:
        return self._get_interface("get_BodyFrameReference", IBodyFrameReference)

    def get_body_index_frame_reference(self) -> IBodyIndexFrameReference:
        return self._get_interface("get_BodyIndexFrameReference", IBodyIndexFrameReference)

    def get_infrared_frame_reference(self) -> IInfraredFrameReference:
        return self._get_interface("get_InfraredFrameReference", IInfraredFrameReference)

    def get_long_exposure_infrared_frame_reference(self) -> ILongExposureInfraredFrameReference:
        return self._get_interface(
            "get_LongExposureInfraredFrameReference", ILongExposureInfraredFrameReference
        )


class IMultiSourceFrameReader(COMBase):
    __slots__ = ()
    _vtable_ = (
        "SubscribeMultiSourceFrameArrived",
        "UnsubscribeMultiSourceFrameArrived",
        "GetMultiSourceFrameArrivedEventData",
        "AcquireLatestFrame",
        "get_FrameSourceTypes",
        "get_IsPaused",
        "put_IsPaused",
        "get_KinectSensor",
    )

    def subscribe_frame_arrived(self) -> int:
        """Return a Win32 waitable handle that is signalled when a frame arrives."""
        handle = c_void_p()
        self._call("SubscribeMultiSourceFrameArrived", (POINTER(c_void_p),), byref(handle))
        return handle.value or 0

    def unsubscribe_frame_arrived(self, handle: int) -> None:
        self._call("UnsubscribeMultiSourceFrameArrived", (_WAITABLE_HANDLE,), handle)

    def clear_frame_arrived(self, handle: int) -> None:
        """Consume one queued frame-arrived event, re-arming ``handle``."""
        _pop_event_data(self, "GetMultiSourceFrameArrivedEventData", handle)

    def acquire_latest_frame(self) -> IMultiSourceFrame | None:
        return self._try_get_interface("AcquireLatestFrame", IMultiSourceFrame)


# ==============================================================================
# Coordinate mapper
# ==============================================================================


class ICoordinateMapper(COMBase):
    __slots__ = ()
    _vtable_ = (
        "SubscribeCoordinateMappingChanged",
        "UnsubscribeCoordinateMappingChanged",
        "GetCoordinateMappingChangedEventData",
        "MapCameraPointToDepthSpace",
        "MapCameraPointToColorSpace",
        "MapDepthPointToCameraSpace",
        "MapDepthPointToColorSpace",
        "MapCameraPointsToDepthSpace",
        "MapCameraPointsToColorSpace",
        "MapDepthPointsToCameraSpace",
        "MapDepthPointsToColorSpace",
        "MapDepthFrameToCameraSpace",
        "MapDepthFrameToColorSpace",
        "MapColorFrameToDepthSpace",
        "MapColorFrameToCameraSpace",
        "GetDepthFrameToCameraSpaceTable",
        "GetDepthCameraIntrinsics",
    )

    def map_camera_point_to_depth_space(self, camera_point: CameraSpacePoint) -> DepthSpacePoint:
        res = DepthSpacePoint()
        self._call(
            "MapCameraPointToDepthSpace",
            (CameraSpacePoint, POINTER(DepthSpacePoint)),
            camera_point,
            byref(res),
        )
        return res

    def map_camera_point_to_color_space(self, camera_point: CameraSpacePoint) -> ColorSpacePoint:
        res = ColorSpacePoint()
        self._call(
            "MapCameraPointToColorSpace",
            (CameraSpacePoint, POINTER(ColorSpacePoint)),
            camera_point,
            byref(res),
        )
        return res

    def map_depth_point_to_camera_space(self, depth_point: DepthSpacePoint, depth: int) -> CameraSpacePoint:
        res = CameraSpacePoint()
        self._call(
            "MapDepthPointToCameraSpace",
            (DepthSpacePoint, c_ushort, POINTER(CameraSpacePoint)),
            depth_point,
            depth,
            byref(res),
        )
        return res

    def map_depth_point_to_color_space(self, depth_point: DepthSpacePoint, depth: int) -> ColorSpacePoint:
        res = ColorSpacePoint()
        self._call(
            "MapDepthPointToColorSpace",
            (DepthSpacePoint, c_ushort, POINTER(ColorSpacePoint)),
            depth_point,
            depth,
            byref(res),
        )
        return res

    def map_depth_frame_to_camera_space(
        self, depth_point_count: int, depth_frame_ptr: Any, camera_points_ptr: Any
    ) -> None:
        self._call(
            "MapDepthFrameToCameraSpace",
            (c_uint, c_void_p, c_uint, c_void_p),
            depth_point_count,
            depth_frame_ptr,
            depth_point_count,
            camera_points_ptr,
        )

    def map_depth_frame_to_color_space(
        self, depth_point_count: int, depth_frame_ptr: Any, color_points_ptr: Any
    ) -> None:
        self._call(
            "MapDepthFrameToColorSpace",
            (c_uint, c_void_p, c_uint, c_void_p),
            depth_point_count,
            depth_frame_ptr,
            depth_point_count,
            color_points_ptr,
        )

    def map_color_frame_to_depth_space(
        self, depth_point_count: int, depth_frame_ptr: Any, color_point_count: int, depth_points_ptr: Any
    ) -> None:
        self._call(
            "MapColorFrameToDepthSpace",
            (c_uint, c_void_p, c_uint, c_void_p),
            depth_point_count,
            depth_frame_ptr,
            color_point_count,
            depth_points_ptr,
        )

    def get_depth_camera_intrinsics(self) -> CameraIntrinsicsNative:
        return self._get_struct("GetDepthCameraIntrinsics", CameraIntrinsicsNative)


# ==============================================================================
# Audio subsystem
# ==============================================================================


class IAudioBodyCorrelation(COMBase):
    """Correlation between an audio beam and a tracked body (DSP body correlation)."""

    __slots__ = ()
    _hold_gil_ = True  # capture hot path: see COMBase._hold_gil_
    _vtable_ = ("get_BodyTrackingId",)

    def get_body_tracking_id(self) -> int:
        return self._get_int("get_BodyTrackingId", c_ulonglong)


class IAudioBeamSubFrame(COMBase):
    """Audio sub-frame: float32 PCM samples, beam angle and body correlation."""

    __slots__ = ()
    _hold_gil_ = True  # capture hot path: see COMBase._hold_gil_
    _vtable_ = (
        "get_FrameLengthInBytes",
        "get_Duration",
        "get_BeamAngle",
        "get_BeamAngleConfidence",
        "get_AudioBeamMode",
        "get_AudioBodyCorrelationCount",
        "GetAudioBodyCorrelation",
        "CopyFrameDataToArray",
        "AccessUnderlyingBuffer",
        "get_RelativeTime",
    )

    def get_frame_length_in_bytes(self) -> int:
        return self._get_int("get_FrameLengthInBytes", c_uint)

    def get_duration(self) -> int:
        """Sub-frame duration in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_Duration", c_longlong)

    def get_beam_angle(self) -> float:
        """Beam azimuth in radians (approx. -0.87 .. +0.87 rad, i.e. -50 deg .. +50 deg)."""
        return self._get_float("get_BeamAngle")

    def get_beam_angle_confidence(self) -> float:
        """Confidence of the beam direction in the range [0.0 .. 1.0]."""
        return self._get_float("get_BeamAngleConfidence")

    def get_audio_beam_mode(self) -> int:
        """The beam mode (``AudioBeamMode``) this sub-frame was captured in."""
        return self._get_int("get_AudioBeamMode", c_int)

    def get_audio_body_correlation_count(self) -> int:
        return self._get_int("get_AudioBodyCorrelationCount", c_uint)

    def get_audio_body_correlation(self, index: int) -> IAudioBodyCorrelation | None:
        return self._try_get_interface("GetAudioBodyCorrelation", IAudioBodyCorrelation, (c_uint,), index)

    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        """Copy the sub-frame payload (1024 bytes = 256 float32 samples) into ``buffer_ptr``."""
        self._call("CopyFrameDataToArray", (c_uint, c_void_p), capacity, buffer_ptr)

    def access_underlying_buffer(self) -> tuple[int, int]:
        """Return ``(size_in_bytes, address)`` of the SDK-owned sample buffer.

        The buffer is only valid until this sub-frame is released.
        """
        capacity = c_uint()
        buffer_ptr = c_void_p()
        self._call(
            "AccessUnderlyingBuffer",
            (POINTER(c_uint), POINTER(c_void_p)),
            byref(capacity),
            byref(buffer_ptr),
        )
        return capacity.value, buffer_ptr.value or 0

    def get_relative_time(self) -> int:
        """Timestamp in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_RelativeTime", c_longlong)


class IAudioBeamFrame(COMBase):
    """Audio beam frame; a container for a list of sub-frames."""

    __slots__ = ()
    _hold_gil_ = True  # capture hot path: see COMBase._hold_gil_
    _vtable_ = (
        "get_AudioSource",
        "get_Duration",
        "get_AudioBeam",
        "get_SubFrameCount",
        "GetSubFrame",
        "get_RelativeTimeStart",
    )

    def get_duration(self) -> int:
        """Frame duration in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_Duration", c_longlong)

    def get_audio_beam(self) -> IAudioBeam:
        return self._get_interface("get_AudioBeam", IAudioBeam)

    def get_sub_frame_count(self) -> int:
        return self._get_int("get_SubFrameCount", c_uint)

    def get_sub_frame(self, index: int) -> IAudioBeamSubFrame | None:
        return self._try_get_interface("GetSubFrame", IAudioBeamSubFrame, (c_uint,), index)

    def get_relative_time_start(self) -> int:
        """Start timestamp in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_RelativeTimeStart", c_longlong)


class IAudioBeamFrameList(COMBase):
    """List of acquired audio beam frames."""

    __slots__ = ()
    _hold_gil_ = True  # capture hot path: see COMBase._hold_gil_
    _vtable_ = ("get_BeamCount", "OpenAudioBeamFrame")

    def get_count(self) -> int:
        return self._get_int("get_BeamCount", c_uint)

    def open_audio_beam_frame(self, index: int) -> IAudioBeamFrame | None:
        return self._try_get_interface("OpenAudioBeamFrame", IAudioBeamFrame, (c_uint,), index)


class IAudioBeam(COMBase):
    """Control of audio beam direction (beamforming)."""

    __slots__ = ()
    _vtable_ = (
        "get_AudioSource",
        "get_AudioBeamMode",
        "put_AudioBeamMode",
        "get_BeamAngle",
        "put_BeamAngle",
        "get_BeamAngleConfidence",
        "OpenInputStream",
        "get_RelativeTime",
    )

    def get_audio_source(self) -> IAudioSource:
        return self._get_interface("get_AudioSource", IAudioSource)

    def get_audio_beam_mode(self) -> int:
        return self._get_int("get_AudioBeamMode", c_int)

    def put_audio_beam_mode(self, mode: int) -> None:
        self._call("put_AudioBeamMode", (c_int,), mode)

    def get_beam_angle(self) -> float:
        return self._get_float("get_BeamAngle")

    def put_beam_angle(self, angle_radians: float) -> None:
        self._call("put_BeamAngle", (c_float,), angle_radians)

    def get_beam_angle_confidence(self) -> float:
        return self._get_float("get_BeamAngleConfidence")

    def get_relative_time(self) -> int:
        """Timestamp in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_RelativeTime", c_longlong)


class IAudioBeamList(COMBase):
    """List of hardware-supported audio beams."""

    __slots__ = ()
    _vtable_ = ("get_BeamCount", "OpenAudioBeam")

    def get_beam_count(self) -> int:
        return self._get_int("get_BeamCount", c_uint)

    def open_audio_beam(self, index: int) -> IAudioBeam:
        return self._get_interface("OpenAudioBeam", IAudioBeam, (c_uint,), index)


class IAudioBeamFrameReader(COMBase):
    """Reader for the audio beam frame stream."""

    __slots__ = ()
    _hold_gil_ = True  # capture hot path: see COMBase._hold_gil_
    _vtable_ = (
        "SubscribeFrameArrived",
        "UnsubscribeFrameArrived",
        "GetFrameArrivedEventData",
        "AcquireLatestBeamFrames",
        "get_IsPaused",
        "put_IsPaused",
        "get_AudioSource",
    )

    def subscribe_frame_arrived(self) -> int:
        """Return a Win32 waitable handle that is signalled when audio arrives."""
        handle = c_void_p()
        self._call("SubscribeFrameArrived", (POINTER(c_void_p),), byref(handle))
        return handle.value or 0

    def unsubscribe_frame_arrived(self, handle: int) -> None:
        self._call("UnsubscribeFrameArrived", (_WAITABLE_HANDLE,), handle)

    def clear_frame_arrived(self, handle: int) -> None:
        """Consume one queued frame-arrived event, re-arming ``handle``."""
        _pop_event_data(self, "GetFrameArrivedEventData", handle)

    def acquire_latest_beam_frames(self) -> IAudioBeamFrameList | None:
        return self._try_get_interface("AcquireLatestBeamFrames", IAudioBeamFrameList)


class IAudioSource(COMBase):
    """Audio data source for the Kinect v2 microphone array."""

    __slots__ = ()
    _vtable_ = (
        "SubscribeFrameCaptured",
        "UnsubscribeFrameCaptured",
        "GetFrameCapturedEventData",
        "get_KinectSensor",
        "get_IsActive",
        "get_SubFrameLengthInBytes",
        "get_SubFrameDuration",
        "get_MaxSubFrameCount",
        "OpenReader",
        "get_AudioBeams",
        "get_AudioCalibrationState",
    )

    def get_is_active(self) -> bool:
        return self._get_bool("get_IsActive")

    def get_sub_frame_length_in_bytes(self) -> int:
        return self._get_int("get_SubFrameLengthInBytes", c_uint)

    def get_sub_frame_duration(self) -> int:
        """Default sub-frame duration in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        return self._get_int("get_SubFrameDuration", c_longlong)

    def get_max_sub_frame_count_for_read(self) -> int:
        return self._get_int("get_MaxSubFrameCount", c_uint)

    def open_reader(self) -> IAudioBeamFrameReader:
        return self._get_interface("OpenReader", IAudioBeamFrameReader)

    def get_audio_beams(self) -> IAudioBeamList:
        return self._get_interface("get_AudioBeams", IAudioBeamList)

    def get_audio_calibration_state(self) -> int:
        return self._get_int("get_AudioCalibrationState", c_int)


# ==============================================================================
# Sensor
# ==============================================================================


class IKinectSensorNative(COMBase):
    """``IKinectSensor`` (named ``...Native`` to avoid clashing with the facade)."""

    __slots__ = ()
    _vtable_ = (
        "SubscribeIsAvailableChanged",
        "UnsubscribeIsAvailableChanged",
        "GetIsAvailableChangedEventData",
        "Open",
        "Close",
        "get_IsOpen",
        "get_IsAvailable",
        "get_ColorFrameSource",
        "get_DepthFrameSource",
        "get_BodyFrameSource",
        "get_BodyIndexFrameSource",
        "get_InfraredFrameSource",
        "get_LongExposureInfraredFrameSource",
        "get_AudioSource",
        "OpenMultiSourceFrameReader",
        "get_CoordinateMapper",
        "get_UniqueKinectId",
        "get_KinectCapabilities",
    )

    def open(self) -> None:
        self._call("Open", ())

    def close(self) -> None:
        self._call("Close", ())

    def is_open(self) -> bool:
        return self._get_bool("get_IsOpen")

    def is_available(self) -> bool:
        return self._get_bool("get_IsAvailable")

    def get_audio_source(self) -> IAudioSource:
        return self._get_interface("get_AudioSource", IAudioSource)

    def open_multi_source_frame_reader(self, enabled_frame_source_types: int) -> IMultiSourceFrameReader:
        return self._get_interface(
            "OpenMultiSourceFrameReader", IMultiSourceFrameReader, (c_ulong,), enabled_frame_source_types
        )

    def get_coordinate_mapper(self) -> ICoordinateMapper:
        return self._get_interface("get_CoordinateMapper", ICoordinateMapper)
