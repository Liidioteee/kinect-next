"""Живой тест: непрерывная запись 5 секунд реального звука и отслеживание луча."""

import time
import numpy as np
from pathlib import Path

from kinect_next import KinectSensor, StreamType
from kinect_next.models.audio import AudioFrame

print("1. Запуск KinectSensor с потоком StreamType.AUDIO | StreamType.BODY...")

all_subframes = []
record_duration_sec = 5.0
output_wav = Path("kinect_live_5sec.wav")

with KinectSensor(streams=StreamType.AUDIO | StreamType.BODY) as kinect:
    print(f" -> Сенсор открыт. Режим луча: {kinect.audio.mode.name}")
    print(f" -> Начинаем запись звука на {record_duration_sec} сек...")
    print(" -> ГОВОРИТЕ ИЛИ ИЗДАВАЙТЕ ЗВУКИ С РАЗНЫХ СТОРОН ОТ СЕНСОРА!\n")
    print("Время  | Угол луча | Уверенность | Громкость (dBFS) | VU-Индикатор")
    print("-" * 65)

    start_time = time.time()
    packet_count = 0

    for audio_frame in kinect.poll_audio():
        packet_count += 1
        all_subframes.extend(audio_frame.subframes)

        # Вычисляем визуальный VU-метр
        db = audio_frame.dbfs
        norm_db = max(0, min(30, int((db + 60) / 2)))  # от -60 dBFS до 0 dBFS
        vu_bar = "█" * norm_db + "░" * (30 - norm_db)

        elapsed = time.time() - start_time
        print(f"{elapsed:4.1f}s | {audio_frame.beam_angle_deg:+5.1f}°   |   {audio_frame.beam_angle_confidence:.2f}      | {db:+5.1f} dBFS  | {vu_bar}")

        if elapsed >= record_duration_sec:
            break

# Формируем итоговый AudioFrame
full_audio = AudioFrame(subframes=all_subframes)
full_audio.save_wav(output_wav, format_type="int16")

print("-" * 65)
print(f"\n2. Запись завершена!")
print(f" -> Получено аудиопакетов: {packet_count}")
print(f" -> Всего субкадров: {len(all_subframes)}")
print(f" -> Всего сэмплов Float32: {len(full_audio.data):,}")
print(f" -> Итоговая длительность: {full_audio.duration_ms / 1000.0:.2f} сек.")
print(f" -> Итоговый RMS: {full_audio.rms:.6f}")
print(f" -> Файл сохранен: {output_wav.resolve()} ({output_wav.stat().st_size:,} байт)")

assert output_wav.exists() and output_wav.stat().st_size > 1000, "WAV файл не был создан или пуст"
assert full_audio.rms > 0.0, "RMS звука равен нулю"

print("\n✅ ШАГ 7 (КОНТРОЛЛЕР И ЖИВАЯ ЗАПИСЬ АУДИО) УСПЕШНО ВЫПОЛНЕН!")