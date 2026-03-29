"""
Racing Line Overlay
====================
Reads state estimation poses from two MCAP files:
  - hackathon_fast_laps.mcap  → builds the "optimal" racing line (x_m, y_m, z_m)
  - hackathon_good_lap.mcap   → provides ego pose + front-left camera image

Projects the optimal racing line into the camera image using:
  - Camera intrinsics  (from camera_fl_info.yaml)
  - Camera extrinsics  (camera-to-vehicle transform — edit EXTRINSICS below)

Requirements (pip install):
    mcap mcap-ros2-support opencv-python numpy

Usage:
    python3 racing_line_overlay.py
    python3 racing_line_overlay.py --fast hackathon_fast_laps.mcap \
                                    --good  hackathon_good_lap.mcap \
                                    --out   output_frames/
"""

import argparse
import os
import json
import struct
from pathlib import Path

import cv2
import numpy as np

try:
    from mcap_ros2.reader import read_ros2_messages
except ImportError:
    read_ros2_messages = None

# ---------------------------------------------------------------------------
# CONFIG — edit these values to match your setup
# ---------------------------------------------------------------------------

# State estimation topic (same in both files)
STATE_TOPIC = "/constructor0/state_estimation"          # adjust if different

# Camera image topic (in good lap file)
IMAGE_TOPIC = "/constructor0/sensor/camera_fl/compressed_image"

# Camera intrinsics from camera_fl_info.yaml
K = np.array([
    [2555.26339,    0.0,       751.52582],
    [   0.0,     2538.42728,  469.37862],
    [   0.0,        0.0,         1.0   ]
], dtype=np.float64)

D = np.array([-0.38385, 0.1615, -0.00085, 0.00053, 0.0], dtype=np.float64)

IMAGE_SIZE = (1506, 728)   # (width, height)

# ---------------------------------------------------------------------------
# EXTRINSICS — camera pose in vehicle frame
#
# This is the rigid transform that moves a point from the VEHICLE frame
# into the CAMERA frame:   p_cam = R_ext @ p_veh + t_ext
#
# If you have a calibration file, replace the values below.
# The defaults assume the front-left camera is:
#   - 1.5 m forward of the vehicle origin
#   - 0.5 m to the left
#   - 1.3 m above ground
#   - rotated so it looks forward (+X vehicle = +Z camera)
#
# Common ROS convention (camera looking along +Z, right = +X, down = +Y):
#   vehicle +X (forward) → camera +Z
#   vehicle +Y (left)    → camera -X
#   vehicle +Z (up)      → camera -Y
# ---------------------------------------------------------------------------
def build_default_extrinsics():
    # Translation: camera position in vehicle frame [m]
    t_cam_in_veh = np.array([1.5, 0.5, 1.3])

    # Rotation: vehicle frame → camera frame
    # Standard forward-facing camera rotation
    R_veh_to_cam = np.array([
        [ 0, -1,  0],   # cam X = -veh Y
        [ 0,  0, -1],   # cam Y = -veh Z
        [ 1,  0,  0],   # cam Z =  veh X
    ], dtype=np.float64)

    return R_veh_to_cam, t_cam_in_veh

# Override here if you have real extrinsics, e.g.:
# R_EXT = np.array([...])   # 3x3
# T_EXT = np.array([x, y, z])
R_EXT, T_EXT = build_default_extrinsics()

# ---------------------------------------------------------------------------
# Visualisation settings
# ---------------------------------------------------------------------------
LOOK_AHEAD_M   = 40.0    # how far ahead of ego to draw the line [m]
LOOK_BEHIND_M  = 0.0     # how far behind ego to draw the line [m]
LINE_COLOR      = (0, 255, 80)    # BGR green
LINE_THICKNESS  = 3
DOT_COLOR       = (0, 80, 255)    # BGR orange-red for nearest point
DOT_RADIUS      = 8
SMOOTHING_WIN   = 20     # smoothing window for the racing line [samples]


def _euler_zyx_to_matrix(yaw, pitch, roll):
    """Return a 3x3 rotation matrix for ZYX Euler angles (yaw, pitch, roll)."""
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cr, sr = np.cos(roll), np.sin(roll)

    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ], dtype=np.float64)


