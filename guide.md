# 📚 Полное руководство разработчика по библиотеке `kinect-next`

> ⚠️ Изменения API в версии 2.0 (в т.ч. `import kinect_next` без Kinect SDK,
> `AsyncKinectSensor`/`COMOperationError` в корне пакета, `reuse_buffers`,
> `save_point_cloud_ply(..., binary=True)`) описаны в [CHANGELOG.md](CHANGELOG.md).

---

## 1. Архитектура и концепция библиотеки

`kinect-next` — это библиотека для сенсора **Microsoft Kinect for Windows v2**, написанная с нуля под **Python 3.10+**.

### Ключевые принципы архитектуры:

1. **Zero-Copy & Direct Buffer View**: массивы NumPy создаются напрямую из нативных буферов драйвера без лишнего копирования в памяти.
2. **RAII Memory Safety**: вызовы COM-методов `AddRef()` и `Release()` изолированы внутри оберток; при удалении объектов Python ссылки в COM-памяти гарантированно освобождаются.
3. **Аппаратная MultiSource- и Audio-синхронизация**: сборка всех потоков (RGB, глубина, ИК, скелет, маски, микрофонная решетка) без разрыва кадров.
4. **Векторизованные вычисления на C/SIMD**: преобразования координат сотен тысяч точек выполняются внутри нативного драйвера, а не в медленных циклах Python.
5. **Аппаратный Beamforming**: автоматическая локализация источника звука (SSL), слежение за азимутом речи ($-50^\circ .. +50^\circ$) и программное наведение микрофона на 3D-суставы людей.
6. **Строгая статическая типизация**: библиотека помечена маркером `py.typed` (PEP 561) и поддерживает проверку `mypy --strict`.

---

## 2. Физические характеристики сенсора Kinect v2

| Подсистема                            | Разрешение / Формат                      | Частота     | Рабочий диапазон / Углы обзора                               |
| :---------------------------------------------- | :------------------------------------------------------- | :----------------- | :------------------------------------------------------------------------------------ |
| **Color Камера**                    | 1920 × 1080 (Full HD, BGRA uint8)                       | 30 FPS             | Угол обзора: 84.1° × 53.8°                                               |
| **Depth Сенсор**                    | 512 × 424 (16-bit uint, мм)                           | 30 FPS             | 0.5 м – 4.5 м (макс. до 8.0 м), обзор: 70.6° × 60.0°                |
| **Infrared (ИК)**                       | 512 × 424 (16-bit uint)                                 | 30 FPS             | Активная ИК-подсветка (ночное видение)                |
| **Body Tracking**                         | До 6 человек, 25 суставов на тело | 30 FPS             | 3D координаты в метрах + кватернионы ориентации |
| **Body Index**                            | 512 × 424 (8-bit uint)                                  | 30 FPS             | Маска силуэтов (ID 0–5, фон: 255)                                    |
| **Микрофонная решетка** | 4 микрофона, 16 kHz Float32/Int16 PCM           | ~62.5 FPS (16мс) | Beamforming$[-50^\circ .. +50^\circ]$, DSP шумо- и эхоподавление  |

---

## 3. Управление жизненным циклом (`KinectSensor` и `AsyncKinectSensor`)

### 3.1. Флаги потоков данных (`StreamType`)

Вы можете комбинировать необходимые потоки через битовое **ИЛИ** (`|`), экономя ресурсы шины USB 3.0 и процессора:

```python
from kinect_next import StreamType

# Только глубина, скелет и аудио
streams = StreamType.DEPTH | StreamType.BODY | StreamType.AUDIO

# Все доступные потоки
streams = StreamType.ALL
```

Доступные флаги:

* `StreamType.NONE`
* `StreamType.COLOR` (Цвет 1080p)
* `StreamType.DEPTH` (Глубина 512x424)
* `StreamType.INFRARED` (Инфракрасный поток)
* `StreamType.LONG_EXPOSURE_INFRARED` (ИК с длинной выдержкой)
* `StreamType.BODY_INDEX` (Маска силуэтов людей)
* `StreamType.BODY` (Скелетный трекинг)
* `StreamType.AUDIO` (Микрофонная решетка и Beamforming)
* `StreamType.ALL` (Все сенсоры)

---

