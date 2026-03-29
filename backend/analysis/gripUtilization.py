from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from analysis.lapTime import _bootstrap_django, _hardcoded_part_metrics

SECTION_ORDER = ("snake", "long", "corner")
ACTIVE_LATERAL_ACCEL_THRESHOLD_MPS2 = 4.0
ACTIVE_SPEED_THRESHOLD_MPS = 15.0
MIN_ACTIVE_SAMPLE_COUNT = 2
MIN_ACTIVE_DURATION_NS = 500_000_000


@dataclass(frozen=True)
class GripSample:
    ts_ns: int
    abs_lateral_accel_mps2: float
    speed_mps: float
    mean_abs_slip_angle_rad: float
    mean_abs_slip_ratio_perc: float


@dataclass(frozen=True)
class GripSectionMetrics:
    section: str
    active_start_ns: int
    active_end_ns: int
    active_sample_count: int
    active_duration_ns: int
    mean_abs_lateral_accel_mps2: float
    peak_abs_lateral_accel_mps2: float
    mean_speed_mps: float
    mean_abs_slip_angle_rad: float
    peak_abs_slip_angle_rad: float
    mean_abs_slip_ratio_perc: float
    peak_abs_slip_ratio_perc: float
    cornering_load_index: float


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


def _safe_ratio(actual: float, reference: float, *, default: float = 1.0) -> float:
    if abs(reference) <= 1e-9:
        return default
    return actual / reference


def _load_section_samples(race_id: str, start_ns: int, end_ns: int) -> list[GripSample]:
    from telemetry.models import TopicStateEstimation

    rows = TopicStateEstimation.objects.filter(
        record__race_id=race_id,
        record__ts_ns__gte=start_ns,
        record__ts_ns__lt=end_ns,
    ).order_by("record__ts_ns").values_list(
        "record__ts_ns",
        "ay_mps2",
        "v_mps",
        "alpha_fl_rad",
        "alpha_fr_rad",
        "alpha_rl_rad",
        "alpha_rr_rad",
        "lambda_fl_perc",
        "lambda_fr_perc",
        "lambda_rl_perc",
        "lambda_rr_perc",
    )

    samples: list[GripSample] = []
    for row in rows:
        ay_mps2 = row[1]
        speed_mps = row[2]
        if ay_mps2 is None or speed_mps is None:
            continue

        mean_abs_slip_angle_rad = sum(abs(value or 0.0) for value in row[3:7]) / 4.0
        mean_abs_slip_ratio_perc = sum(abs(value or 0.0) for value in row[7:11]) / 4.0
        samples.append(
            GripSample(
                ts_ns=int(row[0]),
                abs_lateral_accel_mps2=abs(float(ay_mps2)),
                speed_mps=float(speed_mps),
                mean_abs_slip_angle_rad=mean_abs_slip_angle_rad,
                mean_abs_slip_ratio_perc=mean_abs_slip_ratio_perc,
            )
        )
    return samples


def _is_cornering_sample(sample: GripSample) -> bool:
    return (
        sample.abs_lateral_accel_mps2 >= ACTIVE_LATERAL_ACCEL_THRESHOLD_MPS2
        and sample.speed_mps >= ACTIVE_SPEED_THRESHOLD_MPS
    )


