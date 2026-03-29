from django.urls import path

from .views import get_over_under_steer, get_slip_coaching_metrics, get_steering_angle

urlpatterns = [
    path("getSteeringAngle", get_steering_angle, name="getSteeringAngle"),
    path("getOverUnderSteer", get_over_under_steer, name="getOverUnderSteer"),
    path("getSlipCoachingMetrics", get_slip_coaching_metrics, name="getSlipCoachingMetrics"),
]
