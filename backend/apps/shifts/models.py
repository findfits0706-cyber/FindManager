import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.operations.models import ActiveOrderedModel, Location, StaffLocation, WorkArea, WorkType, WorkTypeAvailability


class ShiftPattern(ActiveOrderedModel):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="shift_patterns")
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta(ActiveOrderedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["location", "code"], name="unique_shift_pattern_code_per_location"),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.name}"


class ShiftPatternSegment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shift_pattern = models.ForeignKey(ShiftPattern, on_delete=models.PROTECT, related_name="segments")
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, related_name="shift_pattern_segments")
    work_area = models.ForeignKey(
        WorkArea,
        on_delete=models.PROTECT,
        related_name="shift_pattern_segments",
        null=True,
        blank=True,
    )
    start_offset_minutes = models.PositiveIntegerField()
    end_offset_minutes = models.PositiveIntegerField()
    display_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_offset_minutes", "display_order", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_offset_minutes__gte=0) & Q(start_offset_minutes__lt=2880),
                name="shift_segment_start_offset_range",
            ),
            models.CheckConstraint(
                condition=Q(end_offset_minutes__gt=0) & Q(end_offset_minutes__lte=2880),
                name="shift_segment_end_offset_range",
            ),
            models.CheckConstraint(
                condition=Q(end_offset_minutes__gt=models.F("start_offset_minutes")),
                name="shift_segment_end_after_start",
            ),
        ]

    @property
    def duration_minutes(self):
        return self.end_offset_minutes - self.start_offset_minutes

    def clean(self):
        errors = {}
        if self.shift_pattern_id and not self.shift_pattern.location.is_active:
            errors["shift_pattern"] = "Shift pattern location must be active."
        if self.work_type_id and not self.work_type.is_active:
            errors["work_type"] = "Inactive work types cannot be assigned."
        if self.work_area_id:
            if not self.work_area.is_active:
                errors["work_area"] = "Inactive work areas cannot be assigned."
            elif self.shift_pattern_id and self.work_area.location_id != self.shift_pattern.location_id:
                errors["work_area"] = "work_area must belong to the shift pattern location."

        if self.start_offset_minutes < 0 or self.start_offset_minutes >= 2880:
            errors["start_offset_minutes"] = "start_offset_minutes must be between 0 and 2879."
        if self.end_offset_minutes <= 0 or self.end_offset_minutes > 2880:
            errors["end_offset_minutes"] = "end_offset_minutes must be between 1 and 2880."
        if self.end_offset_minutes <= self.start_offset_minutes:
            errors["end_offset_minutes"] = "end_offset_minutes must be after start_offset_minutes."
        if self.start_offset_minutes % 15 != 0:
            errors["start_offset_minutes"] = "start_offset_minutes must be in 15-minute increments."
        if self.end_offset_minutes % 15 != 0:
            errors["end_offset_minutes"] = "end_offset_minutes must be in 15-minute increments."
        if self.end_offset_minutes - self.start_offset_minutes > 1440:
            errors["end_offset_minutes"] = "A segment cannot exceed 24 hours."

        if self.shift_pattern_id and self.work_type_id:
            availability = WorkTypeAvailability.objects.filter(
                work_type_id=self.work_type_id,
                location_id=self.shift_pattern.location_id,
                is_active=True,
                work_type__is_active=True,
                location__is_active=True,
            )
            if self.work_area_id:
                availability = availability.filter(Q(work_area__isnull=True) | Q(work_area_id=self.work_area_id))
            if not availability.exists():
                errors["work_type"] = "This work type is not available for the selected location or area."

        if errors:
            raise ValidationError(errors)


class WeeklyShiftTemplate(ActiveOrderedModel):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="weekly_shift_templates")
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta(ActiveOrderedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["location", "code"], name="unique_weekly_template_code_per_location"),
        ]

    def clean(self):
        if self.location_id and not self.location.is_active:
            raise ValidationError({"location": "Inactive locations cannot be assigned."})

    def __str__(self):
        return f"{self.location.short_name} / {self.name}"


