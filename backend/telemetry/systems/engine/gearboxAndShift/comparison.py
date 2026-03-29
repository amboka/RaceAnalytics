from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median
from typing import TypeVar

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

MIN_GEAR_VALUE = 1
MAX_GEAR_VALUE = 8
MIN_MISMATCH_ZONE_POINTS = 3
NEAR_SHIFT_DELTA_M = 5.0
OUTPUT_SAMPLE_HZ = 5.0
OUTPUT_SAMPLE_PERIOD_MS = 1000.0 / OUTPUT_SAMPLE_HZ
TValue = TypeVar("TValue")


@dataclass(frozen=True)
class GearSample:
    ts_ns: int
    x_m: float
    y_m: float
    gear: int
    v_mps: float


@dataclass(frozen=True)
class GearReferencePath:
    points: list[tuple[float, float]]
    cumulative_s: list[float]
    length_m: float
    speed_mps: list[float]


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


def _normalize_gear(value: float | None) -> int | None:
    if value is None:
        return None
    gear = int(round(float(value)))
    if gear < MIN_GEAR_VALUE or gear > MAX_GEAR_VALUE:
        return None
    return gear


def _load_gear_samples(lap: DetectedLap) -> list[GearSample]:
    rows = TopicStateEstimation.objects.filter(
        record__race_id=lap.race_id,
        record__ts_ns__gte=lap.start_ns,
        record__ts_ns__lte=lap.end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "x_m",
        "y_m",
        "gear",
        "v_mps",
    )

    samples: list[GearSample] = []
    previous_ts: int | None = None
    for row in rows:
        ts_ns = int(row[0])
        x_m = row[1]
        y_m = row[2]
        gear = _normalize_gear(row[3])
        speed_mps = row[4]

        if x_m is None or y_m is None or gear is None:
            continue
        if previous_ts is not None and ts_ns <= previous_ts:
            continue

        samples.append(
            GearSample(
                ts_ns=ts_ns,
                x_m=float(x_m),
                y_m=float(y_m),
                gear=gear,
                v_mps=0.0 if speed_mps is None else float(speed_mps),
            )
        )
        previous_ts = ts_ns

    return samples


def _build_reference_path(samples: list[GearSample]) -> GearReferencePath:
    if len(samples) < 2:
        raise ValueError("Reference lap does not contain enough valid gear samples.")

    points = [(sample.x_m, sample.y_m) for sample in samples]
    cumulative_s = [0.0]
    for current, nxt in zip(samples, samples[1:]):
        cumulative_s.append(cumulative_s[-1] + hypot(nxt.x_m - current.x_m, nxt.y_m - current.y_m))

    length_m = cumulative_s[-1]
    if length_m <= 0.0:
        raise ValueError("Reference lap path length is zero.")

    return GearReferencePath(
        points=points,
        cumulative_s=cumulative_s,
        length_m=length_m,
        speed_mps=[sample.v_mps for sample in samples],
    )


