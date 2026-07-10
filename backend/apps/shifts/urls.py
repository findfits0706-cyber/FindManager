from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    MonthlyShiftAssignmentViewSet,
    MonthlyShiftPlanViewSet,
    MonthlyShiftPublicationViewSet,
    MyPublishedShiftViewSet,
    ShiftPatternViewSet,
    WeeklyShiftTemplateViewSet,
)

router = DefaultRouter()
router.register("shift-patterns", ShiftPatternViewSet, basename="shift-pattern")
router.register("weekly-shift-templates", WeeklyShiftTemplateViewSet, basename="weekly-shift-template")
router.register("monthly-shift-plans", MonthlyShiftPlanViewSet, basename="monthly-shift-plan")
router.register("monthly-shift-assignments", MonthlyShiftAssignmentViewSet, basename="monthly-shift-assignment")
router.register("monthly-shift-publications", MonthlyShiftPublicationViewSet, basename="monthly-shift-publication")
router.register("my-published-shifts", MyPublishedShiftViewSet, basename="my-published-shift")

urlpatterns = [
    path("", include(router.urls)),
]
