from math import ceil
from typing import Optional
from django.db.models import F, Max, ExpressionWrapper, FloatField
from django.db.models.functions import Power, Sqrt
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.http import require_GET

from analysis.brakingEfficiency import compute_braking_efficiency
from analysis.gripUtilization import compute_grip_utilization
from analysis.lapTime import compute_lap_times, compute_time_lost_per_section
from telemetry.models import TopicStateEstimation, CameraFrameSQLiteBlob


@require_GET
def get_lap_time(request: HttpRequest) -> JsonResponse:
    segment = request.GET.get("segment")

    if "start_ns" in request.GET or "end_ns" in request.GET:
        return JsonResponse(
            {
                "error": "start_ns/end_ns are not supported.",
                "details": "Provide only 'segment'; API computes segment start/end/duration.",
            },
            status=400,
        )

    try:    
        payload = compute_lap_times(segment=segment)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute lap times.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_top_speed(request: HttpRequest) -> JsonResponse:
    query = TopicStateEstimation.objects.exclude(v_mps__isnull=True)
    
    # Apply optional time range filters
    start_ns = request.GET.get("start_ns")
    end_ns = request.GET.get("end_ns")
    
    if start_ns is not None:
        try:
            query = query.filter(record__ts_ns__gte=int(start_ns))
        except (ValueError, TypeError):
            return JsonResponse(
                {"error": "Invalid start_ns parameter. Must be an integer."},
                status=400,
            )
    
    if end_ns is not None:
        try:
            query = query.filter(record__ts_ns__lt=int(end_ns))
        except (ValueError, TypeError):
            return JsonResponse(
                {"error": "Invalid end_ns parameter. Must be an integer."},
                status=400,
            )
    
    top_speeds = list(
        query
        .values(race_id=F("record__race_id"))
        .annotate(top_speed_mps=Max("v_mps"))
        .order_by("race_id")
    )

    return JsonResponse({"topSpeeds": top_speeds})


@require_GET
def get_time_lost_per_section(request: HttpRequest) -> JsonResponse:
    try:
        payload = compute_time_lost_per_section()
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute time lost per section.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse({"timeLostPerSection": payload})


@require_GET
def get_braking_efficiency(request: HttpRequest) -> JsonResponse:
    # Parse optional time range parameters
    start_ns = request.GET.get("start_ns")
    end_ns = request.GET.get("end_ns")
    segment = request.GET.get("segment")
    race_id = request.GET.get("race_id", "slow")
    reference_race_id = request.GET.get("reference_race_id", "fast")
    
    # Validate time parameters if provided
    if (start_ns is not None and end_ns is None) or (start_ns is None and end_ns is not None):
        return JsonResponse(
            {
                "error": "Both start_ns and end_ns must be provided together.",
            },
            status=400,
        )
    
    try:
        kwargs = {"race_id": race_id, "reference_race_id": reference_race_id}
        if start_ns is not None and end_ns is not None:
            kwargs["start_ns"] = int(start_ns)
            kwargs["end_ns"] = int(end_ns)
        if segment is not None:
            kwargs["segment"] = segment
        
        payload = compute_braking_efficiency(**kwargs)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute braking efficiency.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse({"brakingEfficiency": payload})


@require_GET
def get_grip_utilization(request: HttpRequest) -> JsonResponse:
    # Parse optional time range parameters
    start_ns = request.GET.get("start_ns")
    end_ns = request.GET.get("end_ns")
    segment = request.GET.get("segment")
    race_id = request.GET.get("race_id", "slow")
    reference_race_id = request.GET.get("reference_race_id", "fast")
    
    # Validate time parameters if provided
    if (start_ns is not None and end_ns is None) or (start_ns is None and end_ns is not None):
        return JsonResponse(
            {
                "error": "Both start_ns and end_ns must be provided together.",
            },
            status=400,
        )
    
    try:
        kwargs = {"race_id": race_id, "reference_race_id": reference_race_id}
        if start_ns is not None and end_ns is not None:
            kwargs["start_ns"] = int(start_ns)
            kwargs["end_ns"] = int(end_ns)
        if segment is not None:
            kwargs["segment"] = segment
        
        payload = compute_grip_utilization(**kwargs)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to compute grip utilization.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse({"gripUtilization": payload})