class WeeklyShiftTemplateEntry(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    weekly_shift_template = models.ForeignKey(
        WeeklyShiftTemplate,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="weekly_shift_entries")
    shift_pattern = models.ForeignKey(ShiftPattern, on_delete=models.PROTECT, related_name="weekly_template_entries")
    notes = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["staff__display_name", "weekday", "display_order", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(weekday__gte=0) & Q(weekday__lte=6), name="weekly_entry_weekday_range"),
            models.UniqueConstraint(
                fields=["weekly_shift_template", "weekday", "staff"],
                condition=Q(is_active=True),
                name="unique_active_weekly_entry_per_staff_weekday",
            ),
        ]

    def clean(self):
        errors = {}
        if self.weekday < 0 or self.weekday > 6:
            errors["weekday"] = "weekday must be between 0 and 6."
        if self.staff_id and not self.staff.is_login_allowed():
            errors["staff"] = "Inactive staff cannot be assigned."
        if self.shift_pattern_id and not self.shift_pattern.is_active:
            errors["shift_pattern"] = "Inactive shift patterns cannot be assigned."
        if (
            self.weekly_shift_template_id
            and self.shift_pattern_id
            and self.weekly_shift_template.location_id != self.shift_pattern.location_id
        ):
            errors["shift_pattern"] = "shift_pattern must belong to the same location as the template."
        if self.weekly_shift_template_id and self.staff_id:
            has_location = StaffLocation.objects.filter(
                staff_id=self.staff_id,
                location_id=self.weekly_shift_template.location_id,
                is_active=True,
                staff__is_active=True,
                location__is_active=True,
            ).exists()
            if not has_location:
                errors["staff"] = "Staff must have an active location assignment for this template location."

        if self.is_active and self.weekly_shift_template_id and self.staff_id:
            duplicate = WeeklyShiftTemplateEntry.objects.filter(
                weekly_shift_template_id=self.weekly_shift_template_id,
                weekday=self.weekday,
                staff_id=self.staff_id,
                is_active=True,
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors["non_field_errors"] = "This staff already has an active pattern for this weekday."

        # StaffCapability is intentionally not checked in phase 3 because templates do not have dates.
        # Phase 4 will validate dated StaffLocation and StaffCapability records when expanding monthly shifts.
        if errors:
            raise ValidationError(errors)


class MonthlyShiftPlan(models.Model):
    class WorkflowStatus(models.TextChoices):
        DRAFT = "draft", "draft"
        CONFIRMED = "confirmed", "confirmed"
        PUBLISHED = "published", "published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="monthly_shift_plans")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=150)
    notes = models.TextField(blank=True)
    source_weekly_template = models.ForeignKey(
        WeeklyShiftTemplate,
        on_delete=models.PROTECT,
        related_name="generated_monthly_shift_plans",
        null=True,
        blank=True,
    )
    last_generated_at = models.DateTimeField(null=True, blank=True)
    last_generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_plans_generated",
        null=True,
        blank=True,
    )
    workflow_status = models.CharField(
        max_length=20,
        choices=WorkflowStatus.choices,
        default=WorkflowStatus.DRAFT,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_plans_confirmed",
        null=True,
        blank=True,
    )
    confirmed_content_hash = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_plans_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_plans_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "-month", "location__display_order", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(year__gte=2000) & Q(year__lte=2100), name="monthly_plan_year_range"),
            models.CheckConstraint(condition=Q(month__gte=1) & Q(month__lte=12), name="monthly_plan_month_range"),
            models.UniqueConstraint(
                fields=["location", "year", "month"],
                condition=Q(is_active=True),
                name="unique_active_monthly_plan_location_month",
            ),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.year < 2000 or self.year > 2100:
            errors["year"] = "year must be between 2000 and 2100."
        if self.month < 1 or self.month > 12:
            errors["month"] = "month must be between 1 and 12."
        if self.source_weekly_template_id and self.source_weekly_template.location_id != self.location_id:
            errors["source_weekly_template"] = "Template location must match plan location."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.year}-{self.month:02d}"