def _compute_section_metrics(section: str, samples: list[GripSample]) -> GripSectionMetrics | None:
    active_samples = [sample for sample in samples if _is_cornering_sample(sample)]
    if len(active_samples) < MIN_ACTIVE_SAMPLE_COUNT:
        return None

    active_duration_ns = active_samples[-1].ts_ns - active_samples[0].ts_ns
    if active_duration_ns < MIN_ACTIVE_DURATION_NS:
        return None

    mean_abs_lateral_accel_mps2 = sum(sample.abs_lateral_accel_mps2 for sample in active_samples) / len(active_samples)
    peak_abs_lateral_accel_mps2 = max(sample.abs_lateral_accel_mps2 for sample in active_samples)
    mean_speed_mps = sum(sample.speed_mps for sample in active_samples) / len(active_samples)
    mean_abs_slip_angle_rad = sum(sample.mean_abs_slip_angle_rad for sample in active_samples) / len(active_samples)
    peak_abs_slip_angle_rad = max(sample.mean_abs_slip_angle_rad for sample in active_samples)
    mean_abs_slip_ratio_perc = sum(sample.mean_abs_slip_ratio_perc for sample in active_samples) / len(active_samples)
    peak_abs_slip_ratio_perc = max(sample.mean_abs_slip_ratio_perc for sample in active_samples)
    active_duration_seconds = active_duration_ns / 1_000_000_000
    cornering_load_index = mean_abs_lateral_accel_mps2 * active_duration_seconds

    return GripSectionMetrics(
        section=section,
        active_start_ns=active_samples[0].ts_ns,
        active_end_ns=active_samples[-1].ts_ns,
        active_sample_count=len(active_samples),
        active_duration_ns=active_duration_ns,
        mean_abs_lateral_accel_mps2=mean_abs_lateral_accel_mps2,
        peak_abs_lateral_accel_mps2=peak_abs_lateral_accel_mps2,
        mean_speed_mps=mean_speed_mps,
        mean_abs_slip_angle_rad=mean_abs_slip_angle_rad,
        peak_abs_slip_angle_rad=peak_abs_slip_angle_rad,
        mean_abs_slip_ratio_perc=mean_abs_slip_ratio_perc,
        peak_abs_slip_ratio_perc=peak_abs_slip_ratio_perc,
        cornering_load_index=cornering_load_index,
    )


def _metrics_payload(metrics: GripSectionMetrics | None) -> dict | None:
    if metrics is None:
        return None

    return {
        "active_start": {
            "value": metrics.active_start_ns,
            "seconds": _safe_seconds(metrics.active_start_ns),
        },
        "active_end": {
            "value": metrics.active_end_ns,
            "seconds": _safe_seconds(metrics.active_end_ns),
        },
        "active_sample_count": metrics.active_sample_count,
        "active_duration": {
            "value": metrics.active_duration_ns,
            "unit": "ns",
            "seconds": _safe_seconds(metrics.active_duration_ns),
        },
        "mean_abs_lateral_accel_mps2": _rounded(metrics.mean_abs_lateral_accel_mps2),
        "peak_abs_lateral_accel_mps2": _rounded(metrics.peak_abs_lateral_accel_mps2),
        "mean_speed_mps": _rounded(metrics.mean_speed_mps),
        "mean_abs_slip_angle_rad": _rounded(metrics.mean_abs_slip_angle_rad, 4),
        "peak_abs_slip_angle_rad": _rounded(metrics.peak_abs_slip_angle_rad, 4),
        "mean_abs_slip_ratio_perc": _rounded(metrics.mean_abs_slip_ratio_perc, 3),
        "peak_abs_slip_ratio_perc": _rounded(metrics.peak_abs_slip_ratio_perc, 3),
    }


def _section_status(load_ratio: float, slip_angle_ratio: float, combined_slip_ratio: float) -> str:
    if load_ratio < 0.92 and slip_angle_ratio < 0.95 and combined_slip_ratio <= 1.10:
        return "underutilizing_grip"
    if (slip_angle_ratio > 1.05 or combined_slip_ratio > 1.10) and load_ratio < 0.98:
        return "overdriving"
    return "well_utilized"


