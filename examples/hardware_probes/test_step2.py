import time

from kinect_next.native import (
    CameraSpacePoint,
    IKinectSensorNative,
    get_default_kinect_sensor,
)

print("Подключение к Kinect v2 SDK...")
raw_ptr = get_default_kinect_sensor()
sensor = IKinectSensorNative(raw_ptr)

print("Открытие сенсора...")
sensor.open()

print("Ожидание готовности сенсора (1-2 сек)...")
time.sleep(1.5)

is_open = sensor.is_open()
is_available = sensor.is_available()
print(f"Статус сенсора -> Открыт: {is_open}, Доступен: {is_available}")

mapper = sensor.get_coordinate_mapper()
print("Тестирование CoordinateMapper...")
pt = CameraSpacePoint(0.0, 0.0, 1.5)  # Точка по центру на расстоянии 1.5 метра
depth_pt = mapper.map_camera_point_to_depth_space(pt)
color_pt = mapper.map_camera_point_to_color_space(pt)

print("Проекция точки (0, 0, 1.5м):")
print(f"  -> На Depth-сенсор: x={depth_pt.x:.1f}, y={depth_pt.y:.1f}")
print(f"  -> На Color-сенсор: x={color_pt.x:.1f}, y={color_pt.y:.1f}")

sensor.close()
print("Сенсор успешно закрыт. Память очищена.")
print("✅ ШАГ 2 УСПЕШНО ВЫПОЛНЕН!")