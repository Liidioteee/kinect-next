"""Typed COM interface definitions for the Kinect SDK 2.0.

Every method maps to a single VTable slot. Slot indices are taken from the SDK
headers (``Kinect.h``) and must not be reordered.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    POINTER,
    byref,
    c_bool,
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
    PointF,
    Vector4Native,
)


class IFrameDescription(COMBase):
    def get_width(self) -> int:
        val = c_int()
        self._call_method(3, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value

    def get_height(self) -> int:
        val = c_int()
        self._call_method(4, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value

    def get_length_in_pixels(self) -> int:
        val = c_uint()
        self._call_method(8, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def get_bytes_per_pixel(self) -> int:
        val = c_uint()
        self._call_method(9, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value


class IColorCameraSettings(COMBase):
    def get_exposure_time(self) -> int:
        val = c_longlong()
        self._call_method(3, [POINTER(c_longlong)], ctypes.HRESULT, byref(val))
        return val.value

    def get_gain(self) -> float:
        val = c_float()
        self._call_method(5, [POINTER(c_float)], ctypes.HRESULT, byref(val))
        return val.value

    def get_gamma(self) -> float:
        val = c_float()
        self._call_method(6, [POINTER(c_float)], ctypes.HRESULT, byref(val))
        return val.value


class IColorFrame(COMBase):
    def copy_converted_frame_data_to_array(self, capacity: int, buffer_ptr: Any, color_format: int) -> None:
        self._call_method(7, [c_uint, c_void_p, c_int], ctypes.HRESULT, capacity, buffer_ptr, color_format)

    def get_color_camera_settings(self) -> IColorCameraSettings:
        ptr = c_void_p()
        self._call_method(9, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IColorCameraSettings(ptr)


class IDepthFrame(COMBase):
    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        self._call_method(3, [c_uint, c_void_p], ctypes.HRESULT, capacity, buffer_ptr)

    def get_min_reliable_distance(self) -> int:
        val = c_ushort()
        self._call_method(8, [POINTER(c_ushort)], ctypes.HRESULT, byref(val))
        return val.value

    def get_max_reliable_distance(self) -> int:
        val = c_ushort()
        self._call_method(9, [POINTER(c_ushort)], ctypes.HRESULT, byref(val))
        return val.value


class IInfraredFrame(COMBase):
    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        self._call_method(3, [c_uint, c_void_p], ctypes.HRESULT, capacity, buffer_ptr)


class ILongExposureInfraredFrame(COMBase):
    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        self._call_method(3, [c_uint, c_void_p], ctypes.HRESULT, capacity, buffer_ptr)


class IBodyIndexFrame(COMBase):
    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        self._call_method(3, [c_uint, c_void_p], ctypes.HRESULT, capacity, buffer_ptr)


class IBody(COMBase):
    def get_joints(self, count: int, joints_arr_ptr: Any) -> None:
        self._call_method(3, [c_uint, c_void_p], ctypes.HRESULT, count, joints_arr_ptr)

    def get_joint_orientations(self, count: int, orientations_arr_ptr: Any) -> None:
        self._call_method(4, [c_uint, c_void_p], ctypes.HRESULT, count, orientations_arr_ptr)

    def get_hand_left_state(self) -> int:
        val = c_int()
        self._call_method(9, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value

    def get_hand_left_confidence(self) -> int:
        val = c_int()
        self._call_method(10, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value

    def get_hand_right_state(self) -> int:
        val = c_int()
        self._call_method(11, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value

    def get_hand_right_confidence(self) -> int:
        val = c_int()
        self._call_method(12, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value

    def get_clipped_edges(self) -> int:
        val = c_ulong()
        self._call_method(13, [POINTER(c_ulong)], ctypes.HRESULT, byref(val))
        return val.value

    def get_tracking_id(self) -> int:
        val = c_ulonglong()
        self._call_method(14, [POINTER(c_ulonglong)], ctypes.HRESULT, byref(val))
        return val.value

    def get_is_tracked(self) -> bool:
        val = c_bool()
        self._call_method(15, [POINTER(c_bool)], ctypes.HRESULT, byref(val))
        return val.value

    def get_is_restricted(self) -> bool:
        val = c_bool()
        self._call_method(16, [POINTER(c_bool)], ctypes.HRESULT, byref(val))
        return val.value

    def get_lean(self) -> PointF:
        val = PointF()
        self._call_method(17, [POINTER(PointF)], ctypes.HRESULT, byref(val))
        return val

    def get_lean_tracking_state(self) -> int:
        val = c_int()
        self._call_method(18, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value


class IBodyFrame(COMBase):
    def get_and_refresh_body_data(self, count: int, bodies_array_ptr: Any) -> None:
        self._call_method(3, [c_uint, c_void_p], ctypes.HRESULT, count, bodies_array_ptr)

    def get_floor_clip_plane(self) -> Vector4Native:
        val = Vector4Native()
        self._call_method(4, [POINTER(Vector4Native)], ctypes.HRESULT, byref(val))
        return val


class IColorFrameReference(COMBase):
    def acquire_frame(self) -> IColorFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return IColorFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IDepthFrameReference(COMBase):
    def acquire_frame(self) -> IDepthFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return IDepthFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IBodyFrameReference(COMBase):
    def acquire_frame(self) -> IBodyFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return IBodyFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IBodyIndexFrameReference(COMBase):
    def acquire_frame(self) -> IBodyIndexFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return IBodyIndexFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IInfraredFrameReference(COMBase):
    def acquire_frame(self) -> IInfraredFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return IInfraredFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class ILongExposureInfraredFrameReference(COMBase):
    def acquire_frame(self) -> ILongExposureInfraredFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return ILongExposureInfraredFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IMultiSourceFrame(COMBase):
    def get_color_frame_reference(self) -> IColorFrameReference:
        ptr = c_void_p()
        self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IColorFrameReference(ptr)

    def get_depth_frame_reference(self) -> IDepthFrameReference:
        ptr = c_void_p()
        self._call_method(4, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IDepthFrameReference(ptr)

    def get_body_frame_reference(self) -> IBodyFrameReference:
        ptr = c_void_p()
        self._call_method(5, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IBodyFrameReference(ptr)

    def get_body_index_frame_reference(self) -> IBodyIndexFrameReference:
        ptr = c_void_p()
        self._call_method(6, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IBodyIndexFrameReference(ptr)

    def get_infrared_frame_reference(self) -> IInfraredFrameReference:
        ptr = c_void_p()
        self._call_method(7, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IInfraredFrameReference(ptr)

    def get_long_exposure_infrared_frame_reference(self) -> ILongExposureInfraredFrameReference:
        ptr = c_void_p()
        self._call_method(8, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return ILongExposureInfraredFrameReference(ptr)


class IMultiSourceFrameReader(COMBase):
    def subscribe_frame_arrived(self) -> int:
        handle = c_void_p()
        self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(handle))
        return handle.value or 0

    def unsubscribe_frame_arrived(self, handle: int) -> None:
        self._call_method(4, [c_void_p], ctypes.HRESULT, c_void_p(handle))

    def acquire_latest_frame(self) -> IMultiSourceFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(6, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return IMultiSourceFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class ICoordinateMapper(COMBase):
    def map_camera_point_to_depth_space(self, camera_point: CameraSpacePoint) -> DepthSpacePoint:
        res = DepthSpacePoint()
        self._call_method(
            6, [CameraSpacePoint, POINTER(DepthSpacePoint)], ctypes.HRESULT, camera_point, byref(res)
        )
        return res

    def map_camera_point_to_color_space(self, camera_point: CameraSpacePoint) -> ColorSpacePoint:
        res = ColorSpacePoint()
        self._call_method(
            7, [CameraSpacePoint, POINTER(ColorSpacePoint)], ctypes.HRESULT, camera_point, byref(res)
        )
        return res

    def map_depth_point_to_camera_space(self, depth_point: DepthSpacePoint, depth: int) -> CameraSpacePoint:
        res = CameraSpacePoint()
        self._call_method(
            8,
            [DepthSpacePoint, c_ushort, POINTER(CameraSpacePoint)],
            ctypes.HRESULT,
            depth_point,
            depth,
            byref(res),
        )
        return res

    def map_depth_point_to_color_space(self, depth_point: DepthSpacePoint, depth: int) -> ColorSpacePoint:
        res = ColorSpacePoint()
        self._call_method(
            9,
            [DepthSpacePoint, c_ushort, POINTER(ColorSpacePoint)],
            ctypes.HRESULT,
            depth_point,
            depth,
            byref(res),
        )
        return res

    def map_depth_frame_to_camera_space(
        self, depth_point_count: int, depth_frame_ptr: Any, camera_points_ptr: Any
    ) -> None:
        self._call_method(
            14,
            [c_uint, c_void_p, c_uint, c_void_p],
            ctypes.HRESULT,
            depth_point_count,
            depth_frame_ptr,
            depth_point_count,
            camera_points_ptr,
        )

    def map_depth_frame_to_color_space(
        self, depth_point_count: int, depth_frame_ptr: Any, color_points_ptr: Any
    ) -> None:
        self._call_method(
            15,
            [c_uint, c_void_p, c_uint, c_void_p],
            ctypes.HRESULT,
            depth_point_count,
            depth_frame_ptr,
            depth_point_count,
            color_points_ptr,
        )

    def map_color_frame_to_depth_space(
        self, depth_point_count: int, depth_frame_ptr: Any, color_point_count: int, depth_points_ptr: Any
    ) -> None:
        self._call_method(
            16,
            [c_uint, c_void_p, c_uint, c_void_p],
            ctypes.HRESULT,
            depth_point_count,
            depth_frame_ptr,
            color_point_count,
            depth_points_ptr,
        )

    def get_depth_camera_intrinsics(self) -> CameraIntrinsicsNative:
        intrinsics = CameraIntrinsicsNative()
        self._call_method(19, [POINTER(CameraIntrinsicsNative)], ctypes.HRESULT, byref(intrinsics))
        return intrinsics


# ==============================================================================
# AUDIO SUBSYSTEM COM INTERFACES (KINECT SDK 2.0 AUDIO)
# ==============================================================================


class IAudioBodyCorrelation(COMBase):
    """Correlation between an audio beam and a tracked body (DSP body correlation)."""

    def get_body_tracking_id(self) -> int:
        val = c_ulonglong()
        self._call_method(3, [POINTER(c_ulonglong)], ctypes.HRESULT, byref(val))
        return val.value


class IAudioBeamSubFrame(COMBase):
    """Audio sub-frame: float32 PCM samples, beam angle and body correlation."""

    def get_frame_length_in_bytes(self) -> int:
        val = c_uint()
        self._call_method(3, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def get_duration(self) -> int:
        """Sub-frame duration in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        val = c_longlong()
        self._call_method(4, [POINTER(c_longlong)], ctypes.HRESULT, byref(val))
        return val.value

    def get_beam_angle(self) -> float:
        """Beam azimuth in radians (approx. -0.87 .. +0.87 rad, i.e. -50 deg .. +50 deg)."""
        val = c_float()
        self._call_method(5, [POINTER(c_float)], ctypes.HRESULT, byref(val))
        return val.value

    def get_beam_angle_confidence(self) -> float:
        """Confidence of the beam direction in the range [0.0 .. 1.0]."""
        val = c_float()
        self._call_method(6, [POINTER(c_float)], ctypes.HRESULT, byref(val))
        return val.value

    def get_audio_body_correlation_count(self) -> int:
        val = c_uint()
        self._call_method(7, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def get_audio_body_correlation(self, index: int) -> IAudioBodyCorrelation | None:
        ptr = c_void_p()
        try:
            self._call_method(8, [c_uint, POINTER(c_void_p)], ctypes.HRESULT, index, byref(ptr))
            return IAudioBodyCorrelation(ptr) if ptr.value else None
        except COMOperationError:
            return None

    def copy_frame_data_to_array(self, capacity: int, buffer_ptr: Any) -> None:
        """Copy the sub-frame payload (1024 bytes = 256 float32 samples) into ``buffer_ptr``."""
        self._call_method(10, [c_uint, c_void_p], ctypes.HRESULT, capacity, buffer_ptr)

    def access_underlying_buffer(self) -> tuple[int, c_void_p]:
        """Return a zero-copy pointer to the native sample buffer owned by the SDK."""
        capacity = c_uint()
        buffer_ptr = c_void_p()
        self._call_method(
            11, [POINTER(c_uint), POINTER(c_void_p)], ctypes.HRESULT, byref(capacity), byref(buffer_ptr)
        )
        return capacity.value, buffer_ptr

    def get_relative_time(self) -> int:
        """Timestamp in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        val = c_longlong()
        self._call_method(12, [POINTER(c_longlong)], ctypes.HRESULT, byref(val))
        return val.value


class IAudioBeamFrame(COMBase):
    """Audio beam frame; a container for a list of sub-frames."""

    def get_audio_beam(self) -> IAudioBeam:
        ptr = c_void_p()
        self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IAudioBeam(ptr)

    def get_duration(self) -> int:
        val = c_longlong()
        self._call_method(4, [POINTER(c_longlong)], ctypes.HRESULT, byref(val))
        return val.value

    def get_relative_time_start(self) -> int:
        val = c_longlong()
        self._call_method(5, [POINTER(c_longlong)], ctypes.HRESULT, byref(val))
        return val.value

    def get_sub_frame_count(self) -> int:
        val = c_uint()
        self._call_method(6, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def get_sub_frame(self, index: int) -> IAudioBeamSubFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(7, [c_uint, POINTER(c_void_p)], ctypes.HRESULT, index, byref(ptr))
            return IAudioBeamSubFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IAudioBeamFrameList(COMBase):
    """List of acquired audio beam frames."""

    def get_count(self) -> int:
        val = c_uint()
        self._call_method(3, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def open_audio_beam_frame(self, index: int) -> IAudioBeamFrame | None:
        ptr = c_void_p()
        try:
            self._call_method(4, [c_uint, POINTER(c_void_p)], ctypes.HRESULT, index, byref(ptr))
            return IAudioBeamFrame(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IAudioBeam(COMBase):
    """Control of audio beam direction (beamforming)."""

    def get_audio_source(self) -> IAudioSource:
        ptr = c_void_p()
        self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IAudioSource(ptr)

    def get_audio_beam_mode(self) -> int:
        val = c_int()
        self._call_method(4, [POINTER(c_int)], ctypes.HRESULT, byref(val))
        return val.value

    def put_audio_beam_mode(self, mode: int) -> None:
        self._call_method(5, [c_int], ctypes.HRESULT, mode)

    def get_beam_angle(self) -> float:
        val = c_float()
        self._call_method(6, [POINTER(c_float)], ctypes.HRESULT, byref(val))
        return val.value

    def put_beam_angle(self, angle_radians: float) -> None:
        self._call_method(7, [c_float], ctypes.HRESULT, angle_radians)

    def get_beam_angle_confidence(self) -> float:
        val = c_float()
        self._call_method(8, [POINTER(c_float)], ctypes.HRESULT, byref(val))
        return val.value

    def get_relative_time(self) -> int:
        val = c_longlong()
        self._call_method(9, [POINTER(c_longlong)], ctypes.HRESULT, byref(val))
        return val.value


class IAudioBeamList(COMBase):
    """List of hardware-supported audio beams."""

    def get_beam_count(self) -> int:
        val = c_uint()
        self._call_method(3, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def open_audio_beam(self, index: int) -> IAudioBeam:
        ptr = c_void_p()
        self._call_method(4, [c_uint, POINTER(c_void_p)], ctypes.HRESULT, index, byref(ptr))
        return IAudioBeam(ptr)


class IAudioBeamFrameReader(COMBase):
    """Reader for the audio beam frame stream."""

    def subscribe_frame_arrived(self) -> int:
        handle = c_void_p()
        self._call_method(3, [POINTER(c_void_p)], ctypes.HRESULT, byref(handle))
        return handle.value or 0

    def unsubscribe_frame_arrived(self, handle: int) -> None:
        self._call_method(4, [c_void_p], ctypes.HRESULT, c_void_p(handle))

    def acquire_latest_beam_frames(self) -> IAudioBeamFrameList | None:
        ptr = c_void_p()
        try:
            self._call_method(6, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
            return IAudioBeamFrameList(ptr) if ptr.value else None
        except COMOperationError:
            return None


class IAudioSource(COMBase):
    """Audio data source for the Kinect v2 microphone array."""

    def get_is_active(self) -> bool:
        val = c_bool()
        self._call_method(6, [POINTER(c_bool)], ctypes.HRESULT, byref(val))
        return val.value

    def get_sub_frame_length_in_bytes(self) -> int:
        val = c_uint()
        self._call_method(8, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def get_sub_frame_duration(self) -> int:
        """Default sub-frame duration in 100-nanosecond ticks (Windows ``TIMESPAN``)."""
        val = c_longlong()
        self._call_method(9, [POINTER(c_longlong)], ctypes.HRESULT, byref(val))
        return val.value

    def get_max_sub_frame_count_for_read(self) -> int:
        val = c_uint()
        self._call_method(10, [POINTER(c_uint)], ctypes.HRESULT, byref(val))
        return val.value

    def open_reader(self) -> IAudioBeamFrameReader:
        ptr = c_void_p()
        self._call_method(11, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IAudioBeamFrameReader(ptr)

    def get_audio_beams(self) -> IAudioBeamList:
        ptr = c_void_p()
        self._call_method(12, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IAudioBeamList(ptr)


class IKinectSensorNative(COMBase):
    def open(self) -> None:
        self._call_method(6, [], ctypes.HRESULT)

    def close(self) -> None:
        self._call_method(7, [], ctypes.HRESULT)

    def is_open(self) -> bool:
        val = c_bool()
        self._call_method(8, [POINTER(c_bool)], ctypes.HRESULT, byref(val))
        return val.value

    def is_available(self) -> bool:
        val = c_bool()
        self._call_method(9, [POINTER(c_bool)], ctypes.HRESULT, byref(val))
        return val.value

    def get_audio_source(self) -> IAudioSource:
        ptr = c_void_p()
        self._call_method(16, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return IAudioSource(ptr)

    def open_multi_source_frame_reader(self, enabled_frame_source_types: int) -> IMultiSourceFrameReader:
        ptr = c_void_p()
        self._call_method(
            17, [c_ulong, POINTER(c_void_p)], ctypes.HRESULT, enabled_frame_source_types, byref(ptr)
        )
        return IMultiSourceFrameReader(ptr)

    def get_coordinate_mapper(self) -> ICoordinateMapper:
        ptr = c_void_p()
        self._call_method(18, [POINTER(c_void_p)], ctypes.HRESULT, byref(ptr))
        return ICoordinateMapper(ptr)
