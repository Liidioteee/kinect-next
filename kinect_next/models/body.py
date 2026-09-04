"""Skeleton data models: bodies, joints and hand states."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kinect_next.core.enums import (
    FrameEdges,
    HandState,
    JointType,
    TrackingConfidence,
    TrackingState,
)
from kinect_next.models.geometry import Point2D, Quaternion, Vector3

if TYPE_CHECKING:
    from kinect_next.core.mapper import CoordinateMapper


@dataclass(slots=True, frozen=True)
class Joint:
    """A single tracked skeleton joint."""

    joint_type: JointType
    position: Vector3
    tracking_state: TrackingState
    orientation: Quaternion

    def to_depth_space(self, mapper: CoordinateMapper) -> Point2D:
        """Project this joint onto depth-frame pixel coordinates (512 x 424)."""
        return mapper.map_camera_point_to_depth_space(self.position)

    def to_color_space(self, mapper: CoordinateMapper) -> Point2D:
        """Project this joint onto colour-frame pixel coordinates (1920 x 1080)."""
        return mapper.map_camera_point_to_color_space(self.position)


@dataclass(slots=True, frozen=True)
class Hand:
    """The recognised state of one hand and its confidence."""

    state: HandState
    confidence: TrackingConfidence


@dataclass(slots=True)
class JointCollection:
    """The 25 joints of a body, addressable by :class:`JointType`, index or name."""

    _joints: dict[JointType, Joint] = field(default_factory=dict)

    def __getitem__(self, joint_type: JointType | int) -> Joint:
        return self._joints[JointType(joint_type)]

    def __iter__(self) -> Iterator[Joint]:
        return iter(self._joints.values())

    def __len__(self) -> int:
        return len(self._joints)

    def get(self, joint_type: JointType | int) -> Joint | None:
        """Return the joint, or ``None`` if it is not present."""
        return self._joints.get(JointType(joint_type))

    # Named accessors for IDE autocompletion --------------------------------
    @property
    def head(self) -> Joint:
        return self._joints[JointType.HEAD]

    @property
    def neck(self) -> Joint:
        return self._joints[JointType.NECK]

    @property
    def spine_shoulder(self) -> Joint:
        return self._joints[JointType.SPINE_SHOULDER]

    @property
    def spine_mid(self) -> Joint:
        return self._joints[JointType.SPINE_MID]

    @property
    def spine_base(self) -> Joint:
        return self._joints[JointType.SPINE_BASE]

    @property
    def shoulder_left(self) -> Joint:
        return self._joints[JointType.SHOULDER_LEFT]

    @property
    def elbow_left(self) -> Joint:
        return self._joints[JointType.ELBOW_LEFT]

    @property
    def wrist_left(self) -> Joint:
        return self._joints[JointType.WRIST_LEFT]

    @property
    def hand_left(self) -> Joint:
        return self._joints[JointType.HAND_LEFT]

    @property
    def hand_tip_left(self) -> Joint:
        return self._joints[JointType.HAND_TIP_LEFT]

    @property
    def thumb_left(self) -> Joint:
        return self._joints[JointType.THUMB_LEFT]

    @property
    def shoulder_right(self) -> Joint:
        return self._joints[JointType.SHOULDER_RIGHT]

    @property
    def elbow_right(self) -> Joint:
        return self._joints[JointType.ELBOW_RIGHT]

    @property
    def wrist_right(self) -> Joint:
        return self._joints[JointType.WRIST_RIGHT]

    @property
    def hand_right(self) -> Joint:
        return self._joints[JointType.HAND_RIGHT]

    @property
    def hand_tip_right(self) -> Joint:
        return self._joints[JointType.HAND_TIP_RIGHT]

    @property
    def thumb_right(self) -> Joint:
        return self._joints[JointType.THUMB_RIGHT]

    @property
    def hip_left(self) -> Joint:
        return self._joints[JointType.HIP_LEFT]

    @property
    def knee_left(self) -> Joint:
        return self._joints[JointType.KNEE_LEFT]

    @property
    def ankle_left(self) -> Joint:
        return self._joints[JointType.ANKLE_LEFT]

    @property
    def foot_left(self) -> Joint:
        return self._joints[JointType.FOOT_LEFT]

    @property
    def hip_right(self) -> Joint:
        return self._joints[JointType.HIP_RIGHT]

    @property
    def knee_right(self) -> Joint:
        return self._joints[JointType.KNEE_RIGHT]

    @property
    def ankle_right(self) -> Joint:
        return self._joints[JointType.ANKLE_RIGHT]

    @property
    def foot_right(self) -> Joint:
        return self._joints[JointType.FOOT_RIGHT]


@dataclass(slots=True)
class Body:
    """A person recognised by the Kinect v2 body tracker."""

    tracking_id: int
    is_tracked: bool
    is_restricted: bool
    joints: JointCollection
    hand_left: Hand
    hand_right: Hand
    lean: Point2D
    lean_tracking_state: TrackingState
    clipped_edges: FrameEdges
