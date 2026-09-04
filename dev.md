
# 🛠 Архитектурная инструкция для разработчиков (Handover Guide)

> **Назначение документа**: Данное руководство предназначено для текущих и будущих разработчиков библиотеки `kinect-next`. В нем описана внутренняя архитектура, правила управления памятью, низкоуровневые COM-механизмы, а также **матрица жестких взаимосвязей между файлами** (что и где нужно менять одновременно, чтобы не вызвать краш процесса).

> ⚠️ **Актуальность**: документ описывает общую архитектуру. Точечные изменения версии
> 2.0 (ленивая загрузка `Kinect20.dll`, кэш VTable-тонков в `COMBase`, детерминированное
> освобождение COM в `wait_for_frames`, флаг `reuse_buffers`, англоязычные docstrings,
> ленивый импорт OpenCV в `utils/`) перечислены в [CHANGELOG.md](CHANGELOG.md).

---

## 1. Карта модулей и назначение файлов

```text
kinect_next_project/
│
├── pyproject.toml              # [Build] Конфигурация сборки пакета (PEP 517/518), зависимости, метаданные
├── README.md                   # [Docs] Публичная документация для пользователей
├── guide.md                    # [Docs] Полное практическое руководство разработчика
├── dev.md                      # [Docs] Настоящее архитектурное руководство (VTable, RAII, связи)
│
├── kinect_next/                # [Root Package]
│   ├── __init__.py             # [Public API] Главная точка входа; реэкспорт всего публичного API
│   ├── py.typed                # [Typing] Маркер PEP 561 для IDE и mypy (строгая типизация)
│   │
│   ├── native/                 # [Layer 0: C/Win32/COM Interop] Нативный низкоуровневый слой
│   │   ├── __init__.py         # Реэкспорт нативных структур и интерфейсов
│   │   ├── types.py            # Точные C-структуры (ctypes.Structure): точки, суставы, матрицы
│   │   ├── com_base.py         # Базовый класс COMBase (диспетчеризация VTable, RAII IUnknown::Release)
│   │   ├── win32.py            # Win32 Kernel32 API (события, ожидания) + загрузка Kinect20.dll
│   │   └── interfaces.py       # COM-интерфейсы Kinect SDK 2.0 (видео, маппер и аудиоподсистема)
│   │
│   ├── core/                   # [Layer 1: Runtime Engine] Движок захвата и математический аппарат
│   │   ├── __init__.py         # Реэкспорт ядра (KinectSensor, CoordinateMapper, AudioController, Enums, Exceptions)
│   │   ├── audio.py            # Контроллер лучеформирования (AudioController: наведение, привязка к телу)
│   │   ├── enums.py            # Строго типизированные IntEnum и IntFlag (JointType, HandState, AudioBeamMode)
│   │   ├── exceptions.py       # Дерево кастомных исключений (KinectError, COMOperationError, AudioStreamError)
│   │   ├── mapper.py           # Векторизованный CoordinateMapper (Point Cloud, 2D/3D трансформации)
│   │   └── sensor.py           # Главный контроллер KinectSensor (MultiSource + Audio захват)
│   │
│   ├── models/                 # [Layer 2: Data Models] Высокоуровневые типизированные модели
│   │   ├── __init__.py         # Реэкспорт всех структур данных
│   │   ├── audio.py            # AudioBeamSubFrame, AudioFrame (Float32 PCM, Int16, dBFS, экспорт в WAV)
│   │   ├── geometry.py         # Векторы, кватернионы, точки (Vector3, Quaternion, Point2D)
│   │   ├── color.py            # ColorFrame (BGRA, BGR, RGB, настройки камеры)
│   │   ├── depth.py            # DepthFrame (uint16 карта глубин, выборка дистанций)
│   │   ├── infrared.py         # InfraredFrame, LongExposureInfraredFrame (16-bit ИК)
│   │   ├── body_index.py       # BodyIndexFrame (маски сегментации людей)
│   │   ├── body.py             # Body, Joint, JointCollection, Hand (модели скелета)
│   │   └── frameset.py         # FrameSet (единый контейнер синхронизированных видео- и аудио-данных)
│   │
│   ├── aio/                    # [Layer 3: Async Subsystem] Асинхронный модуль
│   │   ├── __init__.py         # Экспорт AsyncKinectSensor (видео- и аудио-стриминг)
│   │   └── sensor.py           # Асинхронная неблокирующая обертка над KinectSensor
│   │
│   └── utils/                  # [Layer 4: Helpers & Viz] Инструменты визуализации и экспорта
│       ├── __init__.py         # Экспорт утилит
│       ├── visualizer.py       # Рендерер костей, суставов и кистей рук для OpenCV
│       ├── audio_visualizer.py # Audio-Visual Fusion (радар направленности звука, подсветка говорящего)
│       └── point_cloud.py      # Экспорт в .PLY и конвертация в объекты Open3D
```

