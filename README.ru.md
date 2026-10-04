# 🚀 kinect-next

**kinect-next** — современная, высокопроизводительная, аппаратно-синхронизированная и строго типизированная библиотека для сенсора **Microsoft Kinect for Windows v2** под **Python 3.10+** с полной поддержкой видео, 3D Point Cloud и **микрофонной решетки (Beamforming)**.

Библиотека полностью спроектирована и переписана с нуля на замену устаревшей `pykinect2`, устраняя все ее архитектурные проблемы, утечки памяти и несовместимости с современными версиями Python.

> 🇬🇧 English version: [README.md](README.md) · история изменений: [CHANGELOG.md](CHANGELOG.md)
>
> **Начиная с 2.0:** `import kinect_next` больше не требует установленного Kinect SDK
> (`Kinect20.dll` грузится лениво при первом `KinectSensor.open()`) — удобно для CI и юнит-тестов;
> сам Kinect v2 по-прежнему только под Windows. `AsyncKinectSensor` и `COMOperationError`
> доступны из корня пакета. Добавлен флаг `KinectSensor(..., reuse_buffers=True)`.

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

* 🎙 **4-микрофонная решетка и Beamforming**: аппаратная локализация источника звука (SSL), отслеживание азимута речи ($-50^\circ .. +50^\circ$), **непрерывный (без пропусков)** захват 16 kHz Float32/Int16 PCM в фоновом потоке; там, где это поддерживает рантайм Kinect, — ручное наведение луча и привязка к 3D-суставам человека (`track_body`).
* 🎯 **Audio-Visual Fusion**: встроенный полярный радар звука и автоматическая подсветка говорящего человека в OpenCV (`draw_audio_visual_overlay`).
* 🏎 **Экономная работа с кадрами**: каждый кадр копируется ровно один раз — из драйвера сразу в массив NumPy; `BGR` / `RGB` — это представления (views) того же массива, а режим `reuse_buffers` убирает выделения памяти на каждом кадре.
* 💤 **Событийный и потокобезопасный захват**: ожидания блокируются на событиях SDK (≈0 % CPU в простое), `close()` можно вызывать из любого потока, а отмена `asyncio`-задачи действительно прерывает ожидание.
* 🔒 **Zero Memory Leaks (RAII)**: автоматическое и строгое управление временем жизни COM-указателей (`IUnknown::Release`).
* ⏱ **Аппаратная синхронизация (MultiSourceFrameReader)**: кадры цвета, глубины, скелета, ИК-камеры и маски одного такта сенсора поступают в едином объекте `FrameSet` с метками времени сенсора — вместе со всем звуком, записанным с предыдущего `FrameSet`.
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
pip install kinect-next              # ядро библиотеки
pip install "kinect-next[viz]"       # + OpenCV для утилит визуализации
pip install "kinect-next[open3d]"    # + Open3D для конвертации облаков точек
pip install "kinect-next[all]"       # всё сразу
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

        # BGR-представление кадра (1080, 1920, 3); копия нужна, чтобы рисовать поверх
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
from kinect_next import AudioFrame, KinectSensor, StreamType

recording = AudioFrame()

with KinectSensor(streams=StreamType.AUDIO) as kinect:
    for audio_frame in kinect.poll_audio():
        print(f"Азимут голоса: {audio_frame.beam_angle_deg:+4.1f}° | Громкость: {audio_frame.dbfs:.1f} dBFS")

        # Соседние кадры стыкуются без пропусков
        recording.subframes += audio_frame.subframes
        if recording.duration_ms >= 5000:
            break

