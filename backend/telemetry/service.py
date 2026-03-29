from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from telemetry.models import (
    TopicBadenia560TpmsFront,
    TopicBadenia560TpmsRear,
    TopicBadenia560TyreSurfaceTempFront,
    TopicBadenia560TyreSurfaceTempRear,
    TopicKistlerCorrevit,
    TopicStateEstimation,
    TopicWheelsSpeed01,
)
from telemetry.systems.engine.laps import resolve_lap

DEFAULT_POINTS = 900
MIN_POINTS = 100
MAX_POINTS = 5000
THERMAL_TOLERANCE_NS = 5_000_000_000


@dataclass(frozen=True)
class SelectionWindow:
    race_id: str
    lap_id: str | None
    lap_number: int | None
    start_ns: int | None
    end_ns: int | None


def resolve_selection_window(
    *,
    lap_id: str | None,
    race_id: str,
    lap_number: int | None,
) -> SelectionWindow:
    if lap_id or lap_number is not None:
        lap = resolve_lap(
            lap_id=lap_id,
            race_id=None if lap_id else race_id,
            lap_number=lap_number,
        )
        return SelectionWindow(
            race_id=lap.race_id,
            lap_id=lap.lap_id,
            lap_number=lap.lap_number,
            start_ns=lap.start_ns,
            end_ns=lap.end_ns,
        )

    return SelectionWindow(
        race_id=race_id,
        lap_id=None,
        lap_number=None,
        start_ns=None,
        end_ns=None,
    )


def validate_points(points: int) -> int:
    if points < MIN_POINTS or points > MAX_POINTS:
        raise ValueError(
            f"Invalid points value {points}. Expected an integer between {MIN_POINTS} and {MAX_POINTS}."
        )
    return points


def selection_payload(window: SelectionWindow) -> dict:
    return {
        "raceId": window.race_id,
        "lapId": window.lap_id,
        "lapNumber": window.lap_number,
        "startNs": window.start_ns,
        "endNs": window.end_ns,
    }


def _apply_window(queryset, window: SelectionWindow):
    queryset = queryset.filter(record__race_id=window.race_id)
    if window.start_ns is not None:
        queryset = queryset.filter(record__ts_ns__gte=window.start_ns)
    if window.end_ns is not None:
        queryset = queryset.filter(record__ts_ns__lte=window.end_ns)
    return queryset


