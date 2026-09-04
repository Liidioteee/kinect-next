import cv2
import time
from kinect_next import KinectSensor, StreamType, draw_all_skeletons

print("Запуск интерактивного просмотрщика Kinect v2...")
print("Управление:")
print("  - Клавиша 'S': сохранить 3D Point Cloud в файл 'kinect_mesh.ply'")
print("  - Клавиша 'ESC' или 'Q': выход")

with KinectSensor(streams=StreamType.COLOR | StreamType.DEPTH | StreamType.BODY) as kinect:
    fps_time = time.time()
    fps = 0.0

    for frameset in kinect.poll_frames():
        if not frameset.color or not frameset.depth:
            continue

        # 1. Получаем HD изображение (1920x1080) и карту глубины
        color_bgr = frameset.color.as_bgr().copy()
        depth_img = frameset.depth.to_normalized_uint8()
        depth_colored = cv2.applyColorMap(depth_img, cv2.COLORMAP_JET)

        # 2. Отрисовываем скелеты и кисти рук прямо на HD камере и на карте глубины!
        draw_all_skeletons(color_bgr, frameset.bodies, kinect.mapper, target_space="color")
        draw_all_skeletons(depth_colored, frameset.bodies, kinect.mapper, target_space="depth")

        # 3. Расчет FPS
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / (now - fps_time)) if fps > 0 else 30.0
        fps_time = now

        # 4. Отображение информации
        tracked_count = len(frameset.tracked_bodies)
        cv2.putText(color_bgr, f"FPS: {fps:.1f} | Tracked People: {tracked_count}", (30, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)

        # Сжимаем HD превью для удобного показа на экране (1280x720)
        color_preview = cv2.resize(color_bgr, (1280, 720))

        cv2.imshow("Kinect v2 - Skeleton Tracking (HD Color)", color_preview)
        cv2.imshow("Kinect v2 - Depth Map", depth_colored)

        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord('q'), ord('Q')):
            break
        elif key in (ord('s'), ord('S')):
            print("Сохранение 3D облака точек в 'kinect_mesh.ply'...")
            from kinect_next import save_point_cloud_ply
            pcd = kinect.mapper.generate_point_cloud(frameset.depth, frameset.color)
            save_point_cloud_ply("kinect_mesh.ply", pcd)
            print(f" -> Успешно сохранено {len(pcd.points):,} точек!")

cv2.destroyAllWindows()
print("Работа завершена.")