def _compare_sections(
    section: str,
    actual: GripSectionMetrics | None,
    reference: GripSectionMetrics | None,
) -> dict:
    if actual is None or reference is None:
        return {
            "section": section,
            "status": "insufficient_data",
            "score": None,
            "weight": 0.0,
            "ratios": None,
            "penalties": None,
            "race": _metrics_payload(actual),
            "reference": _metrics_payload(reference),
        }

    load_ratio = _safe_ratio(
        actual.mean_abs_lateral_accel_mps2,
        reference.mean_abs_lateral_accel_mps2,
    )
    speed_ratio = _safe_ratio(actual.mean_speed_mps, reference.mean_speed_mps)
    slip_angle_ratio = _safe_ratio(actual.mean_abs_slip_angle_rad, reference.mean_abs_slip_angle_rad)
    combined_slip_ratio = _safe_ratio(actual.mean_abs_slip_ratio_perc, reference.mean_abs_slip_ratio_perc)

    cornering_load_penalty = max(0.0, 1.0 - load_ratio)
    corner_speed_penalty = max(0.0, 1.0 - speed_ratio)
    balance_penalty = abs(load_ratio - slip_angle_ratio)
    combined_slip_penalty = max(0.0, combined_slip_ratio - 1.0)

    score = _clip_score(
        100.0
        * (
            1.0
            - 0.55 * cornering_load_penalty
            - 0.20 * corner_speed_penalty
            - 0.15 * balance_penalty
            - 0.10 * combined_slip_penalty
        )
    )

    return {
        "section": section,
        "status": _section_status(load_ratio, slip_angle_ratio, combined_slip_ratio),
        "score": _rounded(score),
        "weight": reference.cornering_load_index,
        "ratios": {
            "cornering_load": _rounded(load_ratio, 4),
            "corner_speed": _rounded(speed_ratio, 4),
            "slip_angle": _rounded(slip_angle_ratio, 4),
            "combined_slip": _rounded(combined_slip_ratio, 4),
        },
        "penalties": {
            "cornering_load": _rounded(cornering_load_penalty, 4),
            "corner_speed": _rounded(corner_speed_penalty, 4),
            "balance": _rounded(balance_penalty, 4),
            "combined_slip": _rounded(combined_slip_penalty, 4),
        },
        "race": _metrics_payload(actual),
        "reference": _metrics_payload(reference),
    }


def _overall_status(valid_sections: list[dict], weakest_section: dict) -> str:
    counts = Counter(str(section["status"]) for section in valid_sections)
    most_common = counts.most_common()
    if not most_common:
        return "insufficient_data"
    top_count = most_common[0][1]
    leaders = {status for status, count in most_common if count == top_count}
    if len(leaders) == 1:
        return most_common[0][0]
    weakest_status = str(weakest_section["status"])
    if weakest_status in leaders:
        return weakest_status
    return sorted(leaders)[0]


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


def compute_grip_utilization(
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
        status = comparison.get("status")
        
        return {
            "score": score,
            "rating": rating,
            "overallStatus": status,
            "weakestSection": segment,
            "sections": [comparison],
        }

    race_sections = _hardcoded_part_metrics(race_id)
    reference_sections = _hardcoded_part_metrics(reference_race_id)
    if race_sections is None or reference_sections is None:
        raise ValueError("Hardcoded lap sections are required to compute grip utilization.")

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
        raise ValueError("Unable to compute grip utilization from the available telemetry.")

    total_weight = sum(float(section["weight"]) for section in valid_sections)
    if total_weight <= 0:
        overall_score = sum(float(section["score"]) for section in valid_sections) / len(valid_sections)
    else:
        overall_score = sum(
            float(section["score"]) * float(section["weight"])
            for section in valid_sections
        ) / total_weight

    weakest_section = min(valid_sections, key=lambda section: float(section["score"]))
    overall_status = _overall_status(valid_sections, weakest_section)

    for section in sections:
        section.pop("weight", None)

    return {
        "raceId": race_id,
        "referenceRaceId": reference_race_id,
        "score": _rounded(overall_score),
        "rating": _score_label(overall_score),
        "overallStatus": overall_status,
        "sectionCount": len(valid_sections),
        "weakestSection": weakest_section["section"],
        "sections": sections,
    }
