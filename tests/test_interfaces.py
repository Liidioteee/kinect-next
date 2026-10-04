"""Every interface method must call the SDK method it claims to wrap.

``EXPECTED`` is an independent, hand-written statement of intent ("this Python
method wraps that header method"). Each method is invoked through a real VTable
(``FakeCOMObject``) and the slot that was hit is compared with the slot the SDK
header assigns to the expected method. Combined with ``test_vtable_layout.py``
this catches both a mis-ordered VTable and a method wired to the wrong name.
"""

from __future__ import annotations

import ctypes
import inspect
from ctypes import c_float, c_int, c_longlong, c_ubyte, c_uint, c_ulonglong, c_ushort, c_void_p

import pytest

from kinect_next.core.exceptions import COMOperationError
from kinect_next.native import interfaces as native
from kinect_next.native.com_base import COMBase
from kinect_next.native.types import (
    CameraIntrinsicsNative,
    CameraSpacePoint,
    DepthSpacePoint,
    JointNative,
    JointOrientationNative,
    PointF,
    Vector4Native,
)
from tests.fake_com import E_PENDING, FakeCOMObject, write
from tests.kinect_header import HEADER_NAMES, load_snapshot

_PLANAR = {"copy_frame_data_to_array": "CopyFrameDataToArray", "get_relative_time": "get_RelativeTime"}
_REFERENCE = {"acquire_frame": "AcquireFrame"}

