"""Microphone-array beam controller (hardware beamforming)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from kinect_next.core.enums import AudioBeamMode
from kinect_next.core.exceptions import AudioStreamError
from kinect_next.native.interfaces import IAudioBeam

if TYPE_CHECKING:
    from kinect_next.models.body import Body, Joint

MIN_BEAM_ANGLE_DEG: Final = -50.0
MAX_BEAM_ANGLE_DEG: Final = 50.0
_MIN_TRACKABLE_Z_M: Final = 0.2


class AudioController:
    """High-level controller for the Kinect v2 hardware beamformer.

    It switches the beam between ``AUTOMATIC`` (DSP sound-source tracking) and
    ``MANUAL`` (software steering), and can lock the beam onto the 3D joints of a
    tracked person in real time.
    """

    __slots__ = ("_beam",)

    def __init__(self, beam: IAudioBeam) -> None:
        self._beam = beam

    @property
    def mode(self) -> AudioBeamMode:
        """Current beam mode (``AUTOMATIC`` = DSP tracking, ``MANUAL`` = steered)."""
        return AudioBeamMode(self._beam.get_audio_beam_mode())

    @mode.setter
    def mode(self, new_mode: AudioBeamMode) -> None:
        self._beam.put_audio_beam_mode(int(new_mode))

    @property
    def beam_angle(self) -> float:
        """Current beam angle in radians."""
        return self._beam.get_beam_angle()

    @property
    def beam_angle_deg(self) -> float:
        """Current beam angle in degrees (range -50 .. +50)."""
        return math.degrees(self.beam_angle)

    @beam_angle_deg.setter
    def beam_angle_deg(self, angle_deg: float) -> None:
        self.set_beam_angle(angle_deg)

    @property
    def beam_angle_confidence(self) -> float:
        """Confidence of the current beam direction, in the range [0.0 .. 1.0]."""
        return self._beam.get_beam_angle_confidence()

    def set_beam_angle(self, angle_deg: float) -> None:
        """Steer the beam to ``angle_deg`` degrees (clamped to -50 .. +50).

        Switches the beam into :attr:`AudioBeamMode.MANUAL` if necessary.
        """
        clamped_deg = max(MIN_BEAM_ANGLE_DEG, min(MAX_BEAM_ANGLE_DEG, angle_deg))
        if self.mode is not AudioBeamMode.MANUAL:
            self.mode = AudioBeamMode.MANUAL
        self._beam.put_beam_angle(math.radians(clamped_deg))

    def set_mode(self, mode: AudioBeamMode) -> None:
        """Set the beam mode (``AUTOMATIC`` / ``MANUAL``)."""
        self.mode = mode

    def track_joint(self, joint: Joint) -> None:
        """Point the microphone array at a joint's 3D camera-space position.

        The azimuth is ``atan2(x, z)`` in the horizontal plane.

        Raises
        ------
        AudioStreamError
            If the joint is closer than 0.2 m to the sensor.
        """
        pos = joint.position
        if pos.z <= _MIN_TRACKABLE_Z_M:
            raise AudioStreamError("Joint is too close to the sensor (z <= 0.2 m).")

        azimuth_deg = math.degrees(math.atan2(pos.x, pos.z))
        self.set_beam_angle(azimuth_deg)

    def track_body(self, body: Body) -> None:
        """Point the microphone array at a tracked person's head (or neck/shoulder)."""
        if not body.is_tracked:
            return
        head_joint = body.joints.head
        if head_joint.position.is_valid() and head_joint.position.z > _MIN_TRACKABLE_Z_M:
            self.track_joint(head_joint)
        else:
            self.track_joint(body.joints.spine_shoulder)
