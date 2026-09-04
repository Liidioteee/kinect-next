"""Tests for the enum definitions."""

from __future__ import annotations

from kinect_next.core.enums import (
    JOINT_COUNT,
    AudioBeamMode,
    HandState,
    JointType,
    StreamType,
)


def test_joint_type_has_25_members() -> None:
    assert len(JointType) == 25
    assert JointType.count() == 25 == JOINT_COUNT
    assert {j.value for j in JointType} == set(range(25))


def test_stream_type_is_a_flag() -> None:
    combo = StreamType.COLOR | StreamType.DEPTH | StreamType.BODY
    assert StreamType.COLOR in combo
    assert StreamType.AUDIO not in combo
    assert combo & ~StreamType.AUDIO == combo


def test_stream_type_all_contains_every_stream() -> None:
    for member in StreamType:
        if member not in (StreamType.NONE, StreamType.ALL):
            assert member in StreamType.ALL


def test_hand_state_and_beam_mode_values() -> None:
    assert HandState.OPEN == 2
    assert HandState.CLOSED == 3
    assert AudioBeamMode.AUTOMATIC == 0
    assert AudioBeamMode.MANUAL == 1