def _mean(values: Iterable[float | None]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _downsample_records(records: list[dict], points: int) -> tuple[list[dict], int]:
    total = len(records)
    if total == 0:
        return [], 1

    sample_step = max(1, ceil(total / points))
    sampled = records[::sample_step]
    if sampled[-1]["t"] != records[-1]["t"]:
        sampled.append(records[-1])
    return sampled, sample_step


def _rounded(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _normalize_row(ts_ns: int, data: dict[str, float | int | None]) -> dict:
    row = {"t": int(ts_ns)}
    for key, value in data.items():
        if isinstance(value, float):
            row[key] = _rounded(value)
        else:
            row[key] = value
    return row


def _lookup_latest(rows: list[dict], base_ts_ns: list[int], *, tolerance_ns: int | None = None) -> list[dict[str, float | int | None]]:
    if not base_ts_ns:
        return []

    results: list[dict[str, float | int | None]] = []
    current: dict[str, float | int | None] | None = None
    row_index = 0

    for ts_ns in base_ts_ns:
        while row_index < len(rows) and int(rows[row_index]["t"]) <= ts_ns:
            current = rows[row_index]
            row_index += 1

        if current is None:
            results.append({})
            continue

        if tolerance_ns is not None and ts_ns - int(current["t"]) > tolerance_ns:
            results.append({})
            continue

        results.append({key: value for key, value in current.items() if key != "t" and value is not None})

    return results


def get_wheel_speed_dataset(window: SelectionWindow, points: int) -> dict:
    wheel_rows = list(
        _apply_window(TopicWheelsSpeed01.objects, window)
        .order_by("record__ts_ns")
        .values_list(
            "record__ts_ns",
            "wss_speed_fl_rad_s",
            "wss_speed_fr_rad_s",
            "wss_speed_rl_rad_s",
            "wss_speed_rr_rad_s",
        )
    )

    kistler_rows = list(
        _apply_window(TopicKistlerCorrevit.objects, window)
        .order_by("record__ts_ns")
        .values_list("record__ts_ns", "vel_cor")
    )

    kistler_by_ts = _lookup_latest(
        [_normalize_row(ts_ns, {"ground_speed_mps": vel_cor}) for ts_ns, vel_cor in kistler_rows],
        [int(row[0]) for row in wheel_rows],
    )

    samples = []
    for index, row in enumerate(wheel_rows):
        ts_ns, speed_fl, speed_fr, speed_rl, speed_rr = row
        sample = {
            "wheel_speed_fl": speed_fl,
            "wheel_speed_fr": speed_fr,
            "wheel_speed_rl": speed_rl,
            "wheel_speed_rr": speed_rr,
        }
        sample.update(kistler_by_ts[index])
        samples.append(_normalize_row(int(ts_ns), sample))

    sampled, sample_step = _downsample_records(samples, points)
    return {
        "selection": selection_payload(window),
        "series": sampled,
        "pointCount": len(samples),
        "returnedPointCount": len(sampled),
        "sampleStep": sample_step,
        "sourceTopics": [
            "/constructor0/can/wheels_speed_01",
            "/constructor0/can/kistler_correvit",
        ],
    }


def get_braking_slip_dataset(window: SelectionWindow, points: int) -> dict:
    rows = list(
        _apply_window(TopicStateEstimation.objects, window)
        .order_by("record__ts_ns")
        .values_list(
            "record__ts_ns",
            "lambda_fl_perc",
            "lambda_fr_perc",
            "lambda_rl_perc",
            "lambda_rr_perc",
            "cba_actual_pressure_fl_pa",
            "cba_actual_pressure_fr_pa",
            "cba_actual_pressure_rl_pa",
            "cba_actual_pressure_rr_pa",
        )
    )

    samples = [
        _normalize_row(
            int(ts_ns),
            {
                "slip_ratio_fl": slip_fl,
                "slip_ratio_fr": slip_fr,
                "slip_ratio_rl": slip_rl,
                "slip_ratio_rr": slip_rr,
                "brake_pressure_fl": pressure_fl,
                "brake_pressure_fr": pressure_fr,
                "brake_pressure_rl": pressure_rl,
                "brake_pressure_rr": pressure_rr,
            },
        )
        for (
            ts_ns,
            slip_fl,
            slip_fr,
            slip_rl,
            slip_rr,
            pressure_fl,
            pressure_fr,
            pressure_rl,
            pressure_rr,
        ) in rows
    ]

    sampled, sample_step = _downsample_records(samples, points)
    return {
        "selection": selection_payload(window),
        "series": sampled,
        "pointCount": len(samples),
        "returnedPointCount": len(sampled),
        "sampleStep": sample_step,
        "sourceTopics": [
            "/constructor0/state_estimation",
            "/constructor0/can/cba_status_fl",
            "/constructor0/can/cba_status_fr",
            "/constructor0/can/cba_status_rl",
            "/constructor0/can/cba_status_rr",
        ],
    }


def get_tyre_temperature_dataset(window: SelectionWindow, points: int) -> dict:
    front_surface_rows = list(
        _apply_window(TopicBadenia560TyreSurfaceTempFront.objects, window)
        .order_by("record__ts_ns")
        .values_list(
            "record__ts_ns",
            "inner_fl",
            "center_fl",
            "outer_fl",
            "inner_fr",
            "center_fr",
            "outer_fr",
        )
    )
    rear_surface_rows = list(
        _apply_window(TopicBadenia560TyreSurfaceTempRear.objects, window)
        .order_by("record__ts_ns")
        .values_list(
            "record__ts_ns",
            "inner_rl",
            "center_rl",
            "outer_rl",
            "inner_rr",
            "center_rr",
            "outer_rr",
        )
    )
    tpms_front_rows = list(
        _apply_window(TopicBadenia560TpmsFront.objects, window)
        .order_by("record__ts_ns")
        .values_list("record__ts_ns", "tpr4_temp_fl", "tpr4_temp_fr")
    )
    tpms_rear_rows = list(
        _apply_window(TopicBadenia560TpmsRear.objects, window)
        .order_by("record__ts_ns")
        .values_list("record__ts_ns", "tpr4_temp_rl", "tpr4_temp_rr")
    )

    timeline = sorted(
        {
            int(ts_ns)
            for ts_ns, *_ in front_surface_rows
        }
        | {
            int(ts_ns)
            for ts_ns, *_ in rear_surface_rows
        }
    )

    front_surface_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "tyre_temp_fl": _mean([inner_fl, center_fl, outer_fl]),
                    "tyre_temp_fr": _mean([inner_fr, center_fr, outer_fr]),
                },
            )
            for ts_ns, inner_fl, center_fl, outer_fl, inner_fr, center_fr, outer_fr in front_surface_rows
        ],
        timeline,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )
    rear_surface_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "tyre_temp_rl": _mean([inner_rl, center_rl, outer_rl]),
                    "tyre_temp_rr": _mean([inner_rr, center_rr, outer_rr]),
                },
            )
            for ts_ns, inner_rl, center_rl, outer_rl, inner_rr, center_rr, outer_rr in rear_surface_rows
        ],
        timeline,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )
    tpms_front_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "tpms_temp_fl": temp_fl,
                    "tpms_temp_fr": temp_fr,
                },
            )
            for ts_ns, temp_fl, temp_fr in tpms_front_rows
        ],
        timeline,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )
    tpms_rear_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "tpms_temp_rl": temp_rl,
                    "tpms_temp_rr": temp_rr,
                },
            )
            for ts_ns, temp_rl, temp_rr in tpms_rear_rows
        ],
        timeline,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )

    samples = []
    for index, ts_ns in enumerate(timeline):
        sample = {}
        sample.update(front_surface_lookup[index])
        sample.update(rear_surface_lookup[index])
        sample.update(tpms_front_lookup[index])
        sample.update(tpms_rear_lookup[index])
        samples.append(_normalize_row(ts_ns, sample))

    sampled, sample_step = _downsample_records(samples, points)
    return {
        "selection": selection_payload(window),
        "series": sampled,
        "pointCount": len(samples),
        "returnedPointCount": len(sampled),
        "sampleStep": sample_step,
        "sourceTopics": [
            "/constructor0/can/badenia_560_tyre_surface_temp_front",
            "/constructor0/can/badenia_560_tyre_surface_temp_rear",
            "/constructor0/can/badenia_560_tpms_front",
            "/constructor0/can/badenia_560_tpms_rear",
        ],
        "derivation": {
            "tyre_temp_fl": "mean(inner_fl, center_fl, outer_fl)",
            "tyre_temp_fr": "mean(inner_fr, center_fr, outer_fr)",
            "tyre_temp_rl": "mean(inner_rl, center_rl, outer_rl)",
            "tyre_temp_rr": "mean(inner_rr, center_rr, outer_rr)",
        },
    }


