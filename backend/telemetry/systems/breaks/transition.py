from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from telemetry.models import TopicStateEstimation
from telemetry.systems.engine.types import DetectedLap

SUPPORTED_PRESSURE_MODES = {"combined", "front", "rear"}

SMOOTHING_ALPHA = 0.2
ACTIVE_THRESHOLD_RATIO = 0.08
MIN_ACTIVE_THRESHOLD = 0.02
MIN_ZONE_POINTS = 5
MAX_GAP_POINTS = 2
ZONE_MATCH_TOLERANCE_PROGRESS = 0.08
MIN_THROTTLE_ON_PCT = 10.0
MIN_THROTTLE_STABLE_POINTS = 2
APEX_LOOKAHEAD_POINTS = 70
DEFAULT_TRACE_POINTS = 141


@dataclass(frozen=True)
class TransitionSample:
    ts_ns: int
    progress_ratio: float
    distance_m: float
    brake_pressure: float
    throttle_pct: float
    speed_mps: float
    steering_rad: float


@dataclass(frozen=True)
class ZoneWindow:
    start_idx: int
    end_idx: int
    peak_idx: int


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


def _clamp_throttle_pct(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(100.0, float(value) * 100.0))


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

    results: list[float | None] = []
    source_index = 0
    last_index = len(xs) - 1

    for target in targets:
        if target < xs[0] or target > xs[-1]:
            results.append(None)
            continue

        while source_index + 1 < last_index and xs[source_index + 1] < target:
            source_index += 1

        left_x = xs[source_index]
        right_x = xs[min(source_index + 1, last_index)]
        left_y = ys[source_index]
        right_y = ys[min(source_index + 1, last_index)]

        if right_x <= left_x:
            results.append(left_y)
            continue

        fraction = (target - left_x) / (right_x - left_x)
        results.append(left_y + fraction * (right_y - left_y))

    return results


def _load_transition_samples(lap: DetectedLap, pressure_mode: str) -> list[TransitionSample]:
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
        "gas",
        "v_mps",
        "delta_wheel_rad",
    )

    ts_values: list[int] = []
    x_values: list[float] = []
    y_values: list[float] = []
    pressures: list[float] = []
    throttles: list[float] = []
    speeds: list[float] = []
    steerings: list[float] = []

    previous_ts: int | None = None
    for ts_ns, x_m, y_m, fl_pressure, fr_pressure, rl_pressure, rr_pressure, gas, speed_mps, steering_rad in rows:
        if x_m is None or y_m is None:
            continue

        ts_int = int(ts_ns)
        if previous_ts is not None and ts_int <= previous_ts:
            continue

        pressure = _resolve_pressure(fl_pressure, fr_pressure, rl_pressure, rr_pressure, pressure_mode)
        if pressure is None:
            continue

        ts_values.append(ts_int)
        x_values.append(float(x_m))
        y_values.append(float(y_m))
        pressures.append(float(pressure))
        throttles.append(_clamp_throttle_pct(gas))
        speeds.append(0.0 if speed_mps is None else max(0.0, float(speed_mps)))
        steerings.append(0.0 if steering_rad is None else float(steering_rad))
        previous_ts = ts_int

    if len(ts_values) < 2:
        return []

    cumulative = [0.0]
    for idx in range(1, len(ts_values)):
        cumulative.append(
            cumulative[-1] + hypot(x_values[idx] - x_values[idx - 1], y_values[idx] - y_values[idx - 1])
        )

    path_length_m = cumulative[-1]
    if path_length_m <= 0.0:
        return []

    return [
        TransitionSample(
            ts_ns=ts_values[idx],
            progress_ratio=cumulative[idx] / path_length_m,
            distance_m=cumulative[idx],
            brake_pressure=pressures[idx],
            throttle_pct=throttles[idx],
            speed_mps=speeds[idx],
            steering_rad=steerings[idx],
        )
        for idx in range(len(ts_values))
    ]


def _fill_small_gaps(active: list[bool], max_gap_points: int) -> list[bool]:
    if not active:
        return []

    filled = active[:]
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


