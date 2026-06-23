from django.contrib import admin

from .models import ShiftPattern, ShiftPatternSegment, WeeklyShiftTemplate, WeeklyShiftTemplateEntry


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
