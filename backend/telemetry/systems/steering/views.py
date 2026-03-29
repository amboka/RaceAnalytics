from __future__ import annotations

from math import tan

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from telemetry.models import TopicStateEstimation

OUTPUT_SAMPLE_HZ = 5.0
OUTPUT_SAMPLE_PERIOD_NS = int(1_000_000_000 / OUTPUT_SAMPLE_HZ)
DEFAULT_WHEELBASE_M = 2.8
DEFAULT_MIN_SPEED_MPS = 8.0
DEFAULT_MIN_STEERING_RAD = 0.03
DEFAULT_SCORE_THRESHOLD = 0.15
DEFAULT_EMA_ALPHA = 0.25
DEFAULT_MIN_ANALYSIS_SPEED_MPS = 10.0
DEFAULT_MIN_LATERAL_G = 0.20
DEFAULT_TARGET_SLIP_DEG = 6.0
DEFAULT_SLIP_WINDOW_DEG = 2.0
DEFAULT_BALANCE_THRESHOLD_DEG = 1.0


def _downsample_time_series_5hz(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    if not points:
        return []

    sampled: list[tuple[int, float]] = [points[0]]
    next_target_ns = points[0][0] + OUTPUT_SAMPLE_PERIOD_NS

    for ts_ns, value in points[1:]:
        if ts_ns >= next_target_ns:
            sampled.append((ts_ns, value))
            next_target_ns = ts_ns + OUTPUT_SAMPLE_PERIOD_NS

    if sampled[-1][0] != points[-1][0]:
        sampled.append(points[-1])

    return sampled


def _downsample_indices_5hz(ts_ns: list[int]) -> list[int]:
    if not ts_ns:
        return []

    indices = [0]
    next_target_ns = ts_ns[0] + OUTPUT_SAMPLE_PERIOD_NS

    for index in range(1, len(ts_ns)):
        if ts_ns[index] >= next_target_ns:
            indices.append(index)
            next_target_ns = ts_ns[index] + OUTPUT_SAMPLE_PERIOD_NS

    if indices[-1] != len(ts_ns) - 1:
        indices.append(len(ts_ns) - 1)

    return indices


def _select_by_indices(values: list, indices: list[int]) -> list:
    return [values[index] for index in indices]


def _ema(values: list[float], alpha: float) -> list[float]:
    if not values:
        return []

    smoothed = [values[0]]
    for value in values[1:]:
        smoothed.append(alpha * value + (1.0 - alpha) * smoothed[-1])
    return smoothed


def _parse_optional_float(raw_value: str | None, *, default_value: float) -> float:
    if raw_value is None or raw_value == "":
        return default_value
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"Invalid float query value '{raw_value}'.") from exc


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0

    sorted_values = sorted(values)
    q = max(0.0, min(1.0, q))
    position = int(round((len(sorted_values) - 1) * q))
    return sorted_values[position]


@require_GET
def get_steering_angle(request: HttpRequest) -> JsonResponse:
    rows = TopicStateEstimation.objects.exclude(
        delta_wheel_rad__isnull=True,
    ).order_by("record__race_id", "record__ts_ns").values_list(
        "record__race_id",
        "record__ts_ns",
        "delta_wheel_rad",
    )

    race_points: dict[str, list[tuple[int, float]]] = {}
    for race_id, ts_ns, steering_rad in rows.iterator(chunk_size=10_000):
        race_points.setdefault(str(race_id), []).append((int(ts_ns), float(steering_rad)))

    races_payload: list[dict] = []
    for race_id in sorted(race_points):
        sampled = _downsample_time_series_5hz(race_points[race_id])
        ts_ns_values = [point[0] for point in sampled]
        steering_rad_values = [round(point[1], 6) for point in sampled]
        steering_deg_values = [round(point[1] * 57.295779513, 3) for point in sampled]

        races_payload.append(
            {
                "raceId": race_id,
                "sampleCount": len(sampled),
                "series": {
                    "tsNs": ts_ns_values,
                    "steeringAngleRad": steering_rad_values,
                    "steeringAngleDeg": steering_deg_values,
                },
            }
        )

    return JsonResponse(
        {
            "signal": {
                "source": "TopicStateEstimation.delta_wheel_rad",
                "unit": "rad",
                "outputSampleHz": OUTPUT_SAMPLE_HZ,
            },
            "raceCount": len(races_payload),
            "races": races_payload,
        }
    )