def _detect_zone_windows(pressure: list[float], active_threshold: float) -> list[ZoneWindow]:
    active = _fill_small_gaps([value >= active_threshold for value in pressure], MAX_GAP_POINTS)

    zones: list[ZoneWindow] = []
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
        if peak_value < active_threshold * 1.25:
            continue

        peak_idx = start_idx + pressure[start_idx : end_idx + 1].index(peak_value)
        zones.append(ZoneWindow(start_idx=start_idx, end_idx=end_idx, peak_idx=peak_idx))

    return zones


def _find_release_point(pressure: list[float], zone: ZoneWindow, active_threshold: float) -> int:
    release_threshold = max(active_threshold * 1.1, pressure[zone.peak_idx] * 0.18)
    for idx in range(zone.peak_idx, zone.end_idx + 1):
        if pressure[idx] <= release_threshold:
            return idx
    return zone.end_idx


def _find_apex_point(speed: list[float], zone: ZoneWindow) -> int:
    search_end = min(len(speed) - 1, zone.end_idx + APEX_LOOKAHEAD_POINTS)
    search_start = zone.peak_idx
    segment = speed[search_start : search_end + 1]
    if not segment:
        return zone.peak_idx
    return search_start + segment.index(min(segment))


def _find_throttle_application(throttle: list[float], start_idx: int) -> int | None:
    for idx in range(start_idx, len(throttle) - MIN_THROTTLE_STABLE_POINTS):
        if all(throttle[idx + off] >= MIN_THROTTLE_ON_PCT for off in range(MIN_THROTTLE_STABLE_POINTS + 1)):
            return idx
    return None


def _smoothness_score(brake: list[float], throttle: list[float], start_idx: int, end_idx: int) -> float:
    if end_idx <= start_idx + 3:
        return 50.0

    brake_window = brake[start_idx : end_idx + 1]
    throttle_window = throttle[start_idx : end_idx + 1]
    brake_d = [right - left for left, right in zip(brake_window, brake_window[1:])]
    throttle_d = [right - left for left, right in zip(throttle_window, throttle_window[1:])]

    brake_good = sum(1 for delta in brake_d if delta <= 0.0) / max(1, len(brake_d))
    throttle_good = sum(1 for delta in throttle_d if delta >= 0.0) / max(1, len(throttle_d))

    sign_changes = 0
    prev_sign = 0
    for delta in throttle_d:
        if abs(delta) < 0.5:
            continue
        sign = 1 if delta > 0 else -1
        if prev_sign != 0 and sign != prev_sign:
            sign_changes += 1
        prev_sign = sign

    jitter_penalty = min(1.0, sign_changes / 6.0)
    score = (0.45 * brake_good + 0.45 * throttle_good + 0.10 * (1.0 - jitter_penalty)) * 100.0
    return max(0.0, min(100.0, score))


def _transition_label(gap_s: float, smoothness: float) -> str:
    if gap_s < -0.05:
        return "overlap"
    if gap_s > 0.40:
        return "delayed"
    if smoothness < 45.0:
        return "abrupt"
    if gap_s > 0.20 or smoothness < 65.0:
        return "hesitant"
    return "smooth"


