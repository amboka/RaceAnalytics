from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median

from telemetry.models import TopicStateEstimation
from telemetry.systems.engine.types import DetectedLap

DEFAULT_POINTS = 700
MIN_POINTS = 250
MAX_POINTS = 2000
PROJECTION_BACKTRACK_SEGMENTS = 5
PROJECTION_LOOKAHEAD_SEGMENTS = 220
PROJECTION_FALLBACK_ERROR_M = 8.0
MAX_MEDIAN_PROJECTION_ERROR_M = 15.0
MAX_P95_PROJECTION_ERROR_M = 30.0
MIN_VALID_GRID_COVERAGE = 0.95
OUTPUT_SAMPLE_HZ = 5.0
OUTPUT_SAMPLE_PERIOD_MS = 1000.0 / OUTPUT_SAMPLE_HZ
SMOOTHING_ALPHA = 0.2
MIN_ZONE_POINTS = 4
ACTIVE_THRESHOLD_RATIO = 0.08
MIN_ACTIVE_THRESHOLD = 0.02

SUPPORTED_PRESSURE_MODES = {"combined", "front", "rear"}


@dataclass(frozen=True)
class BrakeSample:
    ts_ns: int
    x_m: float
    y_m: float
    pressure: float


@dataclass(frozen=True)
class ReferencePath:
    points: list[tuple[float, float]]
    cumulative_s: list[float]
    length_m: float
    pressure: list[float]
    elapsed_ms: list[float]


@dataclass(frozen=True)
class ProjectionResult:
    raw_s: list[float]
    unwrapped_s: list[float]
    errors_m: list[float]


def _rounded(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int(round((len(ordered) - 1) * 0.95)))
    return ordered[index]


def _validate_points(points: int) -> None:
    if points < MIN_POINTS or points > MAX_POINTS:
        raise ValueError(
            f"Invalid points value {points}. Expected an integer between {MIN_POINTS} and {MAX_POINTS}."
        )


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


def _load_brake_samples(lap: DetectedLap, pressure_mode: str) -> list[BrakeSample]:
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
    )

    samples: list[BrakeSample] = []
    previous_ts: int | None = None
    for ts_ns, x_m, y_m, fl_pressure, fr_pressure, rl_pressure, rr_pressure in rows:
        if x_m is None or y_m is None:
            continue

        ts_ns_int = int(ts_ns)
        if previous_ts is not None and ts_ns_int <= previous_ts:
            continue

        pressure = _resolve_pressure(fl_pressure, fr_pressure, rl_pressure, rr_pressure, pressure_mode)
        if pressure is None:
            continue

        samples.append(
            BrakeSample(
                ts_ns=ts_ns_int,
                x_m=float(x_m),
                y_m=float(y_m),
                pressure=float(pressure),
            )
        )
        previous_ts = ts_ns_int

    return samples


def _build_reference_path(samples: list[BrakeSample]) -> ReferencePath:
    if len(samples) < 2:
        raise ValueError("Reference lap does not contain enough brake pressure samples.")

    points = [(sample.x_m, sample.y_m) for sample in samples]
    cumulative_s = [0.0]
    for current, nxt in zip(samples, samples[1:]):
        cumulative_s.append(cumulative_s[-1] + hypot(nxt.x_m - current.x_m, nxt.y_m - current.y_m))

    length_m = cumulative_s[-1]
    if length_m <= 0.0:
        raise ValueError("Reference lap path length is zero.")

    start_ts_ns = samples[0].ts_ns
    elapsed_ms = [(sample.ts_ns - start_ts_ns) / 1_000_000.0 for sample in samples]

    return ReferencePath(
        points=points,
        cumulative_s=cumulative_s,
        length_m=length_m,
        pressure=[sample.pressure for sample in samples],
        elapsed_ms=elapsed_ms,
    )


def _project_point_to_reference(
    point: tuple[float, float],
    path: ReferencePath,
    start_segment: int,
    end_segment: int,
) -> tuple[int, float, float]:
    best_segment = start_segment
    best_s = 0.0
    best_error_sq = float("inf")

    for segment_index in range(start_segment, end_segment):
        ax, ay = path.points[segment_index]
        bx, by = path.points[segment_index + 1]
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy

        if length_sq <= 1e-12:
            projection_t = 0.0
            proj_x = ax
            proj_y = ay
        else:
            projection_t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / length_sq
            projection_t = max(0.0, min(1.0, projection_t))
            proj_x = ax + projection_t * dx
            proj_y = ay + projection_t * dy

        error_sq = (point[0] - proj_x) ** 2 + (point[1] - proj_y) ** 2
        if error_sq < best_error_sq:
            segment_length = hypot(dx, dy)
            best_segment = segment_index
            best_error_sq = error_sq
            best_s = path.cumulative_s[segment_index] + projection_t * segment_length

    return best_segment, best_s, best_error_sq ** 0.5


