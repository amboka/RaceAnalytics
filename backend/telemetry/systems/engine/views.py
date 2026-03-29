from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from .comparison import DEFAULT_POINTS, compute_throttle_comparison
from .laps import detect_laps_for_race, get_best_lap_for_race, resolve_lap


def _parse_optional_int(raw_value: str | None, *, field_name: str) -> int | None:
    if raw_value is None or raw_value == "":
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name} value '{raw_value}'. Expected an integer.") from exc


@require_GET
def get_engine_laps(request: HttpRequest) -> JsonResponse:
    race_id = (request.GET.get("race_id") or "").strip()
    if not race_id:
        return JsonResponse(
            {"error": "Missing required query parameter 'race_id'."},
            status=400,
        )

    try:
        laps = detect_laps_for_race(race_id)
        best_lap = get_best_lap_for_race(race_id)
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to list engine laps.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(
        {
            "raceId": race_id,
            "lapCount": len(laps),
            "bestLapId": best_lap.lap_id,
            "laps": [
                {
                    "lapId": lap.lap_id,
                    "lapNumber": lap.lap_number,
                    "startNs": lap.start_ns,
                    "endNs": lap.end_ns,
                    "durationNs": lap.duration_ns,
                    "sampleCount": lap.sample_count,
                    "pathLengthM": lap.path_length_m,
                    "isComplete": lap.is_complete,
                    "quality": lap.quality,
                    "isBestLap": lap.lap_id == best_lap.lap_id,
                }
                for lap in laps
            ],
        }
    )


@require_GET
def get_throttle_comparison(request: HttpRequest) -> JsonResponse:
    lap_id = (request.GET.get("lap_id") or "").strip() or None
    reference_lap_id = (request.GET.get("reference_lap_id") or "").strip() or None
    race_id = (request.GET.get("race_id") or "slow").strip()
    reference_race_id = (request.GET.get("reference_race_id") or "fast").strip()

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
        payload = compute_throttle_comparison(
            lap=lap,
            reference_lap=reference_lap,
            points=points,
        )
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute engine throttle comparison.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)
