from __future__ import annotations

from math import hypot

from telemetry.models import TopicStateEstimation

from .types import DetectedLap, StateSample

MIN_LAP_DURATION_NS = 20_000_000_000
MIN_LAP_DISTANCE_M = 500.0
MIN_LAP_SAMPLES = 50
START_RADIUS_M = 8.0


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def load_race_samples(race_id: str) -> list[StateSample]:
    rows = TopicStateEstimation.objects.filter(
        record__race_id=race_id,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "x_m",
        "y_m",
        "gas",
        "v_mps",
    )

    samples: list[StateSample] = []
    previous_ts: int | None = None
    for row in rows:
        ts_ns = int(row[0])
        x_m = row[1]
        y_m = row[2]
        gas = row[3]
        speed_mps = row[4]

        if x_m is None or y_m is None or gas is None:
            continue
        if previous_ts is not None and ts_ns <= previous_ts:
            continue

        samples.append(
            StateSample(
                ts_ns=ts_ns,
                x_m=float(x_m),
                y_m=float(y_m),
                gas_pct=_clamp_percent(float(gas) * 100.0),
                v_mps=0.0 if speed_mps is None else float(speed_mps),
            )
        )
        previous_ts = ts_ns

    return samples


def load_lap_samples(lap: DetectedLap) -> list[StateSample]:
    rows = TopicStateEstimation.objects.filter(
        record__race_id=lap.race_id,
        record__ts_ns__gte=lap.start_ns,
        record__ts_ns__lte=lap.end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "x_m",
        "y_m",
        "gas",
        "v_mps",
    )

    samples: list[StateSample] = []
    previous_ts: int | None = None
    for row in rows:
        ts_ns = int(row[0])
        x_m = row[1]
        y_m = row[2]
        gas = row[3]
        speed_mps = row[4]

        if x_m is None or y_m is None or gas is None:
            continue
        if previous_ts is not None and ts_ns <= previous_ts:
            continue

        samples.append(
            StateSample(
                ts_ns=ts_ns,
                x_m=float(x_m),
                y_m=float(y_m),
                gas_pct=_clamp_percent(float(gas) * 100.0),
                v_mps=0.0 if speed_mps is None else float(speed_mps),
            )
        )
        previous_ts = ts_ns

    return samples


def _cumulative_distances(samples: list[StateSample]) -> list[float]:
    if not samples:
        return []

    cumulative = [0.0]
    for current, nxt in zip(samples, samples[1:]):
        cumulative.append(cumulative[-1] + hypot(nxt.x_m - current.x_m, nxt.y_m - current.y_m))
    return cumulative


def detect_laps_for_race(race_id: str) -> list[DetectedLap]:
    samples = load_race_samples(race_id)
    if len(samples) < MIN_LAP_SAMPLES:
        return []

    cumulative = _cumulative_distances(samples)
    laps: list[DetectedLap] = []
    start_index = 0
    lap_number = 1

    while start_index + MIN_LAP_SAMPLES < len(samples):
        start_sample = samples[start_index]
        lap_end_index: int | None = None
        search_index = start_index + MIN_LAP_SAMPLES

        while search_index < len(samples):
            candidate = samples[search_index]
            duration_ns = candidate.ts_ns - start_sample.ts_ns
            distance_m = cumulative[search_index] - cumulative[start_index]
            distance_to_start_m = hypot(candidate.x_m - start_sample.x_m, candidate.y_m - start_sample.y_m)

            if (
                duration_ns >= MIN_LAP_DURATION_NS
                and distance_m >= MIN_LAP_DISTANCE_M
                and distance_to_start_m <= START_RADIUS_M
            ):
                best_index = search_index
                best_distance = distance_to_start_m
                run_index = search_index + 1
                while run_index < len(samples):
                    run_candidate = samples[run_index]
                    run_distance = hypot(
                        run_candidate.x_m - start_sample.x_m,
                        run_candidate.y_m - start_sample.y_m,
                    )
                    if run_distance > START_RADIUS_M:
                        break
                    if run_distance <= best_distance:
                        best_index = run_index
                        best_distance = run_distance
                    run_index += 1

                lap_end_index = best_index
                break

            search_index += 1

        if lap_end_index is None:
            break

        duration_ns = samples[lap_end_index].ts_ns - start_sample.ts_ns
        path_length_m = cumulative[lap_end_index] - cumulative[start_index]
        sample_count = lap_end_index - start_index + 1

        laps.append(
            DetectedLap(
                lap_id=f"{race_id}:{lap_number}",
                race_id=race_id,
                lap_number=lap_number,
                start_ns=start_sample.ts_ns,
                end_ns=samples[lap_end_index].ts_ns,
                duration_ns=duration_ns,
                sample_count=sample_count,
                path_length_m=round(path_length_m, 3),
                start_index=start_index,
                end_index=lap_end_index,
                quality="good" if path_length_m >= 1_500.0 else "usable",
            )
        )

        start_index = lap_end_index
        lap_number += 1

    return laps


def get_best_lap_for_race(race_id: str) -> DetectedLap:
    laps = detect_laps_for_race(race_id)
    if not laps:
        raise LookupError(f"No complete laps were detected for race '{race_id}'.")
    return min(laps, key=lambda lap: (lap.duration_ns, lap.lap_number))


def resolve_lap(
    *,
    lap_id: str | None = None,
    race_id: str | None = None,
    lap_number: int | None = None,
) -> DetectedLap:
    if lap_id:
        try:
            resolved_race_id, resolved_lap_number = lap_id.rsplit(":", 1)
            lap_number = int(resolved_lap_number)
        except ValueError as exc:
            raise ValueError(
                "Invalid lap_id format. Expected '<race_id>:<lap_number>'."
            ) from exc
        race_id = resolved_race_id

    if not race_id:
        raise ValueError("Missing lap selection. Provide lap_id or race_id.")

    laps = detect_laps_for_race(race_id)
    if not laps:
        raise LookupError(f"No complete laps were detected for race '{race_id}'.")

    if lap_number is None:
        return min(laps, key=lambda lap: (lap.duration_ns, lap.lap_number))

    for lap in laps:
        if lap.lap_number == lap_number:
            return lap

    raise LookupError(f"Lap {lap_number} was not found for race '{race_id}'.")