@require_GET
def get_over_under_steer(request: HttpRequest) -> JsonResponse:
    try:
        wheelbase_m = _parse_optional_float(
            request.GET.get("wheelbase_m"),
            default_value=DEFAULT_WHEELBASE_M,
        )
        min_speed_mps = _parse_optional_float(
            request.GET.get("min_speed_mps"),
            default_value=DEFAULT_MIN_SPEED_MPS,
        )
        min_steering_rad = _parse_optional_float(
            request.GET.get("min_steering_rad"),
            default_value=DEFAULT_MIN_STEERING_RAD,
        )
        score_threshold = _parse_optional_float(
            request.GET.get("score_threshold"),
            default_value=DEFAULT_SCORE_THRESHOLD,
        )
        ema_alpha = _parse_optional_float(
            request.GET.get("ema_alpha"),
            default_value=DEFAULT_EMA_ALPHA,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if wheelbase_m <= 0.0:
        return JsonResponse({"error": "wheelbase_m must be > 0."}, status=400)
    if min_speed_mps < 0.0 or min_steering_rad < 0.0:
        return JsonResponse({"error": "min_speed_mps and min_steering_rad must be >= 0."}, status=400)
    if score_threshold < 0.0:
        return JsonResponse({"error": "score_threshold must be >= 0."}, status=400)
    if ema_alpha <= 0.0 or ema_alpha > 1.0:
        return JsonResponse({"error": "ema_alpha must be in (0, 1]."}, status=400)

    rows = TopicStateEstimation.objects.exclude(
        delta_wheel_rad__isnull=True,
    ).exclude(
        v_mps__isnull=True,
    ).exclude(
        yaw_vel_rad__isnull=True,
    ).order_by("record__race_id", "record__ts_ns").values_list(
        "record__race_id",
        "record__ts_ns",
        "delta_wheel_rad",
        "v_mps",
        "yaw_vel_rad",
    )

    race_points: dict[str, list[tuple[int, float, float, float]]] = {}
    for race_id, ts_ns, steering_rad, speed_mps, yaw_measured in rows.iterator(chunk_size=10_000):
        race_points.setdefault(str(race_id), []).append(
            (int(ts_ns), float(steering_rad), float(speed_mps), float(yaw_measured))
        )

    races_payload: list[dict] = []
    for race_id in sorted(race_points):
        points = race_points[race_id]
        if not points:
            continue

        ts_ns_values = [point[0] for point in points]
        steering_rad = _ema([point[1] for point in points], ema_alpha)
        speed_mps = _ema([point[2] for point in points], ema_alpha)
        yaw_measured_radps = _ema([point[3] for point in points], ema_alpha)

        yaw_expected_radps: list[float] = []
        yaw_error_radps: list[float] = []
        balance_score: list[float] = []
        balance_class: list[str] = []
        is_cornering: list[bool] = []

        for steer, speed, yaw_measured in zip(steering_rad, speed_mps, yaw_measured_radps):
            yaw_expected = (speed / wheelbase_m) * tan(steer)
            error = yaw_measured - yaw_expected
            score = error / (abs(yaw_expected) + 0.05)
            score = max(-3.0, min(3.0, score))

            cornering = abs(steer) >= min_steering_rad and speed >= min_speed_mps
            if not cornering:
                cls = "not_cornering"
            elif score <= -score_threshold:
                cls = "understeer"
            elif score >= score_threshold:
                cls = "oversteer"
            else:
                cls = "neutral"

            yaw_expected_radps.append(yaw_expected)
            yaw_error_radps.append(error)
            balance_score.append(score)
            balance_class.append(cls)
            is_cornering.append(cornering)

        indices = _downsample_indices_5hz(ts_ns_values)

        ts_ns_values = _select_by_indices(ts_ns_values, indices)
        steering_rad = _select_by_indices(steering_rad, indices)
        speed_mps = _select_by_indices(speed_mps, indices)
        yaw_measured_radps = _select_by_indices(yaw_measured_radps, indices)
        yaw_expected_radps = _select_by_indices(yaw_expected_radps, indices)
        yaw_error_radps = _select_by_indices(yaw_error_radps, indices)
        balance_score = _select_by_indices(balance_score, indices)
        balance_class = _select_by_indices(balance_class, indices)
        is_cornering = _select_by_indices(is_cornering, indices)

        cornering_count = sum(1 for flag in is_cornering if flag)
        understeer_count = sum(1 for label in balance_class if label == "understeer")
        oversteer_count = sum(1 for label in balance_class if label == "oversteer")
        neutral_count = sum(1 for label in balance_class if label == "neutral")

        races_payload.append(
            {
                "raceId": race_id,
                "sampleCount": len(ts_ns_values),
                "summary": {
                    "corneringSampleCount": cornering_count,
                    "understeerCount": understeer_count,
                    "oversteerCount": oversteer_count,
                    "neutralCount": neutral_count,
                },
                "series": {
                    "tsNs": ts_ns_values,
                    "steeringAngleRad": [round(value, 6) for value in steering_rad],
                    "speedMps": [round(value, 4) for value in speed_mps],
                    "yawRateMeasuredRadPs": [round(value, 6) for value in yaw_measured_radps],
                    "yawRateExpectedRadPs": [round(value, 6) for value in yaw_expected_radps],
                    "yawRateErrorRadPs": [round(value, 6) for value in yaw_error_radps],
                    "balanceScore": [round(value, 6) for value in balance_score],
                    "balanceClass": balance_class,
                    "isCornering": is_cornering,
                },
            }
        )

    return JsonResponse(
        {
            "method": {
                "name": "yaw_rate_error_bicycle_model",
                "description": "Compares measured yaw rate to expected yaw rate from steering and speed.",
                "scoreDefinition": "(yaw_measured - yaw_expected) / (abs(yaw_expected) + 0.05)",
                "labels": {
                    "understeer": "score <= -threshold while cornering",
                    "oversteer": "score >= threshold while cornering",
                    "neutral": "|score| < threshold while cornering",
                    "not_cornering": "below cornering gates",
                },
            },
            "config": {
                "wheelbaseM": wheelbase_m,
                "minSpeedMps": min_speed_mps,
                "minSteeringRad": min_steering_rad,
                "scoreThreshold": score_threshold,
                "emaAlpha": ema_alpha,
                "outputSampleHz": OUTPUT_SAMPLE_HZ,
            },
            "signal": {
                "steering": "TopicStateEstimation.delta_wheel_rad",
                "speed": "TopicStateEstimation.v_mps",
                "yawRate": "TopicStateEstimation.yaw_vel_rad",
            },
            "raceCount": len(races_payload),
            "races": races_payload,
        }
    )


@require_GET
def get_slip_coaching_metrics(request: HttpRequest) -> JsonResponse:
    try:
        min_speed_mps = _parse_optional_float(
            request.GET.get("min_speed_mps"),
            default_value=DEFAULT_MIN_ANALYSIS_SPEED_MPS,
        )
        min_lateral_g = _parse_optional_float(
            request.GET.get("min_lateral_g"),
            default_value=DEFAULT_MIN_LATERAL_G,
        )
        target_slip_deg = _parse_optional_float(
            request.GET.get("target_slip_deg"),
            default_value=DEFAULT_TARGET_SLIP_DEG,
        )
        slip_window_deg = _parse_optional_float(
            request.GET.get("slip_window_deg"),
            default_value=DEFAULT_SLIP_WINDOW_DEG,
        )
        balance_threshold_deg = _parse_optional_float(
            request.GET.get("balance_threshold_deg"),
            default_value=DEFAULT_BALANCE_THRESHOLD_DEG,
        )
        ema_alpha = _parse_optional_float(
            request.GET.get("ema_alpha"),
            default_value=DEFAULT_EMA_ALPHA,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if min_speed_mps < 0.0:
        return JsonResponse({"error": "min_speed_mps must be >= 0."}, status=400)
    if min_lateral_g < 0.0:
        return JsonResponse({"error": "min_lateral_g must be >= 0."}, status=400)
    if target_slip_deg <= 0.0:
        return JsonResponse({"error": "target_slip_deg must be > 0."}, status=400)
    if slip_window_deg < 0.0:
        return JsonResponse({"error": "slip_window_deg must be >= 0."}, status=400)
    if balance_threshold_deg < 0.0:
        return JsonResponse({"error": "balance_threshold_deg must be >= 0."}, status=400)
    if ema_alpha <= 0.0 or ema_alpha > 1.0:
        return JsonResponse({"error": "ema_alpha must be in (0, 1]."}, status=400)

    rows = TopicStateEstimation.objects.exclude(
        alpha_fl_rad__isnull=True,
    ).exclude(
        alpha_fr_rad__isnull=True,
    ).exclude(
        alpha_rl_rad__isnull=True,
    ).exclude(
        alpha_rr_rad__isnull=True,
    ).exclude(
        ay_mps2__isnull=True,
    ).exclude(
        v_mps__isnull=True,
    ).order_by("record__race_id", "record__ts_ns").values_list(
        "record__race_id",
        "record__ts_ns",
        "alpha_fl_rad",
        "alpha_fr_rad",
        "alpha_rl_rad",
        "alpha_rr_rad",
        "ay_mps2",
        "v_mps",
    )

    race_points: dict[str, list[tuple[int, float, float, float, float, float, float]]] = {}
    for race_id, ts_ns, alpha_fl, alpha_fr, alpha_rl, alpha_rr, ay_mps2, speed_mps in rows.iterator(chunk_size=10_000):
        race_points.setdefault(str(race_id), []).append(
            (
                int(ts_ns),
                float(alpha_fl),
                float(alpha_fr),
                float(alpha_rl),
                float(alpha_rr),
                float(ay_mps2),
                float(speed_mps),
            )
        )

    races_payload: list[dict] = []
    for race_id in sorted(race_points):
        points = race_points[race_id]
        if not points:
            continue

        ts_ns_values = [point[0] for point in points]
        alpha_fl_rad = _ema([point[1] for point in points], ema_alpha)
        alpha_fr_rad = _ema([point[2] for point in points], ema_alpha)
        alpha_rl_rad = _ema([point[3] for point in points], ema_alpha)
        alpha_rr_rad = _ema([point[4] for point in points], ema_alpha)
        ay_mps2 = _ema([point[5] for point in points], ema_alpha)
        speed_mps = _ema([point[6] for point in points], ema_alpha)

        front_slip_deg: list[float] = []
        rear_slip_deg: list[float] = []
        max_slip_deg: list[float] = []
        slip_balance_deg: list[float] = []
        lateral_g: list[float] = []
        grip_usage_ratio: list[float] = []
        coaching_state: list[str] = []
        balance_hint: list[str] = []
        is_high_demand_cornering: list[bool] = []

        for fl, fr, rl, rr, ay_value, speed in zip(
            alpha_fl_rad,
            alpha_fr_rad,
            alpha_rl_rad,
            alpha_rr_rad,
            ay_mps2,
            speed_mps,
        ):
            fl_deg = abs(fl) * 57.295779513
            fr_deg = abs(fr) * 57.295779513
            rl_deg = abs(rl) * 57.295779513
            rr_deg = abs(rr) * 57.295779513

            front_avg = 0.5 * (fl_deg + fr_deg)
            rear_avg = 0.5 * (rl_deg + rr_deg)
            max_slip = max(fl_deg, fr_deg, rl_deg, rr_deg)
            balance = front_avg - rear_avg
            g_lat = ay_value / 9.81

            grip_ratio = max_slip / target_slip_deg
            grip_ratio = max(0.0, min(3.0, grip_ratio))
            high_demand = abs(g_lat) >= min_lateral_g and speed >= min_speed_mps

            if not high_demand:
                state = "not_in_corner_window"
                hint = "insufficient_lateral_load"
            else:
                if max_slip < (target_slip_deg - slip_window_deg):
                    state = "below_optimal_slip"
                elif max_slip > (target_slip_deg + slip_window_deg):
                    state = "over_limit_slip"
                else:
                    state = "in_optimal_window"

                if balance >= balance_threshold_deg:
                    hint = "front_limited"
                elif balance <= -balance_threshold_deg:
                    hint = "rear_limited"
                else:
                    hint = "balanced"

            front_slip_deg.append(front_avg)
            rear_slip_deg.append(rear_avg)
            max_slip_deg.append(max_slip)
            slip_balance_deg.append(balance)
            lateral_g.append(g_lat)
            grip_usage_ratio.append(grip_ratio)
            coaching_state.append(state)
            balance_hint.append(hint)
            is_high_demand_cornering.append(high_demand)

        indices = _downsample_indices_5hz(ts_ns_values)

        ts_ns_values = _select_by_indices(ts_ns_values, indices)
        speed_mps = _select_by_indices(speed_mps, indices)
        ay_mps2 = _select_by_indices(ay_mps2, indices)
        lateral_g = _select_by_indices(lateral_g, indices)
        front_slip_deg = _select_by_indices(front_slip_deg, indices)
        rear_slip_deg = _select_by_indices(rear_slip_deg, indices)
        max_slip_deg = _select_by_indices(max_slip_deg, indices)
        slip_balance_deg = _select_by_indices(slip_balance_deg, indices)
        grip_usage_ratio = _select_by_indices(grip_usage_ratio, indices)
        coaching_state = _select_by_indices(coaching_state, indices)
        balance_hint = _select_by_indices(balance_hint, indices)
        is_high_demand_cornering = _select_by_indices(is_high_demand_cornering, indices)

        analyzed_indices = [i for i, flag in enumerate(is_high_demand_cornering) if flag]
        analyzed_max_slip = [max_slip_deg[i] for i in analyzed_indices]
        analyzed_lateral_g = [abs(lateral_g[i]) for i in analyzed_indices]

        below_count = sum(1 for state in coaching_state if state == "below_optimal_slip")
        in_window_count = sum(1 for state in coaching_state if state == "in_optimal_window")
        over_count = sum(1 for state in coaching_state if state == "over_limit_slip")
        front_limited_count = sum(1 for hint in balance_hint if hint == "front_limited")
        rear_limited_count = sum(1 for hint in balance_hint if hint == "rear_limited")

        races_payload.append(
            {
                "raceId": race_id,
                "sampleCount": len(ts_ns_values),
                "summary": {
                    "analyzedSampleCount": len(analyzed_indices),
                    "belowOptimalSlipCount": below_count,
                    "inOptimalWindowCount": in_window_count,
                    "overLimitSlipCount": over_count,
                    "frontLimitedCount": front_limited_count,
                    "rearLimitedCount": rear_limited_count,
                    "medianMaxSlipDeg": round(_quantile(analyzed_max_slip, 0.5), 3),
                    "p95MaxSlipDeg": round(_quantile(analyzed_max_slip, 0.95), 3),
                    "avgAbsLateralG": round(sum(analyzed_lateral_g) / len(analyzed_lateral_g), 4)
                    if analyzed_lateral_g
                    else 0.0,
                },
                "series": {
                    "tsNs": ts_ns_values,
                    "speedMps": [round(value, 4) for value in speed_mps],
                    "lateralAccelMps2": [round(value, 4) for value in ay_mps2],
                    "lateralG": [round(value, 4) for value in lateral_g],
                    "frontSlipDeg": [round(value, 4) for value in front_slip_deg],
                    "rearSlipDeg": [round(value, 4) for value in rear_slip_deg],
                    "maxSlipDeg": [round(value, 4) for value in max_slip_deg],
                    "slipBalanceDeg": [round(value, 4) for value in slip_balance_deg],
                    "gripUsageRatio": [round(value, 4) for value in grip_usage_ratio],
                    "coachingState": coaching_state,
                    "balanceHint": balance_hint,
                    "isHighDemandCornering": is_high_demand_cornering,
                },
            }
        )

    return JsonResponse(
        {
            "method": {
                "name": "slip_window_and_balance",
                "description": "Combines per-wheel slip angles with lateral load to detect grip usage and balance limits.",
                "coachingStates": {
                    "below_optimal_slip": "Cornering load is high, but slip is below target. Driver may be leaving speed on entry/mid-corner.",
                    "in_optimal_window": "Slip is near target under cornering load.",
                    "over_limit_slip": "Slip exceeds target band under cornering load. Tire likely saturating/sliding.",
                    "not_in_corner_window": "Outside speed/lateral-load gates; no coaching classification.",
                },
                "balanceHints": {
                    "front_limited": "Front slip exceeds rear by threshold (understeer tendency).",
                    "rear_limited": "Rear slip exceeds front by threshold (oversteer tendency).",
                    "balanced": "Front/rear slip demand is within threshold.",
                    "insufficient_lateral_load": "Not enough cornering demand to infer balance.",
                },
            },
            "config": {
                "minSpeedMps": min_speed_mps,
                "minLateralG": min_lateral_g,
                "targetSlipDeg": target_slip_deg,
                "slipWindowDeg": slip_window_deg,
                "balanceThresholdDeg": balance_threshold_deg,
                "emaAlpha": ema_alpha,
                "outputSampleHz": OUTPUT_SAMPLE_HZ,
            },
            "signal": {
                "alphaFl": "TopicStateEstimation.alpha_fl_rad",
                "alphaFr": "TopicStateEstimation.alpha_fr_rad",
                "alphaRl": "TopicStateEstimation.alpha_rl_rad",
                "alphaRr": "TopicStateEstimation.alpha_rr_rad",
                "lateralAccel": "TopicStateEstimation.ay_mps2",
                "speed": "TopicStateEstimation.v_mps",
            },
            "raceCount": len(races_payload),
            "races": races_payload,
        }
    )
