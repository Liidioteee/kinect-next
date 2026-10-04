
# 🛠 Архитектурная инструкция для разработчиков (Handover Guide)

> **Назначение документа**: Данное руководство предназначено для текущих и будущих разработчиков библиотеки `kinect-next`. В нем описана внутренняя архитектура, правила управления памятью, низкоуровневые COM-механизмы, а также **матрица жестких взаимосвязей между файлами** (что и где нужно менять одновременно, чтобы не вызвать краш процесса).

> ⚠️ **Актуальность**: документ описывает общую архитектуру. Точечные изменения
> (ленивая загрузка `Kinect20.dll`, VTable по именам методов, событийные ожидания,
> фоновый поток аудио, потокобезопасное закрытие, флаг `reuse_buffers`) перечислены в
> [CHANGELOG.md](CHANGELOG.md).

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
│   │   ├── com_base.py         # Базовый класс COMBase (VTable по именам методов, RAII IUnknown::Release)
│   │   ├── win32.py            # Win32 Kernel32 API (события, ожидания) + загрузка Kinect20.dll
│   │   └── interfaces.py       # COM-интерфейсы Kinect SDK 2.0 (видео, маппер и аудиоподсистема)
│   │
│   ├── core/                   # [Layer 1: Runtime Engine] Движок захвата и математический аппарат
│   │   ├── __init__.py         # Реэкспорт ядра (KinectSensor, CoordinateMapper, AudioController, Enums, Exceptions)
│   │   ├── _audio_pump.py      # Фоновый поток непрерывного захвата звука (AudioPump) и разбор субкадров
│   │   ├── _cancel.py          # Кооперативная отмена ожиданий (CancelToken) для asyncio-обёртки
│   │   ├── audio.py            # Контроллер лучеформирования (AudioController: наведение, привязка к телу)
│   │   ├── enums.py            # Строго типизированные IntEnum и IntFlag (JointType, HandState, AudioBeamMode)
│   │   ├── exceptions.py       # Дерево кастомных исключений (KinectError, COMOperationError, AudioStreamError)
│   │   ├── mapper.py           # Векторизованный CoordinateMapper (Point Cloud, 2D/3D трансформации)
│   │   └── sensor.py           # Главный контроллер KinectSensor (событийный захват, блокировки, жизненный цикл)
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
  2. `kinect_next/native/interfaces.py` (метод-обёртка, вызывающий `self._call("ИмяМетодаSDK", argtypes, ...)` или помощники `_get_int` / `_get_float` / `_get_bool` / `_get_struct` / `_get_interface`).
  3. `tests/test_interfaces.py` (строка в таблице `EXPECTED`: какой метод SDK оборачивает новый метод Python).
  4. `kinect_next/core/mapper.py`, `kinect_next/core/sensor.py` или `kinect_next/core/audio.py` (верхнеуровневая обертка).
* **Критическое правило:**
  > Индексы VTable **не пишутся руками вообще**. Каждый класс интерфейса перечисляет в `_vtable_` имена *всех* методов интерфейса в порядке их объявления в `Kinect.h` (после трёх методов `IUnknown`); `COMBase` сам вычисляет слот по имени. Список берётся из заголовка SDK, а не подбирается перебором: смещение даже на 1 вызывает чужой метод с чужими аргументами — причём часто без видимой ошибки.
  >
  > Раскладки закреплены тестами: `tests/data/kinect_vtables.json` — снимок `Kinect.h` (обновляется командой `python tests/kinect_header.py`), `tests/test_vtable_layout.py` сверяет с ним каждый `_vtable_` (а при установленном SDK — снимок с самим заголовком), `tests/test_interfaces.py` вызывает каждый метод через настоящую VTable и проверяет, что он попал в нужный слот.
  >

---

### Сценарий Б. Добавление нового потока данных

* **Файлы:**
  1. `kinect_next/core/enums.py` (добавить флаг в `StreamType`).
  2. `kinect_next/native/interfaces.py` (описать соответствующий `I...FrameReader` и `I...Frame`).
  3. `kinect_next/models/` (создать новый файл модели, например `audio.py`).
  4. `kinect_next/models/frameset.py` (добавить поле нового кадра в датакласс `FrameSet`).
  5. `kinect_next/core/sensor.py` (в методе `_read_frameset()` добавить блок извлечения нового кадра при наличии флага в `self._streams`).
  6. `tests/fakes.py` и `tests/test_sensor.py` (фейк нового кадра и тест его чтения).
  7. Все файлы `__init__.py` (пробросить импорты наружу).

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
* `COMBase` — контекстный менеджер: `with ref.acquire_frame() as frame:` освобождает указатель при выходе из блока, не дожидаясь сборщика мусора. `release()` идемпотентен.
* **Правило работы с массивами IBody:**
  `IBodyFrame.get_bodies(6)` вызывает `GetAndRefreshBodyData` и сразу оборачивает каждый ненулевой указатель во владеющий `IBody`. `KinectSensor._parse_bodies` освобождает их все в `finally`, даже если разбор одного из тел упал.

