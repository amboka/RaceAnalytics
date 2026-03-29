"""
mcap_reader.py
==============
Extracts telemetry from A2RL MCAP (ROS 2) files into a clean pandas DataFrame.

Usage:
    from mcap_reader import load_mcap, list_topics
    df = load_mcap("hackathon_good_lap.mcap")
"""

import sys
import struct
import pandas as pd
import numpy as np
from pathlib import Path

# ── Try importing MCAP libraries (graceful fallback for offline dev) ──────────
try:
    from mcap.reader import make_reader
    MCAP_AVAILABLE = True
except ImportError:
    MCAP_AVAILABLE = False
    print("[mcap_reader] WARNING: mcap library not installed. Using synthetic data.")

try:
    from mcap_ros2.reader import read_ros2_messages
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


# ── Topic map: canonical name → list of possible ROS 2 topic paths ───────────
# A2RL topics vary between firmware versions — we try all variants.
TOPIC_MAP = {
    "speed":    ["/vehicle/speed", "/car/speed", "/localization/speed",
                 "/vehicle_state/speed", "/sd/vehicle/speed"],
    "throttle": ["/vehicle/throttle", "/car/throttle", "/vehicle_state/throttle",
                 "/sd/vehicle/throttle", "/control/throttle"],
    "brake":    ["/vehicle/brake", "/car/brake", "/vehicle_state/brake",
                 "/sd/vehicle/brake", "/control/brake"],
    "steering": ["/vehicle/steering", "/car/steering", "/vehicle_state/steering",
                 "/sd/vehicle/steering", "/control/steering"],
    "rpm":      ["/vehicle/rpm", "/car/rpm", "/engine/rpm", "/vehicle_state/rpm"],
    "gear":     ["/vehicle/gear", "/car/gear", "/vehicle_state/gear"],
    "imu":      ["/imu/data", "/kistler/imu", "/vectornav/imu",
                 "/imu/data_raw", "/sd/imu"],
    "gps":      ["/gps/fix", "/vectornav/gps", "/gnss/fix",
                 "/gps/filtered", "/localization/gps"],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Topic Inspector
# ─────────────────────────────────────────────────────────────────────────────
def list_topics(mcap_path: str) -> dict:
    """
    Print and return all topics + message counts found in an MCAP file.
    Run this first to discover what topics your file actually contains.
    """
    if not MCAP_AVAILABLE:
        print("mcap library not available.")
        return {}

    path = Path(mcap_path)
    if not path.exists():
        print(f"File not found: {mcap_path}")
        return {}

    topics = {}
    with open(path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            topics[topic] = topics.get(topic, 0) + 1

    print(f"\n{'─'*60}")
    print(f"  Topics in: {path.name}")
    print(f"{'─'*60}")
    for topic, count in sorted(topics.items()):
        print(f"  {count:>8,}  {topic}")
    print(f"{'─'*60}\n")
    return topics


# ─────────────────────────────────────────────────────────────────────────────
# 2. Generic message value extractor
# ─────────────────────────────────────────────────────────────────────────────
def _extract_value(msg, field_hints: list[str]) -> float | None:
    """
    Try to pull a float value from a ROS message by checking common field names.
    Works with both deserialized objects and raw dicts.
    """
    if msg is None:
        return None

    obj = msg.ros_msg if hasattr(msg, "ros_msg") else msg

    # If it's a dict-like object
    if hasattr(obj, "__dict__"):
        obj = obj.__dict__

    if isinstance(obj, dict):
        for hint in field_hints:
            if hint in obj:
                val = obj[hint]
                return float(val) if val is not None else None
        # Fallback: return first numeric value found
        for v in obj.values():
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    else:
        for hint in field_hints:
            if hasattr(obj, hint):
                return float(getattr(obj, hint))

    return None


def _extract_imu(msg) -> tuple[float, float, float]:
    """Extract linear_acceleration x/y/z from IMU message."""
    obj = msg.ros_msg if hasattr(msg, "ros_msg") else msg
    try:
        la = obj.linear_acceleration
        return float(la.x), float(la.y), float(la.z)
    except AttributeError:
        pass
    try:
        d = obj.__dict__
        la = d.get("linear_acceleration", {})
        if hasattr(la, "__dict__"):
            la = la.__dict__
        return (float(la.get("x", 0)),
                float(la.get("y", 0)),
                float(la.get("z", 0)))
    except Exception:
        return 0.0, 0.0, 0.0


def _extract_gps(msg) -> tuple[float, float]:
    """Extract lat/lon from NavSatFix message."""
    obj = msg.ros_msg if hasattr(msg, "ros_msg") else msg
    try:
        return float(obj.latitude), float(obj.longitude)
    except AttributeError:
        pass
    try:
        d = obj.__dict__
        return float(d.get("latitude", 0)), float(d.get("longitude", 0))
    except Exception:
        return 0.0, 0.0


def _ros_stamp_to_sec(msg) -> float | None:
    """Convert ROS header stamp to seconds."""
    obj = msg.ros_msg if hasattr(msg, "ros_msg") else msg
    try:
        h = obj.header
        return float(h.stamp.sec) + float(h.stamp.nanosec) * 1e-9
    except AttributeError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Main MCAP Loader
# ─────────────────────────────────────────────────────────────────────────────
def load_mcap(mcap_path: str, max_rows: int = 50_000) -> pd.DataFrame:
    """
    Load an MCAP file and return a unified telemetry DataFrame.

    Columns: time, speed, throttle, brake, steering, rpm, gear,
             gx, gy, gz, lat, lon

    Falls back to synthetic data if the file can't be read.
    """
    path = Path(mcap_path)

    if not path.exists():
        print(f"[mcap_reader] File not found: {mcap_path} — generating synthetic data")
        return _generate_synthetic_data()

    if not MCAP_AVAILABLE:
        print("[mcap_reader] mcap not installed — generating synthetic data")
        return _generate_synthetic_data()

    print(f"[mcap_reader] Loading {path.name} ...")

    # Buffers keyed by timestamp (seconds)
    records: dict[float, dict] = {}

    # Map each known topic variant → our canonical key
    topic_to_key: dict[str, str] = {}
    for key, variants in TOPIC_MAP.items():
        for v in variants:
            topic_to_key[v] = key

    try:
        with open(path, "rb") as f:
            reader = make_reader(f)
            row_count = 0

            for schema, channel, message in reader.iter_messages():
                if row_count > max_rows:
                    break

                topic = channel.topic
                key = topic_to_key.get(topic)
                if key is None:
                    continue  # not a topic we care about

                # Convert MCAP log_time (nanoseconds) to seconds
                t = message.log_time * 1e-9

                if t not in records:
                    records[t] = {"time": t}

                # Parse by category
                if key in ("speed", "throttle", "brake", "steering", "rpm", "gear"):
                    # Try common scalar field names
                    hints = ["data", "value", key, "speed", "throttle",
                             "brake", "steering", "rpm", "gear"]
                    try:
                        if ROS2_AVAILABLE:
                            for schema2, ch2, msg2 in read_ros2_messages(
                                path, topics=[topic]
                            ):
                                pass  # handled below via iter_messages
                        val = _extract_value(message, hints)
                    except Exception:
                        val = None
                    if val is not None:
                        records[t][key] = val

                elif key == "imu":
                    gx, gy, gz = 0.0, 0.0, 0.0
                    try:
                        gx, gy, gz = _extract_imu(message)
                    except Exception:
                        pass
                    records[t].update({"gx": gx, "gy": gy, "gz": gz})

                elif key == "gps":
                    lat, lon = 0.0, 0.0
                    try:
                        lat, lon = _extract_gps(message)
                    except Exception:
                        pass
                    records[t].update({"lat": lat, "lon": lon})

                row_count += 1

    except Exception as e:
        print(f"[mcap_reader] Read error: {e} — falling back to synthetic data")
        return _generate_synthetic_data()

    if len(records) < 10:
        print("[mcap_reader] Too few records parsed — trying ROS2 reader fallback")
        fallback_df = _load_via_ros2_reader(path)
        if fallback_df is not None:
            return fallback_df
        return _generate_synthetic_data()

    df = _records_to_dataframe(records)
    print(f"[mcap_reader] Loaded {len(df):,} rows spanning {df['time'].max() - df['time'].min():.1f}s")
    return df


def _load_via_ros2_reader(path: Path) -> pd.DataFrame | None:
    """Alternative loader using mcap_ros2 high-level API."""
    if not ROS2_AVAILABLE:
        return None

    records = {}
    state_topic = "/constructor0/state_estimation"

    def _msg_time_s(m):
        ts = _ros_stamp_to_sec(m)
        if ts is not None:
            return float(ts)
        if hasattr(m, "log_time_ns") and m.log_time_ns is not None:
            return float(m.log_time_ns) * 1e-9
        return None

    def _normalize_brake(raw: float) -> float:
        if raw is None:
            return 0.0
        # Some datasets already store brake as 0..1, others in Pascals (~0..3.2e6).
        if raw <= 1.5:
            return float(np.clip(raw, 0.0, 1.0))
        return float(np.clip(raw / 3_200_000.0, 0.0, 1.0))

    try:
        for message in read_ros2_messages(str(path)):
            topic = message.channel.topic
            t = _msg_time_s(message)
            if t is None:
                continue

            msg = message.ros_msg

            # Preferred path for current A2RL files.
            if topic == state_topic:
                if t not in records:
                    records[t] = {"time": t}

                v_mps = float(getattr(msg, "v_mps", 0.0))
                throttle = float(getattr(msg, "gas", 0.0))
                brake_raw = float(getattr(msg, "brake", 0.0))
                steering = float(getattr(msg, "delta_wheel_rad", 0.0))

                records[t].update({
                    "speed": max(v_mps * 3.6, 0.0),  # m/s -> km/h
                    "throttle": float(np.clip(throttle, 0.0, 1.0)),
                    "brake": _normalize_brake(brake_raw),
                    "steering": steering,
                    "rpm": float(getattr(msg, "rpm", 0.0)),
                    "gear": float(getattr(msg, "gear", 0.0)),
                    "gx": float(getattr(msg, "ax_mps2", 0.0)),
                    "gy": float(getattr(msg, "ay_mps2", 0.0)),
                    "gz": float(getattr(msg, "az_mps2", 0.0)),
                })
                continue

            key = None
            for k, variants in TOPIC_MAP.items():
                if topic in variants:
                    key = k
                    break
            if key is None:
                continue

            if t not in records:
                records[t] = {"time": t}

            if key in ("speed", "throttle", "brake", "steering", "rpm", "gear"):
                for attr in ["data", "value", key]:
                    if hasattr(msg, attr):
                        value = float(getattr(msg, attr))
                        if key == "brake":
                            value = _normalize_brake(value)
                        records[t][key] = value
                        break
            elif key == "imu":
                records[t].update({
                    "gx": float(msg.linear_acceleration.x),
                    "gy": float(msg.linear_acceleration.y),
                    "gz": float(msg.linear_acceleration.z),
                })
            elif key == "gps":
                records[t].update({
                    "lat": float(msg.latitude),
                    "lon": float(msg.longitude),
                })
    except Exception as e:
        print(f"[mcap_reader] ROS2 reader fallback error: {e}")
        return None

    if len(records) < 10:
        return None

    return _records_to_dataframe(records)


def _records_to_dataframe(records: dict) -> pd.DataFrame:
    """Convert timestamp-keyed records dict → clean DataFrame."""
    cols = ["time", "speed", "throttle", "brake", "steering",
            "rpm", "gear", "gx", "gy", "gz", "lat", "lon"]

    df = pd.DataFrame(list(records.values()))

    # Ensure all columns exist with 0.0 defaults
    for col in cols:
        if col not in df.columns:
            df[col] = 0.0

    df = df[cols].sort_values("time").reset_index(drop=True)

    # Normalize time to start at 0
    df["time"] = df["time"] - df["time"].iloc[0]

    # Forward-fill sparse channels, then drop rows with no data at all
    df = df.ffill().fillna(0.0)

    # Resample to 10 Hz for consistent playback (MCAP data is often 250 Hz)
    df = _resample_to_hz(df, hz=10)

    return df


def _resample_to_hz(df: pd.DataFrame, hz: int = 10) -> pd.DataFrame:
    """Resample telemetry to a fixed frequency using linear interpolation."""
    t_start = df["time"].iloc[0]
    t_end   = df["time"].iloc[-1]
    t_new   = np.arange(t_start, t_end, 1.0 / hz)

    result = {"time": t_new}
    for col in df.columns:
        if col == "time":
            continue
        result[col] = np.interp(t_new, df["time"].values, df[col].values)

    return pd.DataFrame(result)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Synthetic Data Fallback (for offline dev / demo without MCAP files)
# ─────────────────────────────────────────────────────────────────────────────
def _generate_synthetic_data(duration: float = 81.0, hz: int = 10) -> pd.DataFrame:
    """
    Generate a realistic synthetic lap (Yas Marina-style) for demo purposes.
    Uses sinusoidal speed patterns with braking zones.
    """
    print("[mcap_reader] Generating synthetic Yas Marina lap data...")
    np.random.seed(42)
    t = np.arange(0, duration, 1.0 / hz)
    n = len(t)

    # Base speed profile: high on straights, low in corners
    speed_base = 120 + 80 * np.sin(2 * np.pi * t / 20)
    speed_base = np.clip(speed_base, 40, 220)
    speed = speed_base + np.random.normal(0, 3, n)

    # Throttle: high on straights, low in braking zones
    throttle = np.clip((speed - 80) / 140, 0, 1)
    throttle += np.random.normal(0, 0.05, n)
    throttle = np.clip(throttle, 0, 1)

    # Brake: inverse of throttle in decel zones
    brake = np.clip(-(np.gradient(speed) * 2), 0, 1)
    brake = np.clip(brake + np.random.normal(0, 0.02, n), 0, 1)

    # Steering: oscillates through corners
    steering = 0.3 * np.sin(2 * np.pi * t / 15) + np.random.normal(0, 0.02, n)

    # G-forces
    gx = np.gradient(speed) / 9.81
    gy = steering * speed / 100
    gz = np.ones(n) * -9.81 + np.random.normal(0, 0.1, n)

    # GPS: oval approximation of Yas Marina
    lat = 24.4672 + 0.002 * np.sin(2 * np.pi * t / duration)
    lon = 54.6031 + 0.003 * np.cos(2 * np.pi * t / duration)

    df = pd.DataFrame({
        "time":     t,
        "speed":    speed,
        "throttle": throttle,
        "brake":    brake,
        "steering": steering,
        "rpm":      speed * 60 + np.random.normal(0, 100, n),
        "gear":     np.clip((speed / 40).astype(int), 1, 8),
        "gx":       gx,
        "gy":       gy,
        "gz":       gz,
        "lat":      lat,
        "lon":      lon,
    })

    return df


# ─────────────────────────────────────────────────────────────────────────────
# CLI: python mcap_reader.py hackathon_good_lap.mcap
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1:
        mcap_file = sys.argv[1]
        print("\n── Topic Inspector ──────────────────────────────")
        list_topics(mcap_file)
        print("\n── Loading Telemetry ────────────────────────────")
        df = load_mcap(mcap_file)
    else:
        df = _generate_synthetic_data()

    print(df.describe())
    print(f"\nFirst rows:\n{df.head()}")
