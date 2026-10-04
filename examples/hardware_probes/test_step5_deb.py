"""Автоматический VTable-сканер для IAudioBeamSubFrame.

Исторический отладочный скрипт: перебирает слоты «вслепую». Раскладка VTable
теперь берётся из заголовка SDK (``Kinect.h``) и проверяется тестом
``tests/test_vtable_layout.py`` — пользуйтесь им, а не перебором.
"""

import ctypes
from ctypes import HRESULT, POINTER, byref, c_float, c_int, c_longlong, c_uint, c_void_p
import math
import time
import numpy as np

from kinect_next.native import (
    IKinectSensorNative,
    WAIT_OBJECT_0,
    get_default_kinect_sensor,
    wait_for_single_object,
)

print("1. Запуск сенсора и захват аудиокадра...")
raw_ptr = get_default_kinect_sensor()
sensor = IKinectSensorNative(raw_ptr)
sensor.open()
time.sleep(1.5)

audio_source = sensor.get_audio_source()
reader = audio_source.open_reader()
event_handle = reader.subscribe_frame_arrived()

wait_res = wait_for_single_object(event_handle, timeout_ms=2000)
assert wait_res == WAIT_OBJECT_0, "Timeout"

frame_list = reader.acquire_latest_beam_frames()
audio_frame = frame_list.open_audio_beam_frame(0)
subframe = audio_frame.get_sub_frame(0)
subframe_ptr = subframe.ptr

print(f" -> Указатель на IAudioBeamSubFrame: 0x{subframe_ptr:X}")

# Извлекаем VTable
vtable = ctypes.cast(subframe_ptr, POINTER(POINTER(c_void_p))).contents

def call_vtable(idx: int, argtypes: list, *args) -> int:
    method_addr = vtable[idx]
    proto = ctypes.WINFUNCTYPE(HRESULT, c_void_p, *argtypes)
    func = proto(method_addr)
    return func(subframe_ptr, *args)

print("\n2. Сканирование VTable индексов 3..13:")
print("-" * 65)

# Буфер под аудио
pcm_buffer = np.zeros(256, dtype=np.float32)
pcm_ptr = pcm_buffer.ctypes.data_as(c_void_p)

for idx in range(3, 14):
    results = []
    
    # 1. Пробуем (c_uint=1024, c_void_p) -> CopyFrameDataToArray
    try:
        hr = call_vtable(idx, [c_uint, c_void_p], 1024, pcm_ptr)
        if hr == 0:
            rms = float(np.sqrt(np.mean(pcm_buffer**2)))
            results.append(f"CopyFrameDataToArray (RMS={rms:.6f}, 5 samples={pcm_buffer[:3]})")
    except Exception:
        pass

    # 2. Пробуем (POINTER(c_uint), POINTER(c_void_p)) -> AccessUnderlyingBuffer
    try:
        cap = c_uint()
        buf = c_void_p()
        hr = call_vtable(idx, [POINTER(c_uint), POINTER(c_void_p)], byref(cap), byref(buf))
        if hr == 0 and cap.value == 1024 and buf.value:
            results.append(f"AccessUnderlyingBuffer (cap={cap.value}, ptr=0x{buf.value:X})")
    except Exception:
        pass

    # 3. Пробуем (c_uint=0, POINTER(c_void_p)) -> GetAudioBodyCorrelation
    try:
        corr_ptr = c_void_p()
        hr = call_vtable(idx, [c_uint, POINTER(c_void_p)], 0, byref(corr_ptr))
        if hr == 0:
            results.append(f"GetAudioBodyCorrelation (ptr=0x{corr_ptr.value or 0:X})")
    except Exception:
        pass

    # 4. Пробуем (POINTER(c_longlong)) -> Timespan / Duration / RelativeTime
    try:
        val_ll = c_longlong()
        hr = call_vtable(idx, [POINTER(c_longlong)], byref(val_ll))
        if hr == 0:
            if val_ll.value == 160000:
                results.append("get_Duration (16.0 ms)")
            else:
                results.append(f"get_RelativeTime / Timespan ({val_ll.value})")
    except Exception:
        pass

    # 5. Пробуем (POINTER(c_float)) -> Float angle / confidence
    try:
        val_f = c_float()
        hr = call_vtable(idx, [POINTER(c_float)], byref(val_f))
        if hr == 0:
            results.append(f"Float property ({val_f.value:.4f})")
    except Exception:
        pass

    # 6. Пробуем (POINTER(c_uint)) -> UINT count / length
    try:
        val_u = c_uint()
        hr = call_vtable(idx, [POINTER(c_uint)], byref(val_u))
        if hr == 0:
            results.append(f"UINT property ({val_u.value})")
    except Exception:
        pass

    # 7. Пробуем (POINTER(c_int)) -> Enum mode
    try:
        val_i = c_int()
        hr = call_vtable(idx, [POINTER(c_int)], byref(val_i))
        if hr == 0:
            results.append(f"INT/Enum property ({val_i.value})")
    except Exception:
        pass

    res_str = " | ".join(results) if results else "FAILED / NOT MATCHED"
    print(f"Индекс {idx:02d}: {res_str}")

print("-" * 65)

print("Сканирование завершено.")