# 5 секунд, 16 kHz mono
recording.save_wav("speech_recording.wav", format_type="int16")
```

Звук записывается непрерывно в фоновом потоке, поэтому ничего не теряется, пока ваш
цикл занят: следующий `AudioFrame` просто содержит больше 16-миллисекундных
субкадров. То же верно для `FrameSet.audio`, когда аудио включено вместе с видео.

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

Контейнер одного снимка всех включённых потоков. Видеокадры относятся к одному такту сенсора; `audio` содержит весь звук, записанный с предыдущего `FrameSet`:

* `frameset.color` (`ColorFrame`): HD изображение 1920x1080 (методы `.as_bgr()`, `.as_rgb()`, `.as_bgra()`).
* `frameset.depth` (`DepthFrame`): Карта глубин 512x424 в миллиметрах (методы `.distance_at(x, y)`, `.to_normalized_uint8()`).
* `frameset.audio` (`AudioFrame`): Непрерывная последовательность аудио-субкадров (методы `.as_int16()`, `.save_wav()`, `.rms`, `.dbfs`, `.correlated_body_ids`).
* `frameset.infrared` (`InfraredFrame`): 16-битный ИК-поток (метод `.to_uint8()`).
* `frameset.long_exposure_infrared` (`LongExposureInfraredFrame`): ИК-поток с накоплением экспозиции.
* `frameset.body_index` (`BodyIndexFrame`): Маска сегментации (0-5 ID человека, 255 фон).
* `frameset.bodies` (`list[Body]`): Список из 6 моделей тел.
* `frameset.tracked_bodies` (`list[Body]`): Список только активно отслеживаемых людей.
* `frameset.floor_clip_plane` (`Vector4`): Вектор уравнения плоскости пола $Ax + By + Cz + D = 0$.
* `frameset.relative_time_ns` (`int`): Время такта по часам сенсора; у каждого кадра и аудио-субкадра есть своя метка `relative_time_ns`.

### Модель `Body` и суставы

* `body.tracking_id`: Уникальный 64-битный ID человека.
* `body.is_tracked`: Флаг активного трекинга.
* `body.joints`: Коллекция всех 25 суставов (`body.joints.head`, `body.joints.spine_mid`, `body.joints[JointType.HAND_LEFT]`).
* `body.hand_left` / `body.hand_right`: Состояние (`HandState.OPEN`, `CLOSED`, `LASSO`) и уровень уверенности.
* `body.lean`: Вектор наклона тела.

---

## 🔊 Звук под нагрузкой

Рантайм Kinect хранит только последние 1–3 аудио-субкадра (по 16 мс), поэтому
kinect-next забирает их фоновым потоком сразу при появлении. По замерам на живом
сенсоре звук идёт без пропусков, пока приложение простаивает, спит по полсекунды на
кадр, строит облако точек или выполняет тяжёлые операции NumPy на каждом кадре.

Потоку захвата всё же нужен GIL на мгновение при каждом чтении. Если другие потоки
выполняют **ресурсоёмкий код на чистом Python** (плотные циклы, не отпускающие GIL),
передача может прийти слишком поздно и субкадр будет пропущен — 1–7 % в стресс-тесте
с 25 мс чистого Python на кадр. Такие пропуски не бывают тихими: они один раз
пишутся в лог и считаются в `kinect.audio_subframes_lost` (`0` означает, что весь
выданный звук непрерывен).

Если ваше приложение такое, уменьшите интервал переключения интерпретатора один раз
при старте — в том же стресс-тесте это свело потери к нулю:

```python
import sys
sys.setswitchinterval(0.0005)   # по умолчанию 0.005 с
```

---

## 🎙 Управление акустическим лучом (`AudioController`)

Контроллер доступен через свойство `kinect.audio`:

```python
audio = kinect.audio
print(audio.mode, audio.beam_angle_deg, audio.beam_angle_confidence)

if audio.supports_manual_steering:
    # 1. Ручное наведение луча на угол (от -50° до +50°)
    audio.set_beam_angle(-20.0)

    # 2. Фокусировка микрофона на конкретном человеке
    for body in frameset.tracked_bodies:
        audio.track_body(body)

    # 3. Возврат в автоматический режим (DSP сам следит за источником звука)
    audio.mode = AudioBeamMode.AUTOMATIC
```

> **Ручное наведение зависит от рантайма Kinect.** Некоторые сочетания SDK и прошивки
> принимают переключение в `MANUAL` и молча остаются в `AUTOMATIC` (официальный
> управляемый API Microsoft ведёт себя на таких машинах так же). kinect-next проверяет
> каждую смену режима: `set_beam_angle()`, `track_joint()`, `track_body()` и
> `audio.mode = AudioBeamMode.MANUAL` бросают `AudioStreamError`, а не делают вид, что
> сработали. В режиме `AUTOMATIC` угол луча, уверенность и
> `AudioFrame.correlated_body_ids` доступны всегда.

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

Покадровые методы принимают `DepthFrame` или «сырой» массив `(424, 512)` `uint16`.
Представления с любыми шагами (зеркальные, срезы) обрабатываются корректно; неверная
форма или dtype дают `ValueError` / `TypeError`, а не молча неправильный результат.
Точка, которую нельзя спроецировать, возвращается как `-inf` — проверяйте
`Point2D.is_valid()` перед `as_int_tuple()`.

---

## ⏳ Ожидание, таймауты и завершение

```python
frameset = kinect.wait_for_frames()              # таймаут по умолчанию: 5 с
frameset = kinect.wait_for_frames(timeout_ms=0)  # опрос: KinectTimeoutError, если кадра нет
```

* **Запуск.** Только что открытому Kinect нужно 1–3 с до первых данных, и обычно он ещё
  раз приостанавливает выдачу на пару секунд сразу после первых кадров. Таймаут 5 с
  покрывает оба случая; `poll_frames()` / `poll_audio()` пропускают таймауты сами.
* **Потокобезопасность.** Захваты сериализуются, поэтому `wait_for_frames()` можно
  вызывать из нескольких потоков. `close()` можно вызывать из любого потока: идущие
  ожидания получают `KinectClosedError`, а генераторы `poll_*` / `stream()` просто
  завершаются.
* **asyncio.** Отмена задачи, ожидающей `AsyncKinectSensor.wait_for_frames()`
  (например, через `asyncio.wait_for`), прерывает и само ожидание.
* **Несколько объектов.** Все `KinectSensor` в процессе делят одно физическое
  устройство; оно закрывается, когда закрыт последний.

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
