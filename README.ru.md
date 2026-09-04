# 🚀 kinect-next

**kinect-next** — современная, высокопроизводительная, аппаратно-синхронизированная и строго типизированная библиотека для сенсора **Microsoft Kinect for Windows v2** под **Python 3.10+** с полной поддержкой видео, 3D Point Cloud и **микрофонной решетки (Beamforming)**.

Библиотека полностью спроектирована и переписана с нуля на замену устаревшей `pykinect2`, устраняя все ее архитектурные проблемы, утечки памяти и несовместимости с современными версиями Python.

> 🇬🇧 English version: [README.md](README.md) · история изменений: [CHANGELOG.md](CHANGELOG.md)
>
> **Начиная с 2.0:** `import kinect_next` больше не требует Kinect SDK и работает на любой ОС —
> `Kinect20.dll` загружается лениво при первом `KinectSensor.open()`. `AsyncKinectSensor`
> и `COMOperationError` доступны из корня пакета. Добавлен флаг `KinectSensor(..., reuse_buffers=True)`.

---

## 📌 Содержание

1. [Ключевые преимущества](#-ключевые-преимущества)
2. [Сравнение с pykinect2](#-сравнение-с-pykinect2)
3. [Системные требования и установка](#-системные-требования-и-установка)
4. [Быстрый старт (Quickstart)](#-быстрый-старт-quickstart)
   - [1. Audio-Visual Fusion (Скелеты + Говорящий человек в OpenCV)](#1-audio-visual-fusion-скелеты--говорящий-человек-в-opencv)
   - [2. Запись 16 kHz звука с микрофонной решетки и трекинг луча](#2-запись-16-khz-звука-с-микрофонной-решетки-и-трекинг-луча)
   - [3. Генерация 3D Point Cloud (Облако точек) и Open3D](#3-генерация-3d-point-cloud-облако-точек-и-open3d)
   - [4. Виртуальный хромакей / Удаление фона](#4-виртуальный-хромакей--удаление-фона)
   - [5. Асинхронный стриминг (Asyncio)](#5-асинхронный-стриминг-asyncio)
   - [6. Инфракрасный режим (Ночное видение / IR)](#6-инфракрасный-режим-ночное-видение--ir)
5. [Архитектура и структуры данных](#-архитектура-и-структуры-данных)
6. [Управление акустическим лучом (AudioController)](#-управление-акустическим-лучом-audiocontroller)
7. [Маппинг систем координат (CoordinateMapper)](#-маппинг-систем-координат-coordinatemapper)
8. [API Reference (Таблица суставов и состояний)](#-api-reference)
9. [Лицензия](#-лицензия)

---

## ✨ Ключевые преимущества

* 🎙 **4-микрофонная решетка и Beamforming**: аппаратная локализация источника звука (SSL), отслеживание азимута речи ($-50^\circ .. +50^\circ$), захват 16 kHz Float32/Int16 PCM и привязка луча к 3D-суставам человека (`track_body`).
* 🎯 **Audio-Visual Fusion**: встроенный полярный радар звука и автоматическая подсветка говорящего человека в OpenCV (`draw_audio_visual_overlay`).
* 🏎 **Максимальная производительность (Zero-Copy)**: преобразование кадров в массивы NumPy (`BGRA`, `BGR`, `RGB`, `uint16`, `float32`) без лишнего дублирования памяти.
* 🔒 **Zero Memory Leaks (RAII)**: автоматическое и строгое управление временем жизни COM-указателей (`IUnknown::Release`).
* ⏱ **Аппаратная синхронизация (MultiSourceFrameReader)**: кадры цвета, глубины, скелета, ИК-камеры и аудио поступают в едином синхронизированном объекте `FrameSet`.
* ☁️ **Векторизованный 3D Point Cloud Engine**: генерация сотен тысяч 3D-точек с цветной текстурой за доли миллисекунды прямо в C-драйвере без блокировки Python GIL.
* 🎯 **100% строгая типизация (PEP 561 / `py.typed`)**: полная поддержка подсказок типов для IDE (VSCode, PyCharm) и анализаторов (`mypy --strict`).
* ⚡ **Поддержка `asyncio`**: нативный асинхронный контекстный менеджер и генератор кадров `AsyncKinectSensor`.

---

## 📊 Сравнение с pykinect2

| Характеристика                                 | Старая`pykinect2`                                                  | **kinect-next**                                                             |
| :----------------------------------------------------------- | :------------------------------------------------------------------------- | :-------------------------------------------------------------------------------- |
| **Поддерживаемые версии Python**   | Python 2.7 / 3.4 (падает на 3.8+)                                  | **Python 3.10, 3.11, 3.12, 3.13+**                                          |
| **Микрофонная решетка (Audio)**      | ❌ Не реализовано                                             | **✅ 16 kHz Float32/Int16 PCM, Beamforming, SSL**                           |
| **Audio-Visual Fusion**                                | ❌ Нет                                                                  | **✅ Детекция говорящего человека и радар** |
| **COM-интероп**                                 | Медленный`comtypes` с генерацией TLB                 | **Прямой нативный VTable диспетчер**                 |
| **Утечки памяти при чтении Body** | ❌ Присутствуют (утечка интерфейсов`IBody`) | **✅ Устранены (100% RAII-очистка)**                        |
| **Синхронизация потоков**          | ❌ Ручной опрос независимых ридеров           | **✅ Аппаратный `MultiSourceFrameReader`**                      |
| **Генерация 3D Point Cloud**                  | ❌ Не реализовано                                             | **✅ Векторизованный NumPy/C маппер**                  |
| **Инфракрасный поток (IR)**           | ❌ Пустая заглушка (`pass`)                                | **✅ Полная поддержка 16-bit IR и Long Exposure IR**        |
| **Удаление фона (BodyIndex)**              | ❌ Сложно и медленно                                        | **✅ Готовые маски сегментации**                     |
| **Отрисовка скелета**                  | ❌ Требовалось писать 100+ строк                     | **✅ Готовые методы `draw_all_skeletons`**                   |
| **Асинхронность (`asyncio`)**           | ❌ Нет                                                                  | **✅ `AsyncKinectSensor` (`async for`)**                                |

---

## 🛠 Системные требования и установка

### Требования:

1. **ОС**: Windows 10 / 11 (64-bit).
2. **Оборудование**: Сенсор Microsoft Kinect v2 с адаптером питания и подключением к порту **USB 3.0**.
3. **Драйвер**: Установленный [Kinect for Windows SDK 2.0](https://www.microsoft.com/en-us/download/details.aspx?id=44561).

### Установка:

```bash
pip install kinect-next            # ядро библиотеки
pip install "kinect-next[viz]"     # + OpenCV / Open3D для утилит визуализации
```

Из исходников:

```bash
git clone https://github.com/Liidioteee/kinect-next.git
cd kinect-next
pip install -e ".[dev]"
```

---

## 💡 Быстрый старт (Quickstart)

### 1. Audio-Visual Fusion (Скелеты + Говорящий человек в OpenCV)

```python
import cv2
from kinect_next import (
    KinectSensor,
    StreamType,
    draw_all_skeletons,
    draw_audio_visual_overlay,
)

# Активируем видеопотоки, скелеты и микрофонную решетку
streams = StreamType.COLOR | StreamType.BODY | StreamType.AUDIO

with KinectSensor(streams=streams) as kinect:
    for frameset in kinect.poll_frames():
        if not frameset.color:
            continue

        # Zero-Copy получение кадра для OpenCV (1080, 1920, 3)
        display = frameset.color.as_bgr().copy()

        # Отрисовка скелетов всех людей и жестов рук
        draw_all_skeletons(display, frameset.bodies, kinect.mapper, target_space="color")

        # Отрисовка акустического радара и подсветка говорящего человека
        draw_audio_visual_overlay(display, frameset, kinect.mapper, target_space="color")

        cv2.imshow("Kinect v2 Audio-Visual Fusion", cv2.resize(display, (1280, 720)))
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

---

### 2. Запись 16 kHz звука с микрофонной решетки и трекинг луча

```python
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.AUDIO) as kinect:
    for audio_frame in kinect.poll_audio():
        print(f"Азимут голоса: {audio_frame.beam_angle_deg:+4.1f}° | Громкость: {audio_frame.dbfs:.1f} dBFS")

        # Сохранение пакета в файл WAV (16 kHz mono)
        audio_frame.save_wav("speech_recording.wav", format_type="int16")
        break
```

---

### 3. Генерация 3D Point Cloud (Облако точек) и Open3D

```python
import open3d as o3d
from kinect_next import KinectSensor, StreamType, save_point_cloud_ply, to_open3d_point_cloud

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH) as kinect:
    frameset = kinect.wait_for_frames()

    # Векторизованная генерация 3D облака точек с наложением реальных цветов RGB
    pcd_data = kinect.mapper.generate_point_cloud(frameset.depth, frameset.color)
    print(f"Сгенерировано точек: {len(pcd_data.points):,}")

    # Экспорт в файл .PLY (поддерживается Blender, MeshLab, CloudCompare)
    save_point_cloud_ply("room_scan.ply", pcd_data)

    # Интерактивный просмотр в Open3D
    pcd_o3d = to_open3d_point_cloud(pcd_data)
    o3d.visualization.draw_geometries([pcd_o3d])
```

---

### 4. Виртуальный хромакей / Удаление фона

```python
import cv2
import numpy as np
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH | StreamType.BODY_INDEX) as kinect:
    for frameset in kinect.poll_frames():
        if not (frameset.color and frameset.depth and frameset.body_index):
            continue

        color_img = frameset.color.as_bgr()
        depth_coords = kinect.mapper.map_color_frame_to_depth_space(frameset.depth)

        # Аппаратный ремап маски силуэта на Full HD
        body_hd = cv2.remap(
            frameset.body_index.data,
            depth_coords[:, :, 0],
            depth_coords[:, :, 1],
            interpolation=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )

        mask = (body_hd != 255).astype(np.uint8) * 255
        mask = cv2.GaussianBlur(mask, (15, 15), 0)
        alpha = (mask.astype(np.float32) / 255.0)[:, :, np.newaxis]

        # Зеленый фон хромакея
        green_bg = np.full_like(color_img, (0, 255, 0))
        result = (color_img * alpha + green_bg * (1.0 - alpha)).astype(np.uint8)

        cv2.imshow("Virtual Green Screen", cv2.resize(result, (1280, 720)))
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

---

### 5. Асинхронный стриминг (Asyncio)

```python
import asyncio
from kinect_next.aio import AsyncKinectSensor
from kinect_next import StreamType

async def main():
    async with AsyncKinectSensor(streams=StreamType.DEPTH | StreamType.BODY | StreamType.AUDIO) as kinect:
        async for frameset in kinect.stream():
            if frameset.depth:
                dist = frameset.depth.distance_at(256, 212)
                print(f"[Async] Дистанция: {dist:.2f} м | Людей в кадре: {len(frameset.tracked_bodies)}")
            if frameset.audio:
                print(f"[Async Audio] Угол луча: {frameset.audio.beam_angle_deg:.1f}°")
            await asyncio.sleep(0)

asyncio.run(main())
```

---

### 6. Инфракрасный режим (Ночное видение / IR)

```python
import cv2
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.INFRARED) as kinect:
    for frameset in kinect.poll_frames():
        # 16-битный инфракрасный кадр преобразуется в контрастный 8-битный вид
        ir_image = frameset.infrared.to_uint8()

        cv2.imshow("Kinect v2 - Infrared (Night Vision)", ir_image)
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

---

## 🏛 Архитектура и структуры данных

### Объект `FrameSet`

Контейнер одного аппаратно-синхронизированного снимка:

* `frameset.color` (`ColorFrame`): HD изображение 1920x1080 (методы `.as_bgr()`, `.as_rgb()`, `.as_bgra()`).
* `frameset.depth` (`DepthFrame`): Карта глубин 512x424 в миллиметрах (методы `.distance_at(x, y)`, `.to_normalized_uint8()`).
* `frameset.audio` (`AudioFrame`): Пакет аудио-субкадров (методы `.as_int16()`, `.save_wav()`, `.rms`, `.dbfs`).
* `frameset.infrared` (`InfraredFrame`): 16-битный ИК-поток (метод `.to_uint8()`).
* `frameset.long_exposure_infrared` (`LongExposureInfraredFrame`): ИК-поток с накоплением экспозиции.
* `frameset.body_index` (`BodyIndexFrame`): Маска сегментации (0-5 ID человека, 255 фон).
* `frameset.bodies` (`list[Body]`): Список из 6 моделей тел.
* `frameset.tracked_bodies` (`list[Body]`): Список только активно отслеживаемых людей.
* `frameset.floor_clip_plane` (`Vector4`): Вектор уравнения плоскости пола $Ax + By + Cz + D = 0$.

### Модель `Body` и суставы

* `body.tracking_id`: Уникальный 64-битный ID человека.
* `body.is_tracked`: Флаг активного трекинга.
* `body.joints`: Коллекция всех 25 суставов (`body.joints.head`, `body.joints.spine_mid`, `body.joints[JointType.HAND_LEFT]`).
* `body.hand_left` / `body.hand_right`: Состояние (`HandState.OPEN`, `CLOSED`, `LASSO`) и уровень уверенности.
* `body.lean`: Вектор наклона тела.

---

## 🎙 Управление акустическим лучом (`AudioController`)

Контроллер доступен через свойство `kinect.audio`:

```python
# 1. Автоматический режим (DSP сам следит за источником звука)
kinect.audio.set_mode(AudioBeamMode.AUTOMATIC)

# 2. Ручное наведение луча на угол (от -50° до +50°)
kinect.audio.set_beam_angle(-20.0)

# 3. Фокусировка микрофона на конкретном человеке
for body in frameset.tracked_bodies:
    kinect.audio.track_body(body)
```

---

## 📐 Маппинг систем координат (CoordinateMapper)

Kinect v2 оперирует тремя пространствами координат:

1. **Camera Space**: 3D метрическое пространство с центром в ИК-камере $(X, Y, Z)$ в метрах.
2. **Depth Space**: 2D плоскость кадра глубины $(512 \times 424)$.
3. **Color Space**: 2D плоскость Full HD камеры $(1920 \times 1080)$.

`CoordinateMapper` предоставляет методы взаимных преобразований:

```python
# 1. Единичные проекции
point_depth = joint.to_depth_space(kinect.mapper)  # Point2D(x, y)
point_color = joint.to_color_space(kinect.mapper)  # Point2D(x, y)

# 2. Пакетная векторизация полного кадра (NumPy arrays)
cam_points = kinect.mapper.map_depth_frame_to_camera_space(frameset.depth) # (424, 512, 3) float32
color_coords = kinect.mapper.map_depth_frame_to_color_space(frameset.depth) # (424, 512, 2) float32
```

---

## 📖 API Reference

### 25 отслеживаемых суставов (`JointType`):

```text
       [HEAD]
          |
        [NECK]
          |
   [SPINE_SHOULDER] --- [SHOULDER_LEFT] --- [ELBOW_LEFT] --- [WRIST_LEFT] --- [HAND_LEFT] --- [HAND_TIP_LEFT]
    /     |      \                                                         \
   /      |       \                                                         [THUMB_LEFT]
  /  [SPINE_MID]   \
 /        |         [SHOULDER_RIGHT] --- [ELBOW_RIGHT] --- [WRIST_RIGHT] --- [HAND_RIGHT] --- [HAND_TIP_RIGHT]
|    [SPINE_BASE]                                                        \
|     /        \                                                          [THUMB_RIGHT]
|  [HIP_LEFT]  [HIP_RIGHT]
|     |            |
|  [KNEE_LEFT]  [KNEE_RIGHT]
|     |            |
|  [ANKLE_LEFT] [ANKLE_RIGHT]
|     |            |
|  [FOOT_LEFT]  [FOOT_RIGHT]
```

### Состояния кистей рук (`HandState`):

* `HandState.UNKNOWN` (0) — состояние не определено.
* `HandState.NOT_TRACKED` (1) — кисть не отслеживается.
* `HandState.OPEN` (2) — открытая ладонь.
* `HandState.CLOSED` (3) — кулак.
* `HandState.LASSO` (4) — указательный и средний пальцы вытянуты (жест лассо / ножницы).

### Режимы луча микрофонной решетки (`AudioBeamMode`):

* `AudioBeamMode.AUTOMATIC` (0) — слежение за источником звука силами DSP.
* `AudioBeamMode.MANUAL` (1) — программно фиксированное направление.

---

## 📄 Лицензия

Проект распространяется под свободной лицензией **MIT License**. Разрешено коммерческое и некоммерческое использование, модификация и распространение.
