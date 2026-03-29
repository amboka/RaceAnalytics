from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from telemetry.systems.engine.laps import resolve_lap

from .comparison import DEFAULT_POINTS, compute_brake_pressure_comparison
from .trail_braking import compute_trail_braking_analysis
from .transition import compute_brake_release_throttle_transition
from .temperature import (
    DEFAULT_POINTS as DEFAULT_TEMPERATURE_POINTS,
    DEFAULT_ZONE_COUNT,
    compute_brake_temperature_comparison,
)


def _parse_optional_int(raw_value: str | None, *, field_name: str) -> int | None:
    if raw_value is None or raw_value == "":
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name} value '{raw_value}'. Expected an integer.") from exc


@require_GET
def get_brake_pressure_comparison(request: HttpRequest) -> JsonResponse:
    lap_id = (request.GET.get("lap_id") or "").strip() or None
    reference_lap_id = (request.GET.get("reference_lap_id") or "").strip() or None
    race_id = (request.GET.get("race_id") or "slow").strip()
    reference_race_id = (request.GET.get("reference_race_id") or "fast").strip()
    pressure_mode = (request.GET.get("pressure_mode") or "combined").strip()

    try:
        lap_number = _parse_optional_int(request.GET.get("lap_number"), field_name="lap_number")
        reference_lap_number = _parse_optional_int(
            request.GET.get("reference_lap_number"),
            field_name="reference_lap_number",
        )
        points = _parse_optional_int(request.GET.get("points"), field_name="points") or DEFAULT_POINTS

        lap = resolve_lap(
            lap_id=lap_id,
            race_id=None if lap_id else race_id,
            lap_number=lap_number,
        )
        reference_lap = resolve_lap(
            lap_id=reference_lap_id,
            race_id=None if reference_lap_id else reference_race_id,
            lap_number=reference_lap_number,
        )
        payload = compute_brake_pressure_comparison(
            lap=lap,
            reference_lap=reference_lap,
            points=points,
            pressure_mode=pressure_mode,
        )
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute brake pressure comparison.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_brake_temperature_comparison(request: HttpRequest) -> JsonResponse:
    lap_id = (request.GET.get("lap_id") or "").strip() or None
    race_id = (request.GET.get("race_id") or "slow").strip()

    reference_lap_id = (request.GET.get("reference_lap_id") or "").strip() or None
    reference_race_id = (request.GET.get("reference_race_id") or "fast").strip()

    try:
        lap_number = _parse_optional_int(request.GET.get("lap_number"), field_name="lap_number")
        reference_lap_number = _parse_optional_int(
            request.GET.get("reference_lap_number"),
            field_name="reference_lap_number",
        )
        points = _parse_optional_int(request.GET.get("points"), field_name="points") or DEFAULT_TEMPERATURE_POINTS
        zone_count = _parse_optional_int(request.GET.get("zone_count"), field_name="zone_count") or DEFAULT_ZONE_COUNT

        lap = resolve_lap(
            lap_id=lap_id,
            race_id=None if lap_id else race_id,
            lap_number=lap_number,
        )

        reference_lap = resolve_lap(
            lap_id=reference_lap_id,
            race_id=None if reference_lap_id else reference_race_id,
            lap_number=reference_lap_number,
        )

        payload = compute_brake_temperature_comparison(
            lap=lap,
            reference_lap=reference_lap,
            points=points,
            zone_count=zone_count,
        )
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute brake temperature comparison.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_trail_braking_analysis(request: HttpRequest) -> JsonResponse:
    lap_id = (request.GET.get("lap_id") or "").strip() or None
    reference_lap_id = (request.GET.get("reference_lap_id") or "").strip() or None
    race_id = (request.GET.get("race_id") or "slow").strip()
    reference_race_id = (request.GET.get("reference_race_id") or "fast").strip()
    pressure_mode = (request.GET.get("pressure_mode") or "combined").strip()

    try:
        lap_number = _parse_optional_int(request.GET.get("lap_number"), field_name="lap_number")
        reference_lap_number = _parse_optional_int(
            request.GET.get("reference_lap_number"),
            field_name="reference_lap_number",
        )
        detailed_zone_id = _parse_optional_int(request.GET.get("zone_id"), field_name="zone_id")

        lap = resolve_lap(
            lap_id=lap_id,
            race_id=None if lap_id else race_id,
            lap_number=lap_number,
        )
        reference_lap = resolve_lap(
            lap_id=reference_lap_id,
            race_id=None if reference_lap_id else reference_race_id,
            lap_number=reference_lap_number,
        )

        payload = compute_trail_braking_analysis(
            lap=lap,
            reference_lap=reference_lap,
            pressure_mode=pressure_mode,
            detailed_zone_id=detailed_zone_id,
        )
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute trail braking analysis.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_brake_release_throttle_transition(request: HttpRequest) -> JsonResponse:
    lap_id = (request.GET.get("lap_id") or "").strip() or None
    reference_lap_id = (request.GET.get("reference_lap_id") or "").strip() or None
    race_id = (request.GET.get("race_id") or "slow").strip()
    reference_race_id = (request.GET.get("reference_race_id") or "fast").strip()
    pressure_mode = (request.GET.get("pressure_mode") or "combined").strip()

    try:
        lap_number = _parse_optional_int(request.GET.get("lap_number"), field_name="lap_number")
        reference_lap_number = _parse_optional_int(
            request.GET.get("reference_lap_number"),
            field_name="reference_lap_number",
        )
        zone_id = _parse_optional_int(request.GET.get("zone_id"), field_name="zone_id")
        trace_points = _parse_optional_int(request.GET.get("trace_points"), field_name="trace_points")

        lap = resolve_lap(
            lap_id=lap_id,
            race_id=None if lap_id else race_id,
            lap_number=lap_number,
        )
        reference_lap = resolve_lap(
            lap_id=reference_lap_id,
            race_id=None if reference_lap_id else reference_race_id,
            lap_number=reference_lap_number,
        )

        payload = compute_brake_release_throttle_transition(
            lap=lap,
            reference_lap=reference_lap,
            pressure_mode=pressure_mode,
            zone_id=zone_id,
            trace_points=141 if trace_points is None else trace_points,
        )
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute brake-release to throttle transition analysis.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)
