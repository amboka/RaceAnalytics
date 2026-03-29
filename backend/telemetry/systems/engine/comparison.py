from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median

from .laps import load_lap_samples
from .types import DetectedLap, StateSample

DEFAULT_POINTS = 600
MIN_POINTS = 200
MAX_POINTS = 1200
PROJECTION_BACKTRACK_SEGMENTS = 5
PROJECTION_LOOKAHEAD_SEGMENTS = 200
PROJECTION_FALLBACK_ERROR_M = 8.0
MAX_MEDIAN_PROJECTION_ERROR_M = 15.0
MAX_P95_PROJECTION_ERROR_M = 30.0
MIN_VALID_GRID_COVERAGE = 0.95
DEFICIT_THRESHOLD_PCT = 8.0
DEFICIT_RELEASE_THRESHOLD_PCT = 6.0
ACTIVE_REFERENCE_THRESHOLD_PCT = 15.0
THROTTLE_ON_THRESHOLD_PCT = 10.0
FULL_THROTTLE_THRESHOLD_PCT = 95.0
MIN_HIGHLIGHT_POINTS = 4
OUTPUT_SAMPLE_HZ = 5.0
OUTPUT_SAMPLE_PERIOD_MS = 1000.0 / OUTPUT_SAMPLE_HZ


@dataclass(frozen=True)
class ReferencePath:
    points: list[tuple[float, float]]
    cumulative_s: list[float]
    length_m: float
    throttle_pct: list[float]
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


def _build_reference_path(samples: list[StateSample]) -> ReferencePath:
    if len(samples) < 2:
        raise ValueError("Reference lap does not contain enough telemetry samples.")

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
        throttle_pct=[sample.gas_pct for sample in samples],
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


def _project_samples_onto_reference(
    samples: list[StateSample],
    path: ReferencePath,
) -> ProjectionResult:
    if len(path.points) < 2:
        raise ValueError("Reference lap path is not usable.")

    segment_count = len(path.points) - 1
    first_point = (samples[0].x_m, samples[0].y_m)
    best_segment, best_s, best_error_m = _project_point_to_reference(
        first_point,
        path,
        0,
        segment_count,
    )

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
            best_segment, best_s, best_error_m = _project_point_to_reference(
                point,
                path,
                0,
                segment_count,
            )

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

    return ProjectionResult(
        raw_s=raw_s,
        unwrapped_s=unwrapped_s,
        errors_m=errors_m,
    )


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


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int(round((len(ordered) - 1) * 0.95)))
    return ordered[index]


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


def _count_direction_changes(values: list[float]) -> int:
    previous_sign = 0
    sign_changes = 0

    for left, right in zip(values, values[1:]):
        delta = right - left
        if abs(delta) < 1.0:
            continue
        current_sign = 1 if delta > 0 else -1
        if previous_sign != 0 and current_sign != previous_sign:
            sign_changes += 1
        previous_sign = current_sign

    return sign_changes


def _build_highlights(
    progress_ratio: list[float],
    distance_m: list[float],
    lap_throttle_pct: list[float],
    reference_throttle_pct: list[float],
) -> list[dict]:
    highlights: list[dict] = []
    deficits = [ref - lap for lap, ref in zip(lap_throttle_pct, reference_throttle_pct)]

    index = 0
    while index < len(deficits):
        if deficits[index] < DEFICIT_THRESHOLD_PCT or reference_throttle_pct[index] < ACTIVE_REFERENCE_THRESHOLD_PCT:
            index += 1
            continue

        start_index = index
        while index < len(deficits):
            still_active = (
                deficits[index] >= DEFICIT_RELEASE_THRESHOLD_PCT
                and reference_throttle_pct[index] >= ACTIVE_REFERENCE_THRESHOLD_PCT
            )
            if not still_active:
                break
            index += 1

        end_index = index - 1
        if end_index - start_index + 1 < MIN_HIGHLIGHT_POINTS:
            continue

        lap_segment = lap_throttle_pct[start_index : end_index + 1]
        reference_segment = reference_throttle_pct[start_index : end_index + 1]
        deficit_segment = deficits[start_index : end_index + 1]

        reference_onset = _first_crossing(reference_segment, THROTTLE_ON_THRESHOLD_PCT)
        lap_onset = _first_crossing(lap_segment, THROTTLE_ON_THRESHOLD_PCT)
        reference_full = _first_crossing(reference_segment, FULL_THROTTLE_THRESHOLD_PCT)
        lap_full = _first_crossing(lap_segment, FULL_THROTTLE_THRESHOLD_PCT)

        traits: list[str] = []
        onset_delay_m = None
        full_throttle_delay_m = None

        if reference_onset is not None:
            if lap_onset is None:
                onset_delay_m = distance_m[end_index] - distance_m[start_index + reference_onset]
            elif lap_onset > reference_onset:
                onset_delay_m = (
                    distance_m[start_index + lap_onset]
                    - distance_m[start_index + reference_onset]
                )
            if onset_delay_m is not None and onset_delay_m >= 5.0:
                traits.append("late_throttle_pickup")

        if reference_full is not None:
            if lap_full is None:
                full_throttle_delay_m = distance_m[end_index] - distance_m[start_index + reference_full]
            elif lap_full > reference_full:
                full_throttle_delay_m = (
                    distance_m[start_index + lap_full]
                    - distance_m[start_index + reference_full]
                )
            if full_throttle_delay_m is not None and full_throttle_delay_m >= 5.0:
                traits.append("late_full_throttle")

        reference_ramp = max(reference_segment) - reference_segment[0]
        lap_ramp = max(lap_segment) - lap_segment[0]
        if reference_ramp >= 10.0 and lap_ramp < reference_ramp * 0.85:
            traits.append("slow_throttle_ramp")

        if _count_direction_changes(lap_segment) >= 2:
            traits.append("throttle_hesitation")

        primary_type = traits[0] if traits else "throttle_deficit"
        highlights.append(
            {
                "type": primary_type,
                "traits": traits,
                "startProgress": _rounded(progress_ratio[start_index], 4),
                "endProgress": _rounded(progress_ratio[end_index], 4),
                "startDistanceM": _rounded(distance_m[start_index], 2),
                "endDistanceM": _rounded(distance_m[end_index], 2),
                "maxDeficitPct": _rounded(max(deficit_segment), 2),
                "meanDeficitPct": _rounded(sum(deficit_segment) / len(deficit_segment), 2),
                "onsetDelayM": _rounded(onset_delay_m, 2),
                "fullThrottleDelayM": _rounded(full_throttle_delay_m, 2),
            }
        )

    return highlights


