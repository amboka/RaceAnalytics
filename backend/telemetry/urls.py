from django.urls import include, path

from telemetry.views import (
    get_braking_efficiency,
    get_grip_utilization,
    get_lap_time,
    get_time_lost_per_section,
    get_top_speed,
    get_trajectories,
    get_brake_temperature,
    get_braking_slip,
    get_minimal_schema,
    get_tyre_temperature,
    get_wheel_speed,
    get_camera_frames,
    get_camera_frames_by_location,
    get_camera_frame_image,
)

urlpatterns = [
    path("getLapTime", get_lap_time, name="getLapTime"),
    path("topSpeed", get_top_speed, name="topSpeed"),
    path("timeLostPerSection", get_time_lost_per_section, name="timeLostPerSection"),
    path("brakingEfficiency", get_braking_efficiency, name="brakingEfficiency"),
    path("gripUtilization", get_grip_utilization, name="gripUtilization"),
    path("engine/", include("telemetry.systems.engine.urls")),
    path("breaks/", include("telemetry.systems.breaks.urls")),
    path("steering/", include("telemetry.systems.steering.urls")),
    path("trajectories", get_trajectories, name="trajectories"),
    path("speed", get_wheel_speed, name="wheelSpeed"),
    path("brakingSlip", get_braking_slip, name="wheelBrakingSlip"),
    path("tyreTemperature", get_tyre_temperature, name="wheelTyreTemperature"),
    path("brakeTemperature", get_brake_temperature, name="wheelBrakeTemperature"),
    path("minimalSchema", get_minimal_schema, name="wheelMinimalSchema"),
    path("camera/frames", get_camera_frames, name="cameraFrames"),
    path("camera/frames-by-location", get_camera_frames_by_location, name="cameraFramesByLocation"),
    path("camera/frame-image", get_camera_frame_image, name="cameraFrameImage"),
]