def _project_point_to_reference(
    point: tuple[float, float],
    path: GearReferencePath,
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


def _project_samples_onto_reference(samples: list[GearSample], path: GearReferencePath) -> ProjectionResult:
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


def _interpolate_step(xs: list[float], ys: list[int], targets: list[float]) -> list[int | None]:
    if len(xs) != len(ys) or not xs:
        return [None for _ in targets]

    results: list[int | None] = []
    source_index = 0
    last_index = len(xs) - 1

    for target in targets:
        if target < xs[0] or target > xs[-1]:
            results.append(None)
            continue

        while source_index + 1 < last_index and xs[source_index + 1] <= target:
            source_index += 1

        results.append(ys[source_index])

    return results


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


def _select_by_indices(values: list[TValue], indices: list[int]) -> list[TValue]:
    return [values[index] for index in indices]


def _coverage(values: list[object | None]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if value is not None) / len(values)


def _require_no_nulls(values: list[object | None], label: str) -> list[object]:
    if any(value is None for value in values):
        raise ValueError(f"Unable to interpolate a complete {label} series.")
    return list(values)


def _detect_shift_events(
    samples: list[GearSample],
    distances_m: list[float],
    progress_ratio: list[float],
) -> list[dict]:
    events: list[dict] = []
    previous_gear = samples[0].gear

    for index in range(1, len(samples)):
        current_gear = samples[index].gear
        if current_gear == previous_gear:
            continue

        shift_type = "upshift" if current_gear > previous_gear else "downshift"
        events.append(
            {
                "type": shift_type,
                "fromGear": previous_gear,
                "toGear": current_gear,
                "distanceM": _rounded(distances_m[index], 3),
                "progressRatio": _rounded(progress_ratio[index], 6),
                "tsNs": samples[index].ts_ns,
                "_distance_raw": distances_m[index],
            }
        )
        previous_gear = current_gear

    return events


def _circular_delta(lap_distance_m: float, reference_distance_m: float, lap_length_m: float) -> float:
    delta = lap_distance_m - reference_distance_m
    if delta > lap_length_m * 0.5:
        delta -= lap_length_m
    if delta < -lap_length_m * 0.5:
        delta += lap_length_m
    return delta


def _match_shift_events(lap_events: list[dict], reference_events: list[dict], lap_length_m: float) -> list[dict]:
    comparisons: list[dict] = []
    reference_groups: dict[tuple[str, int, int], list[dict]] = {}
    lap_groups: dict[tuple[str, int, int], list[dict]] = {}

    for event in reference_events:
        key = (str(event["type"]), int(event["fromGear"]), int(event["toGear"]))
        reference_groups.setdefault(key, []).append(event)
    for event in lap_events:
        key = (str(event["type"]), int(event["fromGear"]), int(event["toGear"]))
        lap_groups.setdefault(key, []).append(event)

    for key in sorted(set(reference_groups) | set(lap_groups)):
        lap_group = lap_groups.get(key, [])
        reference_group = reference_groups.get(key, [])
        pair_count = min(len(lap_group), len(reference_group))

        for index in range(pair_count):
            lap_event = lap_group[index]
            reference_event = reference_group[index]
            delta_m = _circular_delta(
                float(lap_event["_distance_raw"]),
                float(reference_event["_distance_raw"]),
                lap_length_m,
            )
            if abs(delta_m) < NEAR_SHIFT_DELTA_M:
                status = "near_reference"
            elif delta_m > 0:
                status = "later_than_reference"
            else:
                status = "earlier_than_reference"

            comparisons.append(
                {
                    "type": key[0],
                    "fromGear": key[1],
                    "toGear": key[2],
                    "lapDistanceM": lap_event["distanceM"],
                    "referenceDistanceM": reference_event["distanceM"],
                    "distanceDeltaM": _rounded(delta_m, 3),
                    "status": status,
                }
            )

        for event in lap_group[pair_count:]:
            comparisons.append(
                {
                    "type": key[0],
                    "fromGear": key[1],
                    "toGear": key[2],
                    "lapDistanceM": event["distanceM"],
                    "referenceDistanceM": None,
                    "distanceDeltaM": None,
                    "status": "unmatched_lap_shift",
                }
            )

        for event in reference_group[pair_count:]:
            comparisons.append(
                {
                    "type": key[0],
                    "fromGear": key[1],
                    "toGear": key[2],
                    "lapDistanceM": None,
                    "referenceDistanceM": event["distanceM"],
                    "distanceDeltaM": None,
                    "status": "unmatched_reference_shift",
                }
            )

    return comparisons


def _build_mismatch_zones(
    progress_ratio: list[float],
    distance_m: list[float],
    lap_gears: list[int],
    reference_gears: list[int],
    lap_speed_mps: list[float],
    reference_speed_mps: list[float],
) -> list[dict]:
    zones: list[dict] = []
    index = 0

    while index < len(lap_gears):
        if lap_gears[index] == reference_gears[index]:
            index += 1
            continue

        start_index = index
        lap_gear = lap_gears[index]
        reference_gear = reference_gears[index]
        while index < len(lap_gears):
            if lap_gears[index] != lap_gear or reference_gears[index] != reference_gear:
                break
            index += 1

        end_index = index - 1
        if end_index - start_index + 1 < MIN_MISMATCH_ZONE_POINTS:
            continue

        status = "higher_gear_than_reference" if lap_gear > reference_gear else "lower_gear_than_reference"
        speed_delta = [
            lap_speed - ref_speed
            for lap_speed, ref_speed in zip(
                lap_speed_mps[start_index : end_index + 1],
                reference_speed_mps[start_index : end_index + 1],
            )
        ]
        zones.append(
            {
                "startProgress": _rounded(progress_ratio[start_index], 6),
                "endProgress": _rounded(progress_ratio[end_index], 6),
                "startDistanceM": _rounded(distance_m[start_index], 3),
                "endDistanceM": _rounded(distance_m[end_index], 3),
                "lapGear": lap_gear,
                "referenceGear": reference_gear,
                "status": status,
                "meanSpeedDeltaMps": _rounded(sum(speed_delta) / len(speed_delta), 3),
            }
        )

    return zones


def _clean_event_payload(events: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for event in events:
        copy = dict(event)
        copy.pop("_distance_raw", None)
        cleaned.append(copy)
    return cleaned


def compute_gearbox_shift_comparison(
    lap: DetectedLap,
    reference_lap: DetectedLap,
    *,
    points: int = DEFAULT_POINTS,
) -> dict:
    _validate_points(points)

    lap_samples = _load_gear_samples(lap)
    reference_samples = _load_gear_samples(reference_lap)
    if len(lap_samples) < 2:
        raise ValueError("Selected lap does not contain enough valid gear samples.")
    if len(reference_samples) < 2:
        raise ValueError("Selected reference lap does not contain enough valid gear samples.")

    reference_path = _build_reference_path(reference_samples)
    projected_lap = _project_samples_onto_reference(lap_samples, reference_path)

    median_error_m = median(projected_lap.errors_m)
    p95_error_m = _p95(projected_lap.errors_m)
    if median_error_m > MAX_MEDIAN_PROJECTION_ERROR_M or p95_error_m > MAX_P95_PROJECTION_ERROR_M:
        raise ValueError("Lap alignment quality is too poor for a reliable gearbox comparison.")

    distance_m = [(reference_path.length_m * index) / (points - 1) for index in range(points)]
    progress_ratio = [0.0 if reference_path.length_m <= 0 else distance / reference_path.length_m for distance in distance_m]

    reference_gear_raw = _interpolate_step(
        reference_path.cumulative_s,
        [sample.gear for sample in reference_samples],
        distance_m,
    )
    reference_speed_raw = _interpolate_linear(
        reference_path.cumulative_s,
        reference_path.speed_mps,
        distance_m,
    )
    reference_elapsed_raw = _interpolate_linear(
        reference_path.cumulative_s,
        [(sample.ts_ns - reference_samples[0].ts_ns) / 1_000_000.0 for sample in reference_samples],
        distance_m,
    )

    lap_start_abs_s = projected_lap.raw_s[0]
    lap_targets = [distance if distance >= lap_start_abs_s else distance + reference_path.length_m for distance in distance_m]
    lap_gear_raw = _interpolate_step(
        projected_lap.unwrapped_s,
        [sample.gear for sample in lap_samples],
        lap_targets,
    )
    lap_speed_raw = _interpolate_linear(
        projected_lap.unwrapped_s,
        [sample.v_mps for sample in lap_samples],
        lap_targets,
    )
    coverage = _coverage(lap_gear_raw)
    if coverage < MIN_VALID_GRID_COVERAGE:
        raise ValueError("Selected lap does not cover enough of the reference lap for comparison.")

    lap_gears = [int(value) for value in _require_no_nulls(lap_gear_raw, "lap gear")]
    reference_gears = [int(value) for value in _require_no_nulls(reference_gear_raw, "reference gear")]
    lap_speed_mps = [float(value) for value in _require_no_nulls(lap_speed_raw, "lap speed")]
    reference_speed_mps = [float(value) for value in _require_no_nulls(reference_speed_raw, "reference speed")]
    reference_elapsed_ms = [float(value) for value in _require_no_nulls(reference_elapsed_raw, "reference elapsed time")]
    gear_delta = [lap_gear - reference_gear for lap_gear, reference_gear in zip(lap_gears, reference_gears)]

    reference_event_progress = [0.0 if reference_path.length_m <= 0 else distance / reference_path.length_m for distance in reference_path.cumulative_s]
    lap_event_progress = [0.0 if reference_path.length_m <= 0 else distance / reference_path.length_m for distance in projected_lap.raw_s]
    reference_events = _detect_shift_events(reference_samples, reference_path.cumulative_s, reference_event_progress)
    lap_events = _detect_shift_events(lap_samples, projected_lap.raw_s, lap_event_progress)
    comparisons = _match_shift_events(lap_events, reference_events, reference_path.length_m)

    mismatch_zones = _build_mismatch_zones(
        progress_ratio=progress_ratio,
        distance_m=distance_m,
        lap_gears=lap_gears,
        reference_gears=reference_gears,
        lap_speed_mps=lap_speed_mps,
        reference_speed_mps=reference_speed_mps,
    )

    earlier_shift_count = sum(1 for event in comparisons if event["status"] == "earlier_than_reference")
    later_shift_count = sum(1 for event in comparisons if event["status"] == "later_than_reference")

    sampled_indices = _downsample_indices_from_elapsed(reference_elapsed_ms, OUTPUT_SAMPLE_PERIOD_MS)
    progress_ratio = _select_by_indices(progress_ratio, sampled_indices)
    distance_m = _select_by_indices(distance_m, sampled_indices)
    lap_gears = _select_by_indices(lap_gears, sampled_indices)
    reference_gears = _select_by_indices(reference_gears, sampled_indices)
    gear_delta = _select_by_indices(gear_delta, sampled_indices)
    lap_speed_mps = _select_by_indices(lap_speed_mps, sampled_indices)
    reference_speed_mps = _select_by_indices(reference_speed_mps, sampled_indices)

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
            "source": "TopicStateEstimation.gear",
            "gearType": "integer",
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
            "lapGear": lap_gears,
            "referenceGear": reference_gears,
            "gearDelta": gear_delta,
            "lapSpeedMps": [_rounded(value, 3) for value in lap_speed_mps],
            "referenceSpeedMps": [_rounded(value, 3) for value in reference_speed_mps],
        },
        "shiftEvents": {
            "lap": _clean_event_payload(lap_events),
            "reference": _clean_event_payload(reference_events),
            "comparisons": comparisons,
        },
        "mismatchZones": mismatch_zones,
        "summary": {
            "lapShiftCount": len(lap_events),
            "referenceShiftCount": len(reference_events),
            "comparedShiftCount": sum(
                1
                for event in comparisons
                if event["status"] in {"earlier_than_reference", "later_than_reference", "near_reference"}
            ),
            "earlierShiftCount": earlier_shift_count,
            "laterShiftCount": later_shift_count,
            "mismatchZoneCount": len(mismatch_zones),
        },
    }
