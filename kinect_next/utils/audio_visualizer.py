"""OpenCV helpers for the sound-field radar and audio-visual fusion overlay.

``opencv-python`` is imported lazily; ``import kinect_next`` does not require it.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from kinect_next.core.mapper import CoordinateMapper
    from kinect_next.models.body import Body
    from kinect_next.models.frameset import FrameSet


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "opencv-python is required for kinect_next.utils drawing helpers. "
            'Install it with: pip install "kinect-next[viz]"'
        ) from exc
    return cv2


def find_speaking_body(
    bodies: list[Body],
    beam_angle_rad: float,
    confidence: float,
    min_confidence: float = 0.3,
    tolerance_deg: float = 14.0,
) -> Body | None:
    """Return the tracked body whose head azimuth best matches the audio beam.

    Parameters
    ----------
    bodies:
        Candidate bodies (typically ``FrameSet.tracked_bodies``).
    beam_angle_rad:
        Acoustic beam angle in radians.
    confidence:
        Beam-direction confidence in ``[0, 1]``.
    min_confidence:
        Below this confidence the function returns ``None``.
    tolerance_deg:
        Maximum allowed azimuth error, in degrees.
    """
    if confidence < min_confidence or not bodies:
        return None

    target_deg = math.degrees(beam_angle_rad)
    best_body: Body | None = None
    min_diff = float("inf")

    for body in bodies:
        if not body.is_tracked:
            continue

        pos = body.joints.head.position
        if not pos.is_valid() or pos.z <= 0.2:
            pos = body.joints.spine_shoulder.position
            if not pos.is_valid() or pos.z <= 0.2:
                continue

        body_azimuth_deg = math.degrees(math.atan2(pos.x, pos.z))
        diff = abs(body_azimuth_deg - target_deg)
        if diff <= tolerance_deg and diff < min_diff:
            min_diff = diff
            best_body = body

    return best_body


def draw_audio_radar(
    image: npt.NDArray[np.uint8],
    beam_angle_deg: float,
    confidence: float,
    dbfs: float,
    center: tuple[int, int] | None = None,
    radius: int = 65,
) -> None:
    """Draw a polar radar of the microphone array's -50..+50 deg field of view."""
    cv2 = _cv2()
    h, w = image.shape[:2]
    cx, cy = center if center is not None else (w - radius - 25, h - radius - 25)

    overlay = image.copy()
    cv2.circle(overlay, (cx, cy), radius + 12, (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, image, 0.25, 0, image)

    # Field of view: -50 deg (220 deg) .. +50 deg (320 deg) in OpenCV angle space
    # (270 deg points straight ahead).
    cv2.ellipse(image, (cx, cy), (radius, radius), 0, 220, 320, (70, 70, 70), 2, cv2.LINE_AA)
    cv2.line(image, (cx, cy), (cx, cy - radius), (100, 100, 100), 1, cv2.LINE_AA)

    norm_vol = max(0.0, min(1.0, (dbfs + 60.0) / 50.0))  # -60 .. -10 dBFS
    vol_radius = int(radius * norm_vol)
    if vol_radius > 3:
        vol_color = (0, 255, 128) if norm_vol < 0.7 else (0, 165, 255) if norm_vol < 0.9 else (0, 0, 255)
        cv2.circle(image, (cx, cy), vol_radius, vol_color, 1, cv2.LINE_AA)

    beam_rad = math.radians(270.0 + beam_angle_deg)
    bx = int(cx + radius * math.cos(beam_rad))
    by = int(cy + radius * math.sin(beam_rad))

    if confidence >= 0.5:
        beam_color = (0, 255, 0)
    elif confidence > 0.1:
        beam_color = (0, 255, 255)
    else:
        beam_color = (200, 200, 200)

    cv2.line(image, (cx, cy), (bx, by), beam_color, 3, cv2.LINE_AA)
    cv2.circle(image, (bx, by), 5, beam_color, -1, cv2.LINE_AA)
    cv2.circle(image, (cx, cy), 3, (255, 255, 255), -1, cv2.LINE_AA)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(
        image,
        f"{beam_angle_deg:+4.1f} deg",
        (cx - 38, cy + radius + 2),
        font,
        0.40,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        f"{dbfs:+4.1f} dB",
        (cx - 32, cy + radius + 16),
        font,
        0.38,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )


def draw_audio_visual_overlay(
    image: npt.NDArray[np.uint8],
    frameset: FrameSet,
    mapper: CoordinateMapper,
    target_space: Literal["color", "depth"] = "color",
) -> None:
    """Draw the microphone radar and tag the speaking person above their head."""
    if frameset.audio is None or frameset.audio.is_empty:
        return
    cv2 = _cv2()

    audio = frameset.audio
    beam_deg = audio.beam_angle_deg
    beam_conf = audio.beam_angle_confidence

    draw_audio_radar(image, beam_deg, beam_conf, audio.dbfs)

    speaker = find_speaking_body(frameset.tracked_bodies, audio.beam_angle, beam_conf)
    if speaker is None:
        return

    head_pt = (
        speaker.joints.head.to_color_space(mapper)
        if target_space == "color"
        else speaker.joints.head.to_depth_space(mapper)
    )
    hx, hy = head_pt.as_int_tuple()
    if not (0 <= hx < image.shape[1] and 0 <= hy < image.shape[0]):
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    badge_text = f"SPEAKING [{beam_deg:+4.1f} deg]"
    (tw, th), _ = cv2.getTextSize(badge_text, font, 0.6, 2)
    bx1, by1 = max(0, hx - tw // 2 - 8), max(0, hy - 45 - th)
    bx2, by2 = min(image.shape[1], hx + tw // 2 + 8), min(image.shape[0], hy - 35)

    cv2.rectangle(image, (bx1, by1), (bx2, by2), (0, 200, 0), -1)
    cv2.rectangle(image, (bx1, by1), (bx2, by2), (255, 255, 255), 1)
    cv2.putText(image, badge_text, (bx1 + 6, by2 - 5), font, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(image, badge_text, (bx1 + 6, by2 - 5), font, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    cv2.circle(image, (hx, hy - 20), 8, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.circle(image, (hx, hy - 20), 4, (0, 255, 0), -1, cv2.LINE_AA)