def _project_samples_onto_reference(samples: list[BrakeSample], path: ReferencePath) -> ProjectionResult:
    if len(path.points) < 2:
        raise ValueError("Reference lap path is not usable.")

    segment_count = len(path.points) - 1
    first_point = (samples[0].x_m, samples[0].y_m)
    best_segment, best_s, best_error_m = _project_point_to_reference(first_point, path, 0, segment_count)

    raw_s = [best_s]
    errors_m = [best_error_m]
    previous_segment = best_segment

    for sample in samples[1:]:
        point = (sample.x_m, sample.y_m)
        search_start = max(0, previous_segment - PROJECTION_BACKTRACK_SEGMENTS)
        search_end = min(segment_count, previous_segment + PROJECTION_LOOKAHEAD_SEGMENTS)
        best_segment, best_s, best_error_m = _project_point_to_reference(
            point,
            path,
            search_start,
            search_end,
        )

        if best_error_m > PROJECTION_FALLBACK_ERROR_M:
            best_segment, best_s, best_error_m = _project_point_to_reference(point, path, 0, segment_count)

        raw_s.append(best_s)
        errors_m.append(best_error_m)
        previous_segment = best_segment

    unwrapped_s = [raw_s[0]]
    wrap_offset = 0.0
    for current_s in raw_s[1:]:
        candidate_s = current_s + wrap_offset
        if candidate_s < unwrapped_s[-1] - (path.length_m * 0.5):
            wrap_offset += path.length_m
            candidate_s = current_s + wrap_offset
        if candidate_s < unwrapped_s[-1]:
            candidate_s = unwrapped_s[-1]
        unwrapped_s.append(candidate_s)

    return ProjectionResult(raw_s=raw_s, unwrapped_s=unwrapped_s, errors_m=errors_m)


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


def _series_coverage(values: list[float | None]) -> float:
    if not values:
        return 0.0
    valid = sum(1 for value in values if value is not None)
    return valid / len(values)


def _series_without_nulls(values: list[float | None], *, label: str) -> list[float]:
    if any(value is None for value in values):
        raise ValueError(f"Unable to interpolate a complete {label} series.")
    return [float(value) for value in values]


def _ema(values: list[float], alpha: float) -> list[float]:
    if not values:
        return []

    smoothed = [values[0]]
    for value in values[1:]:
        smoothed.append(alpha * value + (1.0 - alpha) * smoothed[-1])
    return smoothed


def _downsample_indices_from_elapsed(elapsed_ms: list[float], sample_period_ms: float) -> list[int]:
    if not elapsed_ms:
        return []

    indices = [0]
    next_target_ms = elapsed_ms[0] + sample_period_ms

    for index in range(1, len(elapsed_ms)):
        current_ms = elapsed_ms[index]
        if current_ms >= next_target_ms:
            indices.append(index)
            next_target_ms = current_ms + sample_period_ms

    if indices[-1] != len(elapsed_ms) - 1:
        indices.append(len(elapsed_ms) - 1)

    return indices


def _select_by_indices(values: list[float], indices: list[int]) -> list[float]:
    return [values[index] for index in indices]


def _first_crossing(values: list[float], threshold: float, start_index: int = 0) -> int | None:
    for index in range(start_index, len(values)):
        if values[index] >= threshold:
            return index
    return None


def _last_crossing(values: list[float], threshold: float) -> int | None:
    for index in range(len(values) - 1, -1, -1):
        if values[index] >= threshold:
            return index
    return None