def _moving_average_1d(values, window):
    """Centered moving average with edge padding (SciPy-free fallback)."""
    if window <= 1 or len(values) < 2:
        return values
    kernel = np.ones(window, dtype=np.float64) / float(window)
    pad_left = window // 2
    pad_right = window - 1 - pad_left
    padded = np.pad(values, (pad_left, pad_right), mode="edge")
    return np.convolve(padded, kernel, mode="valid")

# ---------------------------------------------------------------------------
# MCAP helpers
# ---------------------------------------------------------------------------

def open_mcap(path):
    """Return an mcap Reader. Supports ros2 and protobuf schemas."""
    from mcap.reader import make_reader
    return make_reader(open(path, "rb"))


def _require_ros2_reader():
    if read_ros2_messages is None:
        raise RuntimeError(
            "mcap_ros2 is required. Install with: pip install mcap mcap-ros2-support"
        )


def _timestamp_from_header_or_logtime(ros_msg, fallback_ns):
    if hasattr(ros_msg, "header") and hasattr(ros_msg.header, "stamp"):
        stamp = ros_msg.header.stamp
        sec = float(getattr(stamp, "sec", 0.0))
        nsec = float(getattr(stamp, "nanosec", 0.0))
        return sec + nsec * 1e-9
    return fallback_ns * 1e-9


def _msg_float(ros_msg, *names, default=None):
    for name in names:
        if hasattr(ros_msg, name):
            value = getattr(ros_msg, name)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
    if default is None:
        return None
    return float(default)


def iter_state_msgs(mcap_path, topic):
    """
    Yield dicts with keys: timestamp, x_m, y_m, z_m, yaw, pitch, roll
    Reads ROS2 messages from MCAP.
    """
    _require_ros2_reader()
    checked_fields = False
    for message in read_ros2_messages(str(mcap_path), topics=[topic]):
        ros_msg = message.ros_msg
        ts = _timestamp_from_header_or_logtime(ros_msg, message.log_time)
        x_m = _msg_float(ros_msg, "x_m")
        y_m = _msg_float(ros_msg, "y_m")
        z_m = _msg_float(ros_msg, "z_m")
        yaw = _msg_float(ros_msg, "yaw", "yaw_rad")
        pitch = _msg_float(ros_msg, "pitch", "pitch_rad")
        roll = _msg_float(ros_msg, "roll", "roll_rad")

        if not checked_fields:
            missing = []
            if x_m is None:
                missing.append("x_m")
            if y_m is None:
                missing.append("y_m")
            if z_m is None:
                missing.append("z_m")
            if yaw is None:
                missing.append("yaw/yaw_rad")
            if pitch is None:
                missing.append("pitch/pitch_rad")
            if roll is None:
                missing.append("roll/roll_rad")
            if missing:
                raise RuntimeError(
                    f"State message on '{topic}' is missing required fields: {', '.join(missing)}"
                )
            checked_fields = True

        yield {
            "timestamp": ts,
            "x_m": x_m,
            "y_m": y_m,
            "z_m": z_m,
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
        }


def decode_state(schema, raw_bytes):
    """
    Try common encodings for a state estimation message.
    Adjust field names here if your message type differs.
    """
    enc = schema.encoding if schema else ""

    # --- ROS2 / CDR encoding ---
    if enc in ("ros2msg", "cdr", ""):
        try:
            from mcap_ros2.decoder import DecoderFactory
            # DecoderFactory is used at the reader level; here we get raw dict
            pass
        except ImportError:
            pass
        # Fall through to JSON attempt
        try:
            obj = json.loads(raw_bytes)
            return _extract_state_from_dict(obj)
        except Exception:
            pass

    # --- JSON encoding ---
    if enc == "jsonschema":
        try:
            obj = json.loads(raw_bytes)
            return _extract_state_from_dict(obj)
        except Exception:
            pass

    return None