def _build_trajectory_payload(race_id: str, max_points: int = 2500) -> dict:
    rows = list(
        TopicStateEstimation.objects.filter(
            record__race_id=str(race_id),
            x_m__isnull=False,
            y_m__isnull=False,
        )
        .order_by("record__ts_ns")
        .values_list("x_m", "y_m")
    )

    total_points = len(rows)
    if total_points == 0:
        return {
            "race_id": str(race_id),
            "point_count": 0,
            "sample_step": 1,
            "points": [],
        }

    sample_step = max(1, ceil(total_points / max_points))
    sampled = rows[::sample_step]
    if sampled[-1] != rows[-1]:
        sampled.append(rows[-1])

    points = [{"x_m": float(x), "y_m": float(y)} for x, y in sampled]
    return {
        "race_id": str(race_id),
        "point_count": total_points,
        "sample_step": sample_step,
        "points": points,
    }


def _resolve_race_id(requested_race_id: str) -> str:
    # Keep explicit IDs if they exist; otherwise support FE aliases 0/1 for this dataset.
    race_id = str(requested_race_id)
    has_points = TopicStateEstimation.objects.filter(
        record__race_id=race_id,
        x_m__isnull=False,
        y_m__isnull=False,
    ).exists()
    if has_points:
        return race_id

    alias_map = {
        "0": "slow",
        "1": "fast",
    }
    alias = alias_map.get(race_id)
    if not alias:
        return race_id

    alias_has_points = TopicStateEstimation.objects.filter(
        record__race_id=alias,
        x_m__isnull=False,
        y_m__isnull=False,
    ).exists()
    return alias if alias_has_points else race_id


@require_GET
def get_trajectories(request: HttpRequest) -> JsonResponse:
    current_race_id = _resolve_race_id(request.GET.get("current_race_id", "0"))
    best_race_id = _resolve_race_id(request.GET.get("best_race_id", "1"))

    payload = {
        "currentLap": _build_trajectory_payload(current_race_id),
        "bestLap": _build_trajectory_payload(best_race_id),
    }
    return JsonResponse(payload)


from .service import (
    DEFAULT_POINTS,
    get_brake_temperature_dataset,
    get_braking_slip_dataset,
    get_minimal_schema_dataset,
    get_tyre_temperature_dataset,
    get_wheel_speed_dataset,
    resolve_selection_window,
    validate_points,
)


def _parse_optional_int(raw_value: str | None, *, field_name: str) -> int | None:
    if raw_value is None or raw_value == "":
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name} value '{raw_value}'. Expected an integer.") from exc


def _resolve_request_window(request: HttpRequest):
    lap_id = (request.GET.get("lap_id") or "").strip() or None
    race_id = (request.GET.get("race_id") or "slow").strip()
    lap_number = _parse_optional_int(request.GET.get("lap_number"), field_name="lap_number")
    points = validate_points(
        _parse_optional_int(request.GET.get("points"), field_name="points") or DEFAULT_POINTS
    )
    return resolve_selection_window(lap_id=lap_id, race_id=race_id, lap_number=lap_number), points


@require_GET
def get_wheel_speed(request: HttpRequest) -> JsonResponse:
    try:
        window, points = _resolve_request_window(request)
        payload = get_wheel_speed_dataset(window, points)
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to load wheel speed telemetry.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_braking_slip(request: HttpRequest) -> JsonResponse:
    try:
        window, points = _resolve_request_window(request)
        payload = get_braking_slip_dataset(window, points)
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to load braking slip telemetry.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_tyre_temperature(request: HttpRequest) -> JsonResponse:
    try:
        window, points = _resolve_request_window(request)
        payload = get_tyre_temperature_dataset(window, points)
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to load tyre temperature telemetry.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_brake_temperature(request: HttpRequest) -> JsonResponse:
    try:
        window, points = _resolve_request_window(request)
        payload = get_brake_temperature_dataset(window, points)
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to load brake temperature telemetry.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


