from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ShiftPatternViewSet, WeeklyShiftTemplateViewSet

router = DefaultRouter()
router.register("shift-patterns", ShiftPatternViewSet, basename="shift-pattern")
router.register("weekly-shift-templates", WeeklyShiftTemplateViewSet, basename="weekly-shift-template")

urlpatterns = [
    path("", include(router.urls)),
]
