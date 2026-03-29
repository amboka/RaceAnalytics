from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from telemetry.models import TopicBadenia560TpmsFront, TopicBadenia560TpmsRear, TopicStateEstimation
from telemetry.systems.engine.types import DetectedLap

DEFAULT_POINTS = 500
MIN_POINTS = 200
MAX_POINTS = 1500
DEFAULT_ZONE_COUNT = 16
MIN_ZONE_COUNT = 8
MAX_ZONE_COUNT = 30
MIN_TEMP_C = -40.0
MAX_TEMP_C = 350.0
MIN_ZONE_SAMPLES = 4


@dataclass(frozen=True)
class StateSample:
    ts_ns: int
    progress_ratio: float
    brake_pressure: float


def _rounded(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _validate_points(points: int) -> None:
    if points < MIN_POINTS or points > MAX_POINTS:
        raise ValueError(
            f"Invalid points value {points}. Expected an integer between {MIN_POINTS} and {MAX_POINTS}."
        )


def _validate_zone_count(zone_count: int) -> None:
    if zone_count < MIN_ZONE_COUNT or zone_count > MAX_ZONE_COUNT:
        raise ValueError(
            f"Invalid zone_count value {zone_count}. Expected an integer between {MIN_ZONE_COUNT} and {MAX_ZONE_COUNT}."
        )


def _clamp_temperature(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric < MIN_TEMP_C or numeric > MAX_TEMP_C:
        return None
    return numeric


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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _load_state_progress_samples(lap: DetectedLap) -> list[StateSample]:
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

    if not rows:
        return []

    ts_ns_values: list[int] = []
    x_values: list[float] = []
    y_values: list[float] = []
    brake_pressures: list[float] = []

    previous_ts: int | None = None
    for ts_ns, x_m, y_m, fl_pressure, fr_pressure, rl_pressure, rr_pressure in rows:
        if x_m is None or y_m is None:
            continue

        ts_int = int(ts_ns)
        if previous_ts is not None and ts_int <= previous_ts:
            continue

        # Combine CBA actual pressures from all 4 wheels
        all_pressures = [v for v in [fl_pressure, fr_pressure, rl_pressure, rr_pressure] if v is not None]
        if not all_pressures:
            pressure = 0.0
        else:
            pressure = max(0.0, sum(all_pressures) / len(all_pressures))

        ts_ns_values.append(ts_int)
        x_values.append(float(x_m))
        y_values.append(float(y_m))
        brake_pressures.append(pressure)
        previous_ts = ts_int

    if len(ts_ns_values) < 2:
        return []

    cumulative_s = [0.0]
    for index in range(1, len(ts_ns_values)):
        ds = hypot(x_values[index] - x_values[index - 1], y_values[index] - y_values[index - 1])
        cumulative_s.append(cumulative_s[-1] + ds)

    lap_length_m = cumulative_s[-1]
    if lap_length_m <= 0.0:
        return []

    return [
        StateSample(
            ts_ns=ts_ns_values[index],
            progress_ratio=cumulative_s[index] / lap_length_m,
            brake_pressure=brake_pressures[index],
        )
        for index in range(len(ts_ns_values))
    ]


def _load_wheel_temperature_samples(lap: DetectedLap) -> dict[str, tuple[list[int], list[float]]]:
    wheels = {
        "fl": ([], []),
        "fr": ([], []),
        "rl": ([], []),
        "rr": ([], []),
    }

    front_rows = TopicBadenia560TpmsFront.objects.filter(
        record__race_id=lap.race_id,
        record__ts_ns__gte=lap.start_ns,
        record__ts_ns__lte=lap.end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "tpr4_temp_fl",
        "tpr4_temp_fr",
    )

    rear_rows = TopicBadenia560TpmsRear.objects.filter(
        record__race_id=lap.race_id,
        record__ts_ns__gte=lap.start_ns,
        record__ts_ns__lte=lap.end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "tpr4_temp_rl",
        "tpr4_temp_rr",
    )

    for ts_ns, temp_fl, temp_fr in front_rows:
        ts_int = int(ts_ns)
        clamped_fl = _clamp_temperature(temp_fl)
        clamped_fr = _clamp_temperature(temp_fr)
        if clamped_fl is not None:
            wheels["fl"][0].append(ts_int)
            wheels["fl"][1].append(clamped_fl)
        if clamped_fr is not None:
            wheels["fr"][0].append(ts_int)
            wheels["fr"][1].append(clamped_fr)

    for ts_ns, temp_rl, temp_rr in rear_rows:
        ts_int = int(ts_ns)
        clamped_rl = _clamp_temperature(temp_rl)
        clamped_rr = _clamp_temperature(temp_rr)
        if clamped_rl is not None:
            wheels["rl"][0].append(ts_int)
            wheels["rl"][1].append(clamped_rl)
        if clamped_rr is not None:
            wheels["rr"][0].append(ts_int)
            wheels["rr"][1].append(clamped_rr)

    return wheels


def _map_wheel_series_to_progress_grid(
    *,
    state_samples: list[StateSample],
    wheel_series_by_ts: dict[str, tuple[list[int], list[float]]],
    progress_grid: list[float],
) -> tuple[dict[str, list[float | None]], list[float | None]]:
    state_ts = [sample.ts_ns for sample in state_samples]
    state_progress = [sample.progress_ratio for sample in state_samples]

    wheel_grid_values: dict[str, list[float | None]] = {}
    for wheel_key, (wheel_ts, wheel_temps) in wheel_series_by_ts.items():
        if len(wheel_ts) < 2:
            wheel_grid_values[wheel_key] = [None for _ in progress_grid]
            continue

        wheel_progress = _interpolate_series(state_ts, state_progress, [float(value) for value in wheel_ts])
        filtered_progress: list[float] = []
        filtered_temp: list[float] = []
        previous_progress: float | None = None
        for progress, temp in zip(wheel_progress, wheel_temps):
            if progress is None:
                continue
            progress_float = float(progress)
            if previous_progress is not None and progress_float < previous_progress:
                progress_float = previous_progress
            filtered_progress.append(progress_float)
            filtered_temp.append(float(temp))
            previous_progress = progress_float

        if len(filtered_progress) < 2:
            wheel_grid_values[wheel_key] = [None for _ in progress_grid]
            continue

        wheel_grid_values[wheel_key] = _interpolate_series(filtered_progress, filtered_temp, progress_grid)

    aggregate_temp: list[float | None] = []
    for index in range(len(progress_grid)):
        values_at_index = [
            wheel_grid_values[wheel][index]
            for wheel in ("fl", "fr", "rl", "rr")
            if wheel_grid_values[wheel][index] is not None
        ]
        aggregate_temp.append(_mean([float(value) for value in values_at_index]) if values_at_index else None)

    return wheel_grid_values, aggregate_temp


def _build_zone_summary(
    *,
    progress_grid: list[float],
    distance_grid_m: list[float],
    lap_temp_c: list[float],
    lap_pressure: list[float],
    zone_count: int,
    reference_temp_c: list[float] | None,
) -> list[dict]:
    if not lap_temp_c:
        return []

    zones: list[dict] = []
    sample_count = len(lap_temp_c)

    for zone_index in range(zone_count):
        start_idx = int(zone_index * sample_count / zone_count)
        end_idx = int((zone_index + 1) * sample_count / zone_count)
        end_idx = min(sample_count, max(end_idx, start_idx + 1))

        lap_zone = lap_temp_c[start_idx:end_idx]
        pressure_zone = lap_pressure[start_idx:end_idx]
        if len(lap_zone) < MIN_ZONE_SAMPLES:
            continue

        lap_mean_c = _mean(lap_zone)
        lap_peak_c = max(lap_zone)
        pressure_mean = _mean(pressure_zone)

        reference_mean_c = None
        reference_peak_c = None
        mean_delta_c = None
        peak_delta_c = None
        if reference_temp_c is not None:
            reference_zone = reference_temp_c[start_idx:end_idx]
            reference_mean_c = _mean(reference_zone)
            reference_peak_c = max(reference_zone)
            mean_delta_c = lap_mean_c - reference_mean_c
            peak_delta_c = lap_peak_c - reference_peak_c

        thermal_flag = "normal"
        if lap_peak_c >= 120.0:
            thermal_flag = "very_hot"
        elif lap_peak_c >= 95.0:
            thermal_flag = "hot"

        load_flag = "low"
        if pressure_mean >= 0.5:
            load_flag = "high"
        elif pressure_mean >= 0.25:
            load_flag = "medium"

        zones.append(
            {
                "zoneIndex": len(zones) + 1,
                "startProgress": _rounded(progress_grid[start_idx], 4),
                "endProgress": _rounded(progress_grid[end_idx - 1], 4),
                "startDistanceM": _rounded(distance_grid_m[start_idx], 2),
                "endDistanceM": _rounded(distance_grid_m[end_idx - 1], 2),
                "lap": {
                    "meanTempC": _rounded(lap_mean_c, 3),
                    "peakTempC": _rounded(lap_peak_c, 3),
                    "avgBrakePressure": _rounded(pressure_mean, 4),
                },
                "reference": None
                if reference_temp_c is None
                else {
                    "meanTempC": _rounded(reference_mean_c, 3),
                    "peakTempC": _rounded(reference_peak_c, 3),
                },
                "delta": None
                if reference_temp_c is None
                else {
                    "meanTempC": _rounded(mean_delta_c, 3),
                    "peakTempC": _rounded(peak_delta_c, 3),
                },
                "classification": {
                    "thermal": thermal_flag,
                    "brakeLoad": load_flag,
                    "hotUnderLoad": thermal_flag in {"hot", "very_hot"} and load_flag in {"medium", "high"},
                },
            }
        )

    return zones


def _top_hot_zones(zones: list[dict], *, top_n: int = 5) -> list[dict]:
    ordered = sorted(zones, key=lambda zone: float(zone["lap"]["meanTempC"]), reverse=True)
    return ordered[:top_n]


def _series_without_nulls(values: list[float | None], *, label: str) -> list[float]:
    if any(value is None for value in values):
        raise ValueError(f"Unable to generate complete {label} series from available temperature samples.")
    return [float(value) for value in values]


def _fill_nulls_with_nearest(values: list[float | None]) -> list[float | None]:
    if not values:
        return []

    filled = values[:]
    first_valid = next((idx for idx, value in enumerate(filled) if value is not None), None)
    if first_valid is None:
        return filled

    for idx in range(0, first_valid):
        filled[idx] = filled[first_valid]

    last_valid = first_valid
    for idx in range(first_valid + 1, len(filled)):
        if filled[idx] is None:
            continue

        if idx - last_valid > 1:
            left_value = float(filled[last_valid])
            right_value = float(filled[idx])
            span = idx - last_valid
            for gap_idx in range(last_valid + 1, idx):
                factor = (gap_idx - last_valid) / span
                filled[gap_idx] = left_value + factor * (right_value - left_value)
        last_valid = idx

    for idx in range(last_valid + 1, len(filled)):
        filled[idx] = filled[last_valid]

    return filled


def _build_lap_temperature_profile(lap: DetectedLap, *, points: int) -> dict:
    state_samples = _load_state_progress_samples(lap)
    if len(state_samples) < 2:
        raise ValueError("Selected lap does not contain enough state-estimation samples for thermal alignment.")

    wheel_temp_samples = _load_wheel_temperature_samples(lap)
    if all(len(series[0]) < 2 for series in wheel_temp_samples.values()):
        raise ValueError("Selected lap does not contain enough brake temperature samples.")

    progress_grid = [index / (points - 1) for index in range(points)]
    path_length_m = lap.path_length_m if lap.path_length_m > 0.0 else 0.0
    distance_grid_m = [value * path_length_m for value in progress_grid]

    wheel_on_grid, aggregate_temp = _map_wheel_series_to_progress_grid(
        state_samples=state_samples,
        wheel_series_by_ts=wheel_temp_samples,
        progress_grid=progress_grid,
    )
    aggregate_temp = _fill_nulls_with_nearest(aggregate_temp)
    aggregate_temp_values = _series_without_nulls(aggregate_temp, label="aggregate brake temperature")

    state_progress = [sample.progress_ratio for sample in state_samples]
    state_brake_pressure = [sample.brake_pressure for sample in state_samples]
    brake_pressure_grid = _series_without_nulls(
        _interpolate_series(state_progress, state_brake_pressure, progress_grid),
        label="brake pressure",
    )

    per_wheel_payload = {
        "flTempC": [_rounded(value, 3) for value in wheel_on_grid["fl"]],
        "frTempC": [_rounded(value, 3) for value in wheel_on_grid["fr"]],
        "rlTempC": [_rounded(value, 3) for value in wheel_on_grid["rl"]],
        "rrTempC": [_rounded(value, 3) for value in wheel_on_grid["rr"]],
    }

    peak_temp = max(aggregate_temp_values)
    peak_index = aggregate_temp_values.index(peak_temp)

    return {
        "progressGrid": progress_grid,
        "distanceGridM": distance_grid_m,
        "aggregateTempC": aggregate_temp_values,
        "perWheel": per_wheel_payload,
        "brakePressure": brake_pressure_grid,
        "peak": {
            "tempC": peak_temp,
            "progress": progress_grid[peak_index],
            "distanceM": distance_grid_m[peak_index],
        },
    }


def compute_brake_temperature_comparison(
    *,
    lap: DetectedLap,
    reference_lap: DetectedLap | None,
    points: int = DEFAULT_POINTS,
    zone_count: int = DEFAULT_ZONE_COUNT,
) -> dict:
    _validate_points(points)
    _validate_zone_count(zone_count)

    lap_profile = _build_lap_temperature_profile(lap, points=points)
    reference_profile = None
    if reference_lap is not None:
        reference_profile = _build_lap_temperature_profile(reference_lap, points=points)

    lap_temp_c = lap_profile["aggregateTempC"]
    reference_temp_c = None if reference_profile is None else reference_profile["aggregateTempC"]
    delta_temp_c = None
    if reference_temp_c is not None:
        delta_temp_c = [lap_value - ref_value for lap_value, ref_value in zip(lap_temp_c, reference_temp_c)]

    zone_summary = _build_zone_summary(
        progress_grid=lap_profile["progressGrid"],
        distance_grid_m=lap_profile["distanceGridM"],
        lap_temp_c=lap_temp_c,
        lap_pressure=lap_profile["brakePressure"],
        zone_count=zone_count,
        reference_temp_c=reference_temp_c,
    )
    hottest_zones = _top_hot_zones(zone_summary)

    payload = {
        "lap": {
            "lapId": lap.lap_id,
            "raceId": lap.race_id,
            "lapNumber": lap.lap_number,
            "startNs": lap.start_ns,
            "endNs": lap.end_ns,
            "durationNs": lap.duration_ns,
        },
        "referenceLap": None
        if reference_lap is None
        else {
            "lapId": reference_lap.lap_id,
            "raceId": reference_lap.race_id,
            "lapNumber": reference_lap.lap_number,
            "startNs": reference_lap.start_ns,
            "endNs": reference_lap.end_ns,
            "durationNs": reference_lap.duration_ns,
        },
        "signal": {
            "source": "TopicBadenia560TpmsFront/Rear temperature channels (TPMS) as brake thermal proxy",
            "unit": "degC",
            "series": {
                "aggregate": "mean(FL, FR, RL, RR) where available",
                "perWheel": ["FL", "FR", "RL", "RR"],
            },
        },
        "alignment": {
            "basis": "normalized_lap_progress_from_state_path_distance",
            "progressUnit": "ratio",
            "distanceUnit": "m",
            "pointCount": points,
            "zoneCount": zone_count,
        },
        "series": {
            "progressRatio": [_rounded(value, 6) for value in lap_profile["progressGrid"]],
            "distanceM": [_rounded(value, 3) for value in lap_profile["distanceGridM"]],
            "lapTempC": [_rounded(value, 3) for value in lap_temp_c],
            "lapPerWheelTempC": lap_profile["perWheel"],
            "referenceTempC": None if reference_temp_c is None else [_rounded(value, 3) for value in reference_temp_c],
            "referencePerWheelTempC": None if reference_profile is None else reference_profile["perWheel"],
            "deltaTempC": None if delta_temp_c is None else [_rounded(value, 3) for value in delta_temp_c],
            "lapBrakePressure": [_rounded(value, 4) for value in lap_profile["brakePressure"]],
        },
        "peaks": {
            "lap": {
                "maxTempC": _rounded(float(lap_profile["peak"]["tempC"]), 3),
                "atProgress": _rounded(float(lap_profile["peak"]["progress"]), 4),
                "atDistanceM": _rounded(float(lap_profile["peak"]["distanceM"]), 2),
            },
            "reference": None
            if reference_profile is None
            else {
                "maxTempC": _rounded(float(reference_profile["peak"]["tempC"]), 3),
                "atProgress": _rounded(float(reference_profile["peak"]["progress"]), 4),
                "atDistanceM": _rounded(float(reference_profile["peak"]["distanceM"]), 2),
            },
            "deltaMaxTempC": None
            if reference_profile is None
            else _rounded(float(lap_profile["peak"]["tempC"] - reference_profile["peak"]["tempC"]), 3),
        },
        "zoneSummary": zone_summary,
        "hottestZones": hottest_zones,
    }

    if reference_temp_c is not None:
        hotter_samples = sum(1 for delta in delta_temp_c if delta > 0.0)
        payload["comparisonSummary"] = {
            "hotterProgressRatio": _rounded(hotter_samples / len(delta_temp_c), 4),
            "meanTempDeltaC": _rounded(_mean(delta_temp_c), 3),
            "maxTempDeltaC": _rounded(max(delta_temp_c), 3),
            "minTempDeltaC": _rounded(min(delta_temp_c), 3),
        }

    return payload