@require_GET
def get_minimal_schema(request: HttpRequest) -> JsonResponse:
    try:
        window, points = _resolve_request_window(request)
        payload = get_minimal_schema_dataset(window, points)
    except LookupError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse(
            {
                "error": "Unable to load minimal wheel schema telemetry.",
                "details": str(exc),
            },
            status=500,
        )

    return JsonResponse(payload)


def _resolve_camera_race_id(display_race_id: str) -> str:
	"""
	Map display race IDs used by frontend to camera DB race IDs.
	"""
	mapping = {
		"0": "hackathon_good_lap",
		"1": "hackathon_fast_laps",
		"2": "hackathon_wheel_to_wheel",
		"slow": "hackathon_good_lap",
		"fast": "hackathon_fast_laps",
	}
	return mapping.get(display_race_id, display_race_id)


def _find_nearest_state_by_position(display_race_id: str, x: float, y: float, z: float = 0.0, max_distance: float = 10.0) -> Optional[TopicStateEstimation]:
	"""
	Find the nearest TopicStateEstimation record to the given XYZ position.
	Handles both direct race_ids and display aliases.
	
	Args:
		display_race_id: The display race identifier (e.g., "0", "slow", "fast")
		x, y, z: Target position in meters
		max_distance: Only return if within this distance (meters). Set to None for unlimited.
	
	Returns:
		TopicStateEstimation record closest to the target position, or None if not found
	"""
	# Map display IDs to actual telemetry race_ids
	telemetry_race_map = {
		"0": "slow",
		"1": "fast",
		"slow": "slow",
		"fast": "fast",
		"hackathon_good_lap": "slow",
		"hackathon_fast_laps": "fast",
	}
	
	telemetry_race_id = telemetry_race_map.get(display_race_id, display_race_id)
	
	# Query all state estimation records for this race with valid positions
	states = TopicStateEstimation.objects.filter(
		record__race_id=telemetry_race_id,
		x_m__isnull=False,
		y_m__isnull=False,
		z_m__isnull=False,
	).values_list('record_id', 'x_m', 'y_m', 'z_m').order_by('record__ts_ns')
	
	if not states.exists():
		return None
	
	# Find nearest point by computing distances
	# Using Euclidean distance: sqrt((x_state - x_target)^2 + (y_state - y_target)^2 + (z_state - z_target)^2)
	nearest_record_id = None
	nearest_distance = float('inf')
	
	for record_id, state_x, state_y, state_z in states:
		distance = ((state_x - x) ** 2 + (state_y - y) ** 2 + (state_z - z) ** 2) ** 0.5
		
		if distance < nearest_distance:
			nearest_distance = distance
			nearest_record_id = record_id
	
	# Check if within tolerance
	if max_distance is not None and nearest_distance > max_distance:
		return None
	
	if nearest_record_id is None:
		return None
	
	return TopicStateEstimation.objects.get(record_id=nearest_record_id)


def _ts_ns_to_seconds(ts_ns: int) -> float:
	"""Convert nanosecond timestamp to seconds from recording start."""
	# Assuming ts_ns is absolute, we need a reference point
	# For now, just convert to seconds
	return ts_ns / 1_000_000_000


def _parse_timestamp_string(timestamp_str: str) -> float:
	"""
	Parse lap-relative timestamp from "M:SS.d" format to seconds.
	Examples:
	  "0:08.4" -> 8.4
	  "1:23.5" -> 83.5
	  "2:05.0" -> 125.0
	"""
	parts = timestamp_str.split(':')
	if len(parts) != 2:
		raise ValueError(f"Invalid timestamp format '{timestamp_str}'. Expected 'M:SS.d'")
	
	try:
		minutes = int(parts[0])
		seconds = float(parts[1])
		total_seconds = minutes * 60 + seconds
		return total_seconds
	except ValueError as exc:
		raise ValueError(f"Invalid timestamp format '{timestamp_str}'. Expected 'M:SS.d'") from exc


def _build_blob_frame_url(base_url: str, race_id: str, camera: int, frame_number: int) -> str:
	"""
	Build URL for image bytes served from camera_frame_sqlite_blob.
	"""
	return (
		f"{base_url}/api/camera/frame-image"
		f"?race_id={race_id}&camera={camera}&frame_number={frame_number}"
	)


