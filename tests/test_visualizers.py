"""Drawing helpers and speaker detection.

The drawing functions are exercised twice: against a recording stand-in for
``cv2`` (so the suite needs no OpenCV), and against real OpenCV when it is
installed.
"""

from __future__ import annotations

import builtins
import math
import sys
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import kinect_next.utils.audio_visualizer as audio_viz
import kinect_next.utils.visualizer as viz
from kinect_next import (
    SKELETON_BONES,
    AudioBeamSubFrame,
    AudioFrame,
    Body,
    CoordinateMapper,
    FrameEdges,
    FrameSet,
    Hand,
    HandState,
    Joint,
    JointCollection,
    JointType,
    Point2D,
    Quaternion,
    TrackingConfidence,
    TrackingState,
    Vector3,
    draw_all_skeletons,
    draw_audio_radar,
    draw_audio_visual_overlay,
    draw_body_skeleton,
    find_speaking_body,
)
from tests.fakes import FakeMapper


class RecordingCv2:
    """Records every drawing call instead of rasterising it."""

    LINE_AA = 16
    FONT_HERSHEY_SIMPLEX = 0

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _record(self, name: str) -> Any:
        def call(*args: Any) -> None:
            self.calls.append((name, args))

        return call

    def __getattr__(self, name: str) -> Any:
        if name == "getTextSize":
            return lambda text, *_a: ((len(text) * 10, 12), 4)
        return self._record(name)

    def named(self, name: str) -> list[tuple[Any, ...]]:
        return [args for call, args in self.calls if call == name]


@pytest.fixture
def cv2(monkeypatch: pytest.MonkeyPatch) -> RecordingCv2:
    recorder = RecordingCv2()
    monkeypatch.setattr(viz, "_cv2", lambda: recorder)
    monkeypatch.setattr(audio_viz, "_cv2", lambda: recorder)
    return recorder


@pytest.fixture
def mapper() -> CoordinateMapper:
    return CoordinateMapper(FakeMapper())  # type: ignore[arg-type]


def _body(
    tracking_id: int = 1,
    *,
    tracked: bool = True,
    head: tuple[float, float, float] = (1.0, 1.0, 2.0),
    spine: tuple[float, float, float] = (1.0, 1.5, 2.0),
    untracked_joints: tuple[JointType, ...] = (),
    hands: tuple[HandState, HandState] = (HandState.OPEN, HandState.CLOSED),
) -> Body:
    joints: dict[JointType, Joint] = {}
    for jt in JointType:
        state = TrackingState.NOT_TRACKED if jt in untracked_joints else TrackingState.TRACKED
        joints[jt] = Joint(jt, Vector3(1.0 + 0.01 * jt, 1.0 + 0.02 * jt, 2.0), state, Quaternion(0, 0, 0, 1))
    joints[JointType.HEAD] = Joint(
        JointType.HEAD, Vector3(*head), TrackingState.TRACKED, Quaternion(0, 0, 0, 1)
    )
    joints[JointType.SPINE_SHOULDER] = Joint(
        JointType.SPINE_SHOULDER, Vector3(*spine), TrackingState.TRACKED, Quaternion(0, 0, 0, 1)
    )
    return Body(
        tracking_id=tracking_id,
        is_tracked=tracked,
        is_restricted=False,
        joints=JointCollection(joints),
        hand_left=Hand(hands[0], TrackingConfidence.HIGH),
        hand_right=Hand(hands[1], TrackingConfidence.HIGH),
        lean=Point2D(0.0, 0.0),
        lean_tracking_state=TrackingState.TRACKED,
        clipped_edges=FrameEdges.NONE,
    )


def _audio(angle_deg: float = 0.0, confidence: float = 0.9, ids: tuple[int, ...] = ()) -> AudioFrame:
    sub = AudioBeamSubFrame(
        data=np.full(256, 0.1, dtype=np.float32),
        beam_angle=math.radians(angle_deg),
        beam_angle_confidence=confidence,
        correlated_body_ids=ids,
    )
    return AudioFrame(subframes=[sub])


