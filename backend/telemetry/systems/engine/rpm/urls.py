from django.urls import path

from .views import get_rpm_comparison

urlpatterns = [
    path("comparison", get_rpm_comparison, name="engineRpmComparison"),
]
