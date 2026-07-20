from django.contrib import admin

from .models import (
    AttendanceClosingPeriod,
    AttendanceClosingRecordSnapshot,
    AttendanceClosingStaffSummary,
    LaborCostBudgetAllowanceSnapshot,
    LaborCostBudgetDailySummary,
    LaborCostBudgetPeriod,
    LaborCostBudgetPlanRecordSnapshot,
    LaborCostBudgetStaffSummary,
    LaborCostEstimateAllowanceSnapshot,
    LaborCostEstimatePeriod,
    LaborCostEstimateRecordSnapshot,
    LaborCostEstimateStaffSummary,
    ShiftPattern,
    ShiftPatternSegment,
    StaffAllowanceAssignment,
    StaffCompensationProfile,
    WeeklyShiftTemplate,
    WeeklyShiftTemplateEntry,
)


class ShiftPatternSegmentInline(admin.TabularInline):
    model = ShiftPatternSegment
    extra = 0


@admin.register(ShiftPattern)
class ShiftPatternAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "location", "display_order", "is_active")
    list_filter = ("location", "is_active")
    search_fields = ("code", "name", "short_name")
    inlines = [ShiftPatternSegmentInline]


class WeeklyShiftTemplateEntryInline(admin.TabularInline):
    model = WeeklyShiftTemplateEntry
    extra = 0


@admin.register(WeeklyShiftTemplate)
class WeeklyShiftTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "location", "display_order", "is_active")
    list_filter = ("location", "is_active")
    search_fields = ("code", "name")
    inlines = [WeeklyShiftTemplateEntryInline]


@admin.register(AttendanceClosingPeriod)
class AttendanceClosingPeriodAdmin(admin.ModelAdmin):
    list_display = ("location", "year", "month", "status", "closed_at", "is_active")
    list_filter = ("location", "status", "is_active")
    search_fields = ("name", "location__code", "location__name")


@admin.register(AttendanceClosingRecordSnapshot)
class AttendanceClosingRecordSnapshotAdmin(admin.ModelAdmin):
    list_display = ("closing_period", "work_date", "employee_code_snapshot", "status_snapshot", "warning_count")
    list_filter = ("closing_period__location", "status_snapshot")
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot")


@admin.register(AttendanceClosingStaffSummary)
class AttendanceClosingStaffSummaryAdmin(admin.ModelAdmin):
    list_display = ("closing_period", "employee_code_snapshot", "worked_minutes", "warning_count")
    list_filter = ("closing_period__location",)
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot")


@admin.register(StaffCompensationProfile)
class StaffCompensationProfileAdmin(admin.ModelAdmin):
    list_display = ("location", "staff", "employment_type", "valid_from", "valid_to", "is_active")
    list_filter = ("location", "employment_type", "is_active")
    search_fields = ("staff__display_name", "staff__employee_code", "notes")


@admin.register(StaffAllowanceAssignment)
class StaffAllowanceAssignmentAdmin(admin.ModelAdmin):
    list_display = ("location", "staff", "code", "name", "allowance_type", "valid_from", "valid_to", "is_active")
    list_filter = ("location", "allowance_type", "is_active")
    search_fields = ("staff__display_name", "staff__employee_code", "code", "name")


@admin.register(LaborCostEstimatePeriod)
class LaborCostEstimatePeriodAdmin(admin.ModelAdmin):
    list_display = ("location", "year", "month", "status", "finalized_at", "is_active")
    list_filter = ("location", "status", "is_active")
    search_fields = ("name", "location__code", "location__name")


@admin.register(LaborCostEstimateRecordSnapshot)
class LaborCostEstimateRecordSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "estimate_period",
        "work_date",
        "employee_code_snapshot",
        "estimated_total",
        "warning_count",
        "error_count",
    )
    list_filter = ("estimate_period__location", "employment_type_snapshot")
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot")


@admin.register(LaborCostEstimateStaffSummary)
class LaborCostEstimateStaffSummaryAdmin(admin.ModelAdmin):
    list_display = ("estimate_period", "employee_code_snapshot", "estimated_total", "warning_count", "error_count")
    list_filter = ("estimate_period__location", "employment_type_snapshot")
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot")


@admin.register(LaborCostEstimateAllowanceSnapshot)
class LaborCostEstimateAllowanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("estimate_period", "employee_code_snapshot", "code_snapshot", "estimated_amount", "warning_count")
    list_filter = ("estimate_period__location", "allowance_type_snapshot")
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot", "code_snapshot", "name_snapshot")


@admin.register(LaborCostBudgetPeriod)
class LaborCostBudgetPeriodAdmin(admin.ModelAdmin):
    list_display = ("location", "year", "month", "budget_amount", "status", "approved_at", "is_active")
    list_filter = ("location", "status", "is_active")
    search_fields = ("name", "location__code", "location__name")


@admin.register(LaborCostBudgetPlanRecordSnapshot)
class LaborCostBudgetPlanRecordSnapshotAdmin(admin.ModelAdmin):
    list_display = ("budget_period", "work_date", "employee_code_snapshot", "planned_total", "warning_count")
    list_filter = ("budget_period__location", "plan_source_snapshot", "employment_type_snapshot")
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot")


@admin.register(LaborCostBudgetStaffSummary)
class LaborCostBudgetStaffSummaryAdmin(admin.ModelAdmin):
    list_display = ("budget_period", "employee_code_snapshot", "planned_total", "actual_estimated_total")
    list_filter = ("budget_period__location", "employment_type_snapshot")
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot")


@admin.register(LaborCostBudgetDailySummary)
class LaborCostBudgetDailySummaryAdmin(admin.ModelAdmin):
    list_display = ("budget_period", "work_date", "planned_total", "actual_estimated_total")
    list_filter = ("budget_period__location",)


@admin.register(LaborCostBudgetAllowanceSnapshot)
class LaborCostBudgetAllowanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("budget_period", "employee_code_snapshot", "code_snapshot", "planned_amount")
    list_filter = ("budget_period__location", "allowance_type_snapshot")
    search_fields = ("staff_display_name_snapshot", "employee_code_snapshot", "code_snapshot", "name_snapshot")