def get_brake_temperature_dataset(window: SelectionWindow, points: int) -> dict:
    front_rows = list(
        _apply_window(TopicBadenia560TpmsFront.objects, window)
        .order_by("record__ts_ns")
        .values_list("record__ts_ns", "tpr4_temp_fl", "tpr4_temp_fr")
    )
    rear_rows = list(
        _apply_window(TopicBadenia560TpmsRear.objects, window)
        .order_by("record__ts_ns")
        .values_list("record__ts_ns", "tpr4_temp_rl", "tpr4_temp_rr")
    )

    timeline = sorted({int(ts_ns) for ts_ns, *_ in front_rows} | {int(ts_ns) for ts_ns, *_ in rear_rows})
    front_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "brake_temp_fl": temp_fl,
                    "brake_temp_fr": temp_fr,
                },
            )
            for ts_ns, temp_fl, temp_fr in front_rows
        ],
        timeline,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )
    rear_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "brake_temp_rl": temp_rl,
                    "brake_temp_rr": temp_rr,
                },
            )
            for ts_ns, temp_rl, temp_rr in rear_rows
        ],
        timeline,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )

    samples = []
    for index, ts_ns in enumerate(timeline):
        sample = {}
        sample.update(front_lookup[index])
        sample.update(rear_lookup[index])
        samples.append(_normalize_row(ts_ns, sample))

    sampled, sample_step = _downsample_records(samples, points)
    return {
        "selection": selection_payload(window),
        "series": sampled,
        "pointCount": len(samples),
        "returnedPointCount": len(sampled),
        "sampleStep": sample_step,
        "sourceTopics": [
            "/constructor0/can/badenia_560_tpms_front",
            "/constructor0/can/badenia_560_tpms_rear",
        ],
        "derivation": {
            "brake_temp_fl": "tpr4_temp_fl (TPMS proxy)",
            "brake_temp_fr": "tpr4_temp_fr (TPMS proxy)",
            "brake_temp_rl": "tpr4_temp_rl (TPMS proxy)",
            "brake_temp_rr": "tpr4_temp_rr (TPMS proxy)",
        },
    }


