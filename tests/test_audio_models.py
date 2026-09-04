"""Tests for the audio data models."""

from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from kinect_next.models.audio import (
    KINECT_AUDIO_SAMPLE_RATE,
    AudioBeamSubFrame,
    AudioFrame,
)


def _subframe(
    values: np.ndarray, *, angle: float = 0.0, conf: float = 1.0, ids: tuple[int, ...] = ()
) -> AudioBeamSubFrame:
    return AudioBeamSubFrame(
        data=values.astype(np.float32),
        beam_angle=angle,
        beam_angle_confidence=conf,
        correlated_body_ids=ids,
    )


def test_silence_is_minus_120_dbfs() -> None:
    sf = _subframe(np.zeros(256))
    assert sf.rms == 0.0
    assert sf.dbfs == -120.0


def test_full_scale_sine_rms() -> None:
    t = np.linspace(0, 2 * np.pi, 256, endpoint=False)
    sf = _subframe(np.sin(t))
    assert sf.rms == pytest.approx(1 / np.sqrt(2), rel=1e-3)
    assert sf.dbfs == pytest.approx(-3.01, abs=0.1)


def test_as_int16_clips() -> None:
    sf = _subframe(np.array([2.0, -2.0, 0.0, 0.5]))
    out = sf.as_int16()
    assert out.dtype == np.int16
    assert out[0] == 32767
    assert out[1] == -32767


def test_audio_frame_concatenates_subframes() -> None:
    a = _subframe(np.ones(256))
    b = _subframe(np.zeros(256))
    frame = AudioFrame([a, b])
    assert not frame.is_empty
    assert frame.data.shape == (512,)
    assert frame.duration_ms == pytest.approx(32.0)


def test_audio_frame_beam_angle_follows_last_subframe() -> None:
    frame = AudioFrame([_subframe(np.zeros(4), angle=0.1), _subframe(np.zeros(4), angle=-0.4)])
    assert frame.beam_angle == pytest.approx(-0.4)


def test_correlated_body_ids_are_deduplicated() -> None:
    frame = AudioFrame([_subframe(np.zeros(4), ids=(1, 2)), _subframe(np.zeros(4), ids=(2, 3))])
    assert sorted(frame.correlated_body_ids) == [1, 2, 3]


def test_empty_audio_frame() -> None:
    frame = AudioFrame()
    assert frame.is_empty
    assert frame.data.shape == (0,)
    assert frame.beam_angle == 0.0
    assert frame.dbfs == -120.0


def test_to_wav_bytes_int16_roundtrip() -> None:
    frame = AudioFrame([_subframe(np.linspace(-1, 1, 256))])
    with wave.open(io.BytesIO(frame.to_wav_bytes("int16")), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == KINECT_AUDIO_SAMPLE_RATE
        assert wf.getnframes() == 256


def test_to_wav_bytes_float32_header() -> None:
    frame = AudioFrame([_subframe(np.zeros(256))])
    data = frame.to_wav_bytes("float32")
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"
    # audio-format field (offset 20) == 3 => IEEE float
    assert int.from_bytes(data[20:22], "little") == 3
    assert len(data) == 44 + 256 * 4


def test_save_wav_creates_file(tmp_path) -> None:
    frame = AudioFrame([_subframe(np.zeros(256))])
    target = tmp_path / "nested" / "clip.wav"
    frame.save_wav(target)
    assert target.is_file() and target.stat().st_size > 44