@require_GET
def get_camera_frame_image(request: HttpRequest) -> HttpResponse:
	"""Serve a single camera frame image directly from DB blob storage."""
	race_id_raw = request.GET.get("race_id", "").strip()
	camera_raw = request.GET.get("camera", "").strip()
	frame_raw = request.GET.get("frame_number", "").strip()

	if not race_id_raw or not camera_raw or not frame_raw:
		return JsonResponse(
			{"error": "Missing required parameters: race_id, camera, frame_number"},
			status=400,
		)

	try:
		camera = int(camera_raw)
		frame_number = int(frame_raw)
	except ValueError:
		return JsonResponse(
			{"error": "camera and frame_number must be integers"},
			status=400,
		)

	actual_race_id = _resolve_camera_race_id(race_id_raw)
	frame = (
		CameraFrameSQLiteBlob.objects
		.filter(race_id=actual_race_id, camera=camera, frame_number=frame_number)
		.only("image_blob", "image_format")
		.first()
	)
	if frame is None:
		return JsonResponse({"error": "Frame not found"}, status=404)

	image_format = (frame.image_format or "jpg").lower()
	content_type = "image/jpeg" if image_format in ("jpg", "jpeg") else f"image/{image_format}"
	return HttpResponse(bytes(frame.image_blob), content_type=content_type)


@require_GET
def get_camera_frames(request: HttpRequest) -> JsonResponse:
	"""
	Returns a sequence of camera frame images starting from a given timestamp.
	Reads frames from DB blob table and returns URLs to DB-served images.
	
	Query Parameters:
	  - race_id (required): Session/race identifier (e.g., "0", "1", "hackathon_good_lap")
	  - camera (required): Camera index (0=front-left, 1=rear)
	  - start_ts (required): Lap-relative timestamp in "M:SS.d" format (e.g., "0:08.4")
	  - duration (optional): How many seconds of footage to return, starting from start_ts. Default: 10.
	
	Returns JSON with frames array, fps, frameCount, raceId, camera.
	"""
	try:
		display_race_id = request.GET.get("race_id", "").strip()
		camera_str = request.GET.get("camera", "").strip()
		start_ts_str = request.GET.get("start_ts", "").strip()
		duration_str = request.GET.get("duration", "10").strip()
		
		# Validate required parameters
		if not display_race_id:
			return JsonResponse(
				{"error": "Missing required parameter: race_id"},
				status=400,
			)
		if not camera_str:
			return JsonResponse(
				{"error": "Missing required parameter: camera"},
				status=400,
			)
		if not start_ts_str:
			return JsonResponse(
				{"error": "Missing required parameter: start_ts"},
				status=400,
			)
		
		# Parse and validate camera
		try:
			camera = int(camera_str)
			if camera not in (0, 1):
				return JsonResponse(
					{"error": "Camera must be 0 (front-left) or 1 (rear)"},
					status=400,
				)
		except ValueError:
			return JsonResponse(
				{"error": "Camera must be an integer (0 or 1)"},
				status=400,
			)
		
		# Parse and validate start timestamp
		try:
			start_seconds = _parse_timestamp_string(start_ts_str)
			if start_seconds < 0:
				return JsonResponse(
					{"error": "Timestamp cannot be negative"},
					status=400,
				)
		except ValueError as exc:
			return JsonResponse(
				{"error": str(exc)},
				status=400,
			)
		
		# Parse and validate duration
		try:
			duration = int(duration_str)
			if duration <= 0:
				return JsonResponse(
					{"error": "Duration must be greater than 0"},
					status=400,
				)
		except ValueError:
			return JsonResponse(
				{"error": "Duration must be an integer"},
				status=400,
			)
		
		actual_race_id = _resolve_camera_race_id(display_race_id)
		
		# Query frames for this race_id and camera
		frame_records = list(
			CameraFrameSQLiteBlob.objects
			.filter(race_id=actual_race_id, camera=camera)
			.order_by("frame_number")
			.only("frame_number", "timestamp_seconds", "timestamp_ns", "x_m", "y_m", "z_m")
		)
		
		# Still no frames found
		if not frame_records:
			return JsonResponse({
				"raceId": display_race_id,
				"camera": camera,
				"fps": 5,
				"frameCount": 0,
				"frames": [],
			})
		
		# DB blob table currently stores frames at 5Hz for this dataset.
		fps = 5
		
		# Calculate starting frame index
		start_frame_index = int(start_seconds * fps)
		
		# Calculate number of frames to return
		frame_count = duration * fps
		end_frame_index = start_frame_index + frame_count
		
		# Filter frames in the requested range
		requested_frames = [f for f in frame_records if start_frame_index <= f.frame_number < end_frame_index]
		
		# Build full URLs for each frame
		# Get the request's scheme and netloc to build absolute URLs
		build_scheme = request.scheme
		build_netloc = request.get_host()
		base_url = f"{build_scheme}://{build_netloc}"
		
		frames_payload = [
			{
				"frameNumber": f.frame_number,
				"imageUrl": _build_blob_frame_url(base_url, actual_race_id, camera, f.frame_number),
				"timestampSeconds": float(f.timestamp_seconds),
				"timestampNs": int(f.timestamp_ns),
				"x": float(f.x_m) if f.x_m is not None else None,
				"y": float(f.y_m) if f.y_m is not None else None,
				"z": float(f.z_m) if f.z_m is not None else None,
			}
			for f in requested_frames
		]
		
		return JsonResponse({
			"raceId": display_race_id,
			"camera": camera,
			"fps": fps,
			"frameCount": len(frames_payload),
			"frames": frames_payload,
		})
		
	except Exception as exc:
		return JsonResponse(
			{
				"error": "Unable to load camera frames.",
				"details": str(exc),
			},
			status=500,
		)