def _extract_state_from_dict(obj):
    """Pull pose fields from a decoded message dict. Handles nested structures."""
    # Try flat fields first
    keys_needed = ["x_m", "y_m", "z_m"]
    if all(k in obj for k in keys_needed):
        return {
            "x_m":  float(obj.get("x_m", 0)),
            "y_m":  float(obj.get("y_m", 0)),
            "z_m":  float(obj.get("z_m", 0)),
            "yaw":  float(obj.get("yaw", obj.get("yaw_rad", 0))),
            "pitch":float(obj.get("pitch", obj.get("pitch_rad", 0))),
            "roll": float(obj.get("roll", obj.get("roll_rad", 0))),
        }
    # Try nested pose/position
    for sub in ["pose", "position", "state"]:
        if sub in obj:
            result = _extract_state_from_dict(obj[sub])
            if result:
                return result
    return None


def iter_image_msgs(mcap_path, topic):
    """
    Yield (timestamp_s, compressed_bytes) for each image on the topic.
    Handles sensor_msgs/CompressedImage (ROS2).
    """
    _require_ros2_reader()
    for message in read_ros2_messages(str(mcap_path), topics=[topic]):
        ros_msg = message.ros_msg
        raw = getattr(ros_msg, "data", None)
        if raw is None:
            continue
        arr = np.frombuffer(bytes(raw), dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            continue
        ts = _timestamp_from_header_or_logtime(ros_msg, message.log_time)
        yield ts, img


def decode_compressed_image(schema, raw_bytes):
    """
    Decode a ROS2 CompressedImage message.
    Layout: std_msgs/Header (variable) + string format + uint8[] data
    We try a fast approach: find the JPEG/PNG magic bytes directly.
    """
    # Look for JPEG SOI marker (FF D8)
    idx = raw_bytes.find(b'\xff\xd8')
    if idx != -1:
        arr = np.frombuffer(raw_bytes[idx:], dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            return img

    # Look for PNG magic
    idx = raw_bytes.find(b'\x89PNG')
    if idx != -1:
        arr = np.frombuffer(raw_bytes[idx:], dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            return img

    return None


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def poses_to_array(poses):
    """Convert list of pose dicts to Nx6 numpy array [x,y,z,yaw,pitch,roll]."""
    return np.array([[p["x_m"], p["y_m"], p["z_m"],
                      p["yaw"], p["pitch"], p["roll"]] for p in poses])


def smooth_path(xyz, window=SMOOTHING_WIN):
    """Apply uniform smoothing to reduce noise in the racing line."""
    if len(xyz) < window:
        return xyz
    smoothed = np.stack([
        _moving_average_1d(xyz[:, 0], window=window),
        _moving_average_1d(xyz[:, 1], window=window),
        _moving_average_1d(xyz[:, 2], window=window),
    ], axis=1)
    return smoothed


def world_to_camera(pts_world, ego_pose, R_ext, t_ext):
    """
    Transform Nx3 world points into camera pixel coords.

    ego_pose: dict with x_m, y_m, z_m, yaw, pitch, roll  (vehicle in world)
    Returns:
        pts_px  : Nx2 float array of pixel coords (may be outside image)
        in_front: bool mask — True if point is in front of camera
    """
    # 1. World → vehicle frame
    t_ego = np.array([ego_pose["x_m"], ego_pose["y_m"], ego_pose["z_m"]])
    R_ego = _euler_zyx_to_matrix(
        ego_pose["yaw"], ego_pose["pitch"], ego_pose["roll"]
    )

    # For row vectors, (p_world - t_ego) @ R_ego is equivalent to column form R_ego.T @ (p_world - t_ego).
    pts_veh = (pts_world - t_ego) @ R_ego

    # 2. Vehicle → camera frame
    # p_cam = R_ext @ p_veh + t_ext  (t_ext is camera position in veh frame)
    pts_cam = (pts_veh - t_ext) @ R_ext.T

    in_front = pts_cam[:, 2] > 0.5   # only points with positive depth

    # 3. Project with distortion
    pts_norm = pts_cam[:, :2] / np.maximum(pts_cam[:, 2:3], 1e-6)

    x, y = pts_norm[:, 0], pts_norm[:, 1]
    r2 = x**2 + y**2
    k1, k2, p1, p2, k3 = D
    radial = 1 + k1*r2 + k2*r2**2 + k3*r2**3
    x_d = x*radial + 2*p1*x*y + p2*(r2 + 2*x**2)
    y_d = y*radial + p1*(r2 + 2*y**2) + 2*p2*x*y

    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    u = fx * x_d + cx
    v = fy * y_d + cy

    pts_px = np.stack([u, v], axis=1)
    return pts_px, in_front


def filter_by_distance(racing_xyz, ego_pos, look_ahead=LOOK_AHEAD_M, look_behind=LOOK_BEHIND_M):
    """Keep only racing line points within [look_behind, look_ahead] metres of ego."""
    diff = racing_xyz - ego_pos
    dist = np.linalg.norm(diff[:, :2], axis=1)   # 2D distance
    return dist <= look_ahead   # simple radius; refine below with signed dist

    # Signed distance along ego heading would be better but needs yaw — done in draw step


def closest_index(racing_xyz, ego_pos):
    diff = racing_xyz[:, :2] - ego_pos[:2]
    return int(np.argmin(np.linalg.norm(diff, axis=1)))


def _collect_indices_forward(racing_xyz, start_idx, distance_m):
    """Collect contiguous indices forward from start_idx until distance_m is reached."""
    n = len(racing_xyz)
    if n == 0 or distance_m <= 0:
        return [start_idx]
    idxs = [start_idx]
    travelled = 0.0
    i = start_idx
    for _ in range(n - 1):
        j = (i + 1) % n
        step = float(np.linalg.norm(racing_xyz[j, :2] - racing_xyz[i, :2]))
        travelled += step
        idxs.append(j)
        i = j
        if travelled >= distance_m:
            break
    return idxs


def _collect_indices_backward(racing_xyz, start_idx, distance_m):
    """Collect contiguous indices backward from start_idx until distance_m is reached."""
    n = len(racing_xyz)
    if n == 0 or distance_m <= 0:
        return []
    idxs = []
    travelled = 0.0
    i = start_idx
    for _ in range(n - 1):
        j = (i - 1) % n
        step = float(np.linalg.norm(racing_xyz[i, :2] - racing_xyz[j, :2]))
        travelled += step
        idxs.append(j)
        i = j
        if travelled >= distance_m:
            break
    idxs.reverse()
    return idxs


def select_racing_segment_indices(racing_xyz, closest_idx, look_ahead_m=LOOK_AHEAD_M, look_behind_m=LOOK_BEHIND_M):
    """
    Build a contiguous racing-line segment around closest_idx.
    By default this draws only the next 40 m ahead.
    """
    behind = _collect_indices_backward(racing_xyz, closest_idx, look_behind_m)
    ahead = _collect_indices_forward(racing_xyz, closest_idx, look_ahead_m)
    return np.array(behind + ahead, dtype=np.int64)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw_racing_line(image, pts_px, in_front, img_w, img_h):
    """Draw polyline of projected racing line points onto image."""
    # Filter to visible + in-image points
    valid = in_front.copy()
    valid &= (pts_px[:, 0] > -img_w) & (pts_px[:, 0] < 2*img_w)
    valid &= (pts_px[:, 1] > -img_h) & (pts_px[:, 1] < 2*img_h)

    pts_valid = pts_px[valid].astype(np.int32)
    if len(pts_valid) < 2:
        return image

    # Draw as polyline segments
    for i in range(len(pts_valid) - 1):
        p1 = tuple(pts_valid[i])
        p2 = tuple(pts_valid[i+1])
        # Skip if segment is too long (discontinuity)
        if abs(p1[0]-p2[0]) > img_w//2 or abs(p1[1]-p2[1]) > img_h//2:
            continue
        cv2.line(image, p1, p2, LINE_COLOR, LINE_THICKNESS, cv2.LINE_AA)

    return image


def draw_ego_marker(image, pts_px, in_front, closest_idx):
    """Draw a dot at the nearest racing line point to the ego vehicle."""
    if closest_idx < len(pts_px) and in_front[closest_idx]:
        pt = tuple(pts_px[closest_idx].astype(int))
        cv2.circle(image, pt, DOT_RADIUS, DOT_COLOR, -1, cv2.LINE_AA)
        cv2.circle(image, pt, DOT_RADIUS + 2, (255, 255, 255), 1, cv2.LINE_AA)
    return image


def add_hud(image, ego_pose, frame_idx, total_frames):
    """Overlay small HUD text."""
    lines = [
        f"Frame {frame_idx}/{total_frames}",
        f"Pos  x={ego_pose['x_m']:.1f}  y={ego_pose['y_m']:.1f}  z={ego_pose['z_m']:.1f} m",
        f"Yaw={np.degrees(ego_pose['yaw']):.1f}  Pitch={np.degrees(ego_pose['pitch']):.1f}  Roll={np.degrees(ego_pose['roll']):.1f} deg",
    ]
    for i, line in enumerate(lines):
        y = 28 + i * 22
        cv2.putText(image, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return image


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def load_racing_line(fast_mcap_path, state_topic):
    """Read all state estimation poses from the fast laps file."""
    print(f"[1/4] Reading racing line from: {fast_mcap_path}")
    poses = list(iter_state_msgs(fast_mcap_path, state_topic))
    print(f"      Found {len(poses)} state estimation messages")
    if not poses:
        raise RuntimeError(
            f"No messages found on topic '{state_topic}' in {fast_mcap_path}.\n"
            f"Check STATE_TOPIC at the top of the script."
        )
    arr = poses_to_array(poses)
    xyz = arr[:, :3]
    xyz_smooth = smooth_path(xyz)
    print(f"      Racing line: {xyz_smooth.shape[0]} points, "
          f"extent x=[{xyz_smooth[:,0].min():.1f}, {xyz_smooth[:,0].max():.1f}] "
          f"y=[{xyz_smooth[:,1].min():.1f}, {xyz_smooth[:,1].max():.1f}]")
    return xyz_smooth


def process_good_lap(
    good_mcap_path,
    racing_xyz,
    state_topic,
    image_topic,
    out_dir,
    look_ahead_m=LOOK_AHEAD_M,
    look_behind_m=LOOK_BEHIND_M,
):
    """
    For each image in the good lap:
      - find closest state estimation pose by timestamp
      - project racing line into image
      - save annotated frame
    """
    print(f"[2/4] Reading good lap: {good_mcap_path}")

    # Load all state poses first (fast, small data)
    poses = list(iter_state_msgs(good_mcap_path, state_topic))
    print(f"      Found {len(poses)} state estimation messages")
    if not poses:
        raise RuntimeError(
            f"No state messages on '{state_topic}' in {good_mcap_path}."
        )
    pose_times = np.array([p["timestamp"] for p in poses])

    # Iterate images
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    img_w, img_h = IMAGE_SIZE

    print(f"[3/4] Projecting racing line onto camera frames...")
    frame_idx = 0
    image_msgs = list(iter_image_msgs(good_mcap_path, image_topic))
    total = len(image_msgs)
    print(f"      Found {total} image messages")
    if total == 0:
        raise RuntimeError(
            f"No images found on topic '{image_topic}' in {good_mcap_path}.\n"
            f"Check IMAGE_TOPIC at the top of the script."
        )

    for img_ts, image in image_msgs:
        # Find closest state pose by timestamp
        idx = int(np.argmin(np.abs(pose_times - img_ts)))
        ego_pose = poses[idx]

        # Project full racing line into camera
        pts_px, in_front = world_to_camera(
            racing_xyz, ego_pose, R_EXT, T_EXT
        )

        # Find nearest point on racing line to ego
        ego_pos = np.array([ego_pose["x_m"], ego_pose["y_m"], ego_pose["z_m"]])
        c_idx = closest_index(racing_xyz, ego_pos)
        seg_idx = select_racing_segment_indices(
            racing_xyz, c_idx, look_ahead_m=look_ahead_m, look_behind_m=look_behind_m
        )
        pts_px_seg = pts_px[seg_idx]
        in_front_seg = in_front[seg_idx]
        marker_idx = 0 if look_behind_m <= 0 else int(np.where(seg_idx == c_idx)[0][0])

        # Draw
        out = image.copy()
        out = draw_racing_line(out, pts_px_seg, in_front_seg, img_w, img_h)
        out = draw_ego_marker(out, pts_px_seg, in_front_seg, marker_idx)
        out = add_hud(out, ego_pose, frame_idx + 1, total)

        # Save
        out_path = os.path.join(out_dir, f"frame_{frame_idx:05d}.jpg")
        cv2.imwrite(out_path, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
        frame_idx += 1

        if frame_idx % 50 == 0:
            print(f"      Processed {frame_idx}/{total} frames...")

    print(f"[4/4] Done. {frame_idx} frames saved to: {out_dir}/")
    return frame_idx


def make_video(out_dir, fps=10):
    """Optionally stitch frames into a video."""
    frames = sorted(Path(out_dir).glob("frame_*.jpg"))
    if not frames:
        return
    sample = cv2.imread(str(frames[0]))
    h, w = sample.shape[:2]
    vid_path = str(Path(out_dir) / "racing_line_overlay.mp4")
    writer = cv2.VideoWriter(vid_path,
                             cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (w, h))
    for f in frames:
        writer.write(cv2.imread(str(f)))
    writer.release()
    print(f"      Video saved: {vid_path}")


# ---------------------------------------------------------------------------
# Topic discovery helper
# ---------------------------------------------------------------------------

def list_topics(mcap_path):
    """Print all topics in an MCAP file so you can find the right names."""
    from mcap.reader import make_reader
    reader = make_reader(open(mcap_path, "rb"))
    summary = reader.get_summary()
    if summary:
        print(f"\nTopics in {mcap_path}:")
        for ch in summary.channels.values():
            schema = summary.schemas.get(ch.schema_id)
            schema_name = schema.name if schema else "unknown"
            print(f"  {ch.topic:<60} [{schema_name}]")
    else:
        print("No summary available — scanning messages...")
        seen = set()
        for schema, channel, message in reader.iter_messages():
            if channel.topic not in seen:
                print(f"  {channel.topic}")
                seen.add(channel.topic)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Racing line overlay on camera image")
    parser.add_argument("--fast",   default=str(script_dir / "hackathon_fast_laps.mcap"),
                        help="MCAP with fast laps (racing line source)")
    parser.add_argument("--good",   default=str(script_dir / "hackathon_good_lap.mcap"),
                        help="MCAP with good lap (camera + ego pose)")
    parser.add_argument("--out",    default=str(script_dir / "output_frames"),
                        help="Output directory for annotated frames")
    parser.add_argument("--fps",    type=float, default=10.0,
                        help="FPS for output video")
    parser.add_argument("--look-ahead", type=float, default=LOOK_AHEAD_M,
                        help="Meters of racing line to draw ahead of the ego vehicle")
    parser.add_argument("--look-behind", type=float, default=LOOK_BEHIND_M,
                        help="Meters of racing line to draw behind the ego vehicle")
    parser.add_argument("--video",  action="store_true",
                        help="Also produce an MP4 video from frames")
    parser.add_argument("--topics", action="store_true",
                        help="Just list topics in both files and exit")
    args = parser.parse_args()

    if args.topics:
        list_topics(args.fast)
        list_topics(args.good)
        exit(0)

    # Run pipeline
    racing_xyz = load_racing_line(args.fast, STATE_TOPIC)
    n = process_good_lap(
        args.good,
        racing_xyz,
        STATE_TOPIC,
        IMAGE_TOPIC,
        args.out,
        look_ahead_m=args.look_ahead,
        look_behind_m=args.look_behind,
    )

    if args.video and n > 0:
        print("Stitching video...")
        make_video(args.out, fps=args.fps)

    print("\nDone! Tips:")
    print("  - If the line is misaligned, the extrinsics need calibration.")
    print("  - Run with --topics first to verify topic names.")
    print("  - Edit STATE_TOPIC / IMAGE_TOPIC at the top of the script if needed.")
