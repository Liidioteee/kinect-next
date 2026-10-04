"""Microphone-array beam controller (hardware beamforming)."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Final

from kinect_next.core.enums import AudioBeamMode
from kinect_next.core.exceptions import AudioStreamError
from kinect_next.native.interfaces import IAudioBeam

if TYPE_CHECKING:
    from kinect_next.models.body import Body, Joint

MIN_BEAM_ANGLE_DEG: Final = -50.0
MAX_BEAM_ANGLE_DEG: Final = 50.0
_MIN_TRACKABLE_Z_M: Final = 0.2

# The runtime applies a mode change asynchronously; give it a moment before
# concluding that the request was ignored.
_MODE_SETTLE_S: Final = 0.25
_MODE_POLL_S: Final = 0.01


class AudioController:
    """High-level controller for the Kinect v2 hardware beamformer.

    The beam is either ``AUTOMATIC`` (the DSP follows the dominant sound source)
    or ``MANUAL`` (you steer it, e.g. onto a tracked person).

    .. note::
       Some Kinect runtime / firmware combinations accept the request for
       ``MANUAL`` mode but keep the beam in ``AUTOMATIC``. The controller verifies
       every mode change and raises :class:`AudioStreamError` instead of silently
       doing nothing; use :attr:`supports_manual_steering` to probe up front.
    """

    __slots__ = ("_beam",)

    def __init__(self, beam: IAudioBeam) -> None:
        self._beam = beam

    def __repr__(self) -> str:
        return f"<AudioController mode={self.mode.name} angle={self.beam_angle_deg:+.1f} deg>"

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------
    @property
    def mode(self) -> AudioBeamMode:
        """Current beam mode (``AUTOMATIC`` = DSP tracking, ``MANUAL`` = steered)."""
        return AudioBeamMode(self._beam.get_audio_beam_mode())

    @mode.setter
    def mode(self, new_mode: AudioBeamMode) -> None:
        new_mode = AudioBeamMode(new_mode)
        if not self._request_mode(new_mode):
            raise AudioStreamError(
                f"The Kinect runtime did not switch the audio beam to {new_mode.name} "
                f"(it is still {self.mode.name}). Manual beam steering is not available "
                "with this sensor / runtime."
            )

    def _request_mode(self, new_mode: AudioBeamMode) -> bool:
        """Ask for ``new_mode`` and report whether the runtime actually applied it."""
        self._beam.put_audio_beam_mode(int(new_mode))
        deadline = time.monotonic() + _MODE_SETTLE_S
        while True:
            if self._beam.get_audio_beam_mode() == new_mode:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(_MODE_POLL_S)

    @property
    def supports_manual_steering(self) -> bool:
        """Whether this sensor honours ``MANUAL`` mode.

        Probing briefly switches the beam to ``MANUAL`` and restores the previous
        mode afterwards.
        """
        previous = self.mode
        if previous is AudioBeamMode.MANUAL:
            return True
        supported = self._request_mode(AudioBeamMode.MANUAL)
        if supported:
            self._request_mode(previous)
        return supported

    # ------------------------------------------------------------------
    # Angle
    # ------------------------------------------------------------------
    @property
    def beam_angle(self) -> float:
        """Current beam angle in radians."""
        return self._beam.get_beam_angle()

    @property
    def beam_angle_deg(self) -> float:
        """Current beam angle in degrees (range -50 .. +50). Assign to steer the beam."""
        return math.degrees(self.beam_angle)

    @beam_angle_deg.setter
    def beam_angle_deg(self, angle_deg: float) -> None:
        self.set_beam_angle(angle_deg)

    @property
    def beam_angle_confidence(self) -> float:
        """Confidence of the current beam direction, in the range [0.0 .. 1.0]."""
        return self._beam.get_beam_angle_confidence()

    def set_beam_angle(self, angle_deg: float) -> float:
        """Steer the beam to ``angle_deg`` degrees and return the angle actually used.

        The angle is clamped to -50 .. +50 and the beam is switched into
        :attr:`AudioBeamMode.MANUAL` if necessary.

        Raises
        ------
        ValueError
            If ``angle_deg`` is not a finite number.
        AudioStreamError
            If the runtime refuses to enter ``MANUAL`` mode.
        """
        if not math.isfinite(angle_deg):
            raise ValueError(f"Beam angle must be finite, got {angle_deg!r}.")
        clamped_deg = max(MIN_BEAM_ANGLE_DEG, min(MAX_BEAM_ANGLE_DEG, angle_deg))
        if self.mode is not AudioBeamMode.MANUAL:
            self.mode = AudioBeamMode.MANUAL
        self._beam.put_beam_angle(math.radians(clamped_deg))
        return clamped_deg

    # ------------------------------------------------------------------
    # Tracking helpers
    # ------------------------------------------------------------------
    def track_joint(self, joint: Joint) -> float:
        """Point the microphone array at a joint and return the beam angle in degrees.

        The azimuth is ``atan2(x, z)`` in the horizontal plane of camera space.

        Raises
        ------
        AudioStreamError
            If the joint position is invalid or closer than 0.2 m to the sensor,
            or the runtime refuses to enter ``MANUAL`` mode.
        """
        pos = joint.position
        if not pos.is_valid() or pos.z <= _MIN_TRACKABLE_Z_M:
            raise AudioStreamError("Joint has no usable position (invalid or z <= 0.2 m).")
        return self.set_beam_angle(math.degrees(math.atan2(pos.x, pos.z)))

    def track_body(self, body: Body) -> float | None:
        """Point the microphone array at a person's head (or upper spine).

        Returns the beam angle in degrees, or ``None`` when ``body`` is not
        tracked or has no usable head / spine position.
        """
        if not body.is_tracked:
            return None
        for joint in (body.joints.head, body.joints.spine_shoulder):
            pos = joint.position
            if pos.is_valid() and pos.z > _MIN_TRACKABLE_Z_M:
                return self.track_joint(joint)
        return None
