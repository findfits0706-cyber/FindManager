from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceClosingPeriodViewSet,
    AttendanceCorrectionRequestViewSet,
    AttendanceRecordViewSet,
    LaborCostBudgetPeriodViewSet,
    LaborCostEstimatePeriodViewSet,
    MonthlyShiftAssignmentViewSet,
    MonthlyShiftPlanViewSet,
    MonthlyShiftPublicationViewSet,
    MyAttendanceCorrectionRequestViewSet,
    MyAttendanceMonthlyViewSet,
    MyAttendanceViewSet,
    MyPublishedShiftViewSet,
    MyShiftChangeRequestViewSet,
    MyShiftRequestPeriodViewSet,
    ShiftChangeRequestViewSet,
    ShiftPatternViewSet,
    ShiftRequestPeriodViewSet,
    ShiftRequestSubmissionViewSet,
    StaffAllowanceAssignmentViewSet,
    StaffCompensationProfileViewSet,
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
router.register("shift-change-requests", ShiftChangeRequestViewSet, basename="shift-change-request")
router.register("attendance-records", AttendanceRecordViewSet, basename="attendance-record")
router.register("attendance-closing-periods", AttendanceClosingPeriodViewSet, basename="attendance-closing-period")
router.register("staff-compensation-profiles", StaffCompensationProfileViewSet, basename="staff-compensation-profile")
router.register("staff-allowance-assignments", StaffAllowanceAssignmentViewSet, basename="staff-allowance-assignment")
router.register("labor-cost-estimate-periods", LaborCostEstimatePeriodViewSet, basename="labor-cost-estimate-period")
router.register("labor-cost-budget-periods", LaborCostBudgetPeriodViewSet, basename="labor-cost-budget-period")
router.register(
    "attendance-correction-requests",
    AttendanceCorrectionRequestViewSet,
    basename="attendance-correction-request",
)
router.register("my-attendance", MyAttendanceViewSet, basename="my-attendance")
router.register("my-attendance-monthly", MyAttendanceMonthlyViewSet, basename="my-attendance-monthly")
router.register(
    "my-attendance-corrections",
    MyAttendanceCorrectionRequestViewSet,
    basename="my-attendance-correction",
)
router.register("my-shift-request-periods", MyShiftRequestPeriodViewSet, basename="my-shift-request-period")
router.register("my-shift-change-requests", MyShiftChangeRequestViewSet, basename="my-shift-change-request")
router.register("my-published-shifts", MyPublishedShiftViewSet, basename="my-published-shift")

urlpatterns = [
    path("", include(router.urls)),
]