EXPECTED: dict[str, dict[str, str]] = {
    "IFrameDescription": {
        "get_width": "get_Width",
        "get_height": "get_Height",
        "get_length_in_pixels": "get_LengthInPixels",
        "get_bytes_per_pixel": "get_BytesPerPixel",
    },
    "IColorCameraSettings": {
        "get_exposure_time": "get_ExposureTime",
        "get_frame_interval": "get_FrameInterval",
        "get_gain": "get_Gain",
        "get_gamma": "get_Gamma",
    },
    "IColorFrame": {
        "copy_converted_frame_data_to_array": "CopyConvertedFrameDataToArray",
        "get_color_camera_settings": "get_ColorCameraSettings",
        "get_relative_time": "get_RelativeTime",
    },
    "IDepthFrame": {
        **_PLANAR,
        "get_min_reliable_distance": "get_DepthMinReliableDistance",
        "get_max_reliable_distance": "get_DepthMaxReliableDistance",
    },
    "IInfraredFrame": _PLANAR,
    "ILongExposureInfraredFrame": _PLANAR,
    "IBodyIndexFrame": _PLANAR,
    "IBody": {
        "get_joints": "GetJoints",
        "get_joint_orientations": "GetJointOrientations",
        "get_hand_left_state": "get_HandLeftState",
        "get_hand_left_confidence": "get_HandLeftConfidence",
        "get_hand_right_state": "get_HandRightState",
        "get_hand_right_confidence": "get_HandRightConfidence",
        "get_clipped_edges": "get_ClippedEdges",
        "get_tracking_id": "get_TrackingId",
        "get_is_tracked": "get_IsTracked",
        "get_is_restricted": "get_IsRestricted",
        "get_lean": "get_Lean",
        "get_lean_tracking_state": "get_LeanTrackingState",
    },
    "IBodyFrame": {
        "get_bodies": "GetAndRefreshBodyData",
        "get_floor_clip_plane": "get_FloorClipPlane",
        "get_relative_time": "get_RelativeTime",
    },
    "IColorFrameReference": _REFERENCE,
    "IDepthFrameReference": _REFERENCE,
    "IBodyFrameReference": _REFERENCE,
    "IBodyIndexFrameReference": _REFERENCE,
    "IInfraredFrameReference": _REFERENCE,
    "ILongExposureInfraredFrameReference": _REFERENCE,
    "IMultiSourceFrame": {
        "get_color_frame_reference": "get_ColorFrameReference",
        "get_depth_frame_reference": "get_DepthFrameReference",
        "get_body_frame_reference": "get_BodyFrameReference",
        "get_body_index_frame_reference": "get_BodyIndexFrameReference",
        "get_infrared_frame_reference": "get_InfraredFrameReference",
        "get_long_exposure_infrared_frame_reference": "get_LongExposureInfraredFrameReference",
    },
    "IMultiSourceFrameReader": {
        "subscribe_frame_arrived": "SubscribeMultiSourceFrameArrived",
        "unsubscribe_frame_arrived": "UnsubscribeMultiSourceFrameArrived",
        "clear_frame_arrived": "GetMultiSourceFrameArrivedEventData",
        "acquire_latest_frame": "AcquireLatestFrame",
    },
    "ICoordinateMapper": {
        "map_camera_point_to_depth_space": "MapCameraPointToDepthSpace",
        "map_camera_point_to_color_space": "MapCameraPointToColorSpace",
        "map_depth_point_to_camera_space": "MapDepthPointToCameraSpace",
        "map_depth_point_to_color_space": "MapDepthPointToColorSpace",
        "map_depth_frame_to_camera_space": "MapDepthFrameToCameraSpace",
        "map_depth_frame_to_color_space": "MapDepthFrameToColorSpace",
        "map_color_frame_to_depth_space": "MapColorFrameToDepthSpace",
        "get_depth_camera_intrinsics": "GetDepthCameraIntrinsics",
    },
    "IAudioBodyCorrelation": {"get_body_tracking_id": "get_BodyTrackingId"},
    "IAudioBeamSubFrame": {
        "get_frame_length_in_bytes": "get_FrameLengthInBytes",
        "get_duration": "get_Duration",
        "get_beam_angle": "get_BeamAngle",
        "get_beam_angle_confidence": "get_BeamAngleConfidence",
        "get_audio_beam_mode": "get_AudioBeamMode",
        "get_audio_body_correlation_count": "get_AudioBodyCorrelationCount",
        "get_audio_body_correlation": "GetAudioBodyCorrelation",
        "copy_frame_data_to_array": "CopyFrameDataToArray",
        "access_underlying_buffer": "AccessUnderlyingBuffer",
        "get_relative_time": "get_RelativeTime",
    },
    "IAudioBeamFrame": {
        "get_duration": "get_Duration",
        "get_audio_beam": "get_AudioBeam",
        "get_sub_frame_count": "get_SubFrameCount",
        "get_sub_frame": "GetSubFrame",
        "get_relative_time_start": "get_RelativeTimeStart",
    },
    "IAudioBeamFrameList": {
        "get_count": "get_BeamCount",
        "open_audio_beam_frame": "OpenAudioBeamFrame",
    },
    "IAudioBeam": {
        "get_audio_source": "get_AudioSource",
        "get_audio_beam_mode": "get_AudioBeamMode",
        "put_audio_beam_mode": "put_AudioBeamMode",
        "get_beam_angle": "get_BeamAngle",
        "put_beam_angle": "put_BeamAngle",
        "get_beam_angle_confidence": "get_BeamAngleConfidence",
        "get_relative_time": "get_RelativeTime",
    },
    "IAudioBeamList": {
        "get_beam_count": "get_BeamCount",
        "open_audio_beam": "OpenAudioBeam",
    },
    "IAudioBeamFrameReader": {
        "subscribe_frame_arrived": "SubscribeFrameArrived",
        "unsubscribe_frame_arrived": "UnsubscribeFrameArrived",
        "clear_frame_arrived": "GetFrameArrivedEventData",
        "acquire_latest_beam_frames": "AcquireLatestBeamFrames",
    },
    "IAudioSource": {
        "get_is_active": "get_IsActive",
        "get_sub_frame_length_in_bytes": "get_SubFrameLengthInBytes",
        "get_sub_frame_duration": "get_SubFrameDuration",
        "get_max_sub_frame_count_for_read": "get_MaxSubFrameCount",
        "open_reader": "OpenReader",
        "get_audio_beams": "get_AudioBeams",
        "get_audio_calibration_state": "get_AudioCalibrationState",
    },
    "IKinectSensor": {
        "open": "Open",
        "close": "Close",
        "is_open": "get_IsOpen",
        "is_available": "get_IsAvailable",
        "get_audio_source": "get_AudioSource",
        "open_multi_source_frame_reader": "OpenMultiSourceFrameReader",
        "get_coordinate_mapper": "get_CoordinateMapper",
    },
}

_PYTHON_NAMES = {header: python for python, header in HEADER_NAMES.items()}
_SNAPSHOT = load_snapshot()
_CASES = [(iface, method) for iface, methods in EXPECTED.items() for method in methods]


def _wrapper_class(header_name: str) -> type[COMBase]:
    cls: type[COMBase] = getattr(native, _PYTHON_NAMES.get(header_name, header_name))
    return cls


def _public_methods(cls: type) -> set[str]:
    base = set(vars(COMBase))
    return {
        name
        for klass in cls.__mro__
        if klass not in (COMBase, object)
        for name, value in vars(klass).items()
        if inspect.isfunction(value) and not name.startswith("_") and name not in base
    }


