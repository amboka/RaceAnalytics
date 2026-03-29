from django.urls import path

from .views import (
    get_brake_release_throttle_transition,
    get_brake_pressure_comparison,
    get_brake_temperature_comparison,
    get_trail_braking_analysis,
)

urlpatterns = [
    path("pressureComparison", get_brake_pressure_comparison, name="brakePressureComparison"),
    path("temperatureComparison", get_brake_temperature_comparison, name="brakeTemperatureComparison"),
    path("trailBrakingAnalysis", get_trail_braking_analysis, name="trailBrakingAnalysis"),
    path("releaseThrottleTransition", get_brake_release_throttle_transition, name="brakeReleaseThrottleTransition"),
]