def _build_zone_metrics(
    *,
    zone_id: int,
    zone: ZoneWindow,
    samples: list[TransitionSample],
    smoothed_brake: list[float],
    active_threshold: float,
) -> dict:
    throttle = [sample.throttle_pct for sample in samples]
    speed = [sample.speed_mps for sample in samples]

    release_idx = _find_release_point(smoothed_brake, zone, active_threshold)
    apex_idx = _find_apex_point(speed, zone)
    throttle_start_idx = _find_throttle_application(throttle, start_idx=max(zone.peak_idx, apex_idx - 8))

    release_sample = samples[release_idx]
    apex_sample = samples[apex_idx]
    start_sample = samples[zone.start_idx]
    end_sample = samples[zone.end_idx]
    peak_sample = samples[zone.peak_idx]

    gap_s = None
    gap_m = None
    throttle_delay_vs_apex_s = None
    throttle_delay_vs_apex_m = None
    overlap_s = 0.0
    overlap_m = 0.0

    if throttle_start_idx is not None:
        throttle_sample = samples[throttle_start_idx]
        gap_s = (throttle_sample.ts_ns - release_sample.ts_ns) / 1_000_000_000.0
        gap_m = throttle_sample.distance_m - release_sample.distance_m
        throttle_delay_vs_apex_s = (throttle_sample.ts_ns - apex_sample.ts_ns) / 1_000_000_000.0
        throttle_delay_vs_apex_m = throttle_sample.distance_m - apex_sample.distance_m

        if gap_s < 0.0:
            overlap_s = abs(gap_s)
            overlap_m = abs(gap_m)

    smoothness_end = throttle_start_idx if throttle_start_idx is not None else min(len(samples) - 1, zone.end_idx + 20)
    smoothness = _smoothness_score(smoothed_brake, throttle, zone.peak_idx, smoothness_end)
    label = _transition_label(0.0 if gap_s is None else gap_s, smoothness)

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
        "peakBrake": {
            "progress": _rounded(peak_sample.progress_ratio, 4),
            "distanceM": _rounded(peak_sample.distance_m, 2),
            "tsNs": peak_sample.ts_ns,
            "brakePressure": _rounded(smoothed_brake[zone.peak_idx], 4),
        },
        "brakeRelease": {
            "progress": _rounded(release_sample.progress_ratio, 4),
            "distanceM": _rounded(release_sample.distance_m, 2),
            "tsNs": release_sample.ts_ns,
            "brakePressure": _rounded(smoothed_brake[release_idx], 4),
        },
        "apex": {
            "progress": _rounded(apex_sample.progress_ratio, 4),
            "distanceM": _rounded(apex_sample.distance_m, 2),
            "tsNs": apex_sample.ts_ns,
            "speedMps": _rounded(apex_sample.speed_mps, 3),
        },
        "throttleApplication": None
        if throttle_start_idx is None
        else {
            "progress": _rounded(samples[throttle_start_idx].progress_ratio, 4),
            "distanceM": _rounded(samples[throttle_start_idx].distance_m, 2),
            "tsNs": samples[throttle_start_idx].ts_ns,
            "throttlePct": _rounded(samples[throttle_start_idx].throttle_pct, 3),
        },
        "transition": {
            "brakeToThrottleGapS": _rounded(gap_s, 3),
            "brakeToThrottleGapM": _rounded(gap_m, 2),
            "overlapS": _rounded(overlap_s, 3),
            "overlapM": _rounded(overlap_m, 2),
            "throttleDelayVsApexS": _rounded(throttle_delay_vs_apex_s, 3),
            "throttleDelayVsApexM": _rounded(throttle_delay_vs_apex_m, 2),
            "smoothnessScore": _rounded(smoothness, 2),
            "classification": label,
        },
    }


def _match_reference_zones(lap_zones: list[dict], reference_zones: list[dict]) -> dict[int, dict]:
    if not lap_zones or not reference_zones:
        return {}

    remaining_ref_ids = {zone["zoneId"] for zone in reference_zones}
    ref_by_id = {zone["zoneId"]: zone for zone in reference_zones}
    matched: dict[int, dict] = {}

    for lap_zone in lap_zones:
        lap_peak = float(lap_zone["peakBrake"]["progress"])
        best_ref_id = None
        best_delta = None

        for ref_id in remaining_ref_ids:
            ref_peak = float(ref_by_id[ref_id]["peakBrake"]["progress"])
            delta = abs(lap_peak - ref_peak)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_ref_id = ref_id

        if best_ref_id is None or best_delta is None or best_delta > ZONE_MATCH_TOLERANCE_PROGRESS:
            continue

        matched[lap_zone["zoneId"]] = ref_by_id[best_ref_id]
        remaining_ref_ids.remove(best_ref_id)

    return matched


