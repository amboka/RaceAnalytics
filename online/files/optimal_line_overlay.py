"""
optimal_line_overlay.py
=======================
Extract the optimal lap line (x_m, y_m, z_m) from state estimation and draw it on
front-left camera compressed images.

Typical usage:
    # 1) Extract optimal line from the fast lap MCAP and save CSV
    python3 optimal_line_overlay.py \
        --optimal-mcap hackathon_fast_laps.mcap \
        --tf-mcap merged_for_map.mcap \
        --save-optimal-csv optimal_lap_xyz.csv \
        --max-frames 0

    # 2) Render overlay frames for a run MCAP (or same MCAP for demo)
    python3 optimal_line_overlay.py \
        --optimal-mcap hackathon_fast_laps.mcap \
        --tf-mcap merged_for_map.mcap \
        --run-mcap hackathon_fast_laps.mcap \
        --output-dir overlay_frames \
        --max-frames 50

    # 3) Overlay on a single JPEG with known pose (x_m, y_m, optional yaw)
    python3 optimal_line_overlay.py \
        --optimal-mcap hackathon_fast_laps.mcap \
        --single-image-jpeg frame.jpg \
        --x-m -196.8 --y-m -19.6 --z-m 0.98 --yaw-rad 0.13 \
        --single-output frame_overlay.jpg
"""

from __future__ import annotations

import argparse
import copy
import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
try:
    import cv2
    CV2_AVAILABLE = True
except Exception:
    cv2 = None
    CV2_AVAILABLE = False

try:
    from mcap_ros2.reader import read_ros2_messages
except ImportError as exc:
    raise SystemExit(
        "mcap_ros2 is required. Install with: pip install mcap mcap-ros2-support"
    ) from exc


DEFAULT_STATE_TOPIC = "/constructor0/state_estimation"
DEFAULT_CAMERA_TOPIC = "/constructor0/sensor/camera_fl/compressed_image"


@dataclass
class CameraModel:
    # Camera position in vehicle frame (x forward, y left, z up)
    x_m: float = 1.8
    y_m: float = 0.0
    z_m: float = 1.1
    # Rotation matrix R_base_from_camera from static TF.
    # If identity, camera frame orientation matches base_link orientation.
    rot_base_from_camera: np.ndarray = field(
        default_factory=lambda: np.eye(3, dtype=np.float64)
    )

    # Camera optical model (coarse approximation, tunable)
    pitch_down_deg: float = 0.0
    hfov_deg: float = 74.0
    cx_ratio: float = 0.5
    cy_ratio: float = 0.64
    min_depth_m: float = 0.5

    # Camera intrinsics (camera_fl). If set, these are used instead of HFOV.
    calib_width_px: float = 3874.0
    calib_height_px: float = 2176.0
    fx_px: float | None = 3211.04327
    fy_px: float | None = 3206.56235
    cx_px: float | None = 1954.80339
    cy_px: float | None = 1118.10606

    # Plumb-bob distortion coefficients
    k1: float = -0.38547
    k2: float = 0.19264
    p1: float = -0.00217
    p2: float = -0.00037
    k3: float = 0.0
    use_distortion: bool = True


@dataclass
class FrameCenterlineModel:
    width: int
    height: int
    y_min: float
    y_max: float
    c2_center: float
    c1_center: float
    c0_center: float
    c2_left: float
    c1_left: float
    c0_left: float
    c2_right: float
    c1_right: float
    c0_right: float
    x_left_bottom: float
    x_right_bottom: float
    confidence: float = 0.0


def _stamp_to_seconds(header) -> float:
    stamp = header.stamp
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def _normalize_frame_id(frame_id: str) -> str:
    return str(frame_id).strip().lstrip("/")


