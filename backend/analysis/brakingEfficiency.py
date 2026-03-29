from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from analysis.lapTime import _bootstrap_django, _hardcoded_part_metrics

SECTION_ORDER = ("snake", "long", "corner")
PRESSURE_THRESHOLD_PA = 300_000.0
DECEL_THRESHOLD_MPS2 = -4.0
SPEED_THRESHOLD_MPS = 15.0
MIN_PRESSURE_FOR_DECEL_PA = 50_000.0
MIN_BRAKE_DURATION_NS = 500_000_000
MIN_SPEED_DROP_MPS = 5.0


@dataclass(frozen=True)
class BrakingSample:
    ts_ns: int
    x_m: float | None
    y_m: float | None
    v_mps: float | None
    ax_mps2: float | None
    avg_brake_pressure_pa: float


@dataclass(frozen=True)
class BrakingSectionMetrics:
    section: str
    brake_start_ns: int
    brake_end_ns: int
    active_sample_count: int
    brake_duration_ns: int
    brake_distance_m: float
    entry_speed_mps: float
    min_speed_mps: float
    speed_drop_mps: float
    pressure_impulse_pa_s: float
    pressure_per_speed_drop: float
    peak_decel_mps2: float | None


def _safe_seconds(ns_value: int | None) -> float | None:
    if ns_value is None:
        return None
    return ns_value / 1_000_000_000


