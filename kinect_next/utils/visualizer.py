"""OpenCV helpers for drawing skeletons and hand states over frames.

``opencv-python`` is an optional dependency; it is imported lazily so that
``import kinect_next`` works without it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, Literal

import numpy as np
import numpy.typing as npt

from kinect_next.core.enums import HandState, JointType, TrackingState
from kinect_next.models.body import Body
from kinect_next.models.geometry import Point2D

if TYPE_CHECKING:
    from kinect_next.core.mapper import CoordinateMapper


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "opencv-python is required for kinect_next.utils drawing helpers. "
            'Install it with: pip install "kinect-next[viz]"'
        ) from exc
    return cv2


#: Bone connections of the Kinect v2 skeleton (parent, child) joint pairs.
SKELETON_BONES: Final[tuple[tuple[JointType, JointType], ...]] = (
    # Spine and head
    (JointType.HEAD, JointType.NECK),
    (JointType.NECK, JointType.SPINE_SHOULDER),
    (JointType.SPINE_SHOULDER, JointType.SPINE_MID),
    (JointType.SPINE_MID, JointType.SPINE_BASE),
    # Left arm
    (JointType.SPINE_SHOULDER, JointType.SHOULDER_LEFT),
    (JointType.SHOULDER_LEFT, JointType.ELBOW_LEFT),
    (JointType.ELBOW_LEFT, JointType.WRIST_LEFT),
    (JointType.WRIST_LEFT, JointType.HAND_LEFT),
    (JointType.HAND_LEFT, JointType.HAND_TIP_LEFT),
    (JointType.WRIST_LEFT, JointType.THUMB_LEFT),
    # Right arm
    (JointType.SPINE_SHOULDER, JointType.SHOULDER_RIGHT),
    (JointType.SHOULDER_RIGHT, JointType.ELBOW_RIGHT),
    (JointType.ELBOW_RIGHT, JointType.WRIST_RIGHT),
    (JointType.WRIST_RIGHT, JointType.HAND_RIGHT),
    (JointType.HAND_RIGHT, JointType.HAND_TIP_RIGHT),
    (JointType.WRIST_RIGHT, JointType.THUMB_RIGHT),
    # Left leg
    (JointType.SPINE_BASE, JointType.HIP_LEFT),
    (JointType.HIP_LEFT, JointType.KNEE_LEFT),
    (JointType.KNEE_LEFT, JointType.ANKLE_LEFT),
    (JointType.ANKLE_LEFT, JointType.FOOT_LEFT),
    # Right leg
    (JointType.SPINE_BASE, JointType.HIP_RIGHT),
    (JointType.HIP_RIGHT, JointType.KNEE_RIGHT),
    (JointType.KNEE_RIGHT, JointType.ANKLE_RIGHT),
    (JointType.ANKLE_RIGHT, JointType.FOOT_RIGHT),
)

#: Hand-state indicator colours (BGR).
HAND_STATE_COLORS: Final[dict[HandState, tuple[int, int, int]]] = {
    HandState.OPEN: (0, 255, 0),
    HandState.CLOSED: (0, 0, 255),
    HandState.LASSO: (255, 255, 0),
    HandState.UNKNOWN: (128, 128, 128),
    HandState.NOT_TRACKED: (128, 128, 128),
}


def draw_body_skeleton(
    image: npt.NDArray[np.uint8],
    body: Body,
    mapper: CoordinateMapper,
    target_space: Literal["color", "depth"] = "color",
    bone_color: tuple[int, int, int] = (0, 255, 255),
    joint_color: tuple[int, int, int] = (255, 0, 0),
    joint_radius: int = 4,
    bone_thickness: int = 2,
) -> None:
    """Draw one person's bones, joints and hand-state rings onto ``image`` (in place)."""
    if not body.is_tracked:
        return
    cv2 = _cv2()

    projected: dict[JointType, Point2D] = {}
    for joint in body.joints:
        if joint.tracking_state != TrackingState.NOT_TRACKED:
            pt = joint.to_color_space(mapper) if target_space == "color" else joint.to_depth_space(mapper)
            if pt.is_valid():
                projected[joint.joint_type] = pt

    for joint_a, joint_b in SKELETON_BONES:
        if joint_a in projected and joint_b in projected:
            cv2.line(
                image,
                projected[joint_a].as_int_tuple(),
                projected[joint_b].as_int_tuple(),
                bone_color,
                bone_thickness,
                cv2.LINE_AA,
            )

    for pt in projected.values():
        cv2.circle(image, pt.as_int_tuple(), joint_radius, joint_color, -1, cv2.LINE_AA)

    hand_radius = joint_radius * 2
    for joint_type, hand in (
        (JointType.HAND_LEFT, body.hand_left),
        (JointType.HAND_RIGHT, body.hand_right),
    ):
        if joint_type in projected:
            color = HAND_STATE_COLORS.get(hand.state, (128, 128, 128))
            cv2.circle(image, projected[joint_type].as_int_tuple(), hand_radius, color, 2, cv2.LINE_AA)


def draw_all_skeletons(
    image: npt.NDArray[np.uint8],
    bodies: list[Body],
    mapper: CoordinateMapper,
    target_space: Literal["color", "depth"] = "color",
) -> None:
    """Draw every tracked person in ``bodies`` onto ``image`` (in place)."""
    for body in bodies:
        if body.is_tracked:
            draw_body_skeleton(image, body, mapper, target_space=target_space)