def _detect_braking_zones(
    progress_ratio: list[float],
    distance_m: list[float],
    lap_pressure: list[float],
    reference_pressure: list[float],
) -> tuple[list[dict], list[dict], float]:
    if not distance_m:
        return [], [], MIN_ACTIVE_THRESHOLD

    peak_pressure = max(max(lap_pressure), max(reference_pressure))
    active_threshold = max(MIN_ACTIVE_THRESHOLD, peak_pressure * ACTIVE_THRESHOLD_RATIO)

    active_mask = [max(lap_value, ref_value) >= active_threshold for lap_value, ref_value in zip(lap_pressure, reference_pressure)]

    zones: list[dict] = []
    highlights: list[dict] = []
    index = 0

    while index < len(active_mask):
        if not active_mask[index]:
            index += 1
            continue

        zone_start = index
        while index < len(active_mask) and active_mask[index]:
            index += 1
        zone_end = index - 1

        if zone_end - zone_start + 1 < MIN_ZONE_POINTS:
            continue

        lap_segment = lap_pressure[zone_start : zone_end + 1]
        reference_segment = reference_pressure[zone_start : zone_end + 1]

        lap_onset_rel = _first_crossing(lap_segment, active_threshold)
        reference_onset_rel = _first_crossing(reference_segment, active_threshold)
        lap_release_rel = _last_crossing(lap_segment, active_threshold)
        reference_release_rel = _last_crossing(reference_segment, active_threshold)

        lap_onset_idx = None if lap_onset_rel is None else zone_start + lap_onset_rel
        reference_onset_idx = None if reference_onset_rel is None else zone_start + reference_onset_rel
        lap_release_idx = None if lap_release_rel is None else zone_start + lap_release_rel
        reference_release_idx = None if reference_release_rel is None else zone_start + reference_release_rel

        onset_delta_m = None
        if lap_onset_idx is not None and reference_onset_idx is not None:
            onset_delta_m = distance_m[lap_onset_idx] - distance_m[reference_onset_idx]

        release_delta_m = None
        if lap_release_idx is not None and reference_release_idx is not None:
            release_delta_m = distance_m[lap_release_idx] - distance_m[reference_release_idx]

        lap_peak_pressure = max(lap_segment)
        reference_peak_pressure = max(reference_segment)
        peak_delta = lap_peak_pressure - reference_peak_pressure

        lap_peak_rel = lap_segment.index(lap_peak_pressure)
        reference_peak_rel = reference_segment.index(reference_peak_pressure)
        lap_peak_idx = zone_start + lap_peak_rel
        reference_peak_idx = zone_start + reference_peak_rel

        peak_position_delta_m = distance_m[lap_peak_idx] - distance_m[reference_peak_idx]

        dx = distance_m[1] - distance_m[0] if len(distance_m) > 1 else 0.0
        lap_area = sum(lap_segment) * dx
        reference_area = sum(reference_segment) * dx
        area_delta = lap_area - reference_area

        lap_brake_distance_m = 0.0
        reference_brake_distance_m = 0.0
        for zone_index in range(zone_start, zone_end + 1):
            if lap_pressure[zone_index] >= active_threshold:
                lap_brake_distance_m += dx
            if reference_pressure[zone_index] >= active_threshold:
                reference_brake_distance_m += dx
        duration_delta_m = lap_brake_distance_m - reference_brake_distance_m

        traits: list[str] = []
        if onset_delta_m is not None and onset_delta_m <= -5.0:
            traits.append("earlier_brake_onset")
        elif onset_delta_m is not None and onset_delta_m >= 5.0:
            traits.append("later_brake_onset")

        if release_delta_m is not None and release_delta_m >= 5.0:
            traits.append("longer_brake_release")
        elif release_delta_m is not None and release_delta_m <= -5.0:
            traits.append("earlier_brake_release")

        if reference_peak_pressure > 0.0:
            peak_ratio_delta = peak_delta / reference_peak_pressure
            if peak_ratio_delta >= 0.1:
                traits.append("higher_peak_pressure")
            elif peak_ratio_delta <= -0.1:
                traits.append("lower_peak_pressure")

        if reference_area > 0.0:
            area_ratio_delta = area_delta / reference_area
            if area_ratio_delta >= 0.15:
                traits.append("more_total_brake_input")
            elif area_ratio_delta <= -0.15:
                traits.append("less_total_brake_input")

        severity = 0.0
        if onset_delta_m is not None:
            severity += min(abs(onset_delta_m) / 20.0, 0.35)
        if release_delta_m is not None:
            severity += min(abs(release_delta_m) / 20.0, 0.25)
        if reference_peak_pressure > 0.0:
            severity += min(abs(peak_delta) / (reference_peak_pressure * 0.5), 0.2)
        if reference_area > 0.0:
            severity += min(abs(area_delta) / (reference_area * 0.5), 0.2)

        zone_payload = {
            "zoneIndex": len(zones) + 1,
            "startProgress": _rounded(progress_ratio[zone_start], 4),
            "endProgress": _rounded(progress_ratio[zone_end], 4),
            "startDistanceM": _rounded(distance_m[zone_start], 2),
            "endDistanceM": _rounded(distance_m[zone_end], 2),
            "lap": {
                "onsetDistanceM": None if lap_onset_idx is None else _rounded(distance_m[lap_onset_idx], 2),
                "releaseDistanceM": None if lap_release_idx is None else _rounded(distance_m[lap_release_idx], 2),
                "peakPressure": _rounded(lap_peak_pressure, 3),
                "peakDistanceM": _rounded(distance_m[lap_peak_idx], 2),
                "brakeDistanceM": _rounded(lap_brake_distance_m, 2),
                "brakeArea": _rounded(lap_area, 3),
            },
            "reference": {
                "onsetDistanceM": None if reference_onset_idx is None else _rounded(distance_m[reference_onset_idx], 2),
                "releaseDistanceM": None if reference_release_idx is None else _rounded(distance_m[reference_release_idx], 2),
                "peakPressure": _rounded(reference_peak_pressure, 3),
                "peakDistanceM": _rounded(distance_m[reference_peak_idx], 2),
                "brakeDistanceM": _rounded(reference_brake_distance_m, 2),
                "brakeArea": _rounded(reference_area, 3),
            },
            "differences": {
                "onsetDeltaM": _rounded(onset_delta_m, 2),
                "releaseDeltaM": _rounded(release_delta_m, 2),
                "peakPressureDelta": _rounded(peak_delta, 3),
                "peakPositionDeltaM": _rounded(peak_position_delta_m, 2),
                "brakeDistanceDeltaM": _rounded(duration_delta_m, 2),
                "brakeAreaDelta": _rounded(area_delta, 3),
            },
            "traits": traits,
            "severity": _rounded(min(severity, 1.0), 3),
        }
        zones.append(zone_payload)

        if severity >= 0.35:
            highlights.append(
                {
                    "zoneIndex": zone_payload["zoneIndex"],
                    "type": traits[0] if traits else "braking_difference",
                    "startProgress": zone_payload["startProgress"],
                    "endProgress": zone_payload["endProgress"],
                    "severity": zone_payload["severity"],
                    "notes": "Braking behavior differs materially from reference in this zone.",
                }
            )

    highlights = sorted(highlights, key=lambda item: float(item["severity"]), reverse=True)[:6]
    return zones, highlights, active_threshold


