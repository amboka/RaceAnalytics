from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from telemetry.models import TopicStateEstimation
from telemetry.systems.engine.types import DetectedLap

STEERING_CORNER_THRESHOLD_RAD = 0.04
MIN_ZONE_POINTS = 5
MAX_GAP_POINTS = 2
ACTIVE_THRESHOLD_RATIO = 0.08
MIN_ACTIVE_THRESHOLD = 0.02
MIN_PEAK_FACTOR = 1.25
ZONE_MATCH_TOLERANCE_PROGRESS = 0.08
DEFAULT_TRACE_POINTS = 121
SUPPORTED_PRESSURE_MODES = {"combined", "front", "rear"}


@dataclass(frozen=True)
class BrakeSample:
    ts_ns: int
    progress_ratio: float
    distance_m: float
    pressure: float
    steering_rad: float


@dataclass(frozen=True)
class ZoneComputation:
    start_idx: int
    end_idx: int
    peak_idx: int
    release_idx: int
    corner_start_idx: int | None


def _rounded(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _validate_pressure_mode(pressure_mode: str) -> str:
    mode = pressure_mode.lower().strip()
    if mode not in SUPPORTED_PRESSURE_MODES:
        supported = ", ".join(sorted(SUPPORTED_PRESSURE_MODES))
        raise ValueError(f"Invalid pressure_mode '{pressure_mode}'. Supported values: {supported}.")
    return mode


def _resolve_pressure(fl: float | None, fr: float | None, rl: float | None, rr: float | None, mode: str) -> float | None:
    """Resolve pressure from 4-channel CBA actual pressure data.
    
    Args:
        fl, fr, rl, rr: Pressure values in Pa from CBA actual pressure channels
        mode: 'front' (FL+FR)/2, 'rear' (RL+RR)/2, or 'combined' (all 4 wheels)/4
    """
    if mode == "front":
        front_vals = [v for v in [fl, fr] if v is not None]
        if not front_vals:
            return None
        return max(0.0, sum(front_vals) / len(front_vals))
    
    if mode == "rear":
        rear_vals = [v for v in [rl, rr] if v is not None]
        if not rear_vals:
            return None
        return max(0.0, sum(rear_vals) / len(rear_vals))
    
    # combined mode
    all_vals = [v for v in [fl, fr, rl, rr] if v is not None]
    if not all_vals:
        return None
    return max(0.0, sum(all_vals) / len(all_vals))


def _ema(values: list[float], alpha: float) -> list[float]:
    if not values:
        return []
    smoothed = [values[0]]
    for value in values[1:]:
        smoothed.append(alpha * value + (1.0 - alpha) * smoothed[-1])
    return smoothed


def _interpolate_series(xs: list[float], ys: list[float], targets: list[float]) -> list[float | None]:
    if len(xs) != len(ys) or not xs:
        return [None for _ in targets]

    result: list[float | None] = []
    index = 0
    last_index = len(xs) - 1

    for target in targets:
        if target < xs[0] or target > xs[-1]:
            result.append(None)
            continue

        while index + 1 < last_index and xs[index + 1] < target:
            index += 1

        left_x = xs[index]
        right_x = xs[min(index + 1, last_index)]
        left_y = ys[index]
        right_y = ys[min(index + 1, last_index)]

        if right_x <= left_x:
            result.append(left_y)
            continue

        fraction = (target - left_x) / (right_x - left_x)
        result.append(left_y + fraction * (right_y - left_y))

    return result


def _load_lap_samples(lap: DetectedLap, pressure_mode: str) -> list[BrakeSample]:
    rows = TopicStateEstimation.objects.filter(
        record__race_id=lap.race_id,
        record__ts_ns__gte=lap.start_ns,
        record__ts_ns__lte=lap.end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "x_m",
        "y_m",
        "cba_actual_pressure_fl_pa",
        "cba_actual_pressure_fr_pa",
        "cba_actual_pressure_rl_pa",
        "cba_actual_pressure_rr_pa",
        "delta_wheel_rad",
    )

    timestamps: list[int] = []
    x_values: list[float] = []
    y_values: list[float] = []
    pressures: list[float] = []
    steering: list[float] = []

    previous_ts: int | None = None
    for ts_ns, x_m, y_m, fl_pressure, fr_pressure, rl_pressure, rr_pressure, steering_rad in rows:
        if x_m is None or y_m is None:
            continue

        ts_int = int(ts_ns)
        if previous_ts is not None and ts_int <= previous_ts:
            continue

        pressure = _resolve_pressure(fl_pressure, fr_pressure, rl_pressure, rr_pressure, pressure_mode)
        if pressure is None:
            continue

        timestamps.append(ts_int)
        x_values.append(float(x_m))
        y_values.append(float(y_m))
        pressures.append(float(pressure))
        steering.append(0.0 if steering_rad is None else float(steering_rad))
        previous_ts = ts_int

    if len(timestamps) < 2:
        return []

    cumulative = [0.0]
    for idx in range(1, len(timestamps)):
        cumulative.append(
            cumulative[-1] + hypot(x_values[idx] - x_values[idx - 1], y_values[idx] - y_values[idx - 1])
        )

    path_length_m = cumulative[-1]
    if path_length_m <= 0.0:
        return []

    return [
        BrakeSample(
            ts_ns=timestamps[idx],
            progress_ratio=cumulative[idx] / path_length_m,
            distance_m=cumulative[idx],
            pressure=pressures[idx],
            steering_rad=steering[idx],
        )
        for idx in range(len(timestamps))
    ]


def _fill_small_gaps(active_mask: list[bool], max_gap_points: int) -> list[bool]:
    if not active_mask:
        return []

    filled = active_mask[:]
    index = 0
    while index < len(filled):
        if filled[index]:
            index += 1
            continue

        gap_start = index
        while index < len(filled) and not filled[index]:
            index += 1
        gap_end = index - 1

        left_active = gap_start > 0 and filled[gap_start - 1]
        right_active = index < len(filled) and filled[index]
        gap_size = gap_end - gap_start + 1

        if left_active and right_active and gap_size <= max_gap_points:
            for patch_idx in range(gap_start, gap_end + 1):
                filled[patch_idx] = True

    return filled


def _find_release_index(pressure: list[float], peak_idx: int, end_idx: int) -> int:
    if peak_idx >= end_idx:
        return peak_idx

    for index in range(peak_idx + 1, end_idx - 1):
        if pressure[index + 1] <= pressure[index] and pressure[index + 2] <= pressure[index + 1]:
            return index
    return peak_idx


def _detect_zone_windows(
    pressure: list[float],
    steering: list[float],
    active_threshold: float,
) -> list[ZoneComputation]:
    raw_active = [value >= active_threshold for value in pressure]
    active = _fill_small_gaps(raw_active, MAX_GAP_POINTS)

    zones: list[ZoneComputation] = []
    index = 0
    while index < len(active):
        if not active[index]:
            index += 1
            continue

        start_idx = index
        while index < len(active) and active[index]:
            index += 1
        end_idx = index - 1

        if end_idx - start_idx + 1 < MIN_ZONE_POINTS:
            continue

        peak_value = max(pressure[start_idx : end_idx + 1])
        if peak_value < active_threshold * MIN_PEAK_FACTOR:
            continue

        peak_idx_rel = pressure[start_idx : end_idx + 1].index(peak_value)
        peak_idx = start_idx + peak_idx_rel
        release_idx = _find_release_index(pressure, peak_idx, end_idx)

        corner_start_idx = None
        for scan_idx in range(start_idx, end_idx + 1):
            if abs(steering[scan_idx]) >= STEERING_CORNER_THRESHOLD_RAD:
                corner_start_idx = scan_idx
                break

        zones.append(
            ZoneComputation(
                start_idx=start_idx,
                end_idx=end_idx,
                peak_idx=peak_idx,
                release_idx=release_idx,
                corner_start_idx=corner_start_idx,
            )
        )

    return zones


def _build_zone_payload(
    *,
    zone_id: int,
    zone: ZoneComputation,
    samples: list[BrakeSample],
    pressure: list[float],
) -> dict:
    start_sample = samples[zone.start_idx]
    end_sample = samples[zone.end_idx]
    peak_sample = samples[zone.peak_idx]
    release_sample = samples[zone.release_idx]

    trail_start_idx = max(zone.release_idx, zone.peak_idx)
    trail_start_sample = samples[trail_start_idx]

    trail_length_m = max(0.0, end_sample.distance_m - trail_start_sample.distance_m)
    trail_duration_s = max(0.0, (end_sample.ts_ns - trail_start_sample.ts_ns) / 1_000_000_000.0)

    extends_into_corner = False
    trail_into_corner_length_m = 0.0
    trail_into_corner_duration_s = 0.0
    corner_start_progress = None
    if zone.corner_start_idx is not None:
        corner_sample = samples[zone.corner_start_idx]
        corner_start_progress = corner_sample.progress_ratio
        if zone.end_idx > zone.corner_start_idx:
            extends_into_corner = True
            trail_corner_start_idx = max(trail_start_idx, zone.corner_start_idx)
            trail_corner_start = samples[trail_corner_start_idx]
            trail_into_corner_length_m = max(0.0, end_sample.distance_m - trail_corner_start.distance_m)
            trail_into_corner_duration_s = max(
                0.0,
                (end_sample.ts_ns - trail_corner_start.ts_ns) / 1_000_000_000.0,
            )

    return {
        "zoneId": zone_id,
        "start": {
            "progress": _rounded(start_sample.progress_ratio, 4),
            "distanceM": _rounded(start_sample.distance_m, 2),
            "tsNs": start_sample.ts_ns,
        },
        "end": {
            "progress": _rounded(end_sample.progress_ratio, 4),
            "distanceM": _rounded(end_sample.distance_m, 2),
            "tsNs": end_sample.ts_ns,
        },
        "peak": {
            "progress": _rounded(peak_sample.progress_ratio, 4),
            "distanceM": _rounded(peak_sample.distance_m, 2),
            "tsNs": peak_sample.ts_ns,
            "brakePressure": _rounded(pressure[zone.peak_idx], 4),
        },
        "releasePoint": {
            "progress": _rounded(release_sample.progress_ratio, 4),
            "distanceM": _rounded(release_sample.distance_m, 2),
            "tsNs": release_sample.ts_ns,
            "brakePressure": _rounded(pressure[zone.release_idx], 4),
        },
        "corner": {
            "cornerStartProgress": _rounded(corner_start_progress, 4),
            "extendsIntoCorner": extends_into_corner,
        },
        "trailBraking": {
            "lengthM": _rounded(trail_length_m, 2),
            "durationS": _rounded(trail_duration_s, 3),
            "intoCornerLengthM": _rounded(trail_into_corner_length_m, 2),
            "intoCornerDurationS": _rounded(trail_into_corner_duration_s, 3),
        },
    }


def _match_reference_zones(lap_zones: list[dict], reference_zones: list[dict]) -> dict[int, dict]:
    if not lap_zones or not reference_zones:
        return {}

    remaining_ids = {zone["zoneId"] for zone in reference_zones}
    reference_by_id = {zone["zoneId"]: zone for zone in reference_zones}
    matched: dict[int, dict] = {}

    for lap_zone in lap_zones:
        lap_peak = float(lap_zone["peak"]["progress"])
        best_ref_id = None
        best_delta = None

        for ref_id in remaining_ids:
            ref_peak = float(reference_by_id[ref_id]["peak"]["progress"])
            delta = abs(lap_peak - ref_peak)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_ref_id = ref_id

        if best_ref_id is None:
            continue
        if best_delta is None or best_delta > ZONE_MATCH_TOLERANCE_PROGRESS:
            continue

        matched[lap_zone["zoneId"]] = reference_by_id[best_ref_id]
        remaining_ids.remove(best_ref_id)

    return matched


def _with_reference_deltas(lap_zone: dict, reference_zone: dict | None) -> dict:
    if reference_zone is None:
        lap_zone["reference"] = None
        lap_zone["delta"] = None
        return lap_zone

    lap_zone["reference"] = reference_zone
    lap_zone["delta"] = {
        "startProgress": _rounded(
            float(lap_zone["start"]["progress"]) - float(reference_zone["start"]["progress"]),
            4,
        ),
        "endProgress": _rounded(
            float(lap_zone["end"]["progress"]) - float(reference_zone["end"]["progress"]),
            4,
        ),
        "peakProgress": _rounded(
            float(lap_zone["peak"]["progress"]) - float(reference_zone["peak"]["progress"]),
            4,
        ),
        "trailLengthM": _rounded(
            float(lap_zone["trailBraking"]["lengthM"]) - float(reference_zone["trailBraking"]["lengthM"]),
            2,
        ),
        "trailDurationS": _rounded(
            float(lap_zone["trailBraking"]["durationS"]) - float(reference_zone["trailBraking"]["durationS"]),
            3,
        ),
        "intoCornerLengthM": _rounded(
            float(lap_zone["trailBraking"]["intoCornerLengthM"])
            - float(reference_zone["trailBraking"]["intoCornerLengthM"]),
            2,
        ),
        "intoCornerDurationS": _rounded(
            float(lap_zone["trailBraking"]["intoCornerDurationS"])
            - float(reference_zone["trailBraking"]["intoCornerDurationS"]),
            3,
        ),
    }
    return lap_zone


def _build_zone_trace(
    *,
    samples: list[BrakeSample],
    pressure: list[float],
    zone: dict,
    trace_points: int,
) -> dict:
    start_progress = float(zone["start"]["progress"])
    end_progress = float(zone["end"]["progress"])
    zone_span = max(1e-6, end_progress - start_progress)

    progress = [sample.progress_ratio for sample in samples]
    steering = [sample.steering_rad for sample in samples]

    target_zone_progress = [index / (trace_points - 1) for index in range(trace_points)]
    target_abs_progress = [start_progress + value * zone_span for value in target_zone_progress]

    pressure_trace = _interpolate_series(progress, pressure, target_abs_progress)
    steering_trace = _interpolate_series(progress, steering, target_abs_progress)

    return {
        "zoneProgress": [_rounded(value, 4) for value in target_zone_progress],
        "brakePressure": [_rounded(value, 4) if value is not None else None for value in pressure_trace],
        "steeringRad": [_rounded(value, 5) if value is not None else None for value in steering_trace],
    }


def _prepare_lap_zone_analysis(lap: DetectedLap, pressure_mode: str) -> tuple[list[BrakeSample], list[float], float, list[dict]]:
    samples = _load_lap_samples(lap, pressure_mode)
    if len(samples) < 2:
        raise ValueError("Selected lap does not contain enough brake telemetry samples.")

    raw_pressure = [sample.pressure for sample in samples]
    smoothed_pressure = _ema(raw_pressure, alpha=0.2)

    peak_pressure = max(smoothed_pressure)
    active_threshold = max(MIN_ACTIVE_THRESHOLD, peak_pressure * ACTIVE_THRESHOLD_RATIO)

    steering = [sample.steering_rad for sample in samples]
    zone_windows = _detect_zone_windows(smoothed_pressure, steering, active_threshold)
    if not zone_windows:
        raise ValueError("No braking zones were detected for selected lap with current signal quality.")

    zones = [
        _build_zone_payload(zone_id=index + 1, zone=zone, samples=samples, pressure=smoothed_pressure)
        for index, zone in enumerate(zone_windows)
    ]
    return samples, smoothed_pressure, active_threshold, zones


def compute_trail_braking_analysis(
    *,
    lap: DetectedLap,
    reference_lap: DetectedLap,
    pressure_mode: str = "combined",
    detailed_zone_id: int | None = None,
    trace_points: int = DEFAULT_TRACE_POINTS,
) -> dict:
    selected_mode = _validate_pressure_mode(pressure_mode)

    lap_samples, lap_pressure, lap_threshold, lap_zones = _prepare_lap_zone_analysis(lap, selected_mode)
    ref_samples, ref_pressure, ref_threshold, ref_zones = _prepare_lap_zone_analysis(reference_lap, selected_mode)

    matched_reference = _match_reference_zones(lap_zones, ref_zones)
    compared_zones = [
        _with_reference_deltas(zone, matched_reference.get(zone["zoneId"]))
        for zone in lap_zones
    ]

    detailed_trace = None
    if detailed_zone_id is not None:
        selected_zone = next((zone for zone in compared_zones if zone["zoneId"] == detailed_zone_id), None)
        if selected_zone is None:
            raise LookupError(f"Zone {detailed_zone_id} was not found for selected lap.")

        detailed_trace = {
            "zoneId": detailed_zone_id,
            "lap": _build_zone_trace(
                samples=lap_samples,
                pressure=lap_pressure,
                zone=selected_zone,
                trace_points=trace_points,
            ),
            "reference": None,
        }
        reference_zone = selected_zone.get("reference")
        if reference_zone is not None:
            detailed_trace["reference"] = _build_zone_trace(
                samples=ref_samples,
                pressure=ref_pressure,
                zone=reference_zone,
                trace_points=trace_points,
            )

    return {
        "lap": {
            "lapId": lap.lap_id,
            "raceId": lap.race_id,
            "lapNumber": lap.lap_number,
            "startNs": lap.start_ns,
            "endNs": lap.end_ns,
            "durationNs": lap.duration_ns,
        },
        "referenceLap": {
            "lapId": reference_lap.lap_id,
            "raceId": reference_lap.race_id,
            "lapNumber": reference_lap.lap_number,
            "startNs": reference_lap.start_ns,
            "endNs": reference_lap.end_ns,
            "durationNs": reference_lap.duration_ns,
        },
        "signal": {
            "pressureMode": selected_mode,
            "source": {
                "combined": "mean(front_brake_pressure, rear_brake_pressure)",
                "front": "front_brake_pressure",
                "rear": "rear_brake_pressure",
            }[selected_mode],
            "smoothing": {"method": "ema", "alpha": 0.2},
            "corneringSignal": "delta_wheel_rad",
        },
        "method": {
            "zoneDefinition": "pressure above adaptive threshold with short-gap fill",
            "releaseDefinition": "first sustained pressure decrease after peak",
            "trailDefinition": "segment from max(peak, releasePoint) to zone end",
            "cornerExtensionDefinition": "zone ends after steering exceeds corner threshold",
            "zoneMatch": "nearest peak progress within tolerance",
            "cornerSteeringThresholdRad": STEERING_CORNER_THRESHOLD_RAD,
        },
        "thresholds": {
            "lapActiveThreshold": _rounded(lap_threshold, 4),
            "referenceActiveThreshold": _rounded(ref_threshold, 4),
        },
        "zoneCount": len(compared_zones),
        "zones": compared_zones,
        "detailedTrace": detailed_trace,
    }