def _rounded(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _score_label(score: float) -> str:
    if score >= 95:
        return "excellent"
    if score >= 85:
        return "strong"
    if score >= 70:
        return "fair"
    return "needs_work"


def _clip_score(score: float) -> float:
    return max(0.0, min(100.0, score))


def _load_section_samples(race_id: str, start_ns: int, end_ns: int) -> list[BrakingSample]:
    from telemetry.models import TopicStateEstimation

    rows = TopicStateEstimation.objects.filter(
        record__race_id=race_id,
        record__ts_ns__gte=start_ns,
        record__ts_ns__lt=end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "x_m",
        "y_m",
        "v_mps",
        "ax_mps2",
        "cba_actual_pressure_fl_pa",
        "cba_actual_pressure_fr_pa",
        "cba_actual_pressure_rl_pa",
        "cba_actual_pressure_rr_pa",
    )

    samples: list[BrakingSample] = []
    for row in rows:
        avg_brake_pressure_pa = sum((value or 0.0) for value in row[5:9]) / 4.0
        samples.append(
            BrakingSample(
                ts_ns=int(row[0]),
                x_m=row[1],
                y_m=row[2],
                v_mps=row[3],
                ax_mps2=row[4],
                avg_brake_pressure_pa=avg_brake_pressure_pa,
            )
        )
    return samples


def _is_braking_sample(sample: BrakingSample) -> bool:
    speed = 0.0 if sample.v_mps is None else sample.v_mps
    if speed <= SPEED_THRESHOLD_MPS:
        return False

    if sample.avg_brake_pressure_pa >= PRESSURE_THRESHOLD_PA:
        return True

    if sample.ax_mps2 is None:
        return False

    return (
        sample.ax_mps2 <= DECEL_THRESHOLD_MPS2
        and sample.avg_brake_pressure_pa >= MIN_PRESSURE_FOR_DECEL_PA
    )


def _compute_section_metrics(section: str, samples: list[BrakingSample]) -> BrakingSectionMetrics | None:
    if len(samples) < 2:
        return None

    active_indexes = [index for index, sample in enumerate(samples) if _is_braking_sample(sample)]
    if not active_indexes:
        return None

    first_active = active_indexes[0]
    last_active = active_indexes[-1]
    span_samples = samples[first_active : last_active + 1]

    speeds = [sample.v_mps for sample in span_samples if sample.v_mps is not None]
    if not speeds:
        return None

    brake_duration_ns = 0
    brake_distance_m = 0.0
    pressure_impulse_pa_s = 0.0

    for index in range(len(span_samples) - 1):
        current = span_samples[index]
        next_sample = span_samples[index + 1]
        dt_ns = next_sample.ts_ns - current.ts_ns
        if dt_ns <= 0:
            continue
        if not _is_braking_sample(current):
            continue

        brake_duration_ns += dt_ns
        pressure_impulse_pa_s += current.avg_brake_pressure_pa * (dt_ns / 1_000_000_000)

        if None not in (current.x_m, current.y_m, next_sample.x_m, next_sample.y_m):
            brake_distance_m += hypot(next_sample.x_m - current.x_m, next_sample.y_m - current.y_m)

    entry_speed_mps = span_samples[0].v_mps
    min_speed_mps = min(speeds)
    if entry_speed_mps is None:
        return None

    speed_drop_mps = max(0.0, entry_speed_mps - min_speed_mps)
    if brake_duration_ns < MIN_BRAKE_DURATION_NS or speed_drop_mps < MIN_SPEED_DROP_MPS:
        return None

    negative_accels = [
        -sample.ax_mps2
        for sample in span_samples
        if sample.ax_mps2 is not None and sample.ax_mps2 < 0
    ]
    peak_decel_mps2 = max(negative_accels) if negative_accels else None

    return BrakingSectionMetrics(
        section=section,
        brake_start_ns=span_samples[0].ts_ns,
        brake_end_ns=span_samples[-1].ts_ns,
        active_sample_count=len(active_indexes),
        brake_duration_ns=brake_duration_ns,
        brake_distance_m=brake_distance_m,
        entry_speed_mps=entry_speed_mps,
        min_speed_mps=min_speed_mps,
        speed_drop_mps=speed_drop_mps,
        pressure_impulse_pa_s=pressure_impulse_pa_s,
        pressure_per_speed_drop=pressure_impulse_pa_s / speed_drop_mps,
        peak_decel_mps2=peak_decel_mps2,
    )


def _metrics_payload(metrics: BrakingSectionMetrics | None) -> dict | None:
    if metrics is None:
        return None

    return {
        "brake_start": {
            "value": metrics.brake_start_ns,
            "seconds": _safe_seconds(metrics.brake_start_ns),
        },
        "brake_end": {
            "value": metrics.brake_end_ns,
            "seconds": _safe_seconds(metrics.brake_end_ns),
        },
        "active_sample_count": metrics.active_sample_count,
        "brake_duration": {
            "value": metrics.brake_duration_ns,
            "unit": "ns",
            "seconds": _safe_seconds(metrics.brake_duration_ns),
        },
        "brake_distance_m": _rounded(metrics.brake_distance_m),
        "entry_speed_mps": _rounded(metrics.entry_speed_mps),
        "min_speed_mps": _rounded(metrics.min_speed_mps),
        "speed_drop_mps": _rounded(metrics.speed_drop_mps),
        "pressure_impulse_pa_s": _rounded(metrics.pressure_impulse_pa_s),
        "pressure_per_speed_drop": _rounded(metrics.pressure_per_speed_drop),
        "peak_decel_mps2": _rounded(metrics.peak_decel_mps2),
    }


def _compare_sections(
    section: str,
    actual: BrakingSectionMetrics | None,
    reference: BrakingSectionMetrics | None,
) -> dict:
    if actual is None or reference is None:
        return {
            "section": section,
            "status": "insufficient_data",
            "score": None,
            "weight": 0.0,
            "time_lost": {
                "value": None,
                "unit": "ns",
                "seconds": None,
            },
            "penalties": None,
            "race": _metrics_payload(actual),
            "reference": _metrics_payload(reference),
        }

    distance_penalty = 0.0
    if reference.brake_distance_m > 0:
        distance_penalty = max(0.0, (actual.brake_distance_m - reference.brake_distance_m) / reference.brake_distance_m)

    minimum_speed_penalty = 0.0
    if reference.min_speed_mps > 0:
        minimum_speed_penalty = max(0.0, (reference.min_speed_mps - actual.min_speed_mps) / reference.min_speed_mps)

    effort_penalty = 0.0
    if reference.pressure_per_speed_drop > 0:
        effort_penalty = max(
            0.0,
            (actual.pressure_per_speed_drop - reference.pressure_per_speed_drop)
            / reference.pressure_per_speed_drop,
        )

    score = _clip_score(
        100.0
        * (
            1.0
            - 0.45 * distance_penalty
            - 0.35 * minimum_speed_penalty
            - 0.20 * effort_penalty
        )
    )
    time_lost_ns = max(0, actual.brake_duration_ns - reference.brake_duration_ns)

    return {
        "section": section,
        "status": "ok",
        "score": _rounded(score),
        "weight": reference.speed_drop_mps,
        "time_lost": {
            "value": time_lost_ns,
            "unit": "ns",
            "seconds": _safe_seconds(time_lost_ns),
        },
        "penalties": {
            "distance": _rounded(distance_penalty, 4),
            "minimum_speed": _rounded(minimum_speed_penalty, 4),
            "effort": _rounded(effort_penalty, 4),
        },
        "race": _metrics_payload(actual),
        "reference": _metrics_payload(reference),
    }


def _identify_segment(race_id: str, start_ns: int, end_ns: int) -> str | None:
    """Identify which segment (corner, snake, long) a time window belongs to.
    
    Returns the segment name if a single segment match is found, otherwise None.
    """
    part_metrics = _hardcoded_part_metrics(race_id)
    if part_metrics is None:
        return None
    
    # Check if the window aligns with any segment
    for segment_name in SECTION_ORDER:
        segment_data = part_metrics.get(segment_name)
        if segment_data is None:
            continue
        
        seg_start = segment_data["start_ns"]
        seg_end = segment_data["end_ns"]
        
        # Exact match or close enough (within small tolerance for timing precision)
        tolerance_ns = 1_000_000  # 1ms tolerance
        if (abs(start_ns - seg_start) <= tolerance_ns and 
            abs(end_ns - seg_end) <= tolerance_ns):
            return segment_name
    
    return None


def compute_braking_efficiency(
    race_id: str = "slow",
    reference_race_id: str = "fast",
    start_ns: int | None = None,
    end_ns: int | None = None,
    segment: str | None = None,
) -> dict:
    _bootstrap_django()

    # When custom time range is provided, compute metrics for the segment
    if start_ns is not None and end_ns is not None:
        # Identify the segment if not explicitly provided
        if segment is None:
            segment = _identify_segment(race_id, start_ns, end_ns)
        
        if segment is None:
            segment = "custom"
        
        # Load samples for the time range (race)
        race_samples = _load_section_samples(race_id, start_ns, end_ns)
        race_metrics = _compute_section_metrics(segment, race_samples)
        
        # Load reference metrics using the reference race's segment boundaries
        reference_metrics = None
        if segment != "custom":
            ref_sections = _hardcoded_part_metrics(reference_race_id)
            if ref_sections is not None and segment in ref_sections:
                ref_window = ref_sections[segment]
                reference_samples = _load_section_samples(
                    reference_race_id,
                    int(ref_window["start_ns"]),
                    int(ref_window["end_ns"]),
                )
                reference_metrics = _compute_section_metrics(segment, reference_samples)
        
        # Compute comparison even if one is None
        comparison = _compare_sections(segment, race_metrics, reference_metrics)
        
        # Calculate top-level aggregates
        score = comparison["score"]
        rating = _score_label(score) if score is not None else None
        
        # Extract time lost from comparison
        time_lost_data = comparison.get("time_lost")
        time_lost_ns = time_lost_data["value"] if time_lost_data else None
        
        return {
            "score": score,
            "rating": rating,
            "timeLostUnderBraking": {
                "seconds": _safe_seconds(time_lost_ns)
            } if time_lost_ns is not None else None,
            "weakestSection": segment,
            "sections": [comparison],
        }

    race_sections = _hardcoded_part_metrics(race_id)
    reference_sections = _hardcoded_part_metrics(reference_race_id)
    if race_sections is None or reference_sections is None:
        raise ValueError("Hardcoded lap sections are required to compute braking efficiency.")

    sections: list[dict] = []
    valid_sections: list[dict] = []

    for section in SECTION_ORDER:
        race_window = race_sections.get(section)
        reference_window = reference_sections.get(section)
        if race_window is None or reference_window is None:
            comparison = _compare_sections(section, None, None)
            sections.append(comparison)
            continue

        race_metrics = _compute_section_metrics(
            section,
            _load_section_samples(
                race_id=race_id,
                start_ns=int(race_window["start_ns"]),
                end_ns=int(race_window["end_ns"]),
            ),
        )
        reference_metrics = _compute_section_metrics(
            section,
            _load_section_samples(
                race_id=reference_race_id,
                start_ns=int(reference_window["start_ns"]),
                end_ns=int(reference_window["end_ns"]),
            ),
        )

        comparison = _compare_sections(section, race_metrics, reference_metrics)
        sections.append(comparison)
        if comparison["score"] is not None:
            valid_sections.append(comparison)

    if not valid_sections:
        raise ValueError("Unable to compute braking efficiency from the available telemetry.")

    total_weight = sum(float(section["weight"]) for section in valid_sections)
    if total_weight <= 0:
        overall_score = sum(float(section["score"]) for section in valid_sections) / len(valid_sections)
    else:
        overall_score = sum(
            float(section["score"]) * float(section["weight"])
            for section in valid_sections
        ) / total_weight

    total_time_lost_ns = sum(int(section["time_lost"]["value"]) for section in valid_sections)
    weakest_section = min(valid_sections, key=lambda section: float(section["score"]))

    for section in sections:
        section.pop("weight", None)

    return {
        "raceId": race_id,
        "referenceRaceId": reference_race_id,
        "score": _rounded(overall_score),
        "rating": _score_label(overall_score),
        "timeLostUnderBraking": {
            "value": total_time_lost_ns,
            "unit": "ns",
            "seconds": _safe_seconds(total_time_lost_ns),
        },
        "sectionCount": len(valid_sections),
        "weakestSection": weakest_section["section"],
        "sections": sections,
    }