def _canvas(height: int = 1080, width: int = 1920) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# find_speaking_body
# ---------------------------------------------------------------------------
def test_speaker_is_the_body_closest_to_the_beam() -> None:
    left = _body(1, head=(-1.0, 0.0, 1.0))  # azimuth -45 deg
    right = _body(2, head=(1.0, 0.0, 1.0))  # azimuth +45 deg
    assert find_speaking_body([left, right], math.radians(40.0), 0.9) is right
    assert find_speaking_body([left, right], math.radians(-50.0), 0.9) is left


def test_speaker_needs_confidence_and_a_matching_direction() -> None:
    body = _body(1, head=(1.0, 0.0, 1.0))
    assert find_speaking_body([body], math.radians(45.0), 0.1) is None  # low confidence
    assert find_speaking_body([body], math.radians(0.0), 0.9) is None  # 45 deg off
    assert find_speaking_body([body], math.radians(0.0), 0.9, tolerance_deg=50.0) is body
    assert find_speaking_body([], 0.0, 0.9) is None


def test_untracked_bodies_are_never_speakers() -> None:
    assert find_speaking_body([_body(1, tracked=False, head=(0, 0, 2))], 0.0, 0.9) is None


def test_speaker_falls_back_to_the_spine_when_the_head_is_unusable() -> None:
    body = _body(1, head=(0.0, 0.0, 0.0), spine=(1.0, 0.0, 1.0))
    assert find_speaking_body([body], math.radians(45.0), 0.9) is body
    lost = _body(2, head=(0.0, 0.0, 0.0), spine=(float("nan"), 0.0, 1.0))
    assert find_speaking_body([lost], math.radians(45.0), 0.9) is None


def test_the_sensors_own_correlation_wins() -> None:
    """With working audio-body correlation the DSP's answer beats the geometry."""
    near_beam = _body(1, head=(0.0, 0.0, 2.0))
    correlated = _body(2, head=(1.5, 0.0, 1.0))
    bodies = [near_beam, correlated]
    assert find_speaking_body(bodies, 0.0, 0.9) is near_beam
    assert find_speaking_body(bodies, 0.0, 0.9, correlated_body_ids=[2]) is correlated
    assert find_speaking_body(bodies, 0.0, 0.0, correlated_body_ids=[2]) is correlated
    assert find_speaking_body(bodies, 0.0, 0.9, correlated_body_ids=[99]) is near_beam


# ---------------------------------------------------------------------------
# Skeletons
# ---------------------------------------------------------------------------
def test_skeleton_bones_form_a_tree_over_all_joints() -> None:
    assert len(SKELETON_BONES) == 24
    assert {joint for bone in SKELETON_BONES for joint in bone} == set(JointType)


