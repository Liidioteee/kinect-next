"""Идеальное удаление фона (Плотный хромакей через обратный маппинг Color -> Depth)."""

import cv2
import numpy as np
from kinect_next import KinectSensor, StreamType

print("Запуск идеального виртуального хромакея...")
print("Управление: 'B' - сменить фон (Зеленый / Киберпанк / Размытие / Черный), 'ESC' - выход")

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH | StreamType.BODY_INDEX) as kinect:
    bg_mode = 0

    # Создаем структурирующий элемент для легкого сглаживания краев
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    for frameset in kinect.poll_frames():
        if not frameset.color or not frameset.depth or not frameset.body_index:
            continue

        color_img = frameset.color.as_bgr()     # (1080, 1920, 3)
        depth_frame = frameset.depth             # (424, 512)
        body_index_data = frameset.body_index.data # (424, 512) uint8 (0-5 человек, 255 фон)

        # 1. Получаем точные 2D координаты глубины для КАЖДОГО пикселя Full HD кадра
        depth_coords = kinect.mapper.map_color_frame_to_depth_space(depth_frame) # (1080, 1920, 2)
        map_x = depth_coords[:, :, 0]
        map_y = depth_coords[:, :, 1]

        # 2. Мгновенная интерполяция маски на Full HD через аппаратный remap
        body_index_hd = cv2.remap(
            body_index_data, 
            map_x, 
            map_y, 
            interpolation=cv2.INTER_NEAREST, 
            borderMode=cv2.BORDER_CONSTANT, 
            borderValue=255
        )

        # 3. Плотная бинарная маска человека (255 - человек, 0 - фон)
        person_mask = (body_index_hd != 255).astype(np.uint8) * 255

        # 4. Устраняем мелкие краевые артефакты и сглаживаем контур
        person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_CLOSE, kernel)
        person_mask = cv2.GaussianBlur(person_mask, (5, 5), 0)

        # Переводим маску в 3 канала с диапазоном [0.0 ... 1.0]
        mask_3ch = (person_mask.astype(np.float32) / 255.0)[:, :, np.newaxis]

        # 5. Выбор фона
        if bg_mode == 0:
            bg = np.full_like(color_img, (0, 255, 0))            # Хромакей Green Screen
        elif bg_mode == 1:
            # Неоновый киберпанк градиент
            bg = np.zeros_like(color_img)
            bg[:, :, 0] = 180  # Синий
            bg[:, :, 2] = 200  # Красный
        elif bg_mode == 2:
            bg = cv2.GaussianBlur(color_img, (55, 55), 0)       # Размытие реальной комнаты
        else:
            bg = np.zeros_like(color_img)                        # Чистый черный фон

        # 6. Плотный альфа-блендинг (человек 100% непрозрачный, фон заменен)
        output = (color_img * mask_3ch + bg * (1.0 - mask_3ch)).astype(np.uint8)

        # Показываем результат
        preview = cv2.resize(output, (1280, 720))
        cv2.putText(preview, "Mode: Green/Cyber/Blur/Black (Press 'B')", (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

        cv2.imshow("Kinect v2 - Perfect Background Removal", preview)

        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord('q'), ord('Q')):
            break
        elif key in (ord('b'), ord('B')):
            bg_mode = (bg_mode + 1) % 4

cv2.destroyAllWindows()