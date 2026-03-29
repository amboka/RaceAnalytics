from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median

from telemetry.models import TopicStateEstimation

from ..comparison import (
    DEFAULT_POINTS,
    MAX_MEDIAN_PROJECTION_ERROR_M,
    MAX_P95_PROJECTION_ERROR_M,
    MAX_POINTS,
    MIN_POINTS,
    MIN_VALID_GRID_COVERAGE,
    _p95,
    _rounded,
)
from ..types import DetectedLap

OUTPUT_SAMPLE_HZ = 5.0
OUTPUT_SAMPLE_PERIOD_MS = 1000.0 / OUTPUT_SAMPLE_HZ


@dataclass(frozen=True)
class RpmSample:
    ts_ns: int
    x_m: float
    y_m: float
    rpm: float


@dataclass(frozen=True)
class RpmReferencePath:
    points: list[tuple[float, float]]
    cumulative_s: list[float]
    length_m: float
    rpm: list[float]


@dataclass(frozen=True)
class ProjectionResult:
    raw_s: list[float]
    unwrapped_s: list[float]
    errors_m: list[float]


def _validate_points(points: int) -> None:
    if points < MIN_POINTS or points > MAX_POINTS:
        raise ValueError(
            f"Invalid points value {points}. Expected an integer between {MIN_POINTS} and {MAX_POINTS}."
        )


def _load_rpm_samples(lap: DetectedLap) -> list[RpmSample]:
    rows = TopicStateEstimation.objects.filter(
        record__race_id=lap.race_id,
        record__ts_ns__gte=lap.start_ns,
        record__ts_ns__lte=lap.end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "x_m",
        "y_m",
        "rpm",
    )

    samples: list[RpmSample] = []
    previous_ts: int | None = None
    for row in rows:
        ts_ns = int(row[0])
        x_m = row[1]
        y_m = row[2]
        rpm = row[3]

        if x_m is None or y_m is None or rpm is None:
            continue
        if previous_ts is not None and ts_ns <= previous_ts:
            continue

        samples.append(
            RpmSample(
                ts_ns=ts_ns,
                x_m=float(x_m),
                y_m=float(y_m),
                rpm=float(rpm),
            )
        )
        previous_ts = ts_ns

    return samples


def _build_reference_path(samples: list[RpmSample]) -> RpmReferencePath:
    if len(samples) < 2:
        raise ValueError("Reference lap does not contain enough valid RPM samples.")

    points = [(sample.x_m, sample.y_m) for sample in samples]
    cumulative_s = [0.0]
    for current, nxt in zip(samples, samples[1:]):
        cumulative_s.append(cumulative_s[-1] + hypot(nxt.x_m - current.x_m, nxt.y_m - current.y_m))

    length_m = cumulative_s[-1]
    if length_m <= 0.0:
        raise ValueError("Reference lap path length is zero.")

    return RpmReferencePath(
        points=points,
        cumulative_s=cumulative_s,
        length_m=length_m,
        rpm=[sample.rpm for sample in samples],
    )


