"""Audio-Visual Fusion: рендер скелета + подсветка говорящего человека в OpenCV."""

import cv2

from kinect_next import (
    KinectSensor,
    StreamType,
    draw_all_skeletons,
    draw_audio_visual_overlay,
)

print("Запуск полного Audio-Visual Fusion стрима (COLOR + BODY + AUDIO)...")
print("Встаньте перед камерой и говорите — система подсветит вас бейджем SPEAKING.")
print("Нажмите ESC для выхода.")

streams = StreamType.COLOR | StreamType.BODY | StreamType.AUDIO

with KinectSensor(streams=streams) as kinect:
    for frameset in kinect.poll_frames():
        if not frameset.color:
            continue

        # Zero-Copy BGR срез для OpenCV
        display = frameset.color.as_bgr().copy()

        # 1. Отрисовка всех суставов, костей и жестов рук
        draw_all_skeletons(display, frameset.bodies, kinect.mapper, target_space="color")

        # 2. Отрисовка аудио-радара и детекция говорящего человека
        draw_audio_visual_overlay(display, frameset, kinect.mapper, target_space="color")

        # Вывод в окно 1280x720 (HD Ready)
        resized = cv2.resize(display, (1280, 720))
        cv2.imshow("Kinect v2 Audio-Visual Fusion (kinect-next)", resized)

        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
print("\n✅ ШАГ 8 (AUDIO-VISUAL FUSION) УСПЕШНО ЗАВЕРШЕН!")