### 3.1a. События, ожидания и потоки

* **Событие нужно «перезаряжать».** `WAITABLE_HANDLE` от `Subscribe…FrameArrived` остаётся взведённым, пока не вызван `Get…FrameArrivedEventData` — это делают `reader.clear_frame_arrived(handle)`. Без этого `WaitFor…` возвращается мгновенно и цикл ожидания превращается в холостую прокрутку (100 % ядра).
* **Видео:** `KinectSensor._next_multi_frame` ждёт на двух дескрипторах — событии кадра и внутреннем `_wake_event`. Второй взводят `close()` и отмена ожидания (`_interrupt()`), после чего ожидающий перепроверяет флаги и бросает `KinectClosedError` / `WaitCancelledError`.
* **Аудио:** SDK отдаёт только *последний* аудиокадр (1–2 субкадра по 16 мс); ссылки на более старые протухают. Поэтому `core/_audio_pump.py` держит фоновый поток, который по каждому событию копирует субкадры в ограниченную очередь; `wait_for_frames()` и `wait_for_audio_frame()` только забирают накопленное.
* **Аудио и GIL:** интерфейсы аудио-захвата помечены `_hold_gil_ = True` — их вызовы идут через `ctypes.PYFUNCTYPE` и не отпускают GIL (десятки микросекундных геттеров на кадр иначе означали бы десятки переочередей за GIL). Потоку всё равно нужен GIL после пробуждения; при плотной занятости GIL чужим Python-кодом субкадры могут теряться — это считается в `AudioPump.missed_subframes` / `KinectSensor.audio_subframes_lost`. Надёжное решение на будущее — читать PCM из `IAudioBeam::OpenInputStream`, который буферизует звук внутри SDK.
* **Блокировка:** захват видео и жизненный цикл защищены `KinectSensor._lock` (RLock). `close()` сначала будит ожидающих, затем берёт блокировку и разбирает ресурсы.
* **Запуск сенсора:** после `Open()` данные появляются через 1–3 с, а вскоре после первых кадров рантайм ещё раз приостанавливает выдачу на 1,5–3 с (проверено «сырыми» вызовами SDK). Отсюда `DEFAULT_TIMEOUT_MS = 5000`; тесты на железе сначала ждут ровного потока.

### 3.2. Массивы NumPy: одно копирование и представления

* При передаче массивов в C-функции используется прямой указатель: `array.ctypes.data_as(ctypes.c_void_p)`.
* Буфер для цвета создается размером `(1080, 1920, 4)` формата `BGRA uint8`.
* Метод `ColorFrame.as_bgr()` использует срез `self.data[:, :, :3]`. Это **strided view**, которое занимает 0 байт дополнительной памяти и выполняется мгновенно.
* Кадры копируются из драйвера один раз (`Copy…FrameDataToArray`) — массив принадлежит Python и остаётся валидным после освобождения COM-кадра.
* `CoordinateMapper` передаёт в драйвер адрес буфера глубины, поэтому вход проверяется (`_depth_buffer`): форма `(424, 512)`, `uint16`, C-смежность (несмежные представления копируются).
* В аудио-субкадрах `IAudioBeamSubFrame.access_underlying_buffer()` возвращает `(размер, адрес)` нативного буфера 32-bit Float PCM; он действителен только до освобождения субкадра.

### 3.3. Разница между прямым и обратным маппингом (Coordinate Mapping)

* **Depth $\to$ Color (`map_depth_frame_to_color_space`)**:
  Проецирует 217 088 точек глубины на цвет. Используется для окрашивания облака точек (Point Cloud).
  * *Не подходит для вырезания фона в 1080p*, так как на Full HD матрице точки располагаются с разрывами (эффект «решета»).
* **Color $\to$ Depth (`map_color_frame_to_depth_space`)**:
  Для каждого из 2 073 600 пикселей Full HD находит координату на матрице глубины. В сочетании с `cv2.remap(..., interpolation=cv2.INTER_NEAREST)` дает плотную, монолитную и резкую маску силуэта человека.

---

## 4. Справочник точных индексов VTable COM-интерфейсов

Источник истины — кортежи `_vtable_` в `kinect_next/native/interfaces.py`, сверенные с
`Kinect.h` (см. сценарий А). Таблицы ниже — справка; аудио-таблицы сгенерированы из
снимка заголовка `tests/data/kinect_vtables.json` и перечисляют **все** слоты подряд.

> До версии с проверкой по заголовку шесть аудио-слотов были записаны со сдвигом
> (`get_IsActive`, `IAudioBeam::get_RelativeTime`, `IAudioBeamFrame::get_AudioBeam` /
> `get_RelativeTimeStart`, `IAudioBeamSubFrame::get_AudioBodyCorrelationCount` /
> `GetAudioBodyCorrelation`) — их находили перебором, а не по заголовку.

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

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `SubscribeFrameCaptured` | — |
| `4` | `UnsubscribeFrameCaptured` | — |
| `5` | `GetFrameCapturedEventData` | — |
| `6` | `get_KinectSensor` | — |
| `7` | `get_IsActive` | `get_is_active()` |
| `8` | `get_SubFrameLengthInBytes` | `get_sub_frame_length_in_bytes()` |
| `9` | `get_SubFrameDuration` | `get_sub_frame_duration()` |
| `10` | `get_MaxSubFrameCount` | `get_max_sub_frame_count_for_read()` |
| `11` | `OpenReader` | `open_reader()` |
| `12` | `get_AudioBeams` | `get_audio_beams()` |
| `13` | `get_AudioCalibrationState` | `get_audio_calibration_state()` |