def _dummy_arguments(func: object) -> list[object]:
    scratch = ctypes.create_string_buffer(4096)
    values: dict[str, object] = {
        "int": 1,
        "float": 0.5,
        "Any": scratch,
        "CameraSpacePoint": CameraSpacePoint(0.0, 0.0, 1.0),
        "DepthSpacePoint": DepthSpacePoint(1.0, 2.0),
    }
    params = list(inspect.signature(func).parameters.values())  # type: ignore[arg-type]
    return [values[str(p.annotation)] for p in params]


def test_expected_table_covers_every_wrapper_method() -> None:
    assert sorted(EXPECTED) == sorted(_SNAPSHOT)
    for header_name, methods in EXPECTED.items():
        assert _public_methods(_wrapper_class(header_name)) == set(methods), header_name


@pytest.mark.parametrize(("iface", "method"), _CASES, ids=[f"{i}.{m}" for i, m in _CASES])
def test_method_dispatches_to_the_header_slot(iface: str, method: str) -> None:
    fake = FakeCOMObject(slots=40)
    obj = _wrapper_class(iface)(fake.address, owned=False)
    bound = getattr(obj, method)
    try:
        bound(*_dummy_arguments(bound))
    except COMOperationError as exc:
        # The fake leaves interface out-pointers NULL; the call itself still happened.
        assert "NULL interface pointer" in str(exc)

    expected_slot = 3 + _SNAPSHOT[iface].index(EXPECTED[iface][method])
    assert fake.calls == [expected_slot]


# ---------------------------------------------------------------------------
# Value marshalling
# ---------------------------------------------------------------------------
def _slot(cls: type[COMBase], header_method: str) -> int:
    return cls._slots_[header_method]


def test_scalar_getters_decode_their_native_types() -> None:
    fake = FakeCOMObject(slots=40)
    desc = native.IFrameDescription(fake.address, owned=False)
    fake.on(_slot(native.IFrameDescription, "get_Width"), lambda a1, *_: write(a1, c_int(512)) or 0)
    fake.on(
        _slot(native.IFrameDescription, "get_LengthInPixels"), lambda a1, *_: write(a1, c_uint(217088)) or 0
    )
    assert desc.get_width() == 512
    assert desc.get_length_in_pixels() == 217088

    fake = FakeCOMObject(slots=40)
    depth = native.IDepthFrame(fake.address, owned=False)
    fake.on(
        _slot(native.IDepthFrame, "get_DepthMaxReliableDistance"),
        lambda a1, *_: write(a1, c_ushort(4500)) or 0,
    )
    fake.on(_slot(native.IDepthFrame, "get_RelativeTime"), lambda a1, *_: write(a1, c_longlong(2**40)) or 0)
    assert depth.get_max_reliable_distance() == 4500
    assert depth.get_relative_time() == 2**40

    fake = FakeCOMObject(slots=40)
    body = native.IBody(fake.address, owned=False)
    fake.on(_slot(native.IBody, "get_TrackingId"), lambda a1, *_: write(a1, c_ulonglong(2**63 + 5)) or 0)
    fake.on(_slot(native.IBody, "get_IsTracked"), lambda a1, *_: write(a1, c_ubyte(1)) or 0)
    fake.on(_slot(native.IBody, "get_Lean"), lambda a1, *_: write(a1, PointF(0.25, -0.5)) or 0)
    assert body.get_tracking_id() == 2**63 + 5
    assert body.get_is_tracked() is True
    lean = body.get_lean()
    assert (lean.x, lean.y) == (0.25, -0.5)


def test_boolean_getters_do_not_overrun_their_one_byte_buffer() -> None:
    """Regression: ``get_is_active`` used to hit ``get_KinectSensor`` (an 8-byte write)."""
    fake = FakeCOMObject(slots=40)
    source = native.IAudioSource(fake.address, owned=False)
    fake.on(_slot(native.IAudioSource, "get_IsActive"), lambda a1, *_: write(a1, c_ubyte(1)) or 0)
    assert source.get_is_active() is True
    assert fake.calls == [3 + _SNAPSHOT["IAudioSource"].index("get_IsActive")]
    assert fake.calls != [3 + _SNAPSHOT["IAudioSource"].index("get_KinectSensor")]