### 3.2. Синхронный режим (`KinectSensor`)

#### Вариант А: Менеджер контекста (Рекомендуемый)

```python
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH | StreamType.AUDIO) as kinect:
    # Потоковый генератор (синхронизированный цикл)
    for frameset in kinect.poll_frames():
        if frameset.audio:
            print(f"Азимут звука: {frameset.audio.beam_angle_deg:.1f}°")
```

#### Вариант Б: Высокоскоростной аудио-опрос (~60 FPS)

```python
with KinectSensor(streams=StreamType.AUDIO) as kinect:
    # Захват чистых субкадров звука без ожидания видеокамеры
    for audio_frame in kinect.poll_audio():
        print(f"Громкость: {audio_frame.dbfs:.1f} dBFS")
```

#### Вариант В: Ручное управление

```python
kinect = KinectSensor(streams=StreamType.COLOR | StreamType.AUDIO, auto_open=False)
kinect.open()
try:
    frameset = kinect.wait_for_frames()
finally:
    kinect.close()  # Гарантированное освобождение Win32 и COM ресурсов
```

---

### 3.3. Асинхронный режим (`AsyncKinectSensor`)

Для использования в **FastAPI, Tornado, Asyncio, WebSockets**:

```python
import asyncio
from kinect_next.aio import AsyncKinectSensor
from kinect_next import StreamType

async def main():
    async with AsyncKinectSensor(streams=StreamType.DEPTH | StreamType.BODY | StreamType.AUDIO) as kinect:
        async for frameset in kinect.stream():
            if frameset.depth:
                print(f"Дистанция: {frameset.depth.distance_at(256, 212):.2f} м")
            if frameset.audio:
                print(f"Угол луча: {frameset.audio.beam_angle_deg:.1f}°")
            await asyncio.sleep(0)

asyncio.run(main())
```

---

## 4. Объекты данных и потоки (`FrameSet` и модели)

При каждом захвате возвращается единый снимок `FrameSet`.

```python
frameset = kinect.wait_for_frames()
```

### 4.1. `ColorFrame` (Цветовая камера)

Содержит кадр 1920 × 1080.

```python
if frameset.color:
    # 1. BGR массив для OpenCV за O(1) (Zero-Copy срез)
    bgr_image = frameset.color.as_bgr()     # shape=(1080, 1920, 3), dtype=uint8

    # 2. RGB массив для PIL, Matplotlib, PyTorch
    rgb_image = frameset.color.as_rgb()     # shape=(1080, 1920, 3), dtype=uint8

    # 3. Нативный 4-канальный BGRA массив
    bgra_image = frameset.color.as_bgra()   # shape=(1080, 1920, 4), dtype=uint8

    # 4. Настройки камеры
    if frameset.color.settings:
        print(f"Экспозиция: {frameset.color.settings.exposure_time} мкс")
```

---

### 4.2. `DepthFrame` (Сенсор глубины)

Содержит матрицу расстояний 512 × 424 в миллиметрах (`np.uint16`).

```python
if frameset.depth:
    depth = frameset.depth

    # 1. Сырая матрица (424, 512) uint16
    raw_depth = depth.data 

    # 2. Расстояние в конкретном пикселе (в метрах)
    distance_m = depth.distance_at(x=256, y=212)

    # 3. Нормализация для показа в OpenCV (uint8 0..255)
    depth_gray = depth.to_normalized_uint8()
```

---

### 4.3. `InfraredFrame` и `LongExposureInfraredFrame` (ИК-камера)

16-битный инфракрасный поток с активной подсветкой.

```python
if frameset.infrared:
    raw_ir = frameset.infrared.data          # shape=(424, 512), dtype=uint16
    ir_display = frameset.infrared.to_uint8() # shape=(424, 512), dtype=uint8
```

---

### 4.4. `BodyIndexFrame` (Маска сегментации)

Матрица 512 × 424, где каждый пиксель указывает, какому человеку он принадлежит:

* `0 .. 5`: Индекс отслеживаемого человека.
* `255`: Фон / окружение.

```python
if frameset.body_index:
    all_people_mask = frameset.body_index.get_all_bodies_mask() # np.ndarray[bool] (424, 512)
    person_0_mask = frameset.body_index.get_body_mask(body_index=0)
```