def _quat_to_rot_matrix(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    """Quaternion to 3x3 rotation matrix."""
    n = qx * qx + qy * qy + qz * qz + qw * qw
    if n <= 1e-12:
        return np.eye(3, dtype=np.float64)
    s = 2.0 / n

    xx = qx * qx * s
    yy = qy * qy * s
    zz = qz * qz * s
    xy = qx * qy * s
    xz = qx * qz * s
    yz = qy * qz * s
    wx = qw * qx * s
    wy = qw * qy * s
    wz = qw * qz * s

    return np.array(
        [
            [1.0 - (yy + zz), xy - wz, xz + wy],
            [xy + wz, 1.0 - (xx + zz), yz - wx],
            [xz - wy, yz + wx, 1.0 - (xx + yy)],
        ],
        dtype=np.float64,
    )


def infer_camera_frame_from_topic(
    mcap_path: str | Path,
    camera_topic: str = DEFAULT_CAMERA_TOPIC,
) -> str:
    """Read first camera message and return header.frame_id."""
    for message in read_ros2_messages(str(mcap_path), topics=[camera_topic]):
        ros_msg = message.ros_msg
        if hasattr(ros_msg, "header"):
            frame_id = str(getattr(ros_msg.header, "frame_id", "")).strip()
            if frame_id:
                return _normalize_frame_id(frame_id)
    raise RuntimeError(f"No camera messages found on topic '{camera_topic}' in {mcap_path}")


def load_base_to_camera_static_tf(
    tf_mcap_path: str | Path,
    base_frame: str,
    camera_frame: str,
    tf_topic: str = "/tf_static",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Load static TF transform base_link -> camera frame from MCAP.
    Returns:
        translation_b (3,) in base frame
        rot_base_from_camera (3,3) matrix
    """
    target_parent = _normalize_frame_id(base_frame)
    target_child = _normalize_frame_id(camera_frame)

    for message in read_ros2_messages(str(tf_mcap_path), topics=[tf_topic]):
        ros_msg = message.ros_msg
        for tf in getattr(ros_msg, "transforms", []):
            parent = _normalize_frame_id(tf.header.frame_id)
            child = _normalize_frame_id(tf.child_frame_id)
            if parent != target_parent or child != target_child:
                continue

            tr = tf.transform.translation
            q = tf.transform.rotation
            translation_b = np.array([tr.x, tr.y, tr.z], dtype=np.float64)
            rot_b_c = _quat_to_rot_matrix(q.x, q.y, q.z, q.w)
            return translation_b, rot_b_c

    raise RuntimeError(
        "Static TF not found in MCAP: "
        f"{target_parent} -> {target_child} on topic '{tf_topic}'"
    )


def extract_state_estimation_df(
    mcap_path: str | Path,
    state_topic: str = DEFAULT_STATE_TOPIC,
) -> pd.DataFrame:
    """Extract timestamped pose fields from a state estimation topic."""
    rows: list[dict] = []
    for message in read_ros2_messages(str(mcap_path), topics=[state_topic]):
        ros_msg = message.ros_msg
        if not hasattr(ros_msg, "header"):
            continue
        rows.append(
            {
                "time_s": _stamp_to_seconds(ros_msg.header),
                "x_m": float(getattr(ros_msg, "x_m", np.nan)),
                "y_m": float(getattr(ros_msg, "y_m", np.nan)),
                "z_m": float(getattr(ros_msg, "z_m", np.nan)),
                "roll_rad": float(getattr(ros_msg, "roll_rad", np.nan)),
                "pitch_rad": float(getattr(ros_msg, "pitch_rad", np.nan)),
                "yaw_rad": float(getattr(ros_msg, "yaw_rad", np.nan)),
                "v_mps": float(getattr(ros_msg, "v_mps", np.nan)),
            }
        )

    if not rows:
        raise RuntimeError(
            f"No state messages found on topic '{state_topic}' in {mcap_path}"
        )

    df = pd.DataFrame(rows).dropna(subset=["x_m", "y_m", "z_m"]).sort_values("time_s")
    df = df.drop_duplicates(subset=["time_s"]).reset_index(drop=True)

    # Smoothly recover occasional missing attitude values from neighboring samples.
    for col in ("roll_rad", "pitch_rad", "yaw_rad"):
        if col not in df.columns:
            df[col] = 0.0
            continue
        df[col] = df[col].astype(float).interpolate(limit_direction="both")
        df[col] = df[col].fillna(0.0)

    return df


def _smooth_xyz(xyz: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(xyz) < window:
        return xyz.copy()

    kernel = np.ones(window, dtype=np.float64) / float(window)
    pad = window // 2
    x = np.pad(xyz[:, 0], (pad, pad), mode="edge")
    y = np.pad(xyz[:, 1], (pad, pad), mode="edge")
    z = np.pad(xyz[:, 2], (pad, pad), mode="edge")
    return np.column_stack(
        [
            np.convolve(x, kernel, mode="valid"),
            np.convolve(y, kernel, mode="valid"),
            np.convolve(z, kernel, mode="valid"),
        ]
    )


def _resample_polyline_xyz(xyz: np.ndarray, step_m: float) -> np.ndarray:
    """Resample polyline at approximately uniform arc-length spacing."""
    if len(xyz) < 3 or step_m <= 0:
        return xyz
    seg = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
    keep = seg > 1e-6
    if not np.any(keep):
        return xyz
    seg = np.where(seg > 1e-6, seg, 1e-6)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    if total < step_m * 2:
        return xyz
    s_new = np.arange(0.0, total, step_m)
    x_new = np.interp(s_new, s, xyz[:, 0])
    y_new = np.interp(s_new, s, xyz[:, 1])
    z_new = np.interp(s_new, s, xyz[:, 2])
    return np.column_stack([x_new, y_new, z_new])


def build_optimal_line_xyz(
    state_df: pd.DataFrame,
    smooth_window: int = 9,
    min_step_m: float = 0.08,
    point_stride: int = 1,
    resample_step_m: float = 0.35,
) -> np.ndarray:
    """Build a clean optimal line as an Nx3 array from state estimation data."""
    xyz = state_df[["x_m", "y_m", "z_m"]].to_numpy(dtype=np.float64)
    xyz = _smooth_xyz(xyz, window=max(1, int(smooth_window)))

    if len(xyz) >= 2:
        delta = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
        keep = np.concatenate([[True], delta >= float(min_step_m)])
        xyz = xyz[keep]

    xyz = _resample_polyline_xyz(xyz, step_m=float(resample_step_m))
    stride = max(1, int(point_stride))
    return xyz[::stride]


def _estimate_yaw_from_line(optimal_line_xyz: np.ndarray, nearest_idx: int) -> float:
    n = len(optimal_line_xyz)
    if n < 2:
        return 0.0
    p0 = optimal_line_xyz[(nearest_idx - 1) % n]
    p1 = optimal_line_xyz[(nearest_idx + 1) % n]
    return float(np.arctan2(p1[1] - p0[1], p1[0] - p0[0]))


def _nearest_index(points_xy: np.ndarray, x_m: float, y_m: float) -> int:
    ref = np.array([x_m, y_m], dtype=np.float64)
    return int(np.argmin(np.sum((points_xy - ref) ** 2, axis=1)))


def _nearest_index_with_hint(
    points_xy: np.ndarray,
    x_m: float,
    y_m: float,
    hint_idx: int | None,
    search_window: int = 1200,
) -> int:
    if hint_idx is None or len(points_xy) == 0:
        return _nearest_index(points_xy, x_m, y_m)
    global_idx = _nearest_index(points_xy, x_m, y_m)
    ref = np.array([x_m, y_m], dtype=np.float64)
    global_dist = float(np.linalg.norm(points_xy[global_idx] - ref))
    n = len(points_xy)
    h = int(np.clip(hint_idx, 0, n - 1))
    radius = max(10, min(search_window, n // 2))
    lo = max(0, h - radius)
    hi = min(n, h + radius + 1)
    subset = points_xy[lo:hi]
    if len(subset) == 0:
        return global_idx
    local = int(np.argmin(np.sum((subset - ref) ** 2, axis=1)))
    hint_local_idx = lo + local
    hint_dist = float(np.linalg.norm(points_xy[hint_local_idx] - ref))
    # If hint diverges too much, recover with a global nearest search.
    if hint_dist > max(8.0, global_dist * 1.5):
        return global_idx
    return hint_local_idx


def _interp_pose_at_time(run_state_df: pd.DataFrame, t: float) -> dict:
    """Interpolate pose fields at camera timestamp t."""
    ts = run_state_df["time_s"].to_numpy(dtype=np.float64)
    if len(ts) == 0:
        return {
            "x_m": 0.0,
            "y_m": 0.0,
            "z_m": 0.0,
            "roll_rad": 0.0,
            "pitch_rad": 0.0,
            "yaw_rad": 0.0,
        }
    tt = float(np.clip(t, ts[0], ts[-1]))
    x = np.interp(tt, ts, run_state_df["x_m"].to_numpy(dtype=np.float64))
    y = np.interp(tt, ts, run_state_df["y_m"].to_numpy(dtype=np.float64))
    z = np.interp(tt, ts, run_state_df["z_m"].to_numpy(dtype=np.float64))
    roll = np.interp(tt, ts, run_state_df["roll_rad"].to_numpy(dtype=np.float64))
    pitch = np.interp(tt, ts, run_state_df["pitch_rad"].to_numpy(dtype=np.float64))
    yaw_series = np.unwrap(run_state_df["yaw_rad"].to_numpy(dtype=np.float64))
    yaw = np.interp(tt, ts, yaw_series)
    yaw = np.arctan2(np.sin(yaw), np.cos(yaw))
    return {
        "x_m": float(x),
        "y_m": float(y),
        "z_m": float(z),
        "roll_rad": float(roll),
        "pitch_rad": float(pitch),
        "yaw_rad": float(yaw),
    }


def _rot_world_from_base(roll_rad: float, pitch_rad: float, yaw_rad: float) -> np.ndarray:
    """Rotation matrix R_world_from_base using ZYX intrinsic yaw-pitch-roll."""
    cr = np.cos(roll_rad)
    sr = np.sin(roll_rad)
    cp = np.cos(pitch_rad)
    sp = np.sin(pitch_rad)
    cy = np.cos(yaw_rad)
    sy = np.sin(yaw_rad)

    rx = np.array(
        [[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]],
        dtype=np.float64,
    )
    ry = np.array(
        [[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]],
        dtype=np.float64,
    )
    rz = np.array(
        [[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    return rz @ ry @ rx


def _rot_x(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=np.float64)


def _rot_y(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float64)


def _rot_z(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def _points_ahead_in_car_frame(
    optimal_line_xyz: np.ndarray,
    car_x_m: float,
    car_y_m: float,
    car_z_m: float,
    car_roll_rad: float,
    car_pitch_rad: float,
    car_yaw_rad: float,
    lookahead_m: float,
    max_lateral_m: float,
    sample_stride: int,
    nearest_idx_hint: int | None = None,
) -> tuple[np.ndarray, int | None]:
    if len(optimal_line_xyz) < 2:
        return np.empty((0, 3), dtype=np.float64), None

    nearest_idx = _nearest_index_with_hint(
        optimal_line_xyz[:, :2],
        x_m=car_x_m,
        y_m=car_y_m,
        hint_idx=nearest_idx_hint,
    )
    n = len(optimal_line_xyz)
    step = max(1, int(sample_stride))
    idxs = []
    prev = nearest_idx
    travel = 0.0
    for k in range(0, min(n, 2200), step):
        idx = (nearest_idx + k) % n
        if k > 0:
            seg = float(np.linalg.norm(optimal_line_xyz[idx, :2] - optimal_line_xyz[prev, :2]))
            if seg > 12.0:
                break
            travel += seg
            if travel > lookahead_m:
                break
        idxs.append(idx)
        prev = idx
    if len(idxs) == 0:
        return np.empty((0, 3), dtype=np.float64), nearest_idx
    world_pts = optimal_line_xyz[idxs]

    car_world = np.array([car_x_m, car_y_m, car_z_m], dtype=np.float64)
    delta_world = world_pts - car_world
    r_world_base = _rot_world_from_base(
        roll_rad=car_roll_rad,
        pitch_rad=car_pitch_rad,
        yaw_rad=car_yaw_rad,
    )
    # Row vector transform: delta_base = delta_world @ R_world_from_base
    delta_base = delta_world @ r_world_base

    x_fwd = delta_base[:, 0]
    y_left = delta_base[:, 1]
    z_up = delta_base[:, 2]

    mask = (
        (x_fwd >= 1.0)
        & (x_fwd <= float(lookahead_m))
        & (np.abs(y_left) <= float(max_lateral_m))
        & (np.abs(z_up) <= 15.0)
    )
    if not np.any(mask):
        return np.empty((0, 3), dtype=np.float64), nearest_idx

    return delta_base[mask], nearest_idx


def _project_uv_from_camera_xyz(
    x_cam: np.ndarray,
    y_cam: np.ndarray,
    z_cam: np.ndarray,
    image_size: tuple[int, int],
    camera: CameraModel,
) -> tuple[np.ndarray, np.ndarray]:
    width, height = image_size
    if (
        camera.fx_px is not None
        and camera.fy_px is not None
        and camera.cx_px is not None
        and camera.cy_px is not None
        and camera.calib_width_px > 0
        and camera.calib_height_px > 0
    ):
        sx = width / float(camera.calib_width_px)
        sy = height / float(camera.calib_height_px)
        fx = float(camera.fx_px) * sx
        fy = float(camera.fy_px) * sy
        cx = float(camera.cx_px) * sx
        cy = float(camera.cy_px) * sy
    else:
        fx = width / (2.0 * np.tan(np.deg2rad(camera.hfov_deg) / 2.0))
        fy = fx
        cx = width * camera.cx_ratio
        cy = height * camera.cy_ratio

    x_n = x_cam / z_cam
    y_n = y_cam / z_cam

    if camera.use_distortion:
        r2 = x_n * x_n + y_n * y_n
        r4 = r2 * r2
        r6 = r4 * r2
        radial = 1.0 + camera.k1 * r2 + camera.k2 * r4 + camera.k3 * r6
        x_tan = 2.0 * camera.p1 * x_n * y_n + camera.p2 * (r2 + 2.0 * x_n * x_n)
        y_tan = camera.p1 * (r2 + 2.0 * y_n * y_n) + 2.0 * camera.p2 * x_n * y_n
        x_n = x_n * radial + x_tan
        y_n = y_n * radial + y_tan

    u = fx * x_n + cx
    v = fy * y_n + cy
    return u, v


def _scaled_camera_matrix_and_dist(
    image_size: tuple[int, int],
    camera: CameraModel,
) -> tuple[np.ndarray, np.ndarray]:
    width, height = image_size
    if (
        camera.fx_px is not None
        and camera.fy_px is not None
        and camera.cx_px is not None
        and camera.cy_px is not None
        and camera.calib_width_px > 0
        and camera.calib_height_px > 0
    ):
        sx = width / float(camera.calib_width_px)
        sy = height / float(camera.calib_height_px)
        fx = float(camera.fx_px) * sx
        fy = float(camera.fy_px) * sy
        cx = float(camera.cx_px) * sx
        cy = float(camera.cy_px) * sy
    else:
        fx = width / (2.0 * np.tan(np.deg2rad(camera.hfov_deg) / 2.0))
        fy = fx
        cx = width * camera.cx_ratio
        cy = height * camera.cy_ratio

    k = np.array(
        [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    d = np.array([camera.k1, camera.k2, camera.p1, camera.p2, camera.k3], dtype=np.float64)
    return k, d


def _project_base_points_to_pixels_cv2(
    car_frame_points: np.ndarray,
    image_size: tuple[int, int],
    camera: CameraModel,
) -> list[tuple[float, float]]:
    if not CV2_AVAILABLE or len(car_frame_points) == 0:
        return []

    # base_link -> camera body (from static TF)
    r_bc_body = camera.rot_base_from_camera
    r_cb_body = r_bc_body.T

    # camera body -> optical (x right, y down, z forward)
    r_opt_cam = np.array(
        [[0.0, -1.0, 0.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]],
        dtype=np.float64,
    )

    # Optical frame rotation from base frame
    r_ob = r_opt_cam @ r_cb_body
    if abs(float(camera.pitch_down_deg)) > 1e-9:
        r_ob = _rot_x(np.deg2rad(float(camera.pitch_down_deg))) @ r_ob

    t_bc = np.array([[camera.x_m], [camera.y_m], [camera.z_m]], dtype=np.float64)
    t_ob = -r_ob @ t_bc

    # Filter points behind camera using optical Z.
    p_opt = car_frame_points @ r_ob.T + t_ob.reshape(1, 3)
    valid = p_opt[:, 2] > float(camera.min_depth_m)
    if not np.any(valid):
        return []
    p_base = car_frame_points[valid].astype(np.float64).reshape(-1, 1, 3)

    k, d = _scaled_camera_matrix_and_dist(image_size, camera)
    dist = d if camera.use_distortion else np.zeros((5,), dtype=np.float64)
    rvec, _ = cv2.Rodrigues(r_ob.astype(np.float64))
    img_pts, _ = cv2.projectPoints(p_base, rvec, t_ob.astype(np.float64), k, dist)
    pts = img_pts.reshape(-1, 2)

    width, height = image_size
    out = []
    for uu, vv in pts:
        if -200.0 <= uu <= width + 200.0 and -200.0 <= vv <= height + 200.0:
            out.append((float(uu), float(vv)))
    return out


def _project_base_points_to_pixels(
    car_frame_points: np.ndarray,
    image_size: tuple[int, int],
    camera: CameraModel,
) -> list[tuple[float, float]]:
    if CV2_AVAILABLE:
        pts_cv2 = _project_base_points_to_pixels_cv2(car_frame_points, image_size, camera)
        if pts_cv2:
            return pts_cv2

    width, height = image_size
    if len(car_frame_points) == 0:
        return []

    # Car-frame points are already in base_link coordinates.
    p_base = car_frame_points
    cam_translation_b = np.array([camera.x_m, camera.y_m, camera.z_m], dtype=np.float64)

    # Transform base_link -> camera frame using static TF:
    # p_base = R_base_from_camera @ p_camera + t_base_camera
    # p_camera = R_camera_from_base @ (p_base - t_base_camera)
    r_base_camera = camera.rot_base_from_camera
    r_camera_base = r_base_camera.T
    p_camera = (p_base - cam_translation_b) @ r_camera_base.T

    # Convert camera-frame conventions to optical pinhole axis:
    # base-style frame: x forward, y left, z up
    # optical frame:    X right,   Y down, Z forward
    x0 = -p_camera[:, 1]
    y0 = -p_camera[:, 2]
    z0 = p_camera[:, 0]

    # Apply camera pitch around camera X axis.
    pitch = np.deg2rad(camera.pitch_down_deg)
    cp = np.cos(pitch)
    sp = np.sin(pitch)
    x_cam = x0
    y_cam = cp * y0 - sp * z0
    z_cam = sp * y0 + cp * z0

    valid = z_cam > camera.min_depth_m
    if not np.any(valid):
        return []

    x_cam = x_cam[valid]
    y_cam = y_cam[valid]
    z_cam = z_cam[valid]
    u, v = _project_uv_from_camera_xyz(x_cam, y_cam, z_cam, image_size, camera)

    pixels = []
    for uu, vv in zip(u, v):
        if -200.0 <= uu <= width + 200.0 and -200.0 <= vv <= height + 200.0:
            pixels.append((float(uu), float(vv)))
    return pixels


def _project_optimal_line_pixels(
    optimal_line_xyz: np.ndarray,
    image_size: tuple[int, int],
    camera: CameraModel,
    car_x_m: float,
    car_y_m: float,
    car_z_m: float | None = None,
    car_roll_rad: float | None = None,
    car_pitch_rad: float | None = None,
    car_yaw_rad: float | None = None,
    lookahead_m: float = 40.0,
    max_lateral_m: float = 40.0,
    sample_stride: int = 3,
    nearest_idx_hint: int | None = None,
) -> tuple[np.ndarray, int | None]:
    if len(optimal_line_xyz) < 2:
        return np.empty((0, 2), dtype=np.float64), None

    nearest_idx = _nearest_index_with_hint(
        optimal_line_xyz[:, :2],
        x_m=car_x_m,
        y_m=car_y_m,
        hint_idx=nearest_idx_hint,
    )
    if car_z_m is None or not np.isfinite(car_z_m):
        car_z_m = float(optimal_line_xyz[nearest_idx, 2])
    if car_roll_rad is None or not np.isfinite(car_roll_rad):
        car_roll_rad = 0.0
    if car_pitch_rad is None or not np.isfinite(car_pitch_rad):
        car_pitch_rad = 0.0
    if car_yaw_rad is None or not np.isfinite(car_yaw_rad):
        car_yaw_rad = _estimate_yaw_from_line(optimal_line_xyz, nearest_idx)

    points_car, nearest_idx = _points_ahead_in_car_frame(
        optimal_line_xyz=optimal_line_xyz,
        car_x_m=float(car_x_m),
        car_y_m=float(car_y_m),
        car_z_m=float(car_z_m),
        car_roll_rad=float(car_roll_rad),
        car_pitch_rad=float(car_pitch_rad),
        car_yaw_rad=float(car_yaw_rad),
        lookahead_m=lookahead_m,
        max_lateral_m=max_lateral_m,
        sample_stride=sample_stride,
        nearest_idx_hint=nearest_idx,
    )
    pixels = _project_base_points_to_pixels(points_car, image_size=image_size, camera=camera)
    if not pixels:
        return np.empty((0, 2), dtype=np.float64), nearest_idx
    return np.array(pixels, dtype=np.float64), nearest_idx


def _draw_projected_polyline(
    image: Image.Image,
    pixels: np.ndarray,
    line_width: int,
    line_color_rgb: tuple[int, int, int],
) -> None:
    if len(pixels) < 2:
        return
    draw = ImageDraw.Draw(image)
    pts = np.asarray(pixels, dtype=np.float64)
    # Draw only continuous polyline segments to avoid projection spikes.
    jump = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    breaks = np.where(jump > 140.0)[0]
    start = 0
    for b in breaks:
        seg = pts[start : b + 1]
        if len(seg) >= 2:
            draw.line([tuple(p) for p in seg], fill=line_color_rgb, width=max(1, int(line_width)))
        start = b + 1
    seg = pts[start:]
    if len(seg) >= 2:
        draw.line([tuple(p) for p in seg], fill=line_color_rgb, width=max(1, int(line_width)))


def _draw_track_debug_overlay(
    image: Image.Image,
    model: FrameCenterlineModel | None,
) -> None:
    if model is None:
        return
    y = np.linspace(model.y_min, model.y_max, 80, dtype=np.float64)
    xl, xr = _track_bounds_at_y(model, y)
    xc = model.c2_center * (y ** 2) + model.c1_center * y + model.c0_center
    draw = ImageDraw.Draw(image)
    left_pts = [(float(x), float(yy)) for x, yy in zip(xl, y)]
    right_pts = [(float(x), float(yy)) for x, yy in zip(xr, y)]
    center_pts = [(float(x), float(yy)) for x, yy in zip(xc, y)]
    if len(left_pts) >= 2:
        draw.line(left_pts, fill=(60, 170, 255), width=2)
    if len(right_pts) >= 2:
        draw.line(right_pts, fill=(60, 170, 255), width=2)
    if len(center_pts) >= 2:
        draw.line(center_pts, fill=(255, 200, 0), width=2)


def draw_optimal_line_on_compressed_image(
    image_bytes: bytes,
    optimal_line_xyz: np.ndarray,
    car_x_m: float,
    car_y_m: float,
    car_z_m: float | None = None,
    car_roll_rad: float | None = None,
    car_pitch_rad: float | None = None,
    car_yaw_rad: float | None = None,
    lookahead_m: float = 40.0,
    max_lateral_m: float = 40.0,
    sample_stride: int = 3,
    line_width: int = 6,
    line_color_rgb: tuple[int, int, int] = (0, 255, 0),
    camera: CameraModel | None = None,
) -> bytes:
    """
    Overlay optimal line on a compressed JPEG image and return JPEG bytes.

    If yaw is not provided, it is inferred from the tangent of the nearest point
    on the optimal line.
    """
    if camera is None:
        camera = CameraModel()

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pixels, _ = _project_optimal_line_pixels(
        optimal_line_xyz=optimal_line_xyz,
        image_size=image.size,
        camera=camera,
        car_x_m=car_x_m,
        car_y_m=car_y_m,
        car_z_m=car_z_m,
        car_roll_rad=car_roll_rad,
        car_pitch_rad=car_pitch_rad,
        car_yaw_rad=car_yaw_rad,
        lookahead_m=lookahead_m,
        max_lateral_m=max_lateral_m,
        sample_stride=sample_stride,
    )

    _draw_projected_polyline(
        image=image,
        pixels=pixels,
        line_width=line_width,
        line_color_rgb=line_color_rgb,
    )

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=92)
    return out.getvalue()


def _nearest_time_index(sorted_times: np.ndarray, target_t: float) -> int:
    pos = int(np.searchsorted(sorted_times, target_t, side="left"))
    if pos == 0:
        return 0
    if pos >= len(sorted_times):
        return len(sorted_times) - 1
    before = pos - 1
    after = pos
    return before if abs(sorted_times[before] - target_t) <= abs(sorted_times[after] - target_t) else after


def _polyfit_robust(
    y_vals: np.ndarray,
    x_vals: np.ndarray,
    deg: int = 2,
    max_iter: int = 4,
) -> np.ndarray | None:
    if len(y_vals) < max(12, deg + 4):
        return None
    y = y_vals.astype(np.float64)
    x = x_vals.astype(np.float64)
    mask = np.ones(len(y), dtype=bool)
    coeff = None
    for _ in range(max_iter):
        if np.count_nonzero(mask) < max(10, deg + 3):
            return None
        coeff = np.polyfit(y[mask], x[mask], deg)
        pred = np.polyval(coeff, y)
        residuals = np.abs(pred - x)
        med = np.median(residuals[mask])
        thr = max(10.0, med * 2.8)
        mask = residuals <= thr
    if coeff is None or np.count_nonzero(mask) < max(10, deg + 3):
        return None
    return np.polyfit(y[mask], x[mask], deg)


def _extract_centerline_model_legacy(image: Image.Image) -> FrameCenterlineModel | None:
    """Fallback linear centerline detector."""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    h, w = gray.shape
    if h < 100 or w < 100:
        return None

    grad_x = gray[:, 1:] - gray[:, :-1]
    y0 = int(h * 0.40)
    y1 = int(h * 0.94)
    ys = np.arange(y0, y1, max(3, h // 120), dtype=int)
    left_pts, right_pts, left_abs, right_abs = [], [], [], []
    l0, l1 = int(w * 0.08), int(w * 0.49)
    r0, r1 = int(w * 0.51), int(w * 0.92)
    if l1 <= l0 or r1 <= r0:
        return None

    for yy in ys:
        l_profile = np.abs(grad_x[yy, l0:l1])
        r_profile = np.abs(grad_x[yy, r0:r1])
        if l_profile.size == 0 or r_profile.size == 0:
            continue
        i_l, i_r = int(np.argmax(l_profile)), int(np.argmax(r_profile))
        g_l, g_r = float(l_profile[i_l]), float(r_profile[i_r])
        x_l, x_r = float(l0 + i_l), float(r0 + i_r)
        if x_r - x_l < w * 0.18:
            continue
        left_pts.append((yy, x_l))
        right_pts.append((yy, x_r))
        left_abs.append(g_l)
        right_abs.append(g_r)

    if len(left_pts) < 8 or len(right_pts) < 8:
        return None
    l_thr = np.percentile(np.array(left_abs, dtype=np.float64), 35)
    r_thr = np.percentile(np.array(right_abs, dtype=np.float64), 35)
    left_pts = [p for p, g in zip(left_pts, left_abs) if g >= l_thr]
    right_pts = [p for p, g in zip(right_pts, right_abs) if g >= r_thr]
    if len(left_pts) < 8 or len(right_pts) < 8:
        return None

    y_l = np.array([p[0] for p in left_pts], dtype=np.float64)
    x_l = np.array([p[1] for p in left_pts], dtype=np.float64)
    y_r = np.array([p[0] for p in right_pts], dtype=np.float64)
    x_r = np.array([p[1] for p in right_pts], dtype=np.float64)
    fit_l = _polyfit_robust(y_l, x_l, deg=1)
    fit_r = _polyfit_robust(y_r, x_r, deg=1)
    if fit_l is None or fit_r is None:
        return None
    y_eval = float(y1 - 1)
    x_left_bottom = float(np.polyval(fit_l, y_eval))
    x_right_bottom = float(np.polyval(fit_r, y_eval))
    lane_width = x_right_bottom - x_left_bottom
    if lane_width < w * 0.20 or lane_width > w * 0.90:
        return None
    center_coeff = 0.5 * (fit_l + fit_r)
    left_c1, left_c0 = float(fit_l[0]), float(fit_l[1])
    right_c1, right_c0 = float(fit_r[0]), float(fit_r[1])
    return FrameCenterlineModel(
        width=w,
        height=h,
        y_min=float(y0),
        y_max=float(y1),
        c2_center=0.0,
        c1_center=float(center_coeff[0]),
        c0_center=float(center_coeff[1]),
        c2_left=0.0,
        c1_left=left_c1,
        c0_left=left_c0,
        c2_right=0.0,
        c1_right=right_c1,
        c0_right=right_c0,
        x_left_bottom=x_left_bottom,
        x_right_bottom=x_right_bottom,
        confidence=0.45,
    )


def _extract_centerline_model(image: Image.Image) -> FrameCenterlineModel | None:
    """
    OpenCV-style lane extraction inspired by the common Advanced Lane Finding
    pipeline (thresholding + sliding windows + polynomial lane fit).
    """
    rgb_u8 = np.asarray(image.convert("RGB"), dtype=np.uint8)
    rgb = rgb_u8.astype(np.float32)
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    h, w = gray.shape
    if h < 120 or w < 120:
        return None

    y0 = int(h * 0.35)
    y1 = int(h * 0.97)
    if y1 - y0 < 30:
        return None

    # Binary mask from gradient + saturation in HLS (Udacity OpenCV-style).
    if CV2_AVAILABLE:
        # Night-friendly normalization.
        lab = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2LAB)
        l_eq = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
        l_eq = cv2.GaussianBlur(l_eq, (5, 5), 0)
        hls = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2HLS)
        l_ch = l_eq.astype(np.float32)
        s_ch = hls[:, :, 2].astype(np.float32)
        sobel_x = cv2.Sobel(l_ch, cv2.CV_32F, 1, 0, ksize=3)
        abs_sobel = np.abs(sobel_x)
        edges = cv2.Canny(l_eq, 40, 110).astype(np.float32)
        roi_abs = abs_sobel[y0:y1, :]
        roi_l = l_ch[y0:y1, :]
        roi_s = s_ch[y0:y1, :]
        g_thr = np.percentile(roi_abs, 88)
        l_thr = np.percentile(roi_l, 50)
        s_thr = np.percentile(roi_s, 62)
        binary = (
            ((abs_sobel > g_thr) & (l_ch > l_thr))
            | ((s_ch > s_thr) & (l_ch > l_thr * 0.9))
            | (edges > 0)
        )
        binary_u8 = (binary.astype(np.uint8) * 255)
        k_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        binary_u8 = cv2.morphologyEx(binary_u8, cv2.MORPH_OPEN, k_open, iterations=1)
        binary_u8 = cv2.morphologyEx(binary_u8, cv2.MORPH_CLOSE, k_close, iterations=1)
        binary = binary_u8 > 0
    else:
        grad_x = np.abs(np.gradient(gray, axis=1))
        sat = rgb.max(axis=2) - rgb.min(axis=2)
        roi_grad = grad_x[y0:y1, :]
        roi_gray = gray[y0:y1, :]
        roi_sat = sat[y0:y1, :]
        g_thr = np.percentile(roi_grad, 90)
        i_thr = np.percentile(roi_gray, 55)
        s_thr = np.percentile(roi_sat, 65)
        binary = ((grad_x > g_thr) & (gray > i_thr)) | (sat > s_thr)

    # Trapezoid ROI mask.
    yy = np.arange(h, dtype=np.float32)
    left_bound = np.interp(yy, [y0, y1], [w * 0.28, w * 0.02])
    right_bound = np.interp(yy, [y0, y1], [w * 0.72, w * 0.98])
    xx = np.arange(w, dtype=np.float32)[None, :]
    roi = (yy[:, None] >= y0) & (yy[:, None] <= y1) & (xx >= left_bound[:, None]) & (xx <= right_bound[:, None])
    binary = binary & roi

    # Sliding windows lane search (famous OpenCV lane detector pattern).
    hist = binary[int(h * 0.55):y1, :].sum(axis=0).astype(np.float64)
    mid = w // 2
    left_slice = hist[int(w * 0.05):mid]
    right_slice = hist[mid:int(w * 0.95)]
    if left_slice.size < 10 or right_slice.size < 10:
        return _extract_centerline_model_legacy(image)
    leftx_base = int(np.argmax(left_slice) + int(w * 0.05))
    rightx_base = int(np.argmax(right_slice) + mid)

    nonzero_y, nonzero_x = np.nonzero(binary)
    if len(nonzero_x) < 300:
        return _extract_centerline_model_legacy(image)

    nwindows = 9
    margin = int(w * 0.07)
    minpix = 25
    win_h = max(1, (y1 - y0) // nwindows)
    leftx_current = leftx_base
    rightx_current = rightx_base
    left_idx, right_idx = [], []

    for win in range(nwindows):
        y_low = y1 - (win + 1) * win_h
        y_high = y1 - win * win_h
        xleft_low = leftx_current - margin
        xleft_high = leftx_current + margin
        xright_low = rightx_current - margin
        xright_high = rightx_current + margin

        good_left = (
            (nonzero_y >= y_low) & (nonzero_y < y_high) &
            (nonzero_x >= xleft_low) & (nonzero_x < xleft_high)
        )
        good_right = (
            (nonzero_y >= y_low) & (nonzero_y < y_high) &
            (nonzero_x >= xright_low) & (nonzero_x < xright_high)
        )
        idx_l = np.where(good_left)[0]
        idx_r = np.where(good_right)[0]
        left_idx.append(idx_l)
        right_idx.append(idx_r)
        if len(idx_l) > minpix:
            leftx_current = int(np.mean(nonzero_x[idx_l]))
        if len(idx_r) > minpix:
            rightx_current = int(np.mean(nonzero_x[idx_r]))

    if not left_idx or not right_idx:
        return _extract_centerline_model_legacy(image)
    left_idx = np.concatenate(left_idx) if len(left_idx) else np.array([], dtype=int)
    right_idx = np.concatenate(right_idx) if len(right_idx) else np.array([], dtype=int)
    if len(left_idx) < 120 or len(right_idx) < 120:
        return _extract_centerline_model_legacy(image)

    left_fit = _polyfit_robust(nonzero_y[left_idx], nonzero_x[left_idx], deg=2)
    right_fit = _polyfit_robust(nonzero_y[right_idx], nonzero_x[right_idx], deg=2)
    if left_fit is None or right_fit is None:
        return _extract_centerline_model_legacy(image)

    yb = float(y1 - 1)
    yt = float(y0)
    left_bottom = float(np.polyval(left_fit, yb))
    right_bottom = float(np.polyval(right_fit, yb))
    left_top = float(np.polyval(left_fit, yt))
    right_top = float(np.polyval(right_fit, yt))
    w_bottom = right_bottom - left_bottom
    w_top = right_top - left_top
    if w_bottom < w * 0.16 or w_bottom > w * 0.95:
        return _extract_centerline_model_legacy(image)
    if w_top < w * 0.10 or w_top > w * 0.90:
        return _extract_centerline_model_legacy(image)

    center_fit = 0.5 * (left_fit + right_fit)
    conf = min(1.0, (len(left_idx) + len(right_idx)) / 3500.0)
    return FrameCenterlineModel(
        width=w,
        height=h,
        y_min=float(y0),
        y_max=float(y1),
        c2_center=float(center_fit[0]),
        c1_center=float(center_fit[1]),
        c0_center=float(center_fit[2]),
        c2_left=float(left_fit[0]),
        c1_left=float(left_fit[1]),
        c0_left=float(left_fit[2]),
        c2_right=float(right_fit[0]),
        c1_right=float(right_fit[1]),
        c0_right=float(right_fit[2]),
        x_left_bottom=float(left_bottom),
        x_right_bottom=float(right_bottom),
        confidence=float(conf),
    )


def _centerline_residual(px: np.ndarray, model: FrameCenterlineModel) -> float | None:
    if len(px) < 6:
        return None
    y = px[:, 1]
    x = px[:, 0]
    m = (y >= model.y_min) & (y <= model.y_max)
    if np.count_nonzero(m) < 6:
        return None
    yy = y[m]
    xx = x[m]
    xc = model.c2_center * (yy ** 2) + model.c1_center * yy + model.c0_center
    residuals = np.abs(xx - xc)
    return float(np.median(residuals) / max(0.25, model.confidence))


def _track_bounds_at_y(model: FrameCenterlineModel, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x_left = model.c2_left * (y ** 2) + model.c1_left * y + model.c0_left
    x_right = model.c2_right * (y ** 2) + model.c1_right * y + model.c0_right
    return x_left, x_right


def _clip_and_snap_pixels_to_track(
    pixels: np.ndarray,
    model: FrameCenterlineModel | None,
) -> np.ndarray:
    """
    Keep projected points inside the detected track corridor and clamp points
    that are slightly outside back onto the corridor.
    """
    if model is None or len(pixels) < 2:
        return pixels
    p = np.asarray(pixels, dtype=np.float64)
    y = p[:, 1]
    x = p[:, 0]
    roi = (y >= model.y_min) & (y <= model.y_max)
    if np.count_nonzero(roi) < 2:
        return p

    yy = y[roi]
    xx = x[roi]
    xl, xr = _track_bounds_at_y(model, yy)
    width = xr - xl
    good_width = width > 20.0
    if np.count_nonzero(good_width) < 2:
        return p

    yy = yy[good_width]
    xx = xx[good_width]
    xl = xl[good_width]
    xr = xr[good_width]
    width = width[good_width]

    # Keep line comfortably inside detected edges.
    margin = np.maximum(10.0, width * 0.08)
    low = xl + margin
    high = xr - margin
    high = np.maximum(high, low + 2.0)
    clamped_x = np.clip(xx, low, high)

    # Reject points that are far away from corridor (likely projection outliers).
    dev = np.abs(clamped_x - xx)
    keep = dev <= np.maximum(35.0, width * 0.45)
    if np.count_nonzero(keep) < 2:
        return np.empty((0, 2), dtype=np.float64)

    out = np.column_stack([clamped_x[keep], yy[keep]])
    return out


def _apply_camera_refine_params(
    camera: CameraModel,
    yaw_off_deg: float,
    pitch_off_deg: float,
    roll_off_deg: float,
    cx_shift_px: float,
    cy_shift_px: float,
) -> CameraModel:
    cam = copy.deepcopy(camera)
    # Offset rotation in camera frame.
    r_off = _rot_z(np.deg2rad(yaw_off_deg)) @ _rot_y(np.deg2rad(pitch_off_deg)) @ _rot_x(np.deg2rad(roll_off_deg))
    cam.rot_base_from_camera = cam.rot_base_from_camera @ r_off
    if cam.cx_px is not None:
        cam.cx_px = float(cam.cx_px + cx_shift_px)
    if cam.cy_px is not None:
        cam.cy_px = float(cam.cy_px + cy_shift_px)
    return cam


def refine_camera_from_frames(
    optimal_line_xyz: np.ndarray,
    calibration_frames: list[tuple[bytes, dict]],
    camera: CameraModel,
    lookahead_m: float,
) -> tuple[CameraModel, dict]:
    """
    Refine camera intrinsics/extrinsics offsets by maximizing line-to-track-center
    consistency on real camera images.
    """
    usable = []
    for img_bytes, pose in calibration_frames:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        model = _extract_centerline_model(img)
        if model is None:
            continue
        usable.append((img.size, model, pose))

    if len(usable) < 2:
        return camera, {"used_frames": len(usable), "refined": False}

    def score(cam: CameraModel) -> float:
        frame_scores = []
        for image_size, model, pose in usable:
            px, _ = _project_optimal_line_pixels(
                optimal_line_xyz=optimal_line_xyz,
                image_size=image_size,
                camera=cam,
                car_x_m=pose["x_m"],
                car_y_m=pose["y_m"],
                car_z_m=pose["z_m"],
                car_roll_rad=pose["roll_rad"],
                car_pitch_rad=pose["pitch_rad"],
                car_yaw_rad=pose["yaw_rad"],
                lookahead_m=lookahead_m,
                sample_stride=2,
            )
            res = _centerline_residual(px, model)
            if res is not None:
                frame_scores.append(res)
        if not frame_scores:
            return 1e9
        return float(np.mean(frame_scores))

    def objective(cam: CameraModel, p: np.ndarray) -> float:
        # Keep refinement conservative to avoid per-scene overfitting.
        reg = (
            0.7 * abs(float(p[0])) +
            0.9 * abs(float(p[1])) +
            0.6 * abs(float(p[2])) +
            0.008 * (abs(float(p[3])) + abs(float(p[4])))
        )
        return score(cam) + reg

    best = copy.deepcopy(camera)
    params = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)  # yaw, pitch, roll, cx, cy
    best_score = objective(best, params)

    step_sets = [
        np.array([2.0, 2.0, 1.5, 80.0, 80.0], dtype=np.float64),
        np.array([1.0, 1.0, 0.8, 40.0, 40.0], dtype=np.float64),
        np.array([0.5, 0.5, 0.4, 20.0, 20.0], dtype=np.float64),
    ]

    for steps in step_sets:
        improved = True
        while improved:
            improved = False
            for i in range(len(params)):
                for direction in (-1.0, 1.0):
                    cand_params = params.copy()
                    cand_params[i] += direction * steps[i]
                    cam_cand = _apply_camera_refine_params(
                        camera,
                        yaw_off_deg=float(cand_params[0]),
                        pitch_off_deg=float(cand_params[1]),
                        roll_off_deg=float(cand_params[2]),
                        cx_shift_px=float(cand_params[3]),
                        cy_shift_px=float(cand_params[4]),
                    )
                    cand_score = objective(cam_cand, cand_params)
                    if cand_score + 1e-6 < best_score:
                        best_score = cand_score
                        params = cand_params
                        best = cam_cand
                        improved = True

    residual = score(best)
    info = {
        "used_frames": len(usable),
        "refined": True,
        "score_px": round(residual, 2),
        "objective": round(best_score, 2),
        "yaw_off_deg": round(float(params[0]), 3),
        "pitch_off_deg": round(float(params[1]), 3),
        "roll_off_deg": round(float(params[2]), 3),
        "cx_shift_px": round(float(params[3]), 2),
        "cy_shift_px": round(float(params[4]), 2),
    }
    return best, info


def render_overlay_frames(
    run_mcap: str | Path,
    optimal_line_xyz: np.ndarray,
    state_topic: str,
    camera_topic: str,
    output_dir: str | Path,
    max_frames: int = 50,
    frame_stride: int = 1,
    lookahead_m: float = 40.0,
    line_width: int = 6,
    camera: CameraModel | None = None,
    auto_camera_refine: bool = False,
    refine_frames: int = 12,
    clip_to_track: bool = True,
    debug_track_model: bool = False,
) -> int:
    """
    Render overlaid camera frames from an MCAP.
    Returns number of written frames.
    """
    if camera is None:
        camera = CameraModel()

    run_state_df = extract_state_estimation_df(run_mcap, state_topic=state_topic)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    stride = max(1, int(frame_stride))
    max_n = int(max_frames)
    refine_n = max(0, int(refine_frames))

    refined_camera = camera
    calibration_samples: list[tuple[bytes, dict]] = []
    if auto_camera_refine and refine_n > 0:
        for idx, message in enumerate(read_ros2_messages(str(run_mcap), topics=[camera_topic])):
            if idx >= refine_n:
                break
            ros_msg = message.ros_msg
            t = _stamp_to_seconds(ros_msg.header)
            pose = _interp_pose_at_time(run_state_df, t)
            calibration_samples.append((bytes(ros_msg.data), pose))

        if calibration_samples:
            refined_camera, info = refine_camera_from_frames(
                optimal_line_xyz=optimal_line_xyz,
                calibration_frames=calibration_samples,
                camera=camera,
                lookahead_m=lookahead_m,
            )
            if info.get("refined"):
                print(
                    "[optimal_line] auto camera refine: "
                    f"frames={info['used_frames']} score={info['score_px']}px "
                    f"yaw={info['yaw_off_deg']}deg pitch={info['pitch_off_deg']}deg "
                    f"roll={info['roll_off_deg']}deg cx={info['cx_shift_px']}px "
                    f"cy={info['cy_shift_px']}px"
                )
            else:
                print(
                    "[optimal_line] auto camera refine skipped: "
                    f"usable_frames={info.get('used_frames', 0)}"
                )

    last_nearest_idx: int | None = None
    for idx, message in enumerate(read_ros2_messages(str(run_mcap), topics=[camera_topic])):
        if idx % stride != 0:
            continue

        if max_n > 0 and written >= max_n:
            break

        ros_msg = message.ros_msg
        t = _stamp_to_seconds(ros_msg.header)
        pose = _interp_pose_at_time(run_state_df, t)
        image = Image.open(io.BytesIO(bytes(ros_msg.data))).convert("RGB")
        pixels, last_nearest_idx = _project_optimal_line_pixels(
            optimal_line_xyz=optimal_line_xyz,
            image_size=image.size,
            camera=refined_camera,
            car_x_m=pose["x_m"],
            car_y_m=pose["y_m"],
            car_z_m=pose["z_m"],
            car_roll_rad=pose["roll_rad"],
            car_pitch_rad=pose["pitch_rad"],
            car_yaw_rad=pose["yaw_rad"],
            lookahead_m=lookahead_m,
            sample_stride=2,
            nearest_idx_hint=last_nearest_idx,
        )
        track_model = _extract_centerline_model(image) if (clip_to_track or debug_track_model) else None
        if clip_to_track:
            pixels = _clip_and_snap_pixels_to_track(pixels, track_model)
        _draw_projected_polyline(
            image=image,
            pixels=pixels,
            line_width=line_width,
            line_color_rgb=(0, 255, 0),
        )
        if debug_track_model:
            _draw_track_debug_overlay(image, track_model)

        output_path = out_dir / f"frame_{written:05d}.jpg"
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=92)
        output_path.write_bytes(out.getvalue())
        written += 1

    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract optimal state-estimation XYZ line from MCAP and overlay it on "
            "camera_fl compressed images."
        )
    )
    parser.add_argument("--optimal-mcap", required=True, help="MCAP used to build optimal line")
    parser.add_argument("--run-mcap", help="MCAP to render overlays on (default: --optimal-mcap)")
    parser.add_argument("--state-topic", default=DEFAULT_STATE_TOPIC)
    parser.add_argument("--camera-topic", default=DEFAULT_CAMERA_TOPIC)
    parser.add_argument("--tf-mcap", help="MCAP containing /tf_static (e.g. merged_for_map.mcap)")
    parser.add_argument("--tf-topic", default="/tf_static")
    parser.add_argument("--base-frame", default="constructor0/base_link")
    parser.add_argument("--camera-frame", help="Camera frame id (default: inferred from camera topic)")

    parser.add_argument("--smooth-window", type=int, default=9)
    parser.add_argument("--min-step-m", type=float, default=0.08)
    parser.add_argument("--resample-step-m", type=float, default=0.35)
    parser.add_argument("--line-point-stride", type=int, default=1)
    parser.add_argument("--save-optimal-csv", help="Optional CSV path for extracted state trajectory")

    parser.add_argument("--output-dir", default="overlay_frames")
    parser.add_argument("--max-frames", type=int, default=50, help="0 means skip rendering frames")
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--lookahead-m", type=float, default=40.0)
    parser.add_argument("--line-width", type=int, default=6)
    parser.add_argument(
        "--auto-camera-refine",
        action="store_true",
        dest="auto_camera_refine",
        help="Use image-based camera refinement before rendering overlays (default: on)",
    )
    parser.add_argument(
        "--no-auto-camera-refine",
        action="store_false",
        dest="auto_camera_refine",
        help="Disable image-based camera refinement",
    )
    parser.add_argument(
        "--refine-frames",
        type=int,
        default=12,
        help="Number of initial frames used for image-based camera refinement",
    )
    parser.add_argument(
        "--no-clip-to-track",
        action="store_false",
        dest="clip_to_track",
        help="Disable clipping/snapping the projected line to detected track corridor",
    )
    parser.add_argument(
        "--debug-track-model",
        action="store_true",
        help="Draw detected track boundaries/centerline overlay for debugging",
    )

    parser.add_argument("--camera-x-m", type=float, default=1.8)
    parser.add_argument("--camera-y-m", type=float, default=0.0)
    parser.add_argument("--camera-z-m", type=float, default=1.1)
    parser.add_argument("--pitch-down-deg", type=float, default=0.0)
    parser.add_argument("--hfov-deg", type=float, default=74.0)
    parser.add_argument("--cx-ratio", type=float, default=0.5)
    parser.add_argument("--cy-ratio", type=float, default=0.64)
    parser.add_argument("--calib-width", type=float, default=3874.0)
    parser.add_argument("--calib-height", type=float, default=2176.0)
    parser.add_argument("--fx-px", type=float, default=3211.04327)
    parser.add_argument("--fy-px", type=float, default=3206.56235)
    parser.add_argument("--cx-px", type=float, default=1954.80339)
    parser.add_argument("--cy-px", type=float, default=1118.10606)
    parser.add_argument("--k1", type=float, default=-0.38547)
    parser.add_argument("--k2", type=float, default=0.19264)
    parser.add_argument("--p1", type=float, default=-0.00217)
    parser.add_argument("--p2", type=float, default=-0.00037)
    parser.add_argument("--k3", type=float, default=0.0)
    parser.add_argument(
        "--no-distortion",
        action="store_true",
        help="Disable plumb_bob distortion when projecting pixels",
    )

    parser.add_argument("--single-image-jpeg", help="Render one external JPEG instead of MCAP frames")
    parser.add_argument("--x-m", type=float, help="Vehicle x_m for --single-image-jpeg")
    parser.add_argument("--y-m", type=float, help="Vehicle y_m for --single-image-jpeg")
    parser.add_argument("--z-m", type=float, help="Vehicle z_m for --single-image-jpeg")
    parser.add_argument("--roll-rad", type=float, help="Vehicle roll_rad for --single-image-jpeg")
    parser.add_argument("--pitch-rad", type=float, help="Vehicle pitch_rad for --single-image-jpeg")
    parser.add_argument("--yaw-rad", type=float, help="Vehicle yaw_rad for --single-image-jpeg")
    parser.add_argument("--single-output", default="overlay_single.jpg")

    parser.set_defaults(auto_camera_refine=True, clip_to_track=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"[optimal_line] cv2 projection pipeline: {'enabled' if CV2_AVAILABLE else 'disabled'}")

    run_mcap = args.run_mcap or args.optimal_mcap
    camera_frame = _normalize_frame_id(args.camera_frame) if args.camera_frame else infer_camera_frame_from_topic(
        run_mcap,
        camera_topic=args.camera_topic,
    )

    camera = CameraModel(
        x_m=args.camera_x_m,
        y_m=args.camera_y_m,
        z_m=args.camera_z_m,
        pitch_down_deg=args.pitch_down_deg,
        hfov_deg=args.hfov_deg,
        cx_ratio=args.cx_ratio,
        cy_ratio=args.cy_ratio,
        calib_width_px=args.calib_width,
        calib_height_px=args.calib_height,
        fx_px=args.fx_px,
        fy_px=args.fy_px,
        cx_px=args.cx_px,
        cy_px=args.cy_px,
        k1=args.k1,
        k2=args.k2,
        p1=args.p1,
        p2=args.p2,
        k3=args.k3,
        use_distortion=not args.no_distortion,
    )
    if args.tf_mcap:
        tf_translation, tf_rot_b_c = load_base_to_camera_static_tf(
            tf_mcap_path=args.tf_mcap,
            base_frame=args.base_frame,
            camera_frame=camera_frame,
            tf_topic=args.tf_topic,
        )
        camera.x_m = float(tf_translation[0])
        camera.y_m = float(tf_translation[1])
        camera.z_m = float(tf_translation[2])
        camera.rot_base_from_camera = tf_rot_b_c
        print(
            "[optimal_line] static TF loaded "
            f"{_normalize_frame_id(args.base_frame)} -> {camera_frame}: "
            f"t=({camera.x_m:.6f}, {camera.y_m:.6f}, {camera.z_m:.6f})"
        )
    else:
        print(
            "[optimal_line] static TF not provided; using manual camera offsets "
            f"({camera.x_m:.3f}, {camera.y_m:.3f}, {camera.z_m:.3f})"
        )

    optimal_state_df = extract_state_estimation_df(
        args.optimal_mcap,
        state_topic=args.state_topic,
    )
    optimal_line_xyz = build_optimal_line_xyz(
        optimal_state_df,
        smooth_window=args.smooth_window,
        min_step_m=args.min_step_m,
        resample_step_m=args.resample_step_m,
        point_stride=args.line_point_stride,
    )

    print(
        f"[optimal_line] extracted {len(optimal_state_df):,} state samples, "
        f"{len(optimal_line_xyz):,} line points"
    )

    if args.save_optimal_csv:
        csv_path = Path(args.save_optimal_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        optimal_state_df.to_csv(csv_path, index=False)
        print(f"[optimal_line] saved trajectory CSV -> {csv_path}")

    if args.single_image_jpeg:
        if args.x_m is None or args.y_m is None:
            raise SystemExit("--single-image-jpeg requires --x-m and --y-m")

        input_path = Path(args.single_image_jpeg)
        image_bytes = input_path.read_bytes()
        overlay = draw_optimal_line_on_compressed_image(
            image_bytes=image_bytes,
            optimal_line_xyz=optimal_line_xyz,
            car_x_m=float(args.x_m),
            car_y_m=float(args.y_m),
            car_z_m=args.z_m,
            car_roll_rad=args.roll_rad,
            car_pitch_rad=args.pitch_rad,
            car_yaw_rad=args.yaw_rad,
            lookahead_m=args.lookahead_m,
            line_width=args.line_width,
            camera=camera,
        )
        output_path = Path(args.single_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(overlay)
        print(f"[optimal_line] wrote single overlay -> {output_path}")
        return

    if args.max_frames == 0:
        print("[optimal_line] max-frames is 0, skipping frame rendering.")
        return

    written = render_overlay_frames(
        run_mcap=run_mcap,
        optimal_line_xyz=optimal_line_xyz,
        state_topic=args.state_topic,
        camera_topic=args.camera_topic,
        output_dir=args.output_dir,
        max_frames=args.max_frames,
        frame_stride=args.frame_stride,
        lookahead_m=args.lookahead_m,
        line_width=args.line_width,
        camera=camera,
        auto_camera_refine=args.auto_camera_refine,
        refine_frames=args.refine_frames,
        clip_to_track=args.clip_to_track,
        debug_track_model=args.debug_track_model,
    )
    print(f"[optimal_line] wrote {written} overlaid frame(s) -> {args.output_dir}")


if __name__ == "__main__":
    main()
