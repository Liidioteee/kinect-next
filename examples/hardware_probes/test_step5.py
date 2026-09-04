"""Проверка работы нативного COM-слоя аудио Kinect v2."""

import ctypes
import math
import time
import numpy as np

from kinect_next.native import (
    IKinectSensorNative,
    WAIT_OBJECT_0,
    get_default_kinect_sensor,
    wait_for_single_object,
)
from kinect_next.core.enums import AudioBeamMode

print("1. Подключение к Kinect v2...")
raw_ptr = get_default_kinect_sensor()
sensor = IKinectSensorNative(raw_ptr)
sensor.open()

print("2. Ожидание готовности сенсора...")
time.sleep(1.5)

print("3. Получение интерфейса IAudioSource...")
audio_source = sensor.get_audio_source()
is_active = audio_source.get_is_active()
subframe_len_bytes = audio_source.get_sub_frame_length_in_bytes()
subframe_duration_100ns = audio_source.get_sub_frame_duration()
max_subframes = audio_source.get_max_sub_frame_count_for_read()

print(f" -> Активность источника: {is_active}")
print(f" -> Размер субкадра в байтах: {subframe_len_bytes} байт")
print(f" -> Длительность субкадра: {subframe_duration_100ns / 10_000:.1f} мс")
print(f" -> Макс. субкадров за чтение: {max_subframes}")

print("4. Проверка IAudioBeam...")
beams = audio_source.get_audio_beams()
beam_count = beams.get_beam_count()
print(f" -> Количество доступных аудиолучей: {beam_count}")
assert beam_count > 0, "Ожидался хотя бы 1 аппаратный аудиолуч"

beam = beams.open_audio_beam(0)
beam_mode = AudioBeamMode(beam.get_audio_beam_mode())
beam_angle = beam.get_beam_angle()
beam_conf = beam.get_beam_angle_confidence()
print(f" -> Режим луча: {beam_mode.name}")
print(f" -> Начальный угол луча: {math.degrees(beam_angle):.1f}° (Уверенность: {beam_conf:.2f})")

print("5. Открытие IAudioBeamFrameReader и подписка на Win32 Event...")
reader = audio_source.open_reader()
event_handle = reader.subscribe_frame_arrived()
assert event_handle != 0, "Не удалось получить Win32 Event handle для аудио"

print("6. Ожидание первого аудиокадра (до 2000 мс)...")
wait_res = wait_for_single_object(event_handle, timeout_ms=2000)
if wait_res != WAIT_OBJECT_0:
    raise TimeoutError(f"Таймаут ожидания аудиокадра. Код Win32: {wait_res}")

frame_list = reader.acquire_latest_beam_frames()
assert frame_list is not None, "AcquireLatestBeamFrames вернул NULL"

frame_list_count = frame_list.get_count()
print(f" -> Получено кадров в списке: {frame_list_count}")

first_frame = frame_list.open_audio_beam_frame(0)
assert first_frame is not None, "Не удалось открыть IAudioBeamFrame"

subframes_count = first_frame.get_sub_frame_count()
print(f" -> Субкадров в первом кадре: {subframes_count}")

if subframes_count > 0:
    subframe = first_frame.get_sub_frame(0)
    assert subframe is not None, "Не удалось получить IAudioBeamSubFrame"
    
    sf_len = subframe.get_frame_length_in_bytes()
    float_count = sf_len // 4  # 32-bit float = 4 bytes
    
    # Буфер NumPy под Float32 PCM
    pcm_buffer = np.empty(float_count, dtype=np.float32)
    subframe.copy_frame_data_to_array(sf_len, pcm_buffer.ctypes.data_as(ctypes.c_void_p))
    
    sf_beam_angle = math.degrees(subframe.get_beam_angle())
    sf_beam_conf = subframe.get_beam_angle_confidence()
    
    # Корреляция со скелетами
    corr_count = subframe.get_audio_body_correlation_count()
    
    # RMS амплитуда сигнала
    rms = float(np.sqrt(np.mean(pcm_buffer**2))) if float_count > 0 else 0.0
    
    print(f" -> Успешно извлечено {float_count} Float32 сэмплов!")
    print(f" -> Первые 5 сэмплов: {pcm_buffer[:5]}")
    print(f" -> RMS амплитуда сигнала: {rms:.6f}")
    print(f" -> Угол луча субкадра: {sf_beam_angle:.1f}° (Уверенность: {sf_beam_conf:.2f})")
    print(f" -> Корреляций с отслеживаемыми телами: {corr_count}")

print("7. Очистка ресурсов...")
reader.unsubscribe_frame_arrived(event_handle)
sensor.close()

print("✅ ШАГ 5 (НАТИВНЫЙ COM-СЛОЙ АУДИО) УСПЕШНО ВЫПОЛНЕН!")