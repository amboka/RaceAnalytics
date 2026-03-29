from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateSample:
    ts_ns: int
    x_m: float
    y_m: float
    gas_pct: float
    v_mps: float


@dataclass(frozen=True)
class DetectedLap:
    lap_id: str
    race_id: str
    lap_number: int
    start_ns: int
    end_ns: int
    duration_ns: int
    sample_count: int
    path_length_m: float
    start_index: int
    end_index: int
    is_complete: bool = True
    quality: str = "good"