def test_joint_arrays_are_filled_by_the_native_call() -> None:
    fake = FakeCOMObject(slots=40)

    def fill_joints(count: int, array: int, _a3: int) -> int:
        joints = (JointNative * count).from_address(array)
        for i in range(count):
            joints[i].JointType = i
            joints[i].Position.z = 1.0 + i
            joints[i].TrackingState = 2
        return 0

    def fill_orientations(count: int, array: int, _a3: int) -> int:
        orientations = (JointOrientationNative * count).from_address(array)
        for i in range(count):
            orientations[i].Orientation.w = 1.0
        return 0

    fake.on(_slot(native.IBody, "GetJoints"), fill_joints)
    fake.on(_slot(native.IBody, "GetJointOrientations"), fill_orientations)
    body = native.IBody(fake.address, owned=False)
    joints = body.get_joints(25)
    assert len(joints) == 25
    assert [j.JointType for j in joints] == list(range(25))
    assert joints[24].Position.z == 25.0
    assert body.get_joint_orientations(25)[3].Orientation.w == 1.0


def test_get_bodies_wraps_only_populated_slots() -> None:
    fake = FakeCOMObject(slots=40)
    bodies = [FakeCOMObject(slots=40) for _ in range(2)]

    def fill(count: int, array: int, _a3: int) -> int:
        slots = (c_void_p * count).from_address(array)
        slots[0] = bodies[0].address
        slots[4] = bodies[1].address
        return 0

    fake.on(_slot(native.IBodyFrame, "GetAndRefreshBodyData"), fill)
    wrapped = native.IBodyFrame(fake.address, owned=False).get_bodies(6)
    assert [b.ptr for b in wrapped] == [bodies[0].address, bodies[1].address]
    for body in wrapped:
        body.release()
    assert [b.refcount for b in bodies] == [0, 0]


def test_acquire_returns_none_while_the_frame_is_pending() -> None:
    fake = FakeCOMObject(slots=40)
    reader = native.IMultiSourceFrameReader(fake.address, owned=False)
    fake.on(_slot(native.IMultiSourceFrameReader, "AcquireLatestFrame"), lambda *_: E_PENDING)
    assert reader.acquire_latest_frame() is None

    frame = FakeCOMObject(slots=40)
    fake.on(
        _slot(native.IMultiSourceFrameReader, "AcquireLatestFrame"),
        lambda a1, *_: write(a1, c_void_p(frame.address)) or 0,
    )
    acquired = reader.acquire_latest_frame()
    assert acquired is not None and acquired.ptr == frame.address
    acquired.release()


@pytest.mark.parametrize(
    ("cls", "subscribe", "event_data"),
    [
        (
            native.IMultiSourceFrameReader,
            "SubscribeMultiSourceFrameArrived",
            "GetMultiSourceFrameArrivedEventData",
        ),
        (native.IAudioBeamFrameReader, "SubscribeFrameArrived", "GetFrameArrivedEventData"),
    ],
)
def test_frame_arrived_subscription_and_rearm(cls: type[COMBase], subscribe: str, event_data: str) -> None:
    fake = FakeCOMObject(slots=40)
    event_args = FakeCOMObject()
    seen_handles: list[int] = []

    def pop_event(handle: int, out: int, _a3: int) -> int:
        seen_handles.append(handle)
        write(out, c_void_p(event_args.address))
        return 0

    fake.on(_slot(cls, subscribe), lambda a1, *_: write(a1, c_void_p(0xABC0)) or 0)
    fake.on(_slot(cls, event_data), pop_event)
    reader = cls(fake.address, owned=False)

    handle = reader.subscribe_frame_arrived()  # type: ignore[attr-defined]
    assert handle == 0xABC0
    reader.clear_frame_arrived(handle)  # type: ignore[attr-defined]
    assert seen_handles == [0xABC0]
    assert event_args.refcount == 0, "the event args must be released, not leaked"


def test_clear_frame_arrived_tolerates_an_empty_event_queue() -> None:
    fake = FakeCOMObject(slots=40)
    fake.on(_slot(native.IAudioBeamFrameReader, "GetFrameArrivedEventData"), lambda *_: E_PENDING)
    native.IAudioBeamFrameReader(fake.address, owned=False).clear_frame_arrived(0x10)


def test_audio_body_correlation_uses_count_then_indexed_lookup() -> None:
    """Regression: these two used to be shifted by one slot (mode read as the count)."""
    fake = FakeCOMObject(slots=40)
    correlation = FakeCOMObject()
    requested: list[int] = []

    def lookup(index: int, out: int, _a3: int) -> int:
        requested.append(index)
        write(out, c_void_p(correlation.address))
        return 0

    sub = native.IAudioBeamSubFrame
    fake.on(_slot(sub, "get_AudioBeamMode"), lambda a1, *_: write(a1, c_int(1)) or 0)
    fake.on(_slot(sub, "get_AudioBodyCorrelationCount"), lambda a1, *_: write(a1, c_uint(3)) or 0)
    fake.on(_slot(sub, "GetAudioBodyCorrelation"), lookup)
    correlation.on(3, lambda a1, *_: write(a1, c_ulonglong(72057594037928000)) or 0)

    subframe = sub(fake.address, owned=False)
    assert subframe.get_audio_beam_mode() == 1
    assert subframe.get_audio_body_correlation_count() == 3
    found = subframe.get_audio_body_correlation(2)
    assert requested == [2]
    assert found is not None and found.get_body_tracking_id() == 72057594037928000
    found.release()


