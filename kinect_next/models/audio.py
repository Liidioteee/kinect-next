"""Audio data models, acoustic metrics and WAV export."""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

from kinect_next.core.enums import AudioBeamMode

KINECT_AUDIO_SAMPLE_RATE: Final = 16_000
KINECT_AUDIO_CHANNELS: Final = 1  # mono stream after hardware beamforming
_SILENCE_DBFS: Final = -120.0
_INT16_PEAK: Final = 32_767.0


def _rms(samples: npt.NDArray[np.float32]) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def _dbfs(rms: float) -> float:
    return _SILENCE_DBFS if rms <= 1e-9 else 20.0 * math.log10(rms)


@dataclass(slots=True, frozen=True)
class AudioBeamSubFrame:
    """One Kinect v2 audio sub-frame (~16 ms, 256 float32 PCM samples)."""

    data: npt.NDArray[np.float32]  # shape (256,), values in [-1.0, 1.0]
    beam_angle: float  # azimuth in radians (approx. -0.87 .. +0.87 rad)
    beam_angle_confidence: float  # [0.0, 1.0]
    mode: AudioBeamMode = AudioBeamMode.AUTOMATIC
    duration_ms: float = 16.0
    relative_time_ns: int = 0
    correlated_body_ids: tuple[int, ...] = ()

    @property
    def sample_rate(self) -> int:
        """Sample rate in Hz (always 16000)."""
        return KINECT_AUDIO_SAMPLE_RATE

    @property
    def beam_angle_deg(self) -> float:
        """Beam angle in degrees (-50 .. +50)."""
        return math.degrees(self.beam_angle)

    @property
    def samples_count(self) -> int:
        """Number of PCM samples in this sub-frame."""
        return len(self.data)

    @property
    def rms(self) -> float:
        """Root-mean-square amplitude of the sub-frame."""
        return _rms(self.data)

    @property
    def dbfs(self) -> float:
        """Loudness in decibels relative to full scale (dBFS)."""
        return _dbfs(self.rms)

    def as_int16(self) -> npt.NDArray[np.int16]:
        """Convert float32 ``[-1, 1]`` samples to 16-bit PCM."""
        return (np.clip(self.data, -1.0, 1.0) * _INT16_PEAK).astype(np.int16)


@dataclass(slots=True)
class AudioFrame:
    """The sub-frames that accumulated during one video tick (usually 2-3, ~32-48 ms)."""

    subframes: list[AudioBeamSubFrame] = field(default_factory=list)

    @property
    def sample_rate(self) -> int:
        """Sample rate in Hz (always 16000)."""
        return KINECT_AUDIO_SAMPLE_RATE

    @property
    def is_empty(self) -> bool:
        """``True`` when the frame carries no sub-frames."""
        return not self.subframes

    @property
    def data(self) -> npt.NDArray[np.float32]:
        """All sub-frame samples concatenated into one float32 PCM array."""
        if not self.subframes:
            return np.empty(0, dtype=np.float32)
        if len(self.subframes) == 1:
            return self.subframes[0].data
        return np.concatenate([sf.data for sf in self.subframes])

    @property
    def duration_ms(self) -> float:
        """Total duration of all sub-frames in milliseconds."""
        return sum(sf.duration_ms for sf in self.subframes)

    @property
    def beam_angle(self) -> float:
        """Beam angle of the most recent sub-frame, in radians."""
        return self.subframes[-1].beam_angle if self.subframes else 0.0

    @property
    def beam_angle_deg(self) -> float:
        """Beam angle of the most recent sub-frame, in degrees."""
        return math.degrees(self.beam_angle)

    @property
    def beam_angle_confidence(self) -> float:
        """Beam-direction confidence of the most recent sub-frame."""
        return self.subframes[-1].beam_angle_confidence if self.subframes else 0.0

    @property
    def correlated_body_ids(self) -> list[int]:
        """Distinct tracking IDs of people the DSP believes are speaking now."""
        ids: set[int] = set()
        for sf in self.subframes:
            ids.update(sf.correlated_body_ids)
        return list(ids)

    @property
    def rms(self) -> float:
        """Root-mean-square amplitude of the concatenated frame."""
        return _rms(self.data)

    @property
    def dbfs(self) -> float:
        """Loudness of the concatenated frame in dBFS."""
        return _dbfs(self.rms)

    def as_int16(self) -> npt.NDArray[np.int16]:
        """Concatenated samples as 16-bit PCM."""
        return (np.clip(self.data, -1.0, 1.0) * _INT16_PEAK).astype(np.int16)

    def to_wav_bytes(self, format_type: Literal["int16", "float32"] = "int16") -> bytes:
        """Return the frame as the bytes of a RIFF WAV file (16 kHz, mono)."""
        buf = io.BytesIO()
        if format_type == "int16":
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(KINECT_AUDIO_CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(KINECT_AUDIO_SAMPLE_RATE)
                wf.writeframes(self.as_int16().tobytes())
            return buf.getvalue()

        # 32-bit IEEE float WAV (WAVE_FORMAT_IEEE_FLOAT = 3), written by hand.
        float_bytes = np.ascontiguousarray(self.data, dtype="<f4").tobytes()
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + len(float_bytes),
            b"WAVE",
            b"fmt ",
            16,
            3,
            KINECT_AUDIO_CHANNELS,
            KINECT_AUDIO_SAMPLE_RATE,
            KINECT_AUDIO_SAMPLE_RATE * 4,
            4,
            32,
            b"data",
            len(float_bytes),
        )
        buf.write(header)
        buf.write(float_bytes)
        return buf.getvalue()

    def save_wav(self, file_path: str | Path, format_type: Literal["int16", "float32"] = "int16") -> None:
        """Write the frame to ``file_path`` as a WAV file, creating parent dirs."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.to_wav_bytes(format_type=format_type))