---

### `IAudioBeamFrameReader`

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `SubscribeFrameArrived` | `subscribe_frame_arrived()` |
| `4` | `UnsubscribeFrameArrived` | `unsubscribe_frame_arrived()` |
| `5` | `GetFrameArrivedEventData` | `clear_frame_arrived()` |
| `6` | `AcquireLatestBeamFrames` | `acquire_latest_beam_frames()` |
| `7` | `get_IsPaused` | — |
| `8` | `put_IsPaused` | — |
| `9` | `get_AudioSource` | — |

---

### `IAudioBeamFrameList`

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `get_BeamCount` | `get_count()` |
| `4` | `OpenAudioBeamFrame` | `open_audio_beam_frame()` |

---

### `IAudioBeamFrame`

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `get_AudioSource` | — |
| `4` | `get_Duration` | `get_duration()` |
| `5` | `get_AudioBeam` | `get_audio_beam()` |
| `6` | `get_SubFrameCount` | `get_sub_frame_count()` |
| `7` | `GetSubFrame` | `get_sub_frame()` |
| `8` | `get_RelativeTimeStart` | `get_relative_time_start()` |

---

### `IAudioBeamSubFrame`

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `get_FrameLengthInBytes` | `get_frame_length_in_bytes()` |
| `4` | `get_Duration` | `get_duration()` |
| `5` | `get_BeamAngle` | `get_beam_angle()` |
| `6` | `get_BeamAngleConfidence` | `get_beam_angle_confidence()` |
| `7` | `get_AudioBeamMode` | `get_audio_beam_mode()` |
| `8` | `get_AudioBodyCorrelationCount` | `get_audio_body_correlation_count()` |
| `9` | `GetAudioBodyCorrelation` | `get_audio_body_correlation()` |
| `10` | `CopyFrameDataToArray` | `copy_frame_data_to_array()` |
| `11` | `AccessUnderlyingBuffer` | `access_underlying_buffer()` |
| `12` | `get_RelativeTime` | `get_relative_time()` |

---

### `IAudioBodyCorrelation`

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `get_BodyTrackingId` | `get_body_tracking_id()` |

---

### `IAudioBeamList`

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `get_BeamCount` | `get_beam_count()` |
| `4` | `OpenAudioBeam` | `open_audio_beam()` |

---

### `IAudioBeam`

| Индекс | Метод SDK | Обёртка в `interfaces.py` |
| :--- | :--- | :--- |
| `3` | `get_AudioSource` | `get_audio_source()` |
| `4` | `get_AudioBeamMode` | `get_audio_beam_mode()` |
| `5` | `put_AudioBeamMode` | `put_audio_beam_mode()` |
| `6` | `get_BeamAngle` | `get_beam_angle()` |
| `7` | `put_BeamAngle` | `put_beam_angle()` |
| `8` | `get_BeamAngleConfidence` | `get_beam_angle_confidence()` |
| `9` | `OpenInputStream` | — |
| `10` | `get_RelativeTime` | `get_relative_time()` |

---

## 5. Чек-лист проверки качества перед релизом

1. [X] **Статический анализ типов**: `mypy kinect_next` (strict задан в `pyproject.toml`)
2. [X] **Синтаксический контроль**: `ruff check kinect_next tests` и `ruff format --check kinect_next tests`
3. [X] **Тесты без железа**: `pytest` (фейки нативного слоя + настоящая in-process VTable)
4. [X] **Тесты на сенсоре**: `pytest --run-hardware`
5. [X] **Скрипты ручной проверки** (`examples/hardware_probes/`):
    * `test_step1.py` (геометрия и флаги)
    * `test_step2.py` (Win32 DLL и CoordinateMapper)
    * `test_step3.py` (модели кадров и суставов)
    * `test_step4_live.py` (MultiSource видеопотоки + Point Cloud)
    * `test_step5.py` (нативный COM-слой аудио; `test_step5_deb.py` — исторический сканер VTable, раскладку проверяет `tests/test_vtable_layout.py`)
    * `test_step6.py` (аудио-метрики и WAV экспорт)
    * `test_step7.py` (живая запись 16kHz звука и трекинг луча)
    * `test_step8.py` (детекция говорящего в OpenCV)
6. [X] **Версионирование**:
    * Обновить `__version__` в `kinect_next/__init__.py` — `pyproject.toml` берёт версию оттуда.
    * Перенести раздел `[Unreleased]` в `CHANGELOG.md` под новый номер версии.
7. [ ] **Сборка дистрибутива**:
    ```bash
    python -m build
    ```