class MonthlyShiftAssignment(models.Model):
    class SourceType(models.TextChoices):
        TEMPLATE = "template", "template"
        MANUAL = "manual", "manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    monthly_shift_plan = models.ForeignKey(MonthlyShiftPlan, on_delete=models.PROTECT, related_name="assignments")
    work_date = models.DateField()
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="monthly_shift_assignments"
    )
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    source_weekly_template_entry = models.ForeignKey(
        WeeklyShiftTemplateEntry,
        on_delete=models.PROTECT,
        related_name="monthly_shift_assignments",
        null=True,
        blank=True,
    )
    source_shift_pattern = models.ForeignKey(
        ShiftPattern,
        on_delete=models.PROTECT,
        related_name="monthly_shift_assignments",
        null=True,
        blank=True,
    )
    pattern_code_snapshot = models.CharField(max_length=50, blank=True)
    pattern_name_snapshot = models.CharField(max_length=150, blank=True)
    pattern_short_name_snapshot = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_customized = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_assignments_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_assignments_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["work_date", "display_order", "staff__display_name", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["monthly_shift_plan", "work_date", "staff"],
                condition=Q(is_active=True),
                name="unique_active_monthly_assignment_cell",
            ),
        ]

    def clean(self):
        errors = {}
        if self.monthly_shift_plan_id and self.work_date:
            if (
                self.work_date.year != self.monthly_shift_plan.year
                or self.work_date.month != self.monthly_shift_plan.month
            ):
                errors["work_date"] = "work_date must be within the monthly shift plan."
        if self.staff_id and not self.staff.is_login_allowed():
            errors["staff"] = "Inactive staff cannot be assigned."
        if (
            self.monthly_shift_plan_id
            and self.source_shift_pattern_id
            and self.source_shift_pattern.location_id != self.monthly_shift_plan.location_id
        ):
            errors["source_shift_pattern"] = "Shift pattern location must match plan location."
        if self.is_active and self.monthly_shift_plan_id and self.work_date and self.staff_id:
            duplicate = MonthlyShiftAssignment.objects.filter(
                monthly_shift_plan_id=self.monthly_shift_plan_id,
                work_date=self.work_date,
                staff_id=self.staff_id,
                is_active=True,
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors["non_field_errors"] = "This staff already has an active assignment on this date."
        if errors:
            raise ValidationError(errors)


class MonthlyShiftSegment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    monthly_shift_assignment = models.ForeignKey(
        MonthlyShiftAssignment,
        on_delete=models.PROTECT,
        related_name="segments",
    )
    source_pattern_segment = models.ForeignKey(
        ShiftPatternSegment,
        on_delete=models.PROTECT,
        related_name="monthly_shift_segments",
        null=True,
        blank=True,
    )
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, related_name="monthly_shift_segments")
    work_area = models.ForeignKey(
        WorkArea,
        on_delete=models.PROTECT,
        related_name="monthly_shift_segments",
        null=True,
        blank=True,
    )
    work_type_name_snapshot = models.CharField(max_length=150)
    work_type_short_name_snapshot = models.CharField(max_length=100)
    work_type_color_key_snapshot = models.CharField(max_length=20)
    work_type_is_break_snapshot = models.BooleanField(default=False)
    work_area_name_snapshot = models.CharField(max_length=150, blank=True)
    start_offset_minutes = models.IntegerField()
    end_offset_minutes = models.IntegerField()
    display_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_offset_minutes", "display_order", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_offset_minutes__gte=0) & Q(start_offset_minutes__lt=2880),
                name="monthly_segment_start_offset_range",
            ),
            models.CheckConstraint(
                condition=Q(end_offset_minutes__gt=0) & Q(end_offset_minutes__lte=2880),
                name="monthly_segment_end_offset_range",
            ),
            models.CheckConstraint(
                condition=Q(end_offset_minutes__gt=models.F("start_offset_minutes")),
                name="monthly_segment_end_after_start",
            ),
        ]

    @property
    def duration_minutes(self):
        return self.end_offset_minutes - self.start_offset_minutes

    def clean(self):
        errors = {}
        if self.work_type_id and not self.work_type.is_active:
            errors["work_type"] = "Inactive work types cannot be assigned."
        if self.work_area_id:
            if not self.work_area.is_active:
                errors["work_area"] = "Inactive work areas cannot be assigned."
            elif (
                self.monthly_shift_assignment_id
                and self.work_area.location_id != self.monthly_shift_assignment.monthly_shift_plan.location_id
            ):
                errors["work_area"] = "work_area must belong to the monthly shift plan location."
        if self.start_offset_minutes < 0 or self.start_offset_minutes >= 2880:
            errors["start_offset_minutes"] = "start_offset_minutes must be between 0 and 2879."
        if self.end_offset_minutes <= 0 or self.end_offset_minutes > 2880:
            errors["end_offset_minutes"] = "end_offset_minutes must be between 1 and 2880."
        if self.end_offset_minutes <= self.start_offset_minutes:
            errors["end_offset_minutes"] = "end_offset_minutes must be after start_offset_minutes."
        if self.start_offset_minutes % 15 != 0:
            errors["start_offset_minutes"] = "start_offset_minutes must be in 15-minute increments."
        if self.end_offset_minutes % 15 != 0:
            errors["end_offset_minutes"] = "end_offset_minutes must be in 15-minute increments."
        if self.end_offset_minutes - self.start_offset_minutes > 1440:
            errors["end_offset_minutes"] = "A segment cannot exceed 24 hours."
        if errors:
            raise ValidationError(errors)