def test_a_tracked_body_draws_every_bone_and_joint(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    draw_body_skeleton(_canvas(), _body(), mapper)
    assert len(cv2.named("line")) == len(SKELETON_BONES)
    circles = cv2.named("circle")
    assert len(circles) == 25 + 2  # joints + two hand-state rings
    left_ring, right_ring = circles[-2], circles[-1]
    assert left_ring[3] == viz.HAND_STATE_COLORS[HandState.OPEN]
    assert right_ring[3] == viz.HAND_STATE_COLORS[HandState.CLOSED]


def test_skeleton_coordinates_follow_the_target_space(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    body = _body(head=(1.0, 1.0, 2.0))
    draw_body_skeleton(_canvas(), body, mapper, target_space="color")
    assert (300, 200) in [args[1] for args in cv2.named("circle")]

    cv2.calls.clear()
    draw_body_skeleton(_canvas(424, 512), body, mapper, target_space="depth")
    assert (100, 100) in [args[1] for args in cv2.named("circle")]


def test_untracked_joints_and_their_bones_are_omitted(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    draw_body_skeleton(_canvas(), _body(untracked_joints=(JointType.HAND_LEFT,)), mapper)
    # HAND_LEFT takes part in two bones (wrist-hand, hand-tip).
    assert len(cv2.named("line")) == len(SKELETON_BONES) - 2
    assert len(cv2.named("circle")) == 24 + 1  # no joint dot, no left hand ring


def test_unprojectable_joints_are_skipped(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    draw_body_skeleton(_canvas(), _body(head=(0.0, 0.0, 0.0)), mapper)  # z == 0 -> -inf
    assert len(cv2.named("circle")) == 24 + 2
    assert len(cv2.named("line")) == len(SKELETON_BONES) - 1


def test_an_untracked_body_draws_nothing(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    draw_body_skeleton(_canvas(), _body(tracked=False), mapper)
    assert cv2.calls == []


def test_draw_all_skeletons_draws_only_tracked_bodies(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    draw_all_skeletons(_canvas(), [_body(1), _body(2, tracked=False), _body(3)], mapper)
    assert len(cv2.named("line")) == 2 * len(SKELETON_BONES)


# ---------------------------------------------------------------------------
# Audio radar and overlay
# ---------------------------------------------------------------------------
def test_radar_beam_points_along_the_beam_angle(cv2: RecordingCv2) -> None:
    draw_audio_radar(_canvas(), beam_angle_deg=0.0, confidence=0.9, dbfs=-20.0, center=(500, 500), radius=100)
    beam = cv2.named("line")[-1]
    assert beam[1] == (500, 500) and beam[2] == (500, 400)  # straight ahead = up
    assert beam[3] == (0, 255, 0)  # confident -> green

    cv2.calls.clear()
    draw_audio_radar(_canvas(), 50.0, 0.9, -20.0, center=(500, 500), radius=100)
    end = cv2.named("line")[-1][2]
    assert end[0] > 500 and end[1] < 500  # positive angle swings right


@pytest.mark.parametrize(
    ("confidence", "color"),
    [(0.9, (0, 255, 0)), (0.3, (0, 255, 255)), (0.05, (200, 200, 200))],
)
def test_radar_colour_reflects_confidence(
    cv2: RecordingCv2, confidence: float, color: tuple[int, ...]
) -> None:
    draw_audio_radar(_canvas(), 0.0, confidence, -20.0)
    assert cv2.named("line")[-1][3] == color


@pytest.mark.parametrize(("dbfs", "rings"), [(-120.0, 0), (-40.0, 1), (-12.0, 1), (0.0, 1)])
def test_radar_volume_ring(cv2: RecordingCv2, dbfs: float, rings: int) -> None:
    draw_audio_radar(_canvas(), 0.0, 0.9, dbfs, center=(500, 500), radius=100)
    volume = [args for args in cv2.named("circle") if args[1] == (500, 500) and args[4] == 1]
    assert len(volume) == rings


def test_radar_defaults_to_the_bottom_right_corner(cv2: RecordingCv2) -> None:
    draw_audio_radar(_canvas(480, 640), 0.0, 0.9, -20.0)
    assert cv2.named("circle")[0][1] == (640 - 65 - 25, 480 - 65 - 25)
    labels = [args[1] for args in cv2.named("putText")]
    assert labels == ["+0.0 deg", "-20.0 dB"]


def test_overlay_needs_audio(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    draw_audio_visual_overlay(_canvas(), FrameSet(bodies=[_body()]), mapper)
    draw_audio_visual_overlay(_canvas(), FrameSet(audio=AudioFrame()), mapper)
    assert cv2.calls == []


def test_overlay_tags_the_speaker(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    speaker = _body(1, head=(1.0, 2.0, 1.0))  # azimuth 45 deg -> colour pixel (300, 400)
    frames = FrameSet(bodies=[speaker], audio=_audio(angle_deg=45.0))
    draw_audio_visual_overlay(_canvas(), frames, mapper)
    badges = [args[1] for args in cv2.named("putText") if "SPEAKING" in str(args[1])]
    assert badges == ["SPEAKING [+45.0 deg]"] * 2
    assert (300, 380) in [args[1] for args in cv2.named("circle")]


def test_overlay_uses_depth_space_when_asked(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    frames = FrameSet(bodies=[_body(1, head=(1.0, 2.0, 1.0))], audio=_audio(angle_deg=45.0))
    draw_audio_visual_overlay(_canvas(424, 512), frames, mapper, target_space="depth")
    assert (100, 180) in [args[1] for args in cv2.named("circle")]


def test_overlay_prefers_the_correlated_body(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    quiet = _body(1, head=(0.0, 1.0, 2.0))
    talker = _body(2, head=(2.0, 3.0, 2.0))  # 45 deg off the beam, but correlated
    frames = FrameSet(bodies=[quiet, talker], audio=_audio(angle_deg=0.0, ids=(2,)))
    draw_audio_visual_overlay(_canvas(), frames, mapper)
    assert (600, 580) in [args[1] for args in cv2.named("circle")]


def test_overlay_without_a_speaker_draws_only_the_radar(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    frames = FrameSet(bodies=[_body(1, head=(0.0, 1.0, 2.0))], audio=_audio(angle_deg=45.0))
    draw_audio_visual_overlay(_canvas(), frames, mapper)
    assert not [a for a in cv2.named("putText") if "SPEAKING" in str(a[1])]
    assert cv2.named("ellipse")


def test_overlay_survives_an_unprojectable_head(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    """Regression: a head at -inf pixel coordinates used to raise OverflowError."""
    body = _body(1, head=(0.0, 0.0, 0.0), spine=(1.0, 0.0, 1.0))  # speaker found via the spine
    frames = FrameSet(bodies=[body], audio=_audio(angle_deg=45.0))
    draw_audio_visual_overlay(_canvas(), frames, mapper)
    assert not [a for a in cv2.named("putText") if "SPEAKING" in str(a[1])]


def test_overlay_skips_a_speaker_outside_the_image(cv2: RecordingCv2, mapper: CoordinateMapper) -> None:
    frames = FrameSet(bodies=[_body(1, head=(50.0, 50.0, 50.0))], audio=_audio(angle_deg=45.0))
    draw_audio_visual_overlay(_canvas(), frames, mapper)
    assert not [a for a in cv2.named("putText") if "SPEAKING" in str(a[1])]


# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module", [viz, audio_viz])
def test_a_missing_opencv_gives_an_actionable_error(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def no_cv2(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "cv2":
            raise ImportError("No module named 'cv2'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "cv2", raising=False)
    monkeypatch.setattr(builtins, "__import__", no_cv2)
    with pytest.raises(ImportError, match=r"kinect-next\[viz\]"):
        module._cv2()


@pytest.mark.parametrize("module", [viz, audio_viz])
def test_opencv_is_imported_lazily(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = SimpleNamespace(name="fake-cv2")
    monkeypatch.setitem(sys.modules, "cv2", sentinel)
    assert module._cv2() is sentinel


# ---------------------------------------------------------------------------
# Real OpenCV (when installed)
# ---------------------------------------------------------------------------
def test_real_opencv_renders_skeleton_and_overlay(mapper: CoordinateMapper) -> None:
    pytest.importorskip("cv2")
    image = _canvas()
    speaker = _body(1, head=(1.0, 2.0, 1.0))
    draw_all_skeletons(image, [speaker], mapper)
    assert image.any(), "the skeleton left no pixels"

    overlay = _canvas()
    draw_audio_visual_overlay(overlay, FrameSet(bodies=[speaker], audio=_audio(45.0)), mapper)
    assert overlay[-150:, -150:].any(), "the radar is missing from the bottom-right corner"
    assert overlay[330:370, 250:350].any(), "the SPEAKING badge is missing above the head"

    depth_view = _canvas(424, 512)
    draw_body_skeleton(depth_view, speaker, mapper, target_space="depth")
    assert depth_view.any()