def compute_brake_pressure_comparison(
    lap: DetectedLap,
    reference_lap: DetectedLap,
    *,
    points: int = DEFAULT_POINTS,
    pressure_mode: str = "combined",
) -> dict:
    _validate_points(points)
    selected_mode = _validate_pressure_mode(pressure_mode)

    lap_samples = _load_brake_samples(lap, selected_mode)
    reference_samples = _load_brake_samples(reference_lap, selected_mode)
    if len(lap_samples) < 2:
        raise ValueError("Selected lap does not contain enough brake pressure samples.")
    if len(reference_samples) < 2:
        raise ValueError("Selected reference lap does not contain enough brake pressure samples.")

    reference_path = _build_reference_path(reference_samples)
    projected_lap = _project_samples_onto_reference(lap_samples, reference_path)

    median_error_m = median(projected_lap.errors_m)
    p95_error_m = _p95(projected_lap.errors_m)
    if median_error_m > MAX_MEDIAN_PROJECTION_ERROR_M or p95_error_m > MAX_P95_PROJECTION_ERROR_M:
        raise ValueError("Lap alignment quality is too poor for a reliable brake comparison.")

    distance_m = [(reference_path.length_m * index) / (points - 1) for index in range(points)]
    progress_ratio = [
        0.0 if reference_path.length_m <= 0.0 else value / reference_path.length_m
        for value in distance_m
    ]

    reference_pressure = _series_without_nulls(
        _interpolate_series(reference_path.cumulative_s, reference_path.pressure, distance_m),
        label="reference brake pressure",
    )
    reference_elapsed_ms = _series_without_nulls(
        _interpolate_series(reference_path.cumulative_s, reference_path.elapsed_ms, distance_m),
        label="reference elapsed time",
    )

    lap_start_abs_s = projected_lap.raw_s[0]
    lap_targets = [distance if distance >= lap_start_abs_s else distance + reference_path.length_m for distance in distance_m]

    lap_pressure_raw = _interpolate_series(
        projected_lap.unwrapped_s,
        [sample.pressure for sample in lap_samples],
        lap_targets,
    )
    lap_elapsed_raw = _interpolate_series(
        projected_lap.unwrapped_s,
        [(sample.ts_ns - lap_samples[0].ts_ns) / 1_000_000.0 for sample in lap_samples],
        lap_targets,
    )

    lap_coverage_ratio = _series_coverage(lap_pressure_raw)
    if lap_coverage_ratio < MIN_VALID_GRID_COVERAGE:
        raise ValueError("Selected lap does not cover enough of the reference lap for comparison.")

    lap_pressure = _series_without_nulls(lap_pressure_raw, label="lap brake pressure")
    lap_elapsed_ms = _series_without_nulls(lap_elapsed_raw, label="lap elapsed time")

    # Smooth noisy pressure samples while preserving major braking features.
    lap_pressure_smoothed = _ema(lap_pressure, SMOOTHING_ALPHA)
    reference_pressure_smoothed = _ema(reference_pressure, SMOOTHING_ALPHA)
    delta_pressure = [
        lap_value - ref_value
        for lap_value, ref_value in zip(lap_pressure_smoothed, reference_pressure_smoothed)
    ]

    braking_zones, highlights, active_threshold = _detect_braking_zones(
        progress_ratio=progress_ratio,
        distance_m=distance_m,
        lap_pressure=lap_pressure_smoothed,
        reference_pressure=reference_pressure_smoothed,
    )

    sampled_indices = _downsample_indices_from_elapsed(reference_elapsed_ms, OUTPUT_SAMPLE_PERIOD_MS)
    progress_ratio = _select_by_indices(progress_ratio, sampled_indices)
    distance_m = _select_by_indices(distance_m, sampled_indices)
    lap_pressure_smoothed = _select_by_indices(lap_pressure_smoothed, sampled_indices)
    reference_pressure_smoothed = _select_by_indices(reference_pressure_smoothed, sampled_indices)
    delta_pressure = _select_by_indices(delta_pressure, sampled_indices)
    lap_elapsed_ms = _select_by_indices(lap_elapsed_ms, sampled_indices)
    reference_elapsed_ms = _select_by_indices(reference_elapsed_ms, sampled_indices)

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
            "mode": selected_mode,
            "source": {
                "combined": "mean(TopicStateEstimation.front_brake_pressure, TopicStateEstimation.rear_brake_pressure)",
                "front": "TopicStateEstimation.front_brake_pressure",
                "rear": "TopicStateEstimation.rear_brake_pressure",
            }[selected_mode],
            "unit": "native_pressure_units",
            "smoothing": {
                "method": "ema",
                "alpha": SMOOTHING_ALPHA,
            },
            "activeThreshold": _rounded(active_threshold, 4),
        },
        "alignment": {
            "basis": "reference_path_progress",
            "progressUnit": "ratio",
            "distanceUnit": "m",
            "referencePathLengthM": _rounded(reference_path.length_m, 3),
            "pointCount": len(progress_ratio),
            "outputSampleHz": OUTPUT_SAMPLE_HZ,
            "quality": {
                "lapCoverageRatio": _rounded(lap_coverage_ratio, 4),
                "referenceCoverageRatio": 1.0,
                "lapMedianProjectionErrorM": _rounded(median_error_m, 3),
                "lapP95ProjectionErrorM": _rounded(p95_error_m, 3),
            },
        },
        "series": {
            "progressRatio": [_rounded(value, 6) for value in progress_ratio],
            "distanceM": [_rounded(value, 3) for value in distance_m],
            "lapBrakePressure": [_rounded(value, 4) for value in lap_pressure_smoothed],
            "referenceBrakePressure": [_rounded(value, 4) for value in reference_pressure_smoothed],
            "deltaBrakePressure": [_rounded(value, 4) for value in delta_pressure],
            "lapElapsedMs": [_rounded(value, 3) for value in lap_elapsed_ms],
            "referenceElapsedMs": [_rounded(value, 3) for value in reference_elapsed_ms],
        },
        "brakingZones": braking_zones,
        "highlights": highlights,
    }
