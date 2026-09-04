import numpy as np

from kinect_next import (
    Body,
    ColorFrame,
    DepthFrame,
    FrameEdges,
    FrameSet,
    Hand,
    HandState,
    Joint,
    JointCollection,
    JointType,
    Point2D,
    Quaternion,
    TrackingConfidence,
    TrackingState,
    Vector3,
)

# 1. Проверка ColorFrame и Zero-Copy среза
color_raw = np.zeros((1080, 1920, 4), dtype=np.uint8)
color_raw[0, 0] = [255, 128, 64, 255]  # BGRA
c_frame = ColorFrame(data=color_raw)
bgr = c_frame.as_bgr()
print(f"ColorFrame shape: {c_frame.data.shape}, BGR view shape: {bgr.shape}")
assert bgr[0, 0, 0] == 255 and bgr[0, 0, 1] == 128 and bgr[0, 0, 2] == 64

# 2. Проверка DepthFrame
depth_raw = np.full((424, 512), 1500, dtype=np.uint16)  # 1.5 метра
d_frame = DepthFrame(data=depth_raw)
print(f"Depth at center: {d_frame.distance_at(256, 212):.2f} meters")
assert d_frame.distance_at(256, 212) == 1.5

# 3. Проверка суставов и автокомплита
j_head = Joint(
    joint_type=JointType.HEAD,
    position=Vector3(0.0, 0.5, 1.8),
    tracking_state=TrackingState.TRACKED,
    orientation=Quaternion(0.0, 0.0, 0.0, 1.0),
)
joints_dict = {JointType.HEAD: j_head}
# Заполним остальные дефолтными для теста
for jt in JointType:
    if jt not in joints_dict:
        joints_dict[jt] = Joint(jt, Vector3(0,0,0), TrackingState.NOT_TRACKED, Quaternion(0,0,0,1))

j_col = JointCollection(joints_dict)
body = Body(
    tracking_id=12345,
    is_tracked=True,
    is_restricted=False,
    joints=j_col,
    hand_left=Hand(HandState.OPEN, TrackingConfidence.HIGH),
    hand_right=Hand(HandState.CLOSED, TrackingConfidence.HIGH),
    lean=Point2D(0.0, 0.0),
    lean_tracking_state=TrackingState.TRACKED,
    clipped_edges=FrameEdges.NONE,
)

frameset = FrameSet(color=c_frame, depth=d_frame, bodies=[body])
print(f"Tracked bodies in FrameSet: {len(frameset.tracked_bodies)}")
print(f"User head Y position: {frameset.tracked_bodies[0].joints.head.position.y} meters")
print(f"User right hand state: {frameset.tracked_bodies[0].hand_right.state}")

print("✅ ШАГ 3 УСПЕШНО ВЫПОЛНЕН!")