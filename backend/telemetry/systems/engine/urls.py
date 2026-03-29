from django.urls import include, path

from .views import get_engine_laps, get_throttle_comparison

urlpatterns = [
    path("laps", get_engine_laps, name="engineLaps"),
    path("throttleComparison", get_throttle_comparison, name="engineThrottleComparison"),
    path("rpm/", include("telemetry.systems.engine.rpm.urls")),
    path("gearboxAndShift/", include("telemetry.systems.engine.gearboxAndShift.urls")),
]