---

### 4.5. `Body` и `Joint` (Скелетный трекинг)

```python
for body in frameset.tracked_bodies:
    print(f"Tracking ID: {body.tracking_id}")

    # 1. Доступ к суставам
    head = body.joints.head
    pos = head.position  # Vector3(x, y, z) в метрах
    print(f"Голова: X={pos.x:.2f}м, Y={pos.y:.2f}м, Z={pos.z:.2f}м")

    # 2. Ориентация сустава (Кватернион и углы Эйлера)
    quat = head.orientation
    roll, pitch, yaw = quat.to_euler_angles() # Углы в радианах

    # 3. Состояния кистей рук (Жесты)
    if body.hand_right.state == HandState.CLOSED:
        print("Правая рука сжата в кулак!")
```

---

### 4.6. `AudioFrame` и `AudioBeamSubFrame` (Микрофонная решетка)

```python
if frameset.audio:
    audio = frameset.audio

    # 1. Сэмплы Float32 [-1.0 .. 1.0] (16000 Hz, Mono)
    float_samples = audio.data

    # 2. Сэмплы 16-bit PCM [-32768 .. 32767]
    int16_samples = audio.as_int16()

    # 3. Акустические параметры
    print(f"Азимут луча: {audio.beam_angle_deg:+.1f}°")
    print(f"Уверенность: {audio.beam_angle_confidence:.2f}")
    print(f"Громкость: {audio.dbfs:.1f} dBFS | RMS: {audio.rms:.4f}")

    # 4. Сохранение в файл WAV
    audio.save_wav("speech.wav", format_type="int16")
```

---

## 5. Управление акустическим лучом (`AudioController`)

Контроллер доступен через `kinect.audio` при активации `StreamType.AUDIO`.

### 5.1. Режимы луча (`AudioBeamMode`)

* `AudioBeamMode.AUTOMATIC`: аппаратный DSP Kinect v2 автоматически отслеживает источник звука.
* `AudioBeamMode.MANUAL`: фиксированное программное направление луча.

```python
# Переключение режима
kinect.audio.set_mode(AudioBeamMode.MANUAL)

# Ручная установка угла в градусах (от -50° до +50°)
kinect.audio.set_beam_angle(-25.0)

# Возврат в автоматический режим
kinect.audio.set_mode(AudioBeamMode.AUTOMATIC)
```

### 5.2. Наведение микрофона на 3D-суставы людей

Библиотека позволяет сфокусировать микрофонную решетку на конкретном человеке в комнате:

```python
for body in frameset.tracked_bodies:
    # Фокусирует луч на голове человека
    kinect.audio.track_body(body)
    break
```

---

## 6. Системы координат и `CoordinateMapper`

Kinect v2 работает в 3 независимых пространствах:

1. **Camera Space**: 3D метрическое пространство $(X, Y, Z)$ в метрах. Центр $(0,0,0)$ — ИК-камера.
2. **Depth Space**: 2D плоскость кадра глубины $(512 \times 424)$ в пикселях.
3. **Color Space**: 2D плоскость HD-камеры $(1920 \times 1080)$ в пикселях.

```
                  ┌───────────────────────────────┐
                  │         Camera Space          │
                  │   3D (X, Y, Z) в метрах       │
                  └───────────────┬───────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
   ┌───────────────────────────┐     ┌───────────────────────────┐
   │        Depth Space        │◄───►│        Color Space        │
   │    2D (512 x 424) px      │     │   2D (1920 x 1080) px     │
   └───────────────────────────┘     └───────────────────────────┘
```

### 6.1. Точечные и пакетные преобразования

```python
# 1. 3D точка сустава -> 2D пиксель на HD-камере
color_pt = body.joints.head.to_color_space(kinect.mapper)

# 2. Весь Depth кадр -> 3D Point Cloud матрица (424, 512, 3) float32
cam_matrix = kinect.mapper.map_depth_frame_to_camera_space(frameset.depth)

# 3. Обратный маппинг Color -> Depth (1080, 1920, 2) float32 для хромакея
depth_coords = kinect.mapper.map_color_frame_to_depth_space(frameset.depth)
```

### 6.2. Высокоуровневый генератор 3D Point Cloud

