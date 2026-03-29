from django.urls import path

from .views import get_gearbox_shift_comparison

urlpatterns = [
    path("comparison", get_gearbox_shift_comparison, name="engineGearboxShiftComparison"),
]
