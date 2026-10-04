"""``AudioController``: beam mode, steering and joint tracking (no hardware)."""

from __future__ import annotations

import math

import pytest

import kinect_next.core.audio as audio_mod
from kinect_next import (
    AudioBeamMode,
    AudioController,
    AudioStreamError,
    Body,
    FrameEdges,
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
)
from tests.fakes import FakeBeam


@pytest.fixture(autouse=True)
def _fast_settle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_mod, "_MODE_SETTLE_S", 0.02)
    monkeypatch.setattr(audio_mod, "_MODE_POLL_S", 0.001)


def _controller(honours_manual: bool = True) -> tuple[AudioController, FakeBeam]:
    beam = FakeBeam(honours_manual=honours_manual)
    return AudioController(beam), beam  # type: ignore[arg-type]


def _joint(joint_type: JointType, x: float, y: float, z: float) -> Joint:
    return Joint(joint_type, Vector3(x, y, z), TrackingState.TRACKED, Quaternion(0, 0, 0, 1))


def _body(head: tuple[float, float, float], spine: tuple[float, float, float], tracked: bool = True) -> Body:
    joints = {jt: _joint(jt, 0.0, 0.0, 2.0) for jt in JointType}
    joints[JointType.HEAD] = _joint(JointType.HEAD, *head)
    joints[JointType.SPINE_SHOULDER] = _joint(JointType.SPINE_SHOULDER, *spine)
    hand = Hand(HandState.OPEN, TrackingConfidence.HIGH)
    return Body(
        tracking_id=1,
        is_tracked=tracked,
        is_restricted=False,
        joints=JointCollection(joints),
        hand_left=hand,
        hand_right=hand,
        lean=Point2D(0.0, 0.0),
        lean_tracking_state=TrackingState.TRACKED,
        clipped_edges=FrameEdges.NONE,
    )


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------
def test_mode_round_trip() -> None:
    controller, beam = _controller()
    assert controller.mode is AudioBeamMode.AUTOMATIC
    controller.mode = AudioBeamMode.MANUAL
    assert controller.mode is AudioBeamMode.MANUAL and beam.mode == 1
    controller.mode = AudioBeamMode.AUTOMATIC
    assert controller.mode is AudioBeamMode.AUTOMATIC


def test_an_ignored_mode_change_raises_instead_of_passing_silently() -> None:
    """Regression: the runtime may accept MANUAL with S_OK and stay AUTOMATIC."""
    controller, beam = _controller(honours_manual=False)
    with pytest.raises(AudioStreamError, match="did not switch the audio beam to MANUAL"):
        controller.mode = AudioBeamMode.MANUAL
    assert beam.mode_requests == [1]
    assert controller.mode is AudioBeamMode.AUTOMATIC


def test_a_late_mode_change_is_still_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runtime applies the change asynchronously; give it a moment."""
    controller, beam = _controller(honours_manual=False)
    readings = iter([0, 0, 1, 1, 1])
    monkeypatch.setattr(beam, "get_audio_beam_mode", lambda: next(readings))
    monkeypatch.setattr(audio_mod, "_MODE_SETTLE_S", 1.0)
    controller.mode = AudioBeamMode.MANUAL  # must not raise


def test_supports_manual_steering_probes_and_restores() -> None:
    controller, beam = _controller()
    assert controller.supports_manual_steering is True
    assert beam.mode_requests == [1, 0]
    assert controller.mode is AudioBeamMode.AUTOMATIC

    controller, beam = _controller(honours_manual=False)
    assert controller.supports_manual_steering is False
    assert controller.mode is AudioBeamMode.AUTOMATIC


def test_supports_manual_steering_when_already_manual() -> None:
    controller, beam = _controller()
    controller.mode = AudioBeamMode.MANUAL
    beam.mode_requests.clear()
    assert controller.supports_manual_steering is True
    assert beam.mode_requests == [], "an already-manual beam needs no probing"


# ---------------------------------------------------------------------------
# Steering
# ---------------------------------------------------------------------------
def test_set_beam_angle_switches_to_manual_and_converts_to_radians() -> None:
    controller, beam = _controller()
    assert controller.set_beam_angle(-20.0) == -20.0
    assert beam.mode == 1
    assert beam.angle == pytest.approx(math.radians(-20.0))
    assert controller.beam_angle == pytest.approx(math.radians(-20.0))
    assert controller.beam_angle_deg == pytest.approx(-20.0)


@pytest.mark.parametrize(("requested", "applied"), [(80.0, 50.0), (-75.0, -50.0), (12.5, 12.5)])
def test_set_beam_angle_clamps_to_the_array_field_of_view(requested: float, applied: float) -> None:
    controller, beam = _controller()
    assert controller.set_beam_angle(requested) == applied
    assert beam.angle == pytest.approx(math.radians(applied))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_set_beam_angle_rejects_non_finite_values(bad: float) -> None:
    controller, beam = _controller()
    with pytest.raises(ValueError, match="finite"):
        controller.set_beam_angle(bad)
    assert beam.mode_requests == []


def test_set_beam_angle_fails_loudly_when_manual_is_unavailable() -> None:
    controller, beam = _controller(honours_manual=False)
    with pytest.raises(AudioStreamError):
        controller.set_beam_angle(10.0)
    assert beam.angle == 0.0, "the angle must not be written in AUTOMATIC mode"


def test_beam_angle_deg_is_assignable() -> None:
    controller, beam = _controller()
    controller.beam_angle_deg = 30.0
    assert beam.angle == pytest.approx(math.radians(30.0))


def test_confidence_and_repr() -> None:
    controller, beam = _controller()
    beam.confidence = 0.8
    beam.angle = math.radians(15.0)
    assert controller.beam_angle_confidence == 0.8
    assert repr(controller) == "<AudioController mode=AUTOMATIC angle=+15.0 deg>"


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------
def test_track_joint_points_at_the_joint_azimuth() -> None:
    controller, beam = _controller()
    angle = controller.track_joint(_joint(JointType.HEAD, 1.0, 0.3, 1.0))
    assert angle == pytest.approx(45.0)
    assert beam.angle == pytest.approx(math.radians(45.0))


@pytest.mark.parametrize("position", [(0.0, 0.0, 0.1), (0.0, 0.0, 0.0), (float("inf"), 0.0, 2.0)])
def test_track_joint_rejects_unusable_positions(position: tuple[float, float, float]) -> None:
    controller, beam = _controller()
    with pytest.raises(AudioStreamError, match="no usable position"):
        controller.track_joint(_joint(JointType.HEAD, *position))
    assert beam.mode_requests == []


def test_track_body_aims_at_the_head() -> None:
    controller, _beam = _controller()
    assert controller.track_body(_body(head=(-1.0, 0.5, 1.0), spine=(0.0, 0.0, 2.0))) == pytest.approx(-45.0)


def test_track_body_falls_back_to_the_spine() -> None:
    controller, _beam = _controller()
    angle = controller.track_body(_body(head=(0.0, 0.0, 0.0), spine=(1.0, 0.0, 1.0)))
    assert angle == pytest.approx(45.0)


def test_track_body_ignores_untracked_or_unusable_bodies() -> None:
    controller, beam = _controller()
    assert controller.track_body(_body(head=(0, 0, 2), spine=(0, 0, 2), tracked=False)) is None
    assert controller.track_body(_body(head=(0, 0, 0), spine=(0, 0, 0.1))) is None
    assert beam.mode_requests == []