class MonthlyShiftPublication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    monthly_shift_plan = models.ForeignKey(
        MonthlyShiftPlan,
        on_delete=models.PROTECT,
        related_name="publications",
    )
    version = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="monthly_shift_publications")
    location_name_snapshot = models.CharField(max_length=150)
    location_short_name_snapshot = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    plan_name_snapshot = models.CharField(max_length=150)
    plan_notes_snapshot = models.TextField(blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_publications_published",
    )
    published_at = models.DateTimeField()
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_publications_withdrawn",
        null=True,
        blank=True,
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["monthly_shift_plan", "version"],
                name="unique_monthly_shift_publication_version",
            ),
            models.UniqueConstraint(
                fields=["monthly_shift_plan"],
                condition=Q(is_active=True),
                name="unique_active_monthly_shift_publication",
            ),
        ]

    def __str__(self):
        return f"{self.location_short_name_snapshot} / {self.year}-{self.month:02d} v{self.version}"


class MonthlyShiftPublicationAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication = models.ForeignKey(
        MonthlyShiftPublication,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    source_assignment = models.ForeignKey(
        MonthlyShiftAssignment,
        on_delete=models.PROTECT,
        related_name="publication_snapshots",
    )
    work_date = models.DateField()
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monthly_shift_publication_assignments",
    )
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    source_type = models.CharField(max_length=20, choices=MonthlyShiftAssignment.SourceType.choices)
    is_customized = models.BooleanField(default=False)
    pattern_code_snapshot = models.CharField(max_length=50, blank=True)
    pattern_name_snapshot = models.CharField(max_length=150, blank=True)
    pattern_short_name_snapshot = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    warning_count_snapshot = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["work_date", "display_order", "employee_code_snapshot", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "work_date", "staff"],
                name="unique_publication_assignment_cell",
            ),
        ]


