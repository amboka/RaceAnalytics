#!/usr/bin/env python3
"""Compute lap times for slow and fast races.

Output is JSON and includes:
- one selected track part (if provided), or
- full track by default.

Each result section contains:
- slow race time (ns and s)
- fast race time (ns and s)
- difference (slow - fast, in ns and s)
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


HARDCODED_SEGMENT_BOUNDS_NS: dict[str, dict[str, int]] = {
    "fast": {
        "start": 1763219835170378101,
        "snake_end": 1763219863046608279,
        "long_end": 1763219887262000000,
        "corner_end": 1763219900130000000,
    },
    "slow": {
        "start": 1763219627202000000,
        "snake_end": 1763219658762292711,
        "long_end": 1763219684415923036,
        "corner_end": 1763219699245616802,
    },
}


def _bootstrap_django() -> None:
    """Ensure Django settings are discoverable when run as a script."""
    try:
        from django.apps import apps

        if apps.ready:
            return
    except Exception:
        pass

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()


@dataclass
class RaceWindow:
    race_id: str
    db_start_ns: int | None
    db_end_ns: int | None
    used_start_ns: int | None
    used_end_ns: int | None
    record_count: int


def _safe_seconds(ns_value: int | None) -> float | None:
    if ns_value is None:
        return None
    return ns_value / 1_000_000_000


def _load_line_part_resolver():
    """Load optional get_line_part resolver from analysis.getLinePart."""
    try:
        from analysis.getLinePart import get_line_part  # type: ignore

        return get_line_part
    except Exception:
        return None


def _fallback_part_for_interval(window_start: int, window_end: int, seg_start: int, seg_end: int) -> str:
    """Fallback part assignment using normalized position in the selected window.

    This keeps the script functional if getLinePart helper is not available.
    """
    total = window_end - window_start
    if total <= 0:
        return "unknown"

    midpoint = (seg_start + seg_end) // 2
    progress = (midpoint - window_start) / total

    if progress < 0.40:
        return "long"
    if progress < 0.70:
        return "snake"
    return "corner"


def _part_for_interval(
    resolver,
    window_start: int,
    window_end: int,
    seg_start: int,
    seg_end: int,
) -> str:
    """Resolve track part for [seg_start, seg_end)."""
    if resolver is None:
        return _fallback_part_for_interval(window_start, window_end, seg_start, seg_end)

    try:
        signature = inspect.signature(resolver)
        param_count = len(signature.parameters)

        if param_count >= 2:
            value = resolver(seg_start, seg_end)
        elif param_count == 1:
            value = resolver((seg_start + seg_end) // 2)
        else:
            value = resolver()

        if value is None:
            return "unknown"
        return str(value)
    except Exception:
        return _fallback_part_for_interval(window_start, window_end, seg_start, seg_end)


def _get_race_window(race_id: str) -> RaceWindow:
    from django.db.models import Max, Min
    from telemetry.models import TelemetryIdentity

    qs = TelemetryIdentity.objects.filter(race_id=race_id)
    agg = qs.aggregate(db_start_ns=Min("ts_ns"), db_end_ns=Max("ts_ns"))

    db_start_ns = agg["db_start_ns"]
    db_end_ns = agg["db_end_ns"]

    used_start_ns = db_start_ns
    used_end_ns = db_end_ns

    record_count = qs.count()
    return RaceWindow(
        race_id=race_id,
        db_start_ns=db_start_ns,
        db_end_ns=db_end_ns,
        used_start_ns=used_start_ns,
        used_end_ns=used_end_ns,
        record_count=record_count,
    )


def _hardcoded_part_metrics(race_id: str) -> dict[str, dict[str, int | None]] | None:
    bounds = HARDCODED_SEGMENT_BOUNDS_NS.get(race_id)
    if bounds is None:
        return None

    start = bounds["start"]
    snake_end = bounds["snake_end"]
    long_end = bounds["long_end"]
    corner_end = bounds["corner_end"]

    if not (start <= snake_end <= long_end <= corner_end):
        raise ValueError(f"Invalid hardcoded bounds for race '{race_id}'")

    return {
        "full": {
            "start_ns": start,
            "end_ns": corner_end,
            "duration_ns": corner_end - start,
        },
        "snake": {
            "start_ns": start,
            "end_ns": snake_end,
            "duration_ns": snake_end - start,
        },
        "long": {
            "start_ns": snake_end,
            "end_ns": long_end,
            "duration_ns": long_end - snake_end,
        },
        "corner": {
            "start_ns": long_end,
            "end_ns": corner_end,
            "duration_ns": corner_end - long_end,
        },
    }


def _compute_part_metrics(race_window: RaceWindow, resolver) -> dict[str, dict[str, int | None]]:
    """Compute start/end/duration by track part for one race.

    Durations are calculated by summing consecutive timestamp deltas whose interval
    belongs to the same part.
    """
    from telemetry.models import TelemetryIdentity

    if race_window.used_start_ns is None or race_window.used_end_ns is None:
        return {
            "full": {
                "start_ns": None,
                "end_ns": None,
                "duration_ns": None,
            }
        }

    if race_window.used_end_ns < race_window.used_start_ns:
        return {
            "full": {
                "start_ns": None,
                "end_ns": None,
                "duration_ns": None,
            }
        }

    timestamps = list(
        TelemetryIdentity.objects.filter(
            race_id=race_window.race_id,
            ts_ns__gte=race_window.used_start_ns,
            ts_ns__lte=race_window.used_end_ns,
        )
        .order_by("ts_ns")
        .values_list("ts_ns", flat=True)
    )

    full_duration = race_window.used_end_ns - race_window.used_start_ns
    metrics: dict[str, dict[str, int | None]] = {
        "full": {
            "start_ns": race_window.used_start_ns,
            "end_ns": race_window.used_end_ns,
            "duration_ns": full_duration,
        }
    }

    if len(timestamps) < 2:
        return metrics

    for idx in range(len(timestamps) - 1):
        seg_start = int(timestamps[idx])
        seg_end = int(timestamps[idx + 1])
        delta = seg_end - seg_start
        if delta <= 0:
            continue

        part = _part_for_interval(
            resolver=resolver,
            window_start=race_window.used_start_ns,
            window_end=race_window.used_end_ns,
            seg_start=seg_start,
            seg_end=seg_end,
        )
        part_metric = metrics.get(part)
        if part_metric is None:
            metrics[part] = {
                "start_ns": seg_start,
                "end_ns": seg_end,
                "duration_ns": delta,
            }
            continue

        prev_start = part_metric.get("start_ns")
        prev_end = part_metric.get("end_ns")
        prev_duration = part_metric.get("duration_ns")

        part_metric["start_ns"] = seg_start if prev_start is None else min(int(prev_start), seg_start)
        part_metric["end_ns"] = seg_end if prev_end is None else max(int(prev_end), seg_end)
        part_metric["duration_ns"] = delta if prev_duration is None else int(prev_duration) + delta

    return metrics


def _race_payload(
    race_window: RaceWindow,
    segment: str,
    segment_metric: dict[str, int | None] | None,
) -> dict:
    duration_ns = None if segment_metric is None else segment_metric.get("duration_ns")
    segment_start_ns = None if segment_metric is None else segment_metric.get("start_ns")
    segment_end_ns = None if segment_metric is None else segment_metric.get("end_ns")
    duration_ms = None if duration_ns is None else duration_ns / 1_000_000
    return {
        "race_id": race_window.race_id,
        "record_count": race_window.record_count,
        "db_timestamp_unit": "ns",
        "db_start": {
            "value": race_window.db_start_ns,
            "seconds": _safe_seconds(race_window.db_start_ns),
        },
        "db_end": {
            "value": race_window.db_end_ns,
            "seconds": _safe_seconds(race_window.db_end_ns),
        },
        "segment": {
            "name": segment,
            "start": {
                "value": segment_start_ns,
                "seconds": _safe_seconds(segment_start_ns),
            },
            "end": {
                "value": segment_end_ns,
                "seconds": _safe_seconds(segment_end_ns),
            },
        },
        "duration": {
            "value": duration_ns,
            "unit": "ns",
            "milliseconds": duration_ms,
            "seconds": _safe_seconds(duration_ns),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute lap times from DB timestamps")
    parser.add_argument(
        "--segment",
        type=str,
        default=None,
        help="Optional segment/track-part name (example: snake, long, corner). Default: full track.",
    )
    return parser


def compute_lap_times(
    segment: str | None = None,
) -> dict:
    """Compute lap time report for slow and fast races.

    Args:
        segment: Optional track part to report. If omitted, only full track is reported.
    Returns:
        The JSON-serializable report payload.
    """
    _bootstrap_django()

    slow_window = _get_race_window("slow")
    fast_window = _get_race_window("fast")

    slow_parts = _hardcoded_part_metrics("slow")
    fast_parts = _hardcoded_part_metrics("fast")

    if slow_parts is None or fast_parts is None:
        resolver = _load_line_part_resolver()
        slow_parts = _compute_part_metrics(slow_window, resolver)
        fast_parts = _compute_part_metrics(fast_window, resolver)

    selected_segment = "full" if segment is None else segment.strip()
    if selected_segment == "":
        selected_segment = "full"

    slow_metric = slow_parts.get(selected_segment)
    fast_metric = fast_parts.get(selected_segment)

    if selected_segment != "full" and slow_metric is None and fast_metric is None:
        raise ValueError(f"Unknown segment '{selected_segment}'")

    slow_ns = None if slow_metric is None else slow_metric.get("duration_ns")
    fast_ns = None if fast_metric is None else fast_metric.get("duration_ns")
    diff_ns = None if slow_ns is None or fast_ns is None else int(slow_ns) - int(fast_ns)

    payload = {
        "header": {
            "segment": selected_segment,
        },
        "slow_race": _race_payload(slow_window, selected_segment, slow_metric),
        "fast_race": _race_payload(fast_window, selected_segment, fast_metric),
        "difference": {
            "slow_minus_fast": {
                "value": diff_ns,
                "unit": "ns",
                "seconds": _safe_seconds(diff_ns),
            }
        },
    }

    return payload


def compute_time_lost_per_section() -> dict[str, int | None]:
    slow_parts = _hardcoded_part_metrics("slow")
    fast_parts = _hardcoded_part_metrics("fast")

    if slow_parts is None or fast_parts is None:
        raise ValueError("Hardcoded section bounds are not available.")

    payload: dict[str, int | None] = {}
    for section in ("snake", "long", "corner"):
        slow_ns = slow_parts[section]["duration_ns"]
        fast_ns = fast_parts[section]["duration_ns"]
        payload[section] = None if slow_ns is None or fast_ns is None else int(slow_ns) - int(fast_ns)

    return payload


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        payload = compute_lap_times(
            segment=args.segment,
        )
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
