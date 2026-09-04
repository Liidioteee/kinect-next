from kinect_next import JointType, Quaternion, StreamType, Vector3

# Проверка битовых флагов
streams = StreamType.COLOR | StreamType.DEPTH
print(f"Streams configured: {streams}")

# Проверка геометрии
v1 = Vector3(0.0, 0.0, 1.0)
v2 = Vector3(0.0, 1.0, 1.0)
print(f"Distance: {v1.distance_to(v2):.2f} meters")

q = Quaternion(0.0, 0.0, 0.0, 1.0)
print(f"Euler angles: {q.to_euler_angles()}")
print(f"Total joints count: {JointType.count()}")
print("✅ ШАГ 1 УСПЕШНО ВЫПОЛНЕН!")