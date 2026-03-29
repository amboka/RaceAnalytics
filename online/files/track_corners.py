"""
track_corners.py
================
Loads yas_marina_bnd.json and provides corner detection utilities.
Used by both the voice co-driver and dashboard.
"""

import json
import math
import numpy as np
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Corner:
    name: str
    start_pct: float   # track progress % where corner starts (0–100)
    end_pct: float     # track progress % where corner ends
    apex_speed: float  # expected apex speed km/h (reference)
    direction: str     # "left" or "right"


# ── Yas Marina corners (hardcoded from circuit knowledge + bnd.json) ──────────
# These are approximate lap-time-based intervals for the good lap (81s).
# Override with GPS-based detection when real data is available.
YAS_MARINA_CORNERS = [
    Corner("T1 — Long Right",    start_pct=4,  end_pct=11, apex_speed=145, direction="right"),
    Corner("T2 — Chicane Entry", start_pct=12, end_pct=17, apex_speed=95,  direction="left"),
    Corner("T3 — Chicane Exit",  start_pct=17, end_pct=21, apex_speed=105, direction="right"),
    Corner("T5 — Hotel Hairpin", start_pct=30, end_pct=40, apex_speed=55,  direction="right"),
    Corner("T8 — Marina Curve",  start_pct=52, end_pct=60, apex_speed=110, direction="left"),
    Corner("T11 — Final Sector", start_pct=72, end_pct=80, apex_speed=85,  direction="right"),
    Corner("T14 — Last Corner",  start_pct=87, end_pct=95, apex_speed=70,  direction="left"),
]


# ─────────────────────────────────────────────────────────────────────────────
# GPS-based corner detection from yas_marina_bnd.json
# ─────────────────────────────────────────────────────────────────────────────
def load_track_boundary(json_path: str) -> dict | None:
    """Load and parse the yas_marina_bnd.json track boundary file."""
    path = Path(json_path)
    if not path.exists():
        print(f"[track_corners] {json_path} not found — using time-based corners")
        return None

    with open(path) as f:
        data = json.load(f)

    print(f"[track_corners] Loaded track boundary: {json_path}")
    return data


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distance in metres between two GPS coordinates."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def compute_track_progress(df, track_data: dict | None) -> np.ndarray:
    """
    Return an array of track progress values (0–100%) for each telemetry row.
    Uses GPS distance if available, otherwise falls back to time-based %.
    """
    if track_data is None or df["lat"].max() == 0:
        # Time-based fallback
        t = df["time"].values
        return (t - t[0]) / (t[-1] - t[0]) * 100

    # Compute cumulative distance along GPS path
    lats = df["lat"].values
    lons = df["lon"].values
    dists = np.zeros(len(lats))
    for i in range(1, len(lats)):
        dists[i] = dists[i-1] + _haversine_m(lats[i-1], lons[i-1], lats[i], lons[i])

    total = dists[-1]
    if total == 0:
        t = df["time"].values
        return (t - t[0]) / (t[-1] - t[0]) * 100

    return (dists / total) * 100


def get_corner_at_progress(progress_pct: float) -> Corner | None:
    """Return the Corner object if the current track progress is in a corner."""
    for corner in YAS_MARINA_CORNERS:
        if corner.start_pct <= progress_pct <= corner.end_pct:
            return corner
    return None


def get_corner_at_time(t: float, lap_duration: float) -> Corner | None:
    """Time-based corner lookup (fallback when no GPS)."""
    pct = (t / lap_duration) * 100
    return get_corner_at_progress(pct)


def classify_track_zones(df, track_data: dict | None) -> list[str]:
    """
    Return a list of zone labels for each row: 'straight', 'braking', 'corner', 'exit'.
    """
    progress = compute_track_progress(df, track_data)
    zones = []
    for pct, speed, brake in zip(progress, df["speed"], df["brake"]):
        corner = get_corner_at_progress(pct)
        if corner is None:
            zones.append("straight")
        elif brake > 0.3:
            zones.append("braking")
        elif speed < (corner.apex_speed * 1.15):
            zones.append("corner")
        else:
            zones.append("exit")
    return zones