class MonthlyShiftPublicationSegment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication_assignment = models.ForeignKey(
        MonthlyShiftPublicationAssignment,
        on_delete=models.PROTECT,
        related_name="segments",
    )
    source_segment = models.ForeignKey(
        MonthlyShiftSegment,
        on_delete=models.PROTECT,
        related_name="publication_snapshots",
    )
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, related_name="monthly_shift_publication_segments")
    work_area = models.ForeignKey(
        WorkArea,
        on_delete=models.PROTECT,
        related_name="monthly_shift_publication_segments",
        null=True,
        blank=True,
    )
    work_type_name_snapshot = models.CharField(max_length=150)
    work_type_short_name_snapshot = models.CharField(max_length=100)
    work_type_color_key_snapshot = models.CharField(max_length=20)
    work_type_is_break_snapshot = models.BooleanField(default=False)
    work_area_name_snapshot = models.CharField(max_length=150, blank=True)
    start_offset_minutes = models.IntegerField()
    end_offset_minutes = models.IntegerField()
    display_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_offset_minutes", "display_order", "created_at"]


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "open"
        CLOCKED_IN = "clocked_in", "clocked_in"
        ON_BREAK = "on_break", "on_break"
        CLOCKED_OUT = "clocked_out", "clocked_out"
        PENDING_CORRECTION = "pending_correction", "pending_correction"
        CONFIRMED = "confirmed", "confirmed"
        VOID = "void", "void"

    class Source(models.TextChoices):
        SCHEDULED = "scheduled", "scheduled"
        UNSCHEDULED = "unscheduled", "unscheduled"
        MANUAL = "manual", "manual"
        CORRECTED = "corrected", "corrected"
        IMPORTED = "imported", "imported"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="attendance_records")
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_records")
    work_date = models.DateField()
    monthly_shift_plan = models.ForeignKey(
        MonthlyShiftPlan,
        on_delete=models.PROTECT,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    monthly_shift_assignment = models.ForeignKey(
        MonthlyShiftAssignment,
        on_delete=models.PROTECT,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(
        MonthlyShiftPublication,
        on_delete=models.PROTECT,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    publication_assignment = models.ForeignKey(
        MonthlyShiftPublicationAssignment,
        on_delete=models.PROTECT,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.OPEN)
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.UNSCHEDULED)
    scheduled_start_offset_minutes = models.IntegerField(null=True, blank=True)
    scheduled_end_offset_minutes = models.IntegerField(null=True, blank=True)
    scheduled_pattern_name_snapshot = models.CharField(max_length=150, blank=True)
    scheduled_pattern_short_name_snapshot = models.CharField(max_length=100, blank=True)
    actual_clock_in_at = models.DateTimeField(null=True, blank=True)
    actual_clock_out_at = models.DateTimeField(null=True, blank=True)
    actual_start_offset_minutes = models.IntegerField(null=True, blank=True)
    actual_end_offset_minutes = models.IntegerField(null=True, blank=True)
    break_minutes = models.PositiveIntegerField(default=0)
    worked_minutes = models.PositiveIntegerField(default=0)
    difference_start_minutes = models.IntegerField(null=True, blank=True)
    difference_end_minutes = models.IntegerField(null=True, blank=True)
    difference_worked_minutes = models.IntegerField(null=True, blank=True)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    manager_note = models.TextField(blank=True)
    staff_note = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_records_confirmed",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-work_date", "location__display_order", "staff__employee_code", "created_at"]
        indexes = [
            models.Index(fields=["location", "work_date"], name="attendance_location_date_idx"),
            models.Index(fields=["staff", "work_date"], name="attendance_staff_date_idx"),
            models.Index(fields=["status", "source"], name="attendance_status_source_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "staff", "work_date"],
                condition=Q(is_active=True),
                name="unique_active_attendance_record_day",
            ),
            models.CheckConstraint(
                condition=Q(scheduled_start_offset_minutes__isnull=True)
                | (Q(scheduled_start_offset_minutes__gte=0) & Q(scheduled_start_offset_minutes__lt=2880)),
                name="attendance_scheduled_start_range",
            ),
            models.CheckConstraint(
                condition=Q(scheduled_end_offset_minutes__isnull=True)
                | (Q(scheduled_end_offset_minutes__gt=0) & Q(scheduled_end_offset_minutes__lte=2880)),
                name="attendance_scheduled_end_range",
            ),
            models.CheckConstraint(
                condition=Q(actual_start_offset_minutes__isnull=True)
                | (Q(actual_start_offset_minutes__gte=0) & Q(actual_start_offset_minutes__lt=2880)),
                name="attendance_actual_start_range",
            ),
            models.CheckConstraint(
                condition=Q(actual_end_offset_minutes__isnull=True)
                | (Q(actual_end_offset_minutes__gt=0) & Q(actual_end_offset_minutes__lte=2880)),
                name="attendance_actual_end_range",
            ),
        ]

    def clean(self):
        errors = {}
        for field in [
            "scheduled_start_offset_minutes",
            "scheduled_end_offset_minutes",
            "actual_start_offset_minutes",
            "actual_end_offset_minutes",
        ]:
            value = getattr(self, field)
            if value is not None and value % 15 != 0:
                errors[field] = "offset must be in 15-minute increments."
        if (
            self.actual_start_offset_minutes is not None
            and self.actual_end_offset_minutes is not None
            and self.actual_start_offset_minutes >= self.actual_end_offset_minutes
        ):
            errors["actual_end_offset_minutes"] = "actual_end_offset_minutes must be after start."
        if (
            self.scheduled_start_offset_minutes is not None
            and self.scheduled_end_offset_minutes is not None
            and self.scheduled_start_offset_minutes >= self.scheduled_end_offset_minutes
        ):
            errors["scheduled_end_offset_minutes"] = "scheduled_end_offset_minutes must be after start."
        if self.publication_assignment_id:
            assignment = self.publication_assignment
            if self.publication_id and assignment.publication_id != self.publication_id:
                errors["publication_assignment"] = "publication_assignment must belong to publication."
            if self.location_id and assignment.publication.location_id != self.location_id:
                errors["location"] = "location must match publication assignment."
            if self.staff_id and assignment.staff_id != self.staff_id:
                errors["staff"] = "staff must match publication assignment."
            if self.work_date and assignment.work_date != self.work_date:
                errors["work_date"] = "work_date must match publication assignment."
        if self.monthly_shift_assignment_id:
            assignment = self.monthly_shift_assignment
            if self.monthly_shift_plan_id and assignment.monthly_shift_plan_id != self.monthly_shift_plan_id:
                errors["monthly_shift_assignment"] = "monthly_shift_assignment must belong to monthly_shift_plan."
            if self.location_id and assignment.monthly_shift_plan.location_id != self.location_id:
                errors["location"] = "location must match monthly shift assignment."
            if self.staff_id and assignment.staff_id != self.staff_id:
                errors["staff"] = "staff must match monthly shift assignment."
            if self.work_date and assignment.work_date != self.work_date:
                errors["work_date"] = "work_date must match monthly shift assignment."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.work_date} / {self.staff} / {self.status}"