```python
pcd_data = kinect.mapper.generate_point_cloud(
    depth_frame=frameset.depth,
    color_frame=frameset.color,  # Наложение цвета
    remove_invalid=True          # Удаление выбросов и шумов
)

print(pcd_data.points.shape) # (N, 3) XYZ в метрах
print(pcd_data.colors.shape) # (N, 3) RGB [0.0 .. 1.0]
```

---

## 7. Утилиты визуализации и экспорта (`kinect_next.utils`)

### 7.1. Audio-Visual Fusion (OpenCV)

Отрисовывает полярный радар звука и подсвечивает говорящего человека бейджем `SPEAKING`:

```python
import cv2
from kinect_next.utils import draw_all_skeletons, draw_audio_visual_overlay

color_bgr = frameset.color.as_bgr().copy()

# Скелеты людей
draw_all_skeletons(color_bgr, frameset.bodies, kinect.mapper, target_space="color")

# Акустический радар и подсветка говорящего
draw_audio_visual_overlay(color_bgr, frameset, kinect.mapper, target_space="color")
```

### 7.2. Экспорт в 3D (.PLY и Open3D)

```python
import open3d as o3d
from kinect_next.utils import save_point_cloud_ply, to_open3d_point_cloud

pcd = kinect.mapper.generate_point_cloud(frameset.depth, frameset.color)

# Сохранение в .PLY для Blender/MeshLab
save_point_cloud_ply("scan.ply", pcd)

# Просмотр в Open3D
o3d_cloud = to_open3d_point_cloud(pcd)
o3d.visualization.draw_geometries([o3d_cloud])
```

---

## 8. Практические рецепты (CookBook)

### Рецепт 1: Audio-Visual Fusion с распознаванием жестов

```python
import cv2
from kinect_next import (
    KinectSensor,
    StreamType,
    HandState,
    draw_all_skeletons,
    draw_audio_visual_overlay,
)

streams = StreamType.COLOR | StreamType.BODY | StreamType.AUDIO

with KinectSensor(streams=streams) as kinect:
    for frameset in kinect.poll_frames():
        if not frameset.color:
            continue

        display = frameset.color.as_bgr().copy()

        # Отрисовка скелетов и аудио-оверлея
        draw_all_skeletons(display, frameset.bodies, kinect.mapper, target_space="color")
        draw_audio_visual_overlay(display, frameset, kinect.mapper, target_space="color")

        # Проверка жестов
        for body in frameset.tracked_bodies:
            if body.hand_right.state == HandState.CLOSED:
                cv2.putText(display, "RIGHT HAND: CLOSED", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

        cv2.imshow("Kinect v2 Fusion", cv2.resize(display, (1280, 720)))
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

---

### Рецепт 2: Распознавание речи с OpenAI Whisper

```python
import numpy as np
from kinect_next import KinectSensor, StreamType
import whisper  # pip install openai-whisper

model = whisper.load_model("base")

with KinectSensor(streams=StreamType.AUDIO) as kinect:
    print("Говорите фразу (запись 4 секунды)...")
    buffer = []

    for audio_frame in kinect.poll_audio():
        buffer.extend(audio_frame.subframes)
        total_sec = sum(sf.duration_ms for sf in buffer) / 1000.0
        if total_sec >= 4.0:
            break

    # Склеиваем Float32 сэмплы (16000 Hz, Mono)
    full_audio = np.concatenate([sf.data for sf in buffer])

    # Распознаем речь
    result = model.transcribe(full_audio, fp16=False)
    print(f"Распознано: {result['text']}")