@require_GET
def get_camera_frames_by_location(request: HttpRequest) -> JsonResponse:
	"""
	Returns camera frames between two spatial locations on the track.
	Instead of timestamp-based scrubbing, this uses XYZ position-based scrubbing.
	
	Query Parameters:
	  - race_id (required): Session/race identifier (e.g., "0", "1")
	  - camera (required): Camera index (0=front-left, 1=rear)
	  - start_x, start_y, start_z (required): Starting position (meters)
	  - end_x, end_y, end_z (required): Ending position (meters)
	  - position_tolerance (optional): Max distance to match position (default: 10.0 meters)
	
	Returns JSON with frames array, fps, frameCount, raceId, camera, startPosition, endPosition.
	"""
	try:
		display_race_id = request.GET.get("race_id", "").strip()
		camera_str = request.GET.get("camera", "").strip()
		
		# Parse start position
		try:
			start_x = float(request.GET.get("start_x", ""))
			start_y = float(request.GET.get("start_y", ""))
			start_z = float(request.GET.get("start_z", "0"))
		except (ValueError, TypeError):
			return JsonResponse(
				{"error": "Invalid start position. start_x, start_y, start_z must be numbers."},
				status=400,
			)
		
		# Parse end position
		try:
			end_x = float(request.GET.get("end_x", ""))
			end_y = float(request.GET.get("end_y", ""))
			end_z = float(request.GET.get("end_z", "0"))
		except (ValueError, TypeError):
			return JsonResponse(
				{"error": "Invalid end position. end_x, end_y, end_z must be numbers."},
				status=400,
			)
		
		# Parse position tolerance
		try:
			position_tolerance = float(request.GET.get("position_tolerance", "10.0"))
			if position_tolerance <= 0:
				return JsonResponse(
					{"error": "position_tolerance must be greater than 0"},
					status=400,
				)
		except (ValueError, TypeError):
			return JsonResponse(
				{"error": "position_tolerance must be a number."},
				status=400,
			)
		
		# Validate required parameters
		if not display_race_id:
			return JsonResponse(
				{"error": "Missing required parameter: race_id"},
				status=400,
			)
		if not camera_str:
			return JsonResponse(
				{"error": "Missing required parameter: camera"},
				status=400,
			)
		
		# Parse and validate camera
		try:
			camera = int(camera_str)
			if camera not in (0, 1):
				return JsonResponse(
					{"error": "Camera must be 0 (front-left) or 1 (rear)"},
					status=400,
				)
		except ValueError:
			return JsonResponse(
				{"error": "Camera must be an integer (0 or 1)"},
				status=400,
			)
		
		actual_race_id = _resolve_camera_race_id(display_race_id)
		
		# Query DB-backed frames.
		frame_records = list(
			CameraFrameSQLiteBlob.objects
			.filter(race_id=actual_race_id, camera=camera)
			.order_by("frame_number")
			.only("frame_number", "timestamp_seconds", "timestamp_ns", "x_m", "y_m", "z_m")
		)
		
		# Still no frames found
		if not frame_records:
			return JsonResponse({
				"raceId": display_race_id,
				"camera": camera,
				"fps": 5,
				"frameCount": 0,
				"frames": [],
				"startPosition": {"x": start_x, "y": start_y, "z": start_z},
				"endPosition": {"x": end_x, "y": end_y, "z": end_z},
			})
		
		# Find nearest state estimation records to start and end positions
		start_state = _find_nearest_state_by_position(
			display_race_id, start_x, start_y, start_z, max_distance=position_tolerance
		)
		end_state = _find_nearest_state_by_position(
			display_race_id, end_x, end_y, end_z, max_distance=position_tolerance
		)
		
		if start_state is None:
			return JsonResponse(
				{
					"error": f"No track position found within {position_tolerance}m of start position "
					        f"({start_x}, {start_y}, {start_z})",
				},
				status=400,
			)
		
		if end_state is None:
			return JsonResponse(
				{
					"error": f"No track position found within {position_tolerance}m of end position "
					        f"({end_x}, {end_y}, {end_z})",
				},
				status=400,
			)
		
		# Get timestamps and convert to frame indices
		fps = 5
		
		# Get start and end timestamps (in nanoseconds from record)
		start_ts_ns = start_state.record.ts_ns
		end_ts_ns = end_state.record.ts_ns
		
		# Frame rows already include timestamp_ns aligned to telemetry.
		# Calculate frame ranges based on telemetry timestamps.
		if start_ts_ns <= end_ts_ns:
			requested_frames = []
			for frame in frame_records:
				frame_ts_ns = frame.timestamp_ns
				if start_ts_ns <= frame_ts_ns <= end_ts_ns:
					requested_frames.append(frame)
		else:
			requested_frames = []
			for frame in frame_records:
				frame_ts_ns = frame.timestamp_ns
				if end_ts_ns <= frame_ts_ns <= start_ts_ns:
					requested_frames.append(frame)
		
		# Build full URLs for each frame
		build_scheme = request.scheme
		build_netloc = request.get_host()
		base_url = f"{build_scheme}://{build_netloc}"
		
		frames_payload = [
			{
				"frameNumber": f.frame_number,
				"imageUrl": _build_blob_frame_url(base_url, actual_race_id, camera, f.frame_number),
				"timestampSeconds": float(f.timestamp_seconds),
				"timestampNs": int(f.timestamp_ns),
				"x": float(f.x_m) if f.x_m is not None else None,
				"y": float(f.y_m) if f.y_m is not None else None,
				"z": float(f.z_m) if f.z_m is not None else None,
			}
			for f in requested_frames
		]
		
		return JsonResponse({
			"raceId": display_race_id,
			"camera": camera,
			"fps": fps,
			"frameCount": len(frames_payload),
			"frames": frames_payload,
			"startPosition": {
				"x": float(start_state.x_m),
				"y": float(start_state.y_m),
				"z": float(start_state.z_m),
			},
			"endPosition": {
				"x": float(end_state.x_m),
				"y": float(end_state.y_m),
				"z": float(end_state.z_m),
			},
			"matchedStartDistance": (
				((start_state.x_m - start_x) ** 2 + 
				 (start_state.y_m - start_y) ** 2 + 
				 (start_state.z_m - start_z) ** 2) ** 0.5
			),
			"matchedEndDistance": (
				((end_state.x_m - end_x) ** 2 + 
				 (end_state.y_m - end_y) ** 2 + 
				 (end_state.z_m - end_z) ** 2) ** 0.5
			),
		})
		
	except Exception as exc:
		return JsonResponse(
			{
				"error": "Unable to load camera frames by location.",
				"details": str(exc),
			},
			status=500,
		)