class AttendanceEvent(models.Model):
    class EventType(models.TextChoices):
        CLOCK_IN = "clock_in", "clock_in"
        BREAK_START = "break_start", "break_start"
        BREAK_END = "break_end", "break_end"
        CLOCK_OUT = "clock_out", "clock_out"
        MANUAL_ADJUSTMENT = "manual_adjustment", "manual_adjustment"
        CORRECTION_APPLIED = "correction_applied", "correction_applied"
        VOIDED = "voided", "voided"
        CONFIRMED = "confirmed", "confirmed"
        UNCONFIRMED = "unconfirmed", "unconfirmed"

    class Source(models.TextChoices):
        SELF = "self", "self"
        MANAGER = "manager", "manager"
        SYSTEM = "system", "system"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    occurred_at = models.DateTimeField()
    offset_minutes = models.IntegerField()
    source = models.CharField(max_length=20, choices=Source.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_events")
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "created_at"]
        indexes = [
            models.Index(fields=["attendance_record", "event_type"], name="att_event_record_type_idx"),
            models.Index(fields=["occurred_at"], name="attendance_event_occurred_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(offset_minutes__gte=0) & Q(offset_minutes__lte=2880),
                name="attendance_event_offset_range",
            ),
        ]

    def __str__(self):
        return f"{self.attendance_record_id} / {self.event_type} / {self.occurred_at}"


class AttendanceCorrectionRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        SUBMITTED = "submitted", "submitted"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"
        CANCELLED = "cancelled", "cancelled"
        APPLIED = "applied", "applied"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_correction_requests",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    requested_clock_in_at = models.DateTimeField(null=True, blank=True)
    requested_clock_out_at = models.DateTimeField(null=True, blank=True)
    requested_break_minutes = models.PositiveIntegerField(null=True, blank=True)
    requested_staff_note = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    manager_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_corrections_approved",
        null=True,
        blank=True,
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_corrections_rejected",
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_corrections_cancelled",
        null=True,
        blank=True,
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_corrections_applied",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="attendance_corr_status_idx"),
            models.Index(fields=["requester", "created_at"], name="attendance_corr_requester_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["attendance_record"],
                condition=Q(is_active=True, status__in=["draft", "submitted", "approved"]),
                name="unique_open_attendance_correction",
            ),
            models.CheckConstraint(
                condition=Q(requested_clock_in_at__isnull=True)
                | Q(requested_clock_out_at__isnull=True)
                | Q(requested_clock_out_at__gt=models.F("requested_clock_in_at")),
                name="attendance_corr_clock_out_after_in",
            ),
        ]

    def clean(self):
        errors = {}
        if self.attendance_record_id and self.requester_id and self.attendance_record.staff_id != self.requester_id:
            errors["attendance_record"] = "requester must be the attendance record staff."
        if self.requested_clock_in_at and self.requested_clock_out_at:
            if self.requested_clock_in_at >= self.requested_clock_out_at:
                errors["requested_clock_out_at"] = "requested_clock_out_at must be after requested_clock_in_at."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.attendance_record_id} / {self.status}"