def _attach_reference(zone: dict, reference_zone: dict | None) -> dict:
    if reference_zone is None:
        zone["reference"] = None
        zone["delta"] = None
        return zone

    zone["reference"] = reference_zone
    zone["delta"] = {
        "brakeReleaseProgress": _rounded(
            float(zone["brakeRelease"]["progress"]) - float(reference_zone["brakeRelease"]["progress"]),
            4,
        ),
        "apexProgress": _rounded(
            float(zone["apex"]["progress"]) - float(reference_zone["apex"]["progress"]),
            4,
        ),
        "throttleApplicationProgress": None
        if zone["throttleApplication"] is None or reference_zone["throttleApplication"] is None
        else _rounded(
            float(zone["throttleApplication"]["progress"])
            - float(reference_zone["throttleApplication"]["progress"]),
            4,
        ),
        "gapS": None
        if zone["transition"]["brakeToThrottleGapS"] is None
        or reference_zone["transition"]["brakeToThrottleGapS"] is None
        else _rounded(
            float(zone["transition"]["brakeToThrottleGapS"])
            - float(reference_zone["transition"]["brakeToThrottleGapS"]),
            3,
        ),
        "throttleDelayVsApexS": None
        if zone["transition"]["throttleDelayVsApexS"] is None
        or reference_zone["transition"]["throttleDelayVsApexS"] is None
        else _rounded(
            float(zone["transition"]["throttleDelayVsApexS"])
            - float(reference_zone["transition"]["throttleDelayVsApexS"]),
            3,
        ),
        "smoothnessScore": _rounded(
            float(zone["transition"]["smoothnessScore"]) - float(reference_zone["transition"]["smoothnessScore"]),
            2,
        ),
    }
    return zone


def _to_local_progress(value: float, start: float, apex: float, end: float) -> float:
    if value <= apex:
        denom = max(1e-6, apex - start)
        return -1.0 + (value - start) / denom
    denom = max(1e-6, end - apex)
    return (value - apex) / denom


def _build_detail_trace(samples: list[TransitionSample], brake: list[float], zone: dict, points: int) -> dict:
    progress = [sample.progress_ratio for sample in samples]
    throttle = [sample.throttle_pct for sample in samples]

    zone_start = float(zone["start"]["progress"])
    zone_end = float(zone["end"]["progress"])
    apex = float(zone["apex"]["progress"])

    pre_margin = max(0.015, (apex - zone_start) * 0.25)
    post_margin = max(0.02, (zone_end - apex) * 0.45)
    window_start = max(0.0, zone_start - pre_margin)
    window_end = min(1.0, zone_end + post_margin)
    if window_end <= window_start:
        window_end = min(1.0, window_start + 0.04)

    local_grid = [(-1.0 + 2.0 * idx / (points - 1)) for idx in range(points)]
    abs_grid: list[float] = []
    for local in local_grid:
        if local <= 0.0:
            abs_grid.append(window_start + (local + 1.0) * max(0.0, apex - window_start))
        else:
            abs_grid.append(apex + local * max(0.0, window_end - apex))

    brake_trace = _interpolate_series(progress, brake, abs_grid)
    throttle_trace = _interpolate_series(progress, throttle, abs_grid)

    markers = {
        "brakeRelease": _rounded(_to_local_progress(float(zone["brakeRelease"]["progress"]), window_start, apex, window_end), 4),
        "apex": _rounded(_to_local_progress(apex, window_start, apex, window_end), 4),
        "throttleApplication": None
        if zone["throttleApplication"] is None
        else _rounded(
            _to_local_progress(float(zone["throttleApplication"]["progress"]), window_start, apex, window_end),
            4,
        ),
    }

    return {
        "localProgress": [_rounded(value, 4) for value in local_grid],
        "absoluteProgress": [_rounded(value, 6) for value in abs_grid],
        "brakePressure": [_rounded(value, 4) if value is not None else None for value in brake_trace],
        "throttlePct": [_rounded(value, 4) if value is not None else None for value in throttle_trace],
        "markers": markers,
        "window": {
            "startProgress": _rounded(window_start, 4),
            "apexProgress": _rounded(apex, 4),
            "endProgress": _rounded(window_end, 4),
        },
    }


