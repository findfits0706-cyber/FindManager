from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    MonthlyShiftAssignmentViewSet,
    MonthlyShiftPlanViewSet,
    MonthlyShiftPublicationViewSet,
    MyPublishedShiftViewSet,
    MyShiftRequestPeriodViewSet,
    ShiftPatternViewSet,
    ShiftRequestPeriodViewSet,
    ShiftRequestSubmissionViewSet,
    WeeklyShiftTemplateViewSet,
)

router = DefaultRouter()
router.register("shift-patterns", ShiftPatternViewSet, basename="shift-pattern")
router.register("weekly-shift-templates", WeeklyShiftTemplateViewSet, basename="weekly-shift-template")
router.register("monthly-shift-plans", MonthlyShiftPlanViewSet, basename="monthly-shift-plan")
router.register("monthly-shift-assignments", MonthlyShiftAssignmentViewSet, basename="monthly-shift-assignment")
router.register("monthly-shift-publications", MonthlyShiftPublicationViewSet, basename="monthly-shift-publication")
router.register("shift-request-periods", ShiftRequestPeriodViewSet, basename="shift-request-period")
router.register("shift-request-submissions", ShiftRequestSubmissionViewSet, basename="shift-request-submission")
router.register("my-shift-request-periods", MyShiftRequestPeriodViewSet, basename="my-shift-request-period")
router.register("my-published-shifts", MyPublishedShiftViewSet, basename="my-published-shift")

urlpatterns = [
    path("", include(router.urls)),
]