class ShiftChangeRequest(models.Model):
    class RequestType(models.TextChoices):
        DROP_SHIFT = "drop_shift", "drop_shift"
        SWAP_SHIFT = "swap_shift", "swap_shift"
        COVER_REQUEST = "cover_request", "cover_request"
        CHANGE_TIME = "change_time", "change_time"
        CHANGE_ASSIGNMENT = "change_assignment", "change_assignment"
        MANAGER_ADJUSTMENT = "manager_adjustment", "manager_adjustment"
        NOTE = "note", "note"

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        SUBMITTED = "submitted", "submitted"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"
        CANCELLED = "cancelled", "cancelled"
        APPLIED = "applied", "applied"
        CLOSED = "closed", "closed"

    class Priority(models.TextChoices):
        HIGH = "high", "high"
        NORMAL = "normal", "normal"
        LOW = "low", "low"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="shift_change_requests")
    monthly_shift_plan = models.ForeignKey(
        MonthlyShiftPlan,
        on_delete=models.PROTECT,
        related_name="shift_change_requests",
    )
    publication = models.ForeignKey(
        MonthlyShiftPublication,
        on_delete=models.PROTECT,
        related_name="shift_change_requests",
    )
    publication_assignment = models.ForeignKey(
        MonthlyShiftPublicationAssignment,
        on_delete=models.PROTECT,
        related_name="shift_change_requests",
        null=True,
        blank=True,
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_requested",
    )
    target_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_targeted",
    )
    request_type = models.CharField(max_length=32, choices=RequestType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    work_date = models.DateField()
    original_start_offset_minutes = models.IntegerField(null=True, blank=True)
    original_end_offset_minutes = models.IntegerField(null=True, blank=True)
    original_pattern_name_snapshot = models.CharField(max_length=150, blank=True)
    original_pattern_short_name_snapshot = models.CharField(max_length=100, blank=True)
    requested_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_requested_as_cover",
        null=True,
        blank=True,
    )
    requested_work_date = models.DateField(null=True, blank=True)
    requested_shift_pattern = models.ForeignKey(
        ShiftPattern,
        on_delete=models.PROTECT,
        related_name="shift_change_requests",
        null=True,
        blank=True,
    )
    requested_start_offset_minutes = models.IntegerField(null=True, blank=True)
    requested_end_offset_minutes = models.IntegerField(null=True, blank=True)
    requested_notes = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    manager_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_submitted",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_approved",
        null=True,
        blank=True,
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_rejected",
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_cancelled",
        null=True,
        blank=True,
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_change_requests_applied",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        indexes = [
            models.Index(fields=["location", "work_date"], name="shift_change_location_date_idx"),
            models.Index(fields=["status", "request_type"], name="shift_change_status_type_idx"),
            models.Index(fields=["requester", "work_date"], name="shift_chg_requester_dt_idx"),
            models.Index(fields=["target_staff", "work_date"], name="shift_change_target_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(original_start_offset_minutes__isnull=True)
                | (Q(original_start_offset_minutes__gte=0) & Q(original_start_offset_minutes__lt=2880)),
                name="shift_change_original_start_range",
            ),
            models.CheckConstraint(
                condition=Q(original_end_offset_minutes__isnull=True)
                | (Q(original_end_offset_minutes__gt=0) & Q(original_end_offset_minutes__lte=2880)),
                name="shift_change_original_end_range",
            ),
            models.CheckConstraint(
                condition=Q(requested_start_offset_minutes__isnull=True)
                | (Q(requested_start_offset_minutes__gte=0) & Q(requested_start_offset_minutes__lt=2880)),
                name="shift_change_requested_start_range",
            ),
            models.CheckConstraint(
                condition=Q(requested_end_offset_minutes__isnull=True)
                | (Q(requested_end_offset_minutes__gt=0) & Q(requested_end_offset_minutes__lte=2880)),
                name="shift_change_requested_end_range",
            ),
        ]

    def clean(self):
        errors = {}
        if self.publication_assignment_id:
            assignment = self.publication_assignment
            if self.publication_id and assignment.publication_id != self.publication_id:
                errors["publication_assignment"] = "publication_assignment must belong to publication."
            if (
                self.monthly_shift_plan_id
                and assignment.publication.monthly_shift_plan_id != self.monthly_shift_plan_id
            ):
                errors["monthly_shift_plan"] = "monthly_shift_plan must match the publication assignment."
            if self.location_id and assignment.publication.location_id != self.location_id:
                errors["location"] = "location must match the publication assignment."
            if self.work_date and assignment.work_date != self.work_date:
                errors["work_date"] = "work_date must match the publication assignment."
            if self.target_staff_id and assignment.staff_id != self.target_staff_id:
                errors["target_staff"] = "target_staff must match the publication assignment staff."
        if self.work_date and self.monthly_shift_plan_id:
            if (
                self.work_date.year != self.monthly_shift_plan.year
                or self.work_date.month != self.monthly_shift_plan.month
            ):
                errors["work_date"] = "work_date must be within the monthly shift plan."
        if self.requested_work_date and self.monthly_shift_plan_id:
            if (
                self.requested_work_date.year != self.monthly_shift_plan.year
                or self.requested_work_date.month != self.monthly_shift_plan.month
            ):
                errors["requested_work_date"] = "requested_work_date must be within the monthly shift plan."
        if self.requested_shift_pattern_id and self.monthly_shift_plan_id:
            if self.requested_shift_pattern.location_id != self.monthly_shift_plan.location_id:
                errors["requested_shift_pattern"] = "requested_shift_pattern must belong to the monthly plan location."
        for field in [
            "original_start_offset_minutes",
            "original_end_offset_minutes",
            "requested_start_offset_minutes",
            "requested_end_offset_minutes",
        ]:
            value = getattr(self, field)
            if value is not None and value % 15 != 0:
                errors[field] = "offset must be in 15-minute increments."
        if (
            self.requested_start_offset_minutes is not None
            and self.requested_end_offset_minutes is not None
            and self.requested_start_offset_minutes >= self.requested_end_offset_minutes
        ):
            errors["requested_end_offset_minutes"] = "requested_end_offset_minutes must be after start."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.work_date} / {self.request_type} / {self.status}"


