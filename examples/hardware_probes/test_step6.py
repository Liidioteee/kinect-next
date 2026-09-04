"""Тестирование моделей AudioBeamSubFrame, AudioFrame, конверсий и генерации WAV."""

import math
from pathlib import Path

import numpy as np

from kinect_next.core.enums import AudioBeamMode
from kinect_next.models import AudioBeamSubFrame, AudioFrame, FrameSet

# 1. Синтезируем тестовый синусоидальный сигнал 440 Гц (нота Ля) на 2 субкадра (32 мс)
sample_rate = 16000
freq = 440.0
t1 = np.linspace(0, 0.016, 256, endpoint=False)
t2 = np.linspace(0.016, 0.032, 256, endpoint=False)

data1 = (0.5 * np.sin(2 * np.pi * freq * t1)).astype(np.float32)
data2 = (0.5 * np.sin(2 * np.pi * freq * t2)).astype(np.float32)

# Создаем субкадры
sf1 = AudioBeamSubFrame(
    data=data1,
    beam_angle=math.radians(15.0),
    beam_angle_confidence=0.85,
    mode=AudioBeamMode.AUTOMATIC,
    duration_ms=16.0,
    correlated_body_ids=(101,),
)

sf2 = AudioBeamSubFrame(
    data=data2,
    beam_angle=math.radians(16.5),
    beam_angle_confidence=0.90,
    mode=AudioBeamMode.AUTOMATIC,
    duration_ms=16.0,
    correlated_body_ids=(101, 102),
)

print("1. Проверка субкадра sf1:")
print(f" -> Samples: {sf1.samples_count}")
print(f" -> Beam Angle: {sf1.beam_angle_deg:.1f}°")
print(f" -> RMS: {sf1.rms:.4f}")
print(f" -> dBFS: {sf1.dbfs:.1f} dBFS")
assert abs(sf1.beam_angle_deg - 15.0) < 1e-4
assert sf1.samples_count == 256

# 2. Проверка AudioFrame
frame = AudioFrame(subframes=[sf1, sf2])
print("\n2. Проверка агрегированного AudioFrame:")
print(f" -> Суммарно сэмплов: {len(frame.data)}")
print(f" -> Суммарная длительность: {frame.duration_ms:.1f} мс")
print(f" -> Текущий угол луча: {frame.beam_angle_deg:.1f}°")
print(f" -> Ассоциированные ID людей: {frame.correlated_body_ids}")
assert len(frame.data) == 512
assert frame.duration_ms == 32.0
assert set(frame.correlated_body_ids) == {101, 102}

# 3. Проверка векторизованной конверсии в Int16
int16_pcm = frame.as_int16()
assert int16_pcm.dtype == np.int16
assert len(int16_pcm) == 512
print(f"\n3. Int16 конверсия: мин={int16_pcm.min()}, макс={int16_pcm.max()}")

# 4. Проверка генерации и сохранения WAV файла
out_wav = Path("test_synthetic_tone.wav")
frame.save_wav(out_wav, format_type="int16")
assert out_wav.exists() and out_wav.stat().st_size > 0
print(f"\n4. WAV файл успешно сформирован: {out_wav.name} ({out_wav.stat().st_size} байт)")
out_wav.unlink()  # Удаляем временный файл

# 5. Проверка интеграции в FrameSet
frameset = FrameSet(audio=frame)
assert frameset.audio is not None
assert len(frameset.audio.data) == 512
print("\n5. FrameSet.audio успешно интегрирован!")

print("\n✅ ШАГ 6 (МОДЕЛИ ДАННЫХ И WAV-ЭКСПОРТЕР) УСПЕШНО ВЫПОЛНЕН!")