def _validate_points(points: int) -> None:
    if points < MIN_POINTS or points > MAX_POINTS:
        raise ValueError(
            f"Invalid points value {points}. Expected an integer between {MIN_POINTS} and {MAX_POINTS}."
        )


def compute_throttle_comparison(
    lap: DetectedLap,
    reference_lap: DetectedLap,
    *,
    points: int = DEFAULT_POINTS,
) -> dict:
    _validate_points(points)

    lap_samples = load_lap_samples(lap)
    reference_samples = load_lap_samples(reference_lap)
    if len(lap_samples) < 2:
        raise ValueError("Selected lap does not contain enough telemetry samples.")
    if len(reference_samples) < 2:
        raise ValueError("Selected reference lap does not contain enough telemetry samples.")

    reference_path = _build_reference_path(reference_samples)
    projected_lap = _project_samples_onto_reference(lap_samples, reference_path)

    median_error_m = median(projected_lap.errors_m)
    p95_error_m = _p95(projected_lap.errors_m)
    if median_error_m > MAX_MEDIAN_PROJECTION_ERROR_M or p95_error_m > MAX_P95_PROJECTION_ERROR_M:
        raise ValueError("Lap alignment quality is too poor for a reliable throttle comparison.")

    distance_m = [
        (reference_path.length_m * index) / (points - 1)
        for index in range(points)
    ]
    progress_ratio = [
        0.0 if reference_path.length_m <= 0 else distance / reference_path.length_m
        for distance in distance_m
    ]

    reference_throttle_pct = _series_without_nulls(
        _interpolate_series(reference_path.cumulative_s, reference_path.throttle_pct, distance_m),
        label="reference throttle",
    )
    reference_elapsed_ms = _series_without_nulls(
        _interpolate_series(reference_path.cumulative_s, reference_path.elapsed_ms, distance_m),
        label="reference elapsed time",
    )

    lap_start_abs_s = projected_lap.raw_s[0]
    lap_targets = [
        distance if distance >= lap_start_abs_s else distance + reference_path.length_m
        for distance in distance_m
    ]
    lap_throttle_raw = _interpolate_series(
        projected_lap.unwrapped_s,
        [sample.gas_pct for sample in lap_samples],
        lap_targets,
    )
    lap_elapsed_raw = _interpolate_series(
        projected_lap.unwrapped_s,
        [(sample.ts_ns - lap_samples[0].ts_ns) / 1_000_000.0 for sample in lap_samples],
        lap_targets,
    )

    lap_coverage_ratio = _series_coverage(lap_throttle_raw)
    if lap_coverage_ratio < MIN_VALID_GRID_COVERAGE:
        raise ValueError("Selected lap does not cover enough of the reference lap for comparison.")

    lap_throttle_pct = _series_without_nulls(lap_throttle_raw, label="lap throttle")
    lap_elapsed_ms = _series_without_nulls(lap_elapsed_raw, label="lap elapsed time")
    delta_throttle_pct = [lap_value - ref_value for lap_value, ref_value in zip(lap_throttle_pct, reference_throttle_pct)]

    highlights = _build_highlights(
        progress_ratio=progress_ratio,
        distance_m=distance_m,
        lap_throttle_pct=lap_throttle_pct,
        reference_throttle_pct=reference_throttle_pct,
    )

    sampled_indices = _downsample_indices_from_elapsed(reference_elapsed_ms, OUTPUT_SAMPLE_PERIOD_MS)
    progress_ratio = _select_by_indices(progress_ratio, sampled_indices)
    distance_m = _select_by_indices(distance_m, sampled_indices)
    lap_throttle_pct = _select_by_indices(lap_throttle_pct, sampled_indices)
    reference_throttle_pct = _select_by_indices(reference_throttle_pct, sampled_indices)
    delta_throttle_pct = _select_by_indices(delta_throttle_pct, sampled_indices)
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
            "source": "TopicStateEstimation.gas",
            "unit": "percent",
            "normalizedFrom": "0..1 to 0..100",
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
            "lapThrottlePct": [_rounded(value, 3) for value in lap_throttle_pct],
            "referenceThrottlePct": [_rounded(value, 3) for value in reference_throttle_pct],
            "deltaThrottlePct": [_rounded(value, 3) for value in delta_throttle_pct],
            "lapElapsedMs": [_rounded(value, 3) for value in lap_elapsed_ms],
            "referenceElapsedMs": [_rounded(value, 3) for value in reference_elapsed_ms],
        },
        "highlights": highlights,
    }