class ShiftRequestPeriod(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        OPEN = "open", "open"
        CLOSED = "closed", "closed"
        ARCHIVED = "archived", "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="shift_request_periods")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_request_periods_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shift_request_periods_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-year", "-month", "location__display_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "year", "month"],
                condition=Q(is_active=True),
                name="unique_active_shift_request_period_month",
            ),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.year < 2000 or self.year > 2100:
            errors["year"] = "year must be between 2000 and 2100."
        if self.month < 1 or self.month > 12:
            errors["month"] = "month must be between 1 and 12."
        if self.opens_at and self.closes_at and self.opens_at > self.closes_at:
            errors["closes_at"] = "closes_at must be on or after opens_at."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.year}-{self.month:02d} requests"


class ShiftRequestSubmission(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        SUBMITTED = "submitted", "submitted"
        RETURNED = "returned", "returned"
        LOCKED = "locked", "locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_period = models.ForeignKey(ShiftRequestPeriod, on_delete=models.PROTECT, related_name="submissions")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shift_request_submissions"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shift_request_submissions_submitted",
    )
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shift_request_submissions_returned",
    )
    return_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["request_period", "staff__display_name", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["request_period", "staff"],
                name="unique_shift_request_submission_staff",
            ),
        ]

    def __str__(self):
        return f"{self.request_period} / {self.staff}"


class ShiftRequestItem(models.Model):
    class RequestType(models.TextChoices):
        DAY_OFF = "day_off", "day_off"
        UNAVAILABLE = "unavailable", "unavailable"
        PREFER_WORK = "prefer_work", "prefer_work"
        PREFER_TIME = "prefer_time", "prefer_time"
        NOTE = "note", "note"

    class Priority(models.TextChoices):
        HIGH = "high", "high"
        NORMAL = "normal", "normal"
        LOW = "low", "low"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(ShiftRequestSubmission, on_delete=models.PROTECT, related_name="items")
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    work_date = models.DateField(null=True, blank=True)
    start_offset_minutes = models.IntegerField(null=True, blank=True)
    end_offset_minutes = models.IntegerField(null=True, blank=True)
    work_type = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        related_name="shift_request_items",
        null=True,
        blank=True,
    )
    work_area = models.ForeignKey(
        WorkArea,
        on_delete=models.PROTECT,
        related_name="shift_request_items",
        null=True,
        blank=True,
    )
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["work_date", "start_offset_minutes", "request_type", "created_at"]

    def clean(self):
        errors = {}
        period = self.submission.request_period if self.submission_id else None
        if self.request_type != self.RequestType.NOTE and not self.work_date:
            errors["work_date"] = "work_date is required."
        if self.work_date and period and (self.work_date.year != period.year or self.work_date.month != period.month):
            errors["work_date"] = "work_date must be within the shift request period."
        needs_time = self.request_type in {self.RequestType.UNAVAILABLE, self.RequestType.PREFER_TIME}
        if needs_time and (self.start_offset_minutes is None or self.end_offset_minutes is None):
            errors["start_offset_minutes"] = "start_offset_minutes and end_offset_minutes are required."
        if self.start_offset_minutes is not None:
            if (
                self.start_offset_minutes < 0
                or self.start_offset_minutes >= 2880
                or self.start_offset_minutes % 15 != 0
            ):
                errors["start_offset_minutes"] = "start_offset_minutes must be 0-2879 in 15-minute increments."
        if self.end_offset_minutes is not None:
            if self.end_offset_minutes <= 0 or self.end_offset_minutes > 2880 or self.end_offset_minutes % 15 != 0:
                errors["end_offset_minutes"] = "end_offset_minutes must be 1-2880 in 15-minute increments."
        if (
            self.start_offset_minutes is not None
            and self.end_offset_minutes is not None
            and self.start_offset_minutes >= self.end_offset_minutes
        ):
            errors["end_offset_minutes"] = "end_offset_minutes must be after start_offset_minutes."
        if self.work_type_id and not self.work_type.is_active:
            errors["work_type"] = "Inactive work types cannot be assigned."
        if self.work_area_id:
            if not self.work_area.is_active:
                errors["work_area"] = "Inactive work areas cannot be assigned."
            elif period and self.work_area.location_id != period.location_id:
                errors["work_area"] = "work_area must belong to the request period location."
        if errors:
            raise ValidationError(errors)
