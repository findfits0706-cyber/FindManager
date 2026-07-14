from django.contrib import admin

from .models import (
    AttendanceClosingPeriod,
    AttendanceClosingRecordSnapshot,
    AttendanceClosingStaffSummary,
    ShiftPattern,
    ShiftPatternSegment,
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