---

## 2. ⚠️ Матрица жестких связей (Связанные файлы)

В библиотеке есть группы файлов с **прямой зависимостью**. Изменение одного файла **ОБЯЗАТЕЛЬНО** требует синхронного изменения остальных файлов группы, иначе возникнут сбои VTable (смещение индексов вызовов), утечки памяти или падения с кодом `0xC0000005 (Access Violation)`.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ГРУППА 1: Нативные COM-методы и структуры                                       │
│   native/types.py ──► native/interfaces.py ──► core/mapper.py / core/sensor.py │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│ ГРУППА 2: Потоки данных и модели кадров                                         │
│   core/enums.py ──► models/*.py ──► core/sensor.py ──► models/frameset.py       │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│ ГРУППА 3: Экспорт публичного API (4 уровня __init__.py)                         │
│   models/__init__.py ──► core/__init__.py ──► kinect_next/__init__.py           │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Подробное описание сценариев совместного редактирования:

---

### Сценарий А. Добавление или изменение метода COM-интерфейса Kinect SDK

* **Файлы:**
  1. `kinect_next/native/types.py` (если методу нужны новые C-структуры или типы аргументов).
  2. `kinect_next/native/interfaces.py` (добавление сигнатуры вызова через `_call_method(index, ...)`).
  3. `kinect_next/core/mapper.py`, `kinect_next/core/sensor.py` или `kinect_next/core/audio.py` (верхнеуровневая обертка).
* **Критическое правило:**
  > Индекс метода в VTable **НЕЛЬЗЯ ПРИДУМЫВАТЬ САМОСТОЯТЕЛЬНО**. В COM первые 3 индекса (`0, 1, 2`) всегда занимает `IUnknown` (`QueryInterface`, `AddRef`, `Release`). Пользовательские методы начинаются строго с индекса `3` в порядке их объявления в официальном заголовочном файле `Kinect.h` из C++ SDK. Смещение индекса даже на 1 приведет к вызову чужого метода в C++ памяти и аварийному завершению процесса.
  >

---

### Сценарий Б. Добавление нового потока данных

* **Файлы:**
  1. `kinect_next/core/enums.py` (добавить флаг в `StreamType`).
  2. `kinect_next/native/interfaces.py` (описать соответствующий `I...FrameReader` и `I...Frame`).
  3. `kinect_next/models/` (создать новый файл модели, например `audio.py`).
  4. `kinect_next/models/frameset.py` (добавить поле нового кадра в датакласс `FrameSet`).
  5. `kinect_next/core/sensor.py` (в методе `wait_for_frames()` добавить блок извлечения нового кадра при наличии флага в `self._streams`).
  6. Все файлы `__init__.py` (пробросить импорты наружу).

---

### Сценарий В. Добавление/изменение суставов или моделей тела

* **Файлы:**
  1. `kinect_next/core/enums.py` (обновить `JointType` и метод `count()`).
  2. `kinect_next/models/geometry.py` (если меняются типы векторов).
  3. `kinect_next/models/body.py` (обновить `JointCollection`, добавить именованные свойства для IDE).
  4. `kinect_next/utils/visualizer.py` (обновить кортеж костей `SKELETON_BONES`, если суставы нужно отрисовывать).
  5. `kinect_next/core/sensor.py` (парсинг суставов в цикле чтения `IBody`).

---

### Сценарий Г. Реэкспорт публичного API (Иерархия `__init__.py`)

Любой новый класс, функция или Enum **ДОЛЖНЫ** быть прописаны в `__all__` цепочки файлов:

1. `kinect_next/models/__init__.py` (или `core/__init__.py` / `utils/__init__.py`).
2. `kinect_next/__init__.py` (главный корневой файл пакета).

---

## 3. Низкоуровневые инварианты (Under-the-Hood)

### 3.1. Управление памятью COM и жизненный цикл указателей (RAII)

* Класс `COMBase` в `kinect_next/native/com_base.py` принимает параметр `owned: bool = True`.
* Если `owned=True`, при срабатывании `__del__` сборщик мусора Python вызывает нативный метод `IUnknown::Release()`.
* **Правило работы с массивами IBody:**
  При вызове `b_frame.get_and_refresh_body_data(6, bodies_native)` драйвер Kinect возвращает 6 «сырых» указателей на `IBody`. При оборачивании их в Python-класс обязательно указывается `IBody(ptr, owned=True)`. Как только список тел внутри кадра освобождается, память каждого тела в C++ SDK корректно очищается.

### 3.2. Массивы NumPy и Zero-Copy

* При передаче массивов в C-функции используется прямой указатель: `array.ctypes.data_as(ctypes.c_void_p)`.
* Буфер для цвета создается размером `(1080, 1920, 4)` формата `BGRA uint8`.
* Метод `ColorFrame.as_bgr()` использует срез `self.data[:, :, :3]`. Это **strided view**, которое занимает 0 байт дополнительной памяти и выполняется мгновенно.
* В аудио-субкадрах `IAudioBeamSubFrame.access_underlying_buffer()` (индекс 11) возвращает прямой Zero-Copy указатель на нативный C++ буфер 32-bit Float PCM.

### 3.3. Разница между прямым и обратным маппингом (Coordinate Mapping)

* **Depth $\to$ Color (`map_depth_frame_to_color_space`)**:
  Проецирует 217 088 точек глубины на цвет. Используется для окрашивания облака точек (Point Cloud).
  * *Не подходит для вырезания фона в 1080p*, так как на Full HD матрице точки располагаются с разрывами (эффект «решета»).
* **Color $\to$ Depth (`map_color_frame_to_depth_space`)**:
  Для каждого из 2 073 600 пикселей Full HD находит координату на матрице глубины. В сочетании с `cv2.remap(..., interpolation=cv2.INTER_NEAREST)` дает плотную, монолитную и резкую маску силуэта человека.

---

## 4. Справочник точных индексов VTable COM-интерфейсов

Ниже приведена полная карта индексов виртуальной таблицы методов (VTable) Kinect SDK 2.0:

### `IKinectSensor`

| Индекс | Метод                                  | Сигнатура                     | Описание                                      |
| :----------- | :------------------------------------------ | :------------------------------------- | :---------------------------------------------------- |
| `0..2`     | `QueryInterface`, `AddRef`, `Release` | Стандартные COM             | `IUnknown`                                          |
| `6`        | `Open`                                    | `()`                                 | Открытие сенсора                       |
| `7`        | `Close`                                   | `()`                                 | Закрытие сенсора                       |
| `8`        | `get_IsOpen`                              | `(BOOLEAN*)`                         | Проверка статуса открытия      |
| `9`        | `get_IsAvailable`                         | `(BOOLEAN*)`                         | Проверка готовности сенсора  |
| `16`       | `get_AudioSource`                         | `(IAudioSource**)`                   | Доступ к микрофонной решетке |
| `17`       | `OpenMultiSourceFrameReader`              | `(DWORD, IMultiSourceFrameReader**)` | Открытие видео-ридера              |
| `18`       | `get_CoordinateMapper`                    | `(ICoordinateMapper**)`              | Получение маппера координат  |

---

### `ICoordinateMapper`

| Индекс | Метод                     | Сигнатура                               | Описание                                                         |
| :----------- | :----------------------------- | :----------------------------------------------- | :----------------------------------------------------------------------- |
| `6`        | `MapCameraPointToDepthSpace` | `(CameraSpacePoint, DepthSpacePoint*)`         | 3D Camera Point$\to$ 2D Depth Point                                    |
| `7`        | `MapCameraPointToColorSpace` | `(CameraSpacePoint, ColorSpacePoint*)`         | 3D Camera Point$\to$ 2D Color Point                                    |
| `8`        | `MapDepthPointToCameraSpace` | `(DepthSpacePoint, USHORT, CameraSpacePoint*)` | 2D Depth Point + dist$\to$ 3D Camera Point                             |
| `9`        | `MapDepthPointToColorSpace`  | `(DepthSpacePoint, USHORT, ColorSpacePoint*)`  | 2D Depth Point + dist$\to$ 2D Color Point                              |
| `14`       | `MapDepthFrameToCameraSpace` | `(UINT, void*, UINT, void*)`                   | Весь Depth кадр$\to$ 3D Point Cloud (424x512x3)                |
| `15`       | `MapDepthFrameToColorSpace`  | `(UINT, void*, UINT, void*)`                   | Весь Depth кадр$\to$ Color пиксели (424x512x2)          |
| `16`       | `MapColorFrameToDepthSpace`  | `(UINT, void*, UINT, void*)`                   | Весь Color кадр$\to$ Depth пиксели (1080x1920x2)        |
| `19`       | `GetDepthCameraIntrinsics`   | `(CameraIntrinsicsNative*)`                    | Фокусные расстояния и дисторсия камеры |

---

### `IAudioSource`

| Индекс | Метод                      | Сигнатура            | Описание                                              |
| :----------- | :------------------------------ | :---------------------------- | :------------------------------------------------------------ |
| `6`        | `get_IsActive`                | `(BOOLEAN*)`                | Активность аудио-источника            |
| `8`        | `get_SubFrameLengthInBytes`   | `(UINT*)`                   | Размер субкадра (1024 байта)               |
| `9`        | `get_SubFrameDuration`        | `(TIMESPAN*)`               | Длительность субкадра (160 000 = 16 мс) |
| `10`       | `get_MaxSubFrameCountForRead` | `(UINT*)`                   | Макс. субкадров за чтение (8)            |
| `11`       | `OpenReader`                  | `(IAudioBeamFrameReader**)` | Открытие аудио-ридера                      |
| `12`       | `get_AudioBeams`              | `(IAudioBeamList**)`        | Доступ к лучам микрофона                 |

---

### `IAudioBeamFrameReader`

| Индекс | Метод                  | Сигнатура          | Описание                                                      |
| :----------- | :-------------------------- | :-------------------------- | :-------------------------------------------------------------------- |
| `3`        | `SubscribeFrameArrived`   | `(WAITABLE_HANDLE*)`      | Подписка на Win32 Event аудиокадра                |
| `4`        | `UnsubscribeFrameArrived` | `(WAITABLE_HANDLE)`       | Отписка от Win32 Event                                       |
| `6`        | `AcquireLatestBeamFrames` | `(IAudioBeamFrameList**)` | Захват последнего списка аудиокадров |

---

### `IAudioBeamFrame`

| Индекс | Метод                | Сигнатура               | Описание                                             |
| :----------- | :------------------------ | :------------------------------- | :----------------------------------------------------------- |
| `3`        | `get_AudioBeam`         | `(IAudioBeam**)`               | Получение объекта аудиолуча         |
| `4`        | `get_Duration`          | `(TIMESPAN*)`                  | Суммарная длительность кадра       |
| `5`        | `get_RelativeTimeStart` | `(TIMESPAN*)`                  | Timestamp начала кадра                            |
| `6`        | `get_SubFrameCount`     | `(UINT*)`                      | Количество субкадров в кадре (1–3) |
| `7`        | `GetSubFrame`           | `(UINT, IAudioBeamSubFrame**)` | Извлечение субкадра по индексу    |

---

### `IAudioBeamSubFrame`

| Индекс | Метод                        | Сигнатура                  | Описание                                                       |
| :----------- | :-------------------------------- | :---------------------------------- | :--------------------------------------------------------------------- |
| `3`        | `get_FrameLengthInBytes`        | `(UINT*)`                         | Размер буфера (1024 байта)                            |
| `4`        | `get_Duration`                  | `(TIMESPAN*)`                     | Длительность субкадра (16.0 мс)                  |
| `5`        | `get_BeamAngle`                 | `(float*)`                        | Азимут луча в радианах ($-50^\circ .. +50^\circ$) |
| `6`        | `get_BeamAngleConfidence`       | `(float*)`                        | Уверенность направления ($0.0 .. 1.0$)         |
| `7`        | `get_AudioBodyCorrelationCount` | `(UINT*)`                         | Кол-во ассоциированных скелетов            |
| `8`        | `GetAudioBodyCorrelation`       | `(UINT, IAudioBodyCorrelation**)` | Связка со скелетом (`tracking_id`)                   |
| `10`       | `CopyFrameDataToArray`          | `(UINT, BYTE*)`                   | Копирование Float32 PCM сэмплов                      |
| `11`       | `AccessUnderlyingBuffer`        | `(UINT*, BYTE**)`                 | Нативный Zero-Copy указатель                          |
| `12`       | `get_RelativeTime`              | `(TIMESPAN*)`                     | Временная метка субкадра                         |

---

### `IAudioBeam`

| Индекс | Метод                  | Сигнатура   | Описание                                       |
| :----------- | :-------------------------- | :------------------- | :----------------------------------------------------- |
| `3`        | `get_AudioSource`         | `(IAudioSource**)` | Источник аудио                            |
| `4`        | `get_AudioBeamMode`       | `(AudioBeamMode*)` | Режим луча (AUTOMATIC / MANUAL)               |
| `5`        | `put_AudioBeamMode`       | `(AudioBeamMode)`  | Установка режима луча               |
| `6`        | `get_BeamAngle`           | `(float*)`         | Чтение угла луча в радианах     |
| `7`        | `put_BeamAngle`           | `(float)`          | Ручная установка угла луча      |
| `8`        | `get_BeamAngleConfidence` | `(float*)`         | Уверенность направления луча |
| `9`        | `get_RelativeTime`        | `(TIMESPAN*)`      | Timestamp луча                                     |

---

## 5. Чек-лист проверки качества перед релизом

1. [X] **Статический анализ типов**: `mypy --strict kinect_next`
2. [X] **Синтаксический контроль**: `ruff check kinect_next`
3. [X] **Аппаратные тесты**:
    * `test_step1.py` (геометрия и флаги)
    * `test_step2.py` (Win32 DLL и CoordinateMapper)
    * `test_step3.py` (модели кадров и суставов)
    * `test_step4_live.py` (MultiSource видеопотоки + Point Cloud)
    * `test_step5_vtable_scanner.py` (VTable-контроль аудиоподсистемы)
    * `test_step6_audio_models.py` (аудио-метрики и WAV экспорт)
    * `test_step7_audio_live.py` (живая запись 16kHz звука и трекинг луча)
    * `test_step8_audio_skeleton_fusion.py` (детекция говорящего в OpenCV)
4. [X] **Версионирование**:
    * Обновить `version` в `pyproject.toml` (1.1.0).
    * Обновить `__version__` в `kinect_next/__init__.py` (1.1.0).
5. [ ] **Сборка дистрибутива**:
    ```bash
    python -m build
    ```