def _prepare_lap_transition(lap: DetectedLap, pressure_mode: str) -> tuple[list[TransitionSample], list[float], float, list[dict]]:
    samples = _load_transition_samples(lap, pressure_mode)
    if len(samples) < 2:
        raise ValueError("Selected lap does not contain enough telemetry samples for transition analysis.")

    smoothed_brake = _ema([sample.brake_pressure for sample in samples], alpha=SMOOTHING_ALPHA)
    active_threshold = max(MIN_ACTIVE_THRESHOLD, max(smoothed_brake) * ACTIVE_THRESHOLD_RATIO)
    zones = _detect_zone_windows(smoothed_brake, active_threshold)
    if not zones:
        raise ValueError("No usable braking zones were detected for transition analysis.")

    zone_payload = [
        _build_zone_metrics(
            zone_id=index + 1,
            zone=zone,
            samples=samples,
            smoothed_brake=smoothed_brake,
            active_threshold=active_threshold,
        )
        for index, zone in enumerate(zones)
    ]
    return samples, smoothed_brake, active_threshold, zone_payload


def compute_brake_release_throttle_transition(
    *,
    lap: DetectedLap,
    reference_lap: DetectedLap,
    pressure_mode: str = "combined",
    zone_id: int | None = None,
    trace_points: int = DEFAULT_TRACE_POINTS,
) -> dict:
    selected_mode = _validate_pressure_mode(pressure_mode)
    if trace_points < 61 or trace_points > 301:
        raise ValueError("Invalid trace_points value. Expected an integer between 61 and 301.")

    lap_samples, lap_brake, lap_threshold, lap_zones = _prepare_lap_transition(lap, selected_mode)
    ref_samples, ref_brake, ref_threshold, ref_zones = _prepare_lap_transition(reference_lap, selected_mode)

    matched_reference = _match_reference_zones(lap_zones, ref_zones)
    zones = [_attach_reference(zone, matched_reference.get(zone["zoneId"])) for zone in lap_zones]

    selected_zone_id = zone_id
    if selected_zone_id is None and zones:
        selected_zone_id = zones[0]["zoneId"]

    selected_zone = None if selected_zone_id is None else next((zone for zone in zones if zone["zoneId"] == selected_zone_id), None)
    if selected_zone_id is not None and selected_zone is None:
        raise LookupError(f"Zone {selected_zone_id} was not found for selected lap.")

    detail = None
    if selected_zone is not None:
        detail = {
            "zoneId": selected_zone["zoneId"],
            "lap": _build_detail_trace(lap_samples, lap_brake, selected_zone, trace_points),
            "reference": None,
        }
        reference_zone = selected_zone.get("reference")
        if reference_zone is not None:
            detail["reference"] = _build_detail_trace(ref_samples, ref_brake, reference_zone, trace_points)

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
            "brakePressureMode": selected_mode,
            "brakePressureSource": {
                "combined": "mean(front_brake_pressure, rear_brake_pressure)",
                "front": "front_brake_pressure",
                "rear": "rear_brake_pressure",
            }[selected_mode],
            "throttleSource": "TopicStateEstimation.gas normalized to percent",
            "speedSource": "TopicStateEstimation.v_mps",
            "smoothing": {"method": "ema", "alpha": SMOOTHING_ALPHA},
        },
        "method": {
            "zoneDefinition": "adaptive brake-pressure threshold + short gap fill",
            "releaseDefinition": "first point after peak where pressure falls near release threshold",
            "apexDefinition": "minimum speed point after peak within local lookahead",
            "throttleApplicationDefinition": "first sustained throttle >= threshold",
            "alignmentForDetail": "local normalized transition axis centered on apex",
            "throttleOnThresholdPct": MIN_THROTTLE_ON_PCT,
        },
        "thresholds": {
            "lapBrakeActiveThreshold": _rounded(lap_threshold, 4),
            "referenceBrakeActiveThreshold": _rounded(ref_threshold, 4),
        },
        "zoneCount": len(zones),
        "zones": zones,
        "selectedZoneDetail": detail,
    }
