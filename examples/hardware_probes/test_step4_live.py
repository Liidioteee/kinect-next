import time

from kinect_next import KinectSensor, StreamType

print("Инициализация KinectSensor с потоками COLOR, DEPTH, BODY, INFRARED...")

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH | StreamType.BODY | StreamType.INFRARED) as kinect:
    print("Сенсор успешно открыт. Ожидание первого кадра...")
    
    start_time = time.time()
    frames_count = 0

    for frameset in kinect.poll_frames():
        frames_count += 1
        
        # Проверяем полученные кадры
        c_shape = frameset.color.data.shape if frameset.color else None
        d_shape = frameset.depth.data.shape if frameset.depth else None
        ir_shape = frameset.infrared.data.shape if frameset.infrared else None
        tracked = len(frameset.tracked_bodies)

        print(f"Кадр #{frames_count:02d} | Color: {c_shape} | Depth: {d_shape} | IR: {ir_shape} | Людей в кадре: {tracked}")
        
        # Тестируем Point Cloud генератор на 5-м кадре
        if frames_count == 5 and frameset.depth and frameset.color:
            print(" -> Тестирование генератора Point Cloud...")
            pcd = kinect.mapper.generate_point_cloud(frameset.depth, frameset.color)
            print(f" -> Сгенерировано 3D точек: {len(pcd.points):,} | Массив цветов: {pcd.colors.shape if pcd.colors is not None else None}")

        if frames_count >= 10:
            break

    elapsed = time.time() - start_time
    fps = frames_count / elapsed
    print(f"\nУспешно получено {frames_count} кадров за {elapsed:.2f} сек. (~{fps:.1f} FPS)")

print("✅ ШАГ 4 УСПЕШНО ВЫПОЛНЕН!")