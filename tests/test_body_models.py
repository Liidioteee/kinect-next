"""Skeleton data models and the remaining frame-model corners."""

from __future__ import annotations

import numpy as np
import pytest

from kinect_next import (
    BodyIndexFrame,
    ColorFrame,
    CoordinateMapper,
    DepthFrame,
    FrameSet,
    InfraredFrame,
    Joint,
    JointCollection,
    JointType,
    Point2D,
    Quaternion,
    TrackingState,
    Vector3,
)
from kinect_next.models.audio import AudioBeamSubFrame, AudioFrame
from tests.fakes import FakeMapper


def _collection() -> JointCollection:
    return JointCollection(
        {
            jt: Joint(jt, Vector3(float(jt), 0.0, 2.0), TrackingState.TRACKED, Quaternion(0, 0, 0, 1))
            for jt in JointType
        }
    )


def test_joint_collection_is_addressable_by_type_index_and_name() -> None:
    joints = _collection()
    assert len(joints) == 25
    assert joints[JointType.HAND_LEFT] is joints[7] is joints.hand_left
    assert joints.get(JointType.HEAD) is joints.head
    assert [j.joint_type for j in joints] == list(JointType)


def test_every_joint_has_a_named_accessor() -> None:
    joints = _collection()
    for joint_type in JointType:
        assert getattr(joints, joint_type.name.lower()).joint_type is joint_type


def test_joint_collection_lookups_fail_cleanly() -> None:
    empty = JointCollection()
    assert len(empty) == 0 and empty.get(JointType.HEAD) is None
    with pytest.raises(KeyError):
        _ = empty[JointType.HEAD]
    with pytest.raises(ValueError):
        _collection()[99]


def test_joint_projection_helpers() -> None:
    mapper = CoordinateMapper(FakeMapper())  # type: ignore[arg-type]
    joint = Joint(JointType.HEAD, Vector3(1.0, 2.0, 1.5), TrackingState.TRACKED, Quaternion(0, 0, 0, 1))
    assert joint.to_depth_space(mapper) == Point2D(100.0, 200.0)
    assert joint.to_color_space(mapper) == Point2D(300.0, 400.0)


def test_frame_dimensions() -> None:
    color = ColorFrame(data=np.zeros((1080, 1920, 4), dtype=np.uint8))
    depth = DepthFrame(data=np.zeros((424, 512), dtype=np.uint16))
    infrared = InfraredFrame(data=np.zeros((424, 512), dtype=np.uint16))
    index = BodyIndexFrame(data=np.full((424, 512), 255, dtype=np.uint8))
    assert (color.width, color.height) == (1920, 1080)
    assert (depth.width, depth.height) == (512, 424)
    assert (infrared.width, infrared.height) == (512, 424)
    assert (index.width, index.height) == (512, 424)
    assert color.as_bgra() is color.data


def test_depth_helpers_handle_out_of_range_input() -> None:
    depth = DepthFrame(data=np.zeros((424, 512), dtype=np.uint16))
    assert depth.distance_at(-1, 0) == 0.0 and depth.distance_at(0, 424) == 0.0
    assert not depth.to_normalized_uint8().any(), "a frame with no reliable depth is all black"


def test_frameset_defaults_and_tracked_bodies() -> None:
    frames = FrameSet()
    assert frames.bodies == [] and frames.tracked_bodies == []
    assert frames.color is None and frames.audio is None and frames.relative_time_ns == 0


def test_audio_metadata_properties() -> None:
    sub = AudioBeamSubFrame(data=np.zeros(256, dtype=np.float32), beam_angle=0.5, beam_angle_confidence=0.7)
    frame = AudioFrame(subframes=[sub])
    assert sub.sample_rate == frame.sample_rate == 16_000
    assert sub.samples_count == 256
    assert sub.beam_angle_deg == pytest.approx(28.6479, abs=1e-3)
    assert frame.beam_angle_deg == pytest.approx(sub.beam_angle_deg)
    assert frame.beam_angle_confidence == 0.7
    assert frame.data is sub.data, "a single sub-frame is returned without copying"
    assert frame.rms == 0.0 and frame.dbfs == -120.0