def get_minimal_schema_dataset(window: SelectionWindow, points: int) -> dict:
    state_rows = list(
        _apply_window(TopicStateEstimation.objects, window)
        .order_by("record__ts_ns")
        .values_list(
            "record__ts_ns",
            "lambda_fl_perc",
            "lambda_fr_perc",
            "lambda_rl_perc",
            "lambda_rr_perc",
            "cba_actual_pressure_fl_pa",
            "cba_actual_pressure_fr_pa",
            "cba_actual_pressure_rl_pa",
            "cba_actual_pressure_rr_pa",
            "omega_w_fl",
            "omega_w_fr",
            "omega_w_rl",
            "omega_w_rr",
        )
    )
    base_ts = [int(row[0]) for row in state_rows]

    wheel_speed_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "wheel_speed_fl": speed_fl,
                    "wheel_speed_fr": speed_fr,
                    "wheel_speed_rl": speed_rl,
                    "wheel_speed_rr": speed_rr,
                },
            )
            for ts_ns, speed_fl, speed_fr, speed_rl, speed_rr in _apply_window(
                TopicWheelsSpeed01.objects,
                window,
            )
            .order_by("record__ts_ns")
            .values_list(
                "record__ts_ns",
                "wss_speed_fl_rad_s",
                "wss_speed_fr_rad_s",
                "wss_speed_rl_rad_s",
                "wss_speed_rr_rad_s",
            )
        ],
        base_ts,
    )
    tyre_temp_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "tyre_temp_fl": _mean([inner_fl, center_fl, outer_fl]),
                    "tyre_temp_fr": _mean([inner_fr, center_fr, outer_fr]),
                },
            )
            for ts_ns, inner_fl, center_fl, outer_fl, inner_fr, center_fr, outer_fr in _apply_window(
                TopicBadenia560TyreSurfaceTempFront.objects,
                window,
            )
            .order_by("record__ts_ns")
            .values_list(
                "record__ts_ns",
                "inner_fl",
                "center_fl",
                "outer_fl",
                "inner_fr",
                "center_fr",
                "outer_fr",
            )
        ],
        base_ts,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )
    tyre_temp_rear_lookup = _lookup_latest(
        [
            _normalize_row(
                int(ts_ns),
                {
                    "tyre_temp_rl": _mean([inner_rl, center_rl, outer_rl]),
                    "tyre_temp_rr": _mean([inner_rr, center_rr, outer_rr]),
                },
            )
            for ts_ns, inner_rl, center_rl, outer_rl, inner_rr, center_rr, outer_rr in _apply_window(
                TopicBadenia560TyreSurfaceTempRear.objects,
                window,
            )
            .order_by("record__ts_ns")
            .values_list(
                "record__ts_ns",
                "inner_rl",
                "center_rl",
                "outer_rl",
                "inner_rr",
                "center_rr",
                "outer_rr",
            )
        ],
        base_ts,
        tolerance_ns=THERMAL_TOLERANCE_NS,
    )
    samples = []
    for index, row in enumerate(state_rows):
        (
            ts_ns,
            slip_fl,
            slip_fr,
            slip_rl,
            slip_rr,
            pressure_fl,
            pressure_fr,
            pressure_rl,
            pressure_rr,
            omega_fl,
            omega_fr,
            omega_rl,
            omega_rr,
        ) = row
        sample = {
            "wheel_speed_fl": omega_fl,
            "wheel_speed_fr": omega_fr,
            "wheel_speed_rl": omega_rl,
            "wheel_speed_rr": omega_rr,
            "slip_ratio_fl": slip_fl,
            "slip_ratio_fr": slip_fr,
            "slip_ratio_rl": slip_rl,
            "slip_ratio_rr": slip_rr,
            "brake_pressure_fl": pressure_fl,
            "brake_pressure_fr": pressure_fr,
            "brake_pressure_rl": pressure_rl,
            "brake_pressure_rr": pressure_rr,
        }
        sample.update(wheel_speed_lookup[index])
        sample.update(tyre_temp_lookup[index])
        sample.update(tyre_temp_rear_lookup[index])
        samples.append(_normalize_row(int(ts_ns), sample))

    sampled, sample_step = _downsample_records(samples, points)
    return {
        "selection": selection_payload(window),
        "series": sampled,
        "pointCount": len(samples),
        "returnedPointCount": len(sampled),
        "sampleStep": sample_step,
        "schema": [
            "t",
            "wheel_speed_fl",
            "wheel_speed_fr",
            "wheel_speed_rl",
            "wheel_speed_rr",
            "slip_ratio_fl",
            "slip_ratio_fr",
            "slip_ratio_rl",
            "slip_ratio_rr",
            "brake_pressure_fl",
            "brake_pressure_fr",
            "brake_pressure_rl",
            "brake_pressure_rr",
            "tyre_temp_fl",
            "tyre_temp_fr",
            "tyre_temp_rl",
            "tyre_temp_rr",
        ],
        "notes": [
            "Base timeline is /constructor0/state_estimation timestamps.",
            "wheel_speed_* prefers /constructor0/can/wheels_speed_01 and falls back to state_estimation omega_w_* when no newer CAN sample exists.",
            "tyre_temp_* is derived as the mean of inner/center/outer tyre surface channels.",
            "tyre_temp_* uses latest-sample carry-forward within a 5 s tolerance.",
        ],
    }