```

---

### Рецепт 3: Плотный виртуальный хромакей в 1080p

```python
import cv2
import numpy as np
from kinect_next import KinectSensor, StreamType

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH | StreamType.BODY_INDEX) as kinect:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    for frameset in kinect.poll_frames():
        if not (frameset.color and frameset.depth and frameset.body_index):
            continue

        color_img = frameset.color.as_bgr()

        # 1. Обратный маппинг Color -> Depth
        depth_coords = kinect.mapper.map_color_frame_to_depth_space(frameset.depth)

        # 2. Ремап маски силуэта на Full HD
        body_hd = cv2.remap(
            frameset.body_index.data,
            depth_coords[:, :, 0],
            depth_coords[:, :, 1],
            interpolation=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )

        # 3. Сглаживание маски
        mask = (body_hd != 255).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        alpha = (mask.astype(np.float32) / 255.0)[:, :, np.newaxis]

        # 4. Наложение на зеленый фон
        green_bg = np.full_like(color_img, (0, 255, 0))
        output = (color_img * alpha + green_bg * (1.0 - alpha)).astype(np.uint8)

        cv2.imshow("Green Screen", cv2.resize(output, (1280, 720)))
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
```

---

## 9. Справочник констант и типов (API Reference)

### 9.1. Суставы человека (`JointType`)

| Имя сустава (`JointType`) | Значение | Описание                                                  |
| :------------------------------------ | :--------------- | :---------------------------------------------------------------- |
| `SPINE_BASE`                        | 0                | Основание позвоночника (центр таза) |
| `SPINE_MID`                         | 1                | Поясница                                                  |
| `NECK`                              | 2                | Шея                                                            |
| `HEAD`                              | 3                | Голова                                                      |
| `SHOULDER_LEFT`                     | 4                | Левое плечо                                             |
| `ELBOW_LEFT`                        | 5                | Левый локоть                                           |
| `WRIST_LEFT`                        | 6                | Левое запястье                                       |
| `HAND_LEFT`                         | 7                | Левая ладонь                                           |
| `SHOULDER_RIGHT`                    | 8                | Правое плечо                                           |
| `ELBOW_RIGHT`                       | 9                | Правый локоть                                         |
| `WRIST_RIGHT`                       | 10               | Правое запястье                                     |
| `HAND_RIGHT`                        | 11               | Правая ладонь                                         |
| `HIP_LEFT`                          | 12               | Левое бедро                                             |
| `KNEE_LEFT`                         | 13               | Левое колено                                           |
| `ANKLE_LEFT`                        | 14               | Левая лодыжка                                         |
| `FOOT_LEFT`                         | 15               | Левая стопа                                             |
| `HIP_RIGHT`                         | 16               | Правое бедро                                           |
| `KNEE_RIGHT`                        | 17               | Правое колено                                         |
| `ANKLE_RIGHT`                       | 18               | Правая лодыжка                                       |
| `FOOT_RIGHT`                        | 19               | Правая стопа                                           |
| `SPINE_SHOULDER`                    | 20               | Верх позвоночника                                 |
| `HAND_TIP_LEFT`                     | 21               | Кончики пальцев левой руки                 |
| `THUMB_LEFT`                        | 22               | Большой палец левой руки                     |
| `HAND_TIP_RIGHT`                    | 23               | Кончики пальцев правой руки               |
| `THUMB_RIGHT`                       | 24               | Большой палец правой руки                   |

### 9.2. Режимы луча (`AudioBeamMode`)

* `AudioBeamMode.AUTOMATIC` (0): DSP сенсора сам поворачивает луч за голосом.
* `AudioBeamMode.MANUAL` (1): угол луча зафиксирован программно.

### 9.3. Состояния кистей рук (`HandState`)

* `HandState.UNKNOWN` (0): не определено.
* `HandState.NOT_TRACKED` (1): кисть вне зоны видимости.
* `HandState.OPEN` (2): ладонь раскрыта.
* `HandState.CLOSED` (3): кулак.
* `HandState.LASSO` (4): указательный и средний пальцы вытянуты.

---

## 10. Диагностика и устранение неполадок (Troubleshooting)

### Ошибка: `KinectNotAvailableError: Библиотека Kinect20.dll не найдена`

* **Решение**: Установите [Kinect for Windows SDK 2.0](https://www.microsoft.com/en-us/download/details.aspx?id=44561).

### Ошибка: `KinectTimeoutError: Таймаут ожидания кадра`

* Убедитесь, что сенсор подключен к порту **USB 3.0** (синий разъем).
* Проверьте блок питания (индикатор должен гореть белым, а не оранжевым).
* Закройте другие программы, использующие сенсор (Kinect Studio, Skype, OBS).

### Микрофонная решетка не определяет угол речи

* Убедитесь, что в помещении нет громкого фонового эха.
* Проверьте, что сенсор не закрыт посторонними предметами (микрофоны расположены снизу вдоль передней панели).