def test_access_underlying_buffer_returns_size_and_address() -> None:
    fake = FakeCOMObject(slots=40)

    def access(size_out: int, ptr_out: int, _a3: int) -> int:
        write(size_out, c_uint(1024))
        write(ptr_out, c_void_p(0x5000))
        return 0

    fake.on(_slot(native.IAudioBeamSubFrame, "AccessUnderlyingBuffer"), access)
    assert native.IAudioBeamSubFrame(fake.address, owned=False).access_underlying_buffer() == (1024, 0x5000)


def test_beam_setters_pass_their_values() -> None:
    fake = FakeCOMObject(slots=40)
    modes: list[int] = []
    fake.on(_slot(native.IAudioBeam, "put_AudioBeamMode"), lambda a1, *_: modes.append(a1) or 0)
    beam = native.IAudioBeam(fake.address, owned=False)
    beam.put_audio_beam_mode(1)
    beam.put_beam_angle(0.5)  # the float travels in XMM1; only the dispatch is observable
    assert modes == [1]
    assert fake.calls[-1] == _slot(native.IAudioBeam, "put_BeamAngle")


def test_structs_are_passed_by_value_per_the_x64_abi() -> None:
    """A 12-byte ``CameraSpacePoint`` goes by hidden pointer, an 8-byte point in a register."""
    fake = FakeCOMObject(slots=40)
    mapper = native.ICoordinateMapper

    def camera_to_depth(point: int, out: int, _a3: int) -> int:
        src = CameraSpacePoint.from_address(point)
        write(out, DepthSpacePoint(src.x * 100.0, src.z * 100.0))
        return 0

    def depth_to_camera(point_bits: int, depth: int, out: int) -> int:
        packed = ctypes.c_uint64(point_bits)
        src = DepthSpacePoint.from_buffer_copy(packed)
        write(out, CameraSpacePoint(src.x, src.y, (depth & 0xFFFF) / 1000.0))
        return 0

    fake.on(_slot(mapper, "MapCameraPointToDepthSpace"), camera_to_depth)
    fake.on(_slot(mapper, "MapDepthPointToCameraSpace"), depth_to_camera)
    obj = mapper(fake.address, owned=False)

    depth_pt = obj.map_camera_point_to_depth_space(CameraSpacePoint(1.5, 9.0, 2.5))
    assert (depth_pt.x, depth_pt.y) == (150.0, 250.0)
    camera_pt = obj.map_depth_point_to_camera_space(DepthSpacePoint(256.0, 212.0), 1500)
    assert (camera_pt.x, camera_pt.y, camera_pt.z) == (256.0, 212.0, 1.5)


def test_depth_camera_intrinsics_struct() -> None:
    fake = FakeCOMObject(slots=40)
    intrinsics = CameraIntrinsicsNative(366.0, 366.5, 255.0, 206.0, 0.1, 0.2, 0.3)
    fake.on(
        _slot(native.ICoordinateMapper, "GetDepthCameraIntrinsics"), lambda a1, *_: write(a1, intrinsics) or 0
    )
    got = native.ICoordinateMapper(fake.address, owned=False).get_depth_camera_intrinsics()
    assert (got.FocalLengthX, got.FocalLengthY, got.PrincipalPointX, got.PrincipalPointY) == (
        366.0,
        366.5,
        255.0,
        206.0,
    )


def test_floor_plane_and_float_getters() -> None:
    fake = FakeCOMObject(slots=40)
    fake.on(
        _slot(native.IBodyFrame, "get_FloorClipPlane"),
        lambda a1, *_: write(a1, Vector4Native(0.0, 1.0, 0.0, 0.8)) or 0,
    )
    floor = native.IBodyFrame(fake.address, owned=False).get_floor_clip_plane()
    assert (floor.y, floor.w) == (1.0, pytest.approx(0.8))

    fake = FakeCOMObject(slots=40)
    fake.on(_slot(native.IColorCameraSettings, "get_Gain"), lambda a1, *_: write(a1, c_float(4.0)) or 0)
    assert native.IColorCameraSettings(fake.address, owned=False).get_gain() == 4.0