def _project_point_to_reference(
    point: tuple[float, float],
    path: RpmReferencePath,
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


def _project_samples_onto_reference(samples: list[RpmSample], path: RpmReferencePath) -> ProjectionResult:
    segment_count = len(path.points) - 1
    if segment_count <= 0:
        raise ValueError("Reference lap path is not usable.")

    first_point = (samples[0].x_m, samples[0].y_m)
    best_segment, best_s, best_error_m = _project_point_to_reference(first_point, path, 0, segment_count)

    raw_s = [best_s]
    errors_m = [best_error_m]
    previous_segment = best_segment

    for sample in samples[1:]:
        point = (sample.x_m, sample.y_m)
        search_start = max(0, previous_segment - 5)
        search_end = min(segment_count, previous_segment + 200)
        best_segment, best_s, best_error_m = _project_point_to_reference(
            point,
            path,
            search_start,
            search_end,
        )

        if best_error_m > 8.0:
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


def _interpolate_linear(xs: list[float], ys: list[float], targets: list[float]) -> list[float | None]:
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


def _coverage(values: list[float | None]) -> float:
    if not values:
        return 0.0
    valid = sum(1 for value in values if value is not None)
    return valid / len(values)


def _require_no_nulls(values: list[float | None], label: str) -> list[float]:
    if any(value is None for value in values):
        raise ValueError(f"Unable to interpolate a complete {label} series.")
    return [float(value) for value in values]


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


def compute_rpm_comparison(
    lap: DetectedLap,
    reference_lap: DetectedLap,
    *,
    points: int = DEFAULT_POINTS,
) -> dict:
    _validate_points(points)

    lap_samples = _load_rpm_samples(lap)
    reference_samples = _load_rpm_samples(reference_lap)
    if len(lap_samples) < 2:
        raise ValueError("Selected lap does not contain enough valid RPM samples.")
    if len(reference_samples) < 2:
        raise ValueError("Selected reference lap does not contain enough valid RPM samples.")

    reference_path = _build_reference_path(reference_samples)
    projected_lap = _project_samples_onto_reference(lap_samples, reference_path)

    median_error_m = median(projected_lap.errors_m)
    p95_error_m = _p95(projected_lap.errors_m)
    if median_error_m > MAX_MEDIAN_PROJECTION_ERROR_M or p95_error_m > MAX_P95_PROJECTION_ERROR_M:
        raise ValueError("Lap alignment quality is too poor for a reliable RPM comparison.")

    distance_m = [(reference_path.length_m * index) / (points - 1) for index in range(points)]
    progress_ratio = [0.0 if reference_path.length_m <= 0 else distance / reference_path.length_m for distance in distance_m]

    reference_rpm_raw = _interpolate_linear(reference_path.cumulative_s, reference_path.rpm, distance_m)
    reference_elapsed_raw = _interpolate_linear(
        reference_path.cumulative_s,
        [(sample.ts_ns - reference_samples[0].ts_ns) / 1_000_000.0 for sample in reference_samples],
        distance_m,
    )

    lap_start_abs_s = projected_lap.raw_s[0]
    lap_targets = [distance if distance >= lap_start_abs_s else distance + reference_path.length_m for distance in distance_m]
    lap_rpm_raw = _interpolate_linear(
        projected_lap.unwrapped_s,
        [sample.rpm for sample in lap_samples],
        lap_targets,
    )
    lap_elapsed_raw = _interpolate_linear(
        projected_lap.unwrapped_s,
        [(sample.ts_ns - lap_samples[0].ts_ns) / 1_000_000.0 for sample in lap_samples],
        lap_targets,
    )

    coverage = _coverage(lap_rpm_raw)
    if coverage < MIN_VALID_GRID_COVERAGE:
        raise ValueError("Selected lap does not cover enough of the reference lap for comparison.")

    lap_rpm = _require_no_nulls(lap_rpm_raw, "lap RPM")
    reference_rpm = _require_no_nulls(reference_rpm_raw, "reference RPM")
    lap_elapsed_ms = _require_no_nulls(lap_elapsed_raw, "lap elapsed time")
    reference_elapsed_ms = _require_no_nulls(reference_elapsed_raw, "reference elapsed time")
    delta_rpm = [lap_value - reference_value for lap_value, reference_value in zip(lap_rpm, reference_rpm)]

    sampled_indices = _downsample_indices_from_elapsed(reference_elapsed_ms, OUTPUT_SAMPLE_PERIOD_MS)
    progress_ratio = _select_by_indices(progress_ratio, sampled_indices)
    distance_m = _select_by_indices(distance_m, sampled_indices)
    lap_rpm = _select_by_indices(lap_rpm, sampled_indices)
    reference_rpm = _select_by_indices(reference_rpm, sampled_indices)
    delta_rpm = _select_by_indices(delta_rpm, sampled_indices)
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
            "source": "TopicStateEstimation.rpm",
            "unit": "rpm",
        },
        "alignment": {
            "basis": "reference_path_progress",
            "progressUnit": "ratio",
            "distanceUnit": "m",
            "referencePathLengthM": _rounded(reference_path.length_m, 3),
            "pointCount": len(progress_ratio),
            "outputSampleHz": OUTPUT_SAMPLE_HZ,
            "quality": {
                "lapCoverageRatio": _rounded(coverage, 4),
                "referenceCoverageRatio": 1.0,
                "lapMedianProjectionErrorM": _rounded(median_error_m, 3),
                "lapP95ProjectionErrorM": _rounded(p95_error_m, 3),
            },
        },
        "series": {
            "progressRatio": [_rounded(value, 6) for value in progress_ratio],
            "distanceM": [_rounded(value, 3) for value in distance_m],
            "lapRpm": [_rounded(value, 3) for value in lap_rpm],
            "referenceRpm": [_rounded(value, 3) for value in reference_rpm],
            "deltaRpm": [_rounded(value, 3) for value in delta_rpm],
            "lapElapsedMs": [_rounded(value, 3) for value in lap_elapsed_ms],
            "referenceElapsedMs": [_rounded(value, 3) for value in reference_elapsed_ms],
        },
    }
