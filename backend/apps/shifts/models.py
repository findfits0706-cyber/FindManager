import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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


revenue_code_validator = RegexValidator(
    regex=r"^[A-Za-z0-9_-]+$",
    message="code must contain only letters, numbers, hyphens, and underscores.",
)


class RevenueCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="revenue_categories")
    code = models.CharField(max_length=50, validators=[revenue_code_validator])
    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_categories_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_categories_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["location__display_order", "display_order", "code", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["location", "code"], name="uniq_revenue_category_code"),
            models.CheckConstraint(condition=Q(display_order__gte=0), name="revenue_category_order_gte0"),
        ]

    def clean(self):
        if self.location_id and not self.location.is_active:
            raise ValidationError({"location": "Inactive locations cannot be assigned."})

    def __str__(self):
        return f"{self.location.short_name} / {self.name}"


class RevenueBudgetPeriod(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        REVIEW = "review", "review"
        APPROVED = "approved", "approved"
        REOPENED = "reopened", "reopened"
        ARCHIVED = "archived", "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="revenue_budget_periods")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    content_hash = models.CharField(max_length=64, blank=True)
    validation_fingerprint = models.CharField(max_length=64, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_budget_periods_approved",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_budget_periods_reopened",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_budget_periods_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_budget_periods_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-year", "-month", "location__display_order", "created_at"]
        indexes = [
            models.Index(fields=["location", "year", "month"], name="revenue_budget_lookup_idx"),
            models.Index(fields=["status", "is_active"], name="revenue_budget_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "year", "month"],
                condition=Q(is_active=True),
                name="uniq_active_revenue_budget",
            ),
            models.CheckConstraint(condition=Q(year__gte=2000) & Q(year__lte=2100), name="revenue_budget_year_range"),
            models.CheckConstraint(condition=Q(month__gte=1) & Q(month__lte=12), name="revenue_budget_month_range"),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.year < 2000 or self.year > 2100:
            errors["year"] = "year must be between 2000 and 2100."
        if self.month < 1 or self.month > 12:
            errors["month"] = "month must be between 1 and 12."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.year}-{self.month:02d} / {self.status}"


class RevenueBudgetLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget_period = models.ForeignKey(RevenueBudgetPeriod, on_delete=models.CASCADE, related_name="lines")
    category = models.ForeignKey(RevenueCategory, on_delete=models.PROTECT, related_name="budget_lines")
    category_code_snapshot = models.CharField(max_length=50)
    category_name_snapshot = models.CharField(max_length=150)
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "category_code_snapshot", "created_at"]
        indexes = [models.Index(fields=["budget_period", "is_active"], name="revenue_budget_line_idx")]
        constraints = [
            models.UniqueConstraint(fields=["budget_period", "category"], name="uniq_revenue_budget_line"),
            models.CheckConstraint(condition=Q(budget_amount__gte=0), name="revenue_budget_amount_gte0"),
            models.CheckConstraint(condition=Q(display_order__gte=0), name="revenue_budget_order_gte0"),
        ]

    def clean(self):
        errors = {}
        if self.budget_amount is not None and self.budget_amount < 0:
            errors["budget_amount"] = "budget_amount must be greater than or equal to 0."
        if self.budget_period_id and self.category_id:
            if self.budget_period.location_id != self.category.location_id:
                errors["category"] = "category must belong to the budget period location."
            if self._state.adding and not self.category.is_active:
                errors["category"] = "Inactive categories cannot be used for new monthly input."
        if self.budget_period_id and self.budget_period.status in {
            RevenueBudgetPeriod.Status.APPROVED,
            RevenueBudgetPeriod.Status.ARCHIVED,
        }:
            errors["budget_period"] = "Approved or archived budget periods are read-only."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.budget_period_id} / {self.category_code_snapshot}"


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
        if self.actual_start_offset_minutes is not None and self.actual_end_offset_minutes is not None:
            if self.actual_clock_in_at and self.actual_clock_out_at:
                invalid_actual_order = self.actual_clock_in_at >= self.actual_clock_out_at
            else:
                invalid_actual_order = self.actual_start_offset_minutes >= self.actual_end_offset_minutes
            if invalid_actual_order or self.actual_start_offset_minutes > self.actual_end_offset_minutes:
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


class AttendanceClosingPeriod(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        REVIEW = "review", "review"
        CLOSED = "closed", "closed"
        REOPENED = "reopened", "reopened"
        ARCHIVED = "archived", "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="attendance_closing_periods")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    content_hash = models.CharField(max_length=64, blank=True)
    validation_fingerprint = models.CharField(max_length=64, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_closing_periods_closed",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_closing_periods_reopened",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_closing_periods_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_closing_periods_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-year", "-month", "location__display_order", "created_at"]
        indexes = [
            models.Index(fields=["location", "year", "month"], name="att_close_period_lookup_idx"),
            models.Index(fields=["status", "is_active"], name="att_close_period_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "year", "month"],
                condition=Q(is_active=True),
                name="uniq_active_att_close_period",
            ),
            models.CheckConstraint(condition=Q(year__gte=2000) & Q(year__lte=2100), name="att_close_year_range"),
            models.CheckConstraint(condition=Q(month__gte=1) & Q(month__lte=12), name="att_close_month_range"),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.year < 2000 or self.year > 2100:
            errors["year"] = "year must be between 2000 and 2100."
        if self.month < 1 or self.month > 12:
            errors["month"] = "month must be between 1 and 12."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.year}-{self.month:02d} / {self.status}"


class AttendanceClosingRecordSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    closing_period = models.ForeignKey(
        AttendanceClosingPeriod,
        on_delete=models.CASCADE,
        related_name="record_snapshots",
    )
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.PROTECT,
        related_name="closing_snapshots",
        null=True,
        blank=True,
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="attendance_closing_snapshots")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_closing_snapshots",
    )
    location_code_snapshot = models.CharField(max_length=50)
    location_name_snapshot = models.CharField(max_length=150)
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    work_date = models.DateField()
    monthly_shift_plan = models.ForeignKey(
        MonthlyShiftPlan,
        on_delete=models.PROTECT,
        related_name="attendance_closing_snapshots",
        null=True,
        blank=True,
    )
    monthly_shift_assignment = models.ForeignKey(
        MonthlyShiftAssignment,
        on_delete=models.PROTECT,
        related_name="attendance_closing_snapshots",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(
        MonthlyShiftPublication,
        on_delete=models.PROTECT,
        related_name="attendance_closing_snapshots",
        null=True,
        blank=True,
    )
    publication_assignment = models.ForeignKey(
        MonthlyShiftPublicationAssignment,
        on_delete=models.PROTECT,
        related_name="attendance_closing_snapshots",
        null=True,
        blank=True,
    )
    status_snapshot = models.CharField(max_length=32)
    source_snapshot = models.CharField(max_length=32)
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
    manager_note_snapshot = models.TextField(blank=True)
    staff_note_snapshot = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_closing_snapshots_confirmed",
        null=True,
        blank=True,
    )
    confirmed_by_display_name_snapshot = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["work_date", "employee_code_snapshot", "created_at"]
        indexes = [
            models.Index(fields=["closing_period", "work_date"], name="att_close_snap_date_idx"),
            models.Index(fields=["staff", "work_date"], name="att_close_snap_staff_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["closing_period", "staff", "work_date", "location"],
                name="uniq_att_close_snapshot_day",
            ),
        ]

    def __str__(self):
        return f"{self.closing_period_id} / {self.work_date} / {self.staff_id}"


class AttendanceClosingStaffSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    closing_period = models.ForeignKey(
        AttendanceClosingPeriod,
        on_delete=models.CASCADE,
        related_name="staff_summaries",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_closing_summaries",
    )
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    scheduled_days = models.PositiveIntegerField(default=0)
    attendance_record_days = models.PositiveIntegerField(default=0)
    worked_days = models.PositiveIntegerField(default=0)
    unscheduled_work_days = models.PositiveIntegerField(default=0)
    scheduled_minutes = models.PositiveIntegerField(default=0)
    worked_minutes = models.PositiveIntegerField(default=0)
    break_minutes = models.PositiveIntegerField(default=0)
    late_count = models.PositiveIntegerField(default=0)
    early_leave_count = models.PositiveIntegerField(default=0)
    missing_clock_in_count = models.PositiveIntegerField(default=0)
    missing_clock_out_count = models.PositiveIntegerField(default=0)
    open_break_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    confirmed_count = models.PositiveIntegerField(default=0)
    unconfirmed_count = models.PositiveIntegerField(default=0)
    pending_correction_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee_code_snapshot", "staff_display_name_snapshot", "created_at"]
        indexes = [
            models.Index(fields=["closing_period", "staff"], name="att_close_sum_staff_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["closing_period", "staff"],
                name="uniq_att_close_staff_sum",
            ),
        ]

    def __str__(self):
        return f"{self.closing_period_id} / {self.staff_id}"


class StaffCompensationProfile(models.Model):
    class EmploymentType(models.TextChoices):
        HOURLY = "hourly", "hourly"
        MONTHLY_FIXED = "monthly_fixed", "monthly_fixed"
        OTHER = "other", "other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="staff_compensation_profiles")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="compensation_profiles",
    )
    employment_type = models.CharField(
        max_length=32,
        choices=EmploymentType.choices,
        default=EmploymentType.HOURLY,
    )
    base_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fixed_monthly_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_compensation_profiles_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_compensation_profiles_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["location__display_order", "staff__employee_code", "-valid_from", "created_at"]
        indexes = [
            models.Index(fields=["location", "staff", "is_active"], name="comp_profile_lookup_idx"),
            models.Index(fields=["valid_from", "valid_to"], name="comp_profile_period_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_from__lte=models.F("valid_to")),
                name="comp_profile_valid_range",
            ),
            models.CheckConstraint(
                condition=Q(base_hourly_rate__isnull=True) | Q(base_hourly_rate__gte=0),
                name="comp_profile_hourly_gte0",
            ),
            models.CheckConstraint(
                condition=Q(fixed_monthly_amount__isnull=True) | Q(fixed_monthly_amount__gte=0),
                name="comp_profile_fixed_gte0",
            ),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.staff_id and not self.staff.is_login_allowed():
            errors["staff"] = "Inactive staff cannot be assigned."
        if self.valid_to and self.valid_from > self.valid_to:
            errors["valid_to"] = "valid_to must be on or after valid_from."
        if self.employment_type == self.EmploymentType.HOURLY and self.base_hourly_rate is None:
            errors["base_hourly_rate"] = "base_hourly_rate is required for hourly employment_type."
        if self.employment_type == self.EmploymentType.MONTHLY_FIXED and self.fixed_monthly_amount is None:
            errors["fixed_monthly_amount"] = "fixed_monthly_amount is required for monthly_fixed employment_type."
        if self.base_hourly_rate is not None and self.base_hourly_rate < 0:
            errors["base_hourly_rate"] = "base_hourly_rate must be greater than or equal to 0."
        if self.fixed_monthly_amount is not None and self.fixed_monthly_amount < 0:
            errors["fixed_monthly_amount"] = "fixed_monthly_amount must be greater than or equal to 0."
        if self.location_id and self.staff_id and self.valid_from and self.is_active:
            overlap_end = self.valid_to or self.valid_from
            overlapping_profiles = StaffCompensationProfile.objects.filter(
                location_id=self.location_id,
                staff_id=self.staff_id,
                is_active=True,
                valid_from__lte=overlap_end,
            ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=self.valid_from))
            if self.valid_to is None:
                overlapping_profiles = StaffCompensationProfile.objects.filter(
                    location_id=self.location_id,
                    staff_id=self.staff_id,
                    is_active=True,
                ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=self.valid_from))
            if self.pk:
                overlapping_profiles = overlapping_profiles.exclude(pk=self.pk)
            if overlapping_profiles.exists():
                errors["non_field_errors"] = "Active compensation profile periods cannot overlap."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.staff} / {self.valid_from}"


class StaffAllowanceAssignment(models.Model):
    class AllowanceType(models.TextChoices):
        PER_WORKED_DAY = "per_worked_day", "per_worked_day"
        PER_WORKED_HOUR = "per_worked_hour", "per_worked_hour"
        FIXED_MONTHLY = "fixed_monthly", "fixed_monthly"
        MANUAL = "manual", "manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="staff_allowance_assignments")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="allowance_assignments",
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    allowance_type = models.CharField(
        max_length=32,
        choices=AllowanceType.choices,
        default=AllowanceType.PER_WORKED_DAY,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_allowance_assignments_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_allowance_assignments_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["location__display_order", "staff__employee_code", "code", "-valid_from", "created_at"]
        indexes = [
            models.Index(fields=["location", "staff", "code", "is_active"], name="allowance_lookup_idx"),
            models.Index(fields=["valid_from", "valid_to"], name="allowance_period_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_from__lte=models.F("valid_to")),
                name="allowance_valid_range",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="allowance_amount_gte0"),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.staff_id and not self.staff.is_login_allowed():
            errors["staff"] = "Inactive staff cannot be assigned."
        if self.valid_to and self.valid_from > self.valid_to:
            errors["valid_to"] = "valid_to must be on or after valid_from."
        if self.amount is not None and self.amount < 0:
            errors["amount"] = "amount must be greater than or equal to 0."
        if self.location_id and self.staff_id and self.code and self.valid_from and self.is_active:
            overlap_end = self.valid_to or self.valid_from
            overlapping_assignments = StaffAllowanceAssignment.objects.filter(
                location_id=self.location_id,
                staff_id=self.staff_id,
                code=self.code,
                is_active=True,
                valid_from__lte=overlap_end,
            ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=self.valid_from))
            if self.valid_to is None:
                overlapping_assignments = StaffAllowanceAssignment.objects.filter(
                    location_id=self.location_id,
                    staff_id=self.staff_id,
                    code=self.code,
                    is_active=True,
                ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=self.valid_from))
            if self.pk:
                overlapping_assignments = overlapping_assignments.exclude(pk=self.pk)
            if overlapping_assignments.exists():
                errors["non_field_errors"] = "Active allowance assignment periods with the same code cannot overlap."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.staff} / {self.code}"


class LaborCostEstimatePeriod(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        REVIEW = "review", "review"
        FINALIZED = "finalized", "finalized"
        REOPENED = "reopened", "reopened"
        ARCHIVED = "archived", "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="labor_cost_estimate_periods")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    attendance_closing_period = models.ForeignKey(
        AttendanceClosingPeriod,
        on_delete=models.PROTECT,
        related_name="labor_cost_estimate_periods",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    content_hash = models.CharField(max_length=64, blank=True)
    validation_fingerprint = models.CharField(max_length=64, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_estimate_periods_finalized",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_estimate_periods_reopened",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_estimate_periods_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_estimate_periods_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-year", "-month", "location__display_order", "created_at"]
        indexes = [
            models.Index(fields=["location", "year", "month"], name="labor_period_lookup_idx"),
            models.Index(fields=["status", "is_active"], name="labor_period_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "year", "month"],
                condition=Q(is_active=True),
                name="uniq_active_labor_period",
            ),
            models.CheckConstraint(condition=Q(year__gte=2000) & Q(year__lte=2100), name="labor_period_year_range"),
            models.CheckConstraint(condition=Q(month__gte=1) & Q(month__lte=12), name="labor_period_month_range"),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.year < 2000 or self.year > 2100:
            errors["year"] = "year must be between 2000 and 2100."
        if self.month < 1 or self.month > 12:
            errors["month"] = "month must be between 1 and 12."
        if self.attendance_closing_period_id:
            closing = self.attendance_closing_period
            if closing.location_id != self.location_id or closing.year != self.year or closing.month != self.month:
                errors["attendance_closing_period"] = "attendance_closing_period must match location/year/month."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.year}-{self.month:02d} / {self.status}"


class LaborCostEstimateRecordSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate_period = models.ForeignKey(
        LaborCostEstimatePeriod,
        on_delete=models.CASCADE,
        related_name="record_snapshots",
    )
    attendance_closing_snapshot = models.ForeignKey(
        AttendanceClosingRecordSnapshot,
        on_delete=models.PROTECT,
        related_name="labor_cost_snapshots",
        null=True,
        blank=True,
    )
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.PROTECT,
        related_name="labor_cost_snapshots",
        null=True,
        blank=True,
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="labor_cost_record_snapshots")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_record_snapshots",
    )
    location_code_snapshot = models.CharField(max_length=50)
    location_name_snapshot = models.CharField(max_length=150)
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    work_date = models.DateField()
    employment_type_snapshot = models.CharField(max_length=32)
    base_hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fixed_monthly_amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    worked_minutes = models.PositiveIntegerField(default=0)
    worked_hours_decimal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    base_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowance_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["work_date", "employee_code_snapshot", "created_at"]
        indexes = [
            models.Index(fields=["estimate_period", "work_date"], name="labor_snap_date_idx"),
            models.Index(fields=["staff", "work_date"], name="labor_snap_staff_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["estimate_period", "staff", "work_date", "location"],
                name="uniq_labor_snapshot_day",
            ),
        ]

    def __str__(self):
        return f"{self.estimate_period_id} / {self.work_date} / {self.staff_id}"


class LaborCostEstimateStaffSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate_period = models.ForeignKey(
        LaborCostEstimatePeriod,
        on_delete=models.CASCADE,
        related_name="staff_summaries",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_staff_summaries",
    )
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    employment_type_snapshot = models.CharField(max_length=32)
    base_hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fixed_monthly_amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    worked_days = models.PositiveIntegerField(default=0)
    worked_minutes = models.PositiveIntegerField(default=0)
    worked_hours_decimal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    base_pay_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowance_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee_code_snapshot", "staff_display_name_snapshot", "created_at"]
        indexes = [
            models.Index(fields=["estimate_period", "staff"], name="labor_sum_staff_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["estimate_period", "staff"],
                name="uniq_labor_staff_sum",
            ),
        ]

    def __str__(self):
        return f"{self.estimate_period_id} / {self.staff_id}"


class LaborCostEstimateAllowanceSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate_period = models.ForeignKey(
        LaborCostEstimatePeriod,
        on_delete=models.CASCADE,
        related_name="allowance_snapshots",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_allowance_snapshots",
    )
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    allowance_assignment = models.ForeignKey(
        StaffAllowanceAssignment,
        on_delete=models.PROTECT,
        related_name="labor_cost_snapshots",
        null=True,
        blank=True,
    )
    code_snapshot = models.CharField(max_length=50)
    name_snapshot = models.CharField(max_length=150)
    allowance_type_snapshot = models.CharField(max_length=32)
    amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee_code_snapshot", "code_snapshot", "created_at"]
        indexes = [
            models.Index(fields=["estimate_period", "staff"], name="labor_allow_staff_idx"),
            models.Index(fields=["allowance_assignment"], name="labor_allow_assign_idx"),
        ]

    def __str__(self):
        return f"{self.estimate_period_id} / {self.staff_id} / {self.code_snapshot}"


class LaborCostBudgetPeriod(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        REVIEW = "review", "review"
        APPROVED = "approved", "approved"
        REOPENED = "reopened", "reopened"
        ARCHIVED = "archived", "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="labor_cost_budget_periods")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    warning_threshold_percent = models.DecimalField(max_digits=6, decimal_places=2, default=90)
    critical_threshold_percent = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    source_monthly_shift_plan = models.ForeignKey(
        MonthlyShiftPlan,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_periods",
        null=True,
        blank=True,
    )
    source_publication = models.ForeignKey(
        MonthlyShiftPublication,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_periods",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    content_hash = models.CharField(max_length=64, blank=True)
    validation_fingerprint = models.CharField(max_length=64, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_periods_approved",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_periods_reopened",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_periods_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_periods_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-year", "-month", "location__display_order", "created_at"]
        indexes = [
            models.Index(fields=["location", "year", "month"], name="labor_budget_lookup_idx"),
            models.Index(fields=["status", "is_active"], name="labor_budget_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "year", "month"],
                condition=Q(is_active=True),
                name="uniq_active_labor_budget",
            ),
            models.CheckConstraint(condition=Q(year__gte=2000) & Q(year__lte=2100), name="labor_budget_year_range"),
            models.CheckConstraint(condition=Q(month__gte=1) & Q(month__lte=12), name="labor_budget_month_range"),
            models.CheckConstraint(condition=Q(budget_amount__gte=0), name="labor_budget_amount_gte0"),
            models.CheckConstraint(condition=Q(warning_threshold_percent__gte=0), name="labor_budget_warn_gte0"),
            models.CheckConstraint(
                condition=Q(critical_threshold_percent__gte=models.F("warning_threshold_percent")),
                name="labor_budget_critical_gte_warn",
            ),
            models.CheckConstraint(
                condition=Q(critical_threshold_percent__lte=999.99),
                name="labor_budget_critical_lte999",
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
        if self.budget_amount is not None and self.budget_amount < 0:
            errors["budget_amount"] = "budget_amount must be greater than or equal to 0."
        if self.warning_threshold_percent is not None and self.warning_threshold_percent < 0:
            errors["warning_threshold_percent"] = "warning_threshold_percent must be greater than or equal to 0."
        if (
            self.warning_threshold_percent is not None
            and self.critical_threshold_percent is not None
            and self.critical_threshold_percent < self.warning_threshold_percent
        ):
            errors["critical_threshold_percent"] = "critical_threshold_percent must not be below warning threshold."
        if self.critical_threshold_percent is not None and self.critical_threshold_percent > Decimal("999.99"):
            errors["critical_threshold_percent"] = "critical_threshold_percent must be at most 999.99."
        if self.source_monthly_shift_plan_id:
            plan = self.source_monthly_shift_plan
            if plan.location_id != self.location_id or plan.year != self.year or plan.month != self.month:
                errors["source_monthly_shift_plan"] = "source plan must match location/year/month."
        if self.source_publication_id:
            publication = self.source_publication
            if (
                publication.location_id != self.location_id
                or publication.year != self.year
                or publication.month != self.month
            ):
                errors["source_publication"] = "source publication must match location/year/month."
            if (
                self.source_monthly_shift_plan_id
                and publication.monthly_shift_plan_id != self.source_monthly_shift_plan_id
            ):
                errors["source_publication"] = "source publication must belong to the source plan."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.year}-{self.month:02d} / {self.status}"


class LaborCostBudgetPlanRecordSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget_period = models.ForeignKey(
        LaborCostBudgetPeriod,
        on_delete=models.CASCADE,
        related_name="plan_record_snapshots",
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="labor_cost_budget_plan_snapshots")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_plan_snapshots",
    )
    work_date = models.DateField()
    monthly_shift_plan = models.ForeignKey(
        MonthlyShiftPlan,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_plan_snapshots",
        null=True,
        blank=True,
    )
    monthly_shift_assignment = models.ForeignKey(
        MonthlyShiftAssignment,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_plan_snapshots",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(
        MonthlyShiftPublication,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_plan_snapshots",
        null=True,
        blank=True,
    )
    publication_assignment = models.ForeignKey(
        MonthlyShiftPublicationAssignment,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_plan_snapshots",
        null=True,
        blank=True,
    )
    location_code_snapshot = models.CharField(max_length=50)
    location_name_snapshot = models.CharField(max_length=150)
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    plan_source_snapshot = models.CharField(max_length=20)
    employment_type_snapshot = models.CharField(max_length=32)
    base_hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fixed_monthly_amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    planned_start_offset_minutes = models.IntegerField(null=True, blank=True)
    planned_end_offset_minutes = models.IntegerField(null=True, blank=True)
    planned_worked_minutes = models.PositiveIntegerField(default=0)
    planned_hours_decimal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    planned_base_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    planned_daily_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    planned_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["work_date", "employee_code_snapshot", "created_at"]
        indexes = [
            models.Index(fields=["budget_period", "work_date"], name="labor_budget_plan_date_idx"),
            models.Index(fields=["staff", "work_date"], name="labor_budget_plan_staff_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["budget_period", "staff", "work_date", "location"],
                name="uniq_labor_budget_plan_day",
            ),
        ]


class LaborCostBudgetStaffSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget_period = models.ForeignKey(
        LaborCostBudgetPeriod,
        on_delete=models.CASCADE,
        related_name="staff_summaries",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_staff_summaries",
    )
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    employment_type_snapshot = models.CharField(max_length=32)
    base_hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fixed_monthly_amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    planned_worked_days = models.PositiveIntegerField(default=0)
    planned_worked_minutes = models.PositiveIntegerField(default=0)
    planned_hours_decimal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    planned_hourly_base_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    planned_fixed_monthly_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    planned_allowance_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    planned_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_worked_minutes = models.PositiveIntegerField(default=0)
    actual_base_pay_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_allowance_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_plan_variance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_plan_variance_percent = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    warning_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee_code_snapshot", "staff_display_name_snapshot", "created_at"]
        indexes = [models.Index(fields=["budget_period", "staff"], name="labor_budget_staff_sum_idx")]
        constraints = [
            models.UniqueConstraint(fields=["budget_period", "staff"], name="uniq_labor_budget_staff_sum"),
        ]


class LaborCostBudgetDailySummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget_period = models.ForeignKey(
        LaborCostBudgetPeriod,
        on_delete=models.CASCADE,
        related_name="daily_summaries",
    )
    work_date = models.DateField()
    planned_staff_count = models.PositiveIntegerField(default=0)
    planned_worked_minutes = models.PositiveIntegerField(default=0)
    planned_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_staff_count = models.PositiveIntegerField(default=0)
    actual_worked_minutes = models.PositiveIntegerField(default=0)
    actual_estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_plan_variance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_plan_variance_percent = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    warning_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["work_date", "created_at"]
        indexes = [models.Index(fields=["budget_period", "work_date"], name="labor_budget_daily_idx")]
        constraints = [
            models.UniqueConstraint(fields=["budget_period", "work_date"], name="uniq_labor_budget_daily_sum"),
        ]


class LaborCostBudgetAllowanceSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget_period = models.ForeignKey(
        LaborCostBudgetPeriod,
        on_delete=models.CASCADE,
        related_name="allowance_snapshots",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_allowance_snapshots",
    )
    staff_display_name_snapshot = models.CharField(max_length=150)
    employee_code_snapshot = models.CharField(max_length=50, blank=True)
    allowance_assignment = models.ForeignKey(
        StaffAllowanceAssignment,
        on_delete=models.PROTECT,
        related_name="labor_cost_budget_snapshots",
        null=True,
        blank=True,
    )
    code_snapshot = models.CharField(max_length=50)
    name_snapshot = models.CharField(max_length=150)
    allowance_type_snapshot = models.CharField(max_length=32)
    amount_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    planned_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee_code_snapshot", "code_snapshot", "created_at"]
        indexes = [
            models.Index(fields=["budget_period", "staff"], name="labor_budget_allow_staff_idx"),
            models.Index(fields=["allowance_assignment"], name="labor_budget_allow_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["budget_period", "staff", "allowance_assignment"],
                condition=Q(allowance_assignment__isnull=False),
                name="uniq_labor_budget_allow_assign",
            ),
            models.UniqueConstraint(
                fields=["budget_period", "staff", "code_snapshot", "allowance_type_snapshot"],
                condition=Q(allowance_assignment__isnull=True),
                name="uniq_labor_budget_allow_code",
            ),
        ]


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


class RevenueActualPeriod(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        REVIEW = "review", "review"
        FINALIZED = "finalized", "finalized"
        REOPENED = "reopened", "reopened"
        ARCHIVED = "archived", "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="revenue_actual_periods")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    revenue_budget_period = models.ForeignKey(
        RevenueBudgetPeriod,
        on_delete=models.PROTECT,
        related_name="revenue_actual_periods",
        null=True,
        blank=True,
    )
    labor_cost_budget_period = models.ForeignKey(
        LaborCostBudgetPeriod,
        on_delete=models.PROTECT,
        related_name="revenue_actual_periods",
        null=True,
        blank=True,
    )
    labor_cost_estimate_period = models.ForeignKey(
        LaborCostEstimatePeriod,
        on_delete=models.PROTECT,
        related_name="revenue_actual_periods",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    content_hash = models.CharField(max_length=64, blank=True)
    validation_fingerprint = models.CharField(max_length=64, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_actual_periods_finalized",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_actual_periods_reopened",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_actual_periods_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revenue_actual_periods_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-year", "-month", "location__display_order", "created_at"]
        indexes = [
            models.Index(fields=["location", "year", "month"], name="revenue_actual_lookup_idx"),
            models.Index(fields=["status", "is_active"], name="revenue_actual_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "year", "month"],
                condition=Q(is_active=True),
                name="uniq_active_revenue_actual",
            ),
            models.CheckConstraint(condition=Q(year__gte=2000) & Q(year__lte=2100), name="revenue_actual_year_range"),
            models.CheckConstraint(condition=Q(month__gte=1) & Q(month__lte=12), name="revenue_actual_month_range"),
        ]

    def clean(self):
        errors = {}
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.year < 2000 or self.year > 2100:
            errors["year"] = "year must be between 2000 and 2100."
        if self.month < 1 or self.month > 12:
            errors["month"] = "month must be between 1 and 12."
        for field_name in [
            "revenue_budget_period",
            "labor_cost_budget_period",
            "labor_cost_estimate_period",
        ]:
            related = getattr(self, field_name, None)
            if related and (
                related.location_id != self.location_id or related.year != self.year or related.month != self.month
            ):
                errors[field_name] = f"{field_name} must match location/year/month."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.location.short_name} / {self.year}-{self.month:02d} / {self.status}"


class RevenueActualLine(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "manual"
        IMPORTED = "imported", "imported"
        ADJUSTED = "adjusted", "adjusted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actual_period = models.ForeignKey(RevenueActualPeriod, on_delete=models.CASCADE, related_name="lines")
    category = models.ForeignKey(RevenueCategory, on_delete=models.PROTECT, related_name="actual_lines")
    category_code_snapshot = models.CharField(max_length=50)
    category_name_snapshot = models.CharField(max_length=150)
    actual_amount = models.DecimalField(max_digits=14, decimal_places=2)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    notes = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "category_code_snapshot", "created_at"]
        indexes = [models.Index(fields=["actual_period", "is_active"], name="revenue_actual_line_idx")]
        constraints = [
            models.UniqueConstraint(fields=["actual_period", "category"], name="uniq_revenue_actual_line"),
            models.CheckConstraint(condition=Q(actual_amount__gte=0), name="revenue_actual_amount_gte0"),
            models.CheckConstraint(condition=Q(display_order__gte=0), name="revenue_actual_order_gte0"),
        ]

    def clean(self):
        errors = {}
        if self.actual_amount is not None and self.actual_amount < 0:
            errors["actual_amount"] = "actual_amount must be greater than or equal to 0."
        if self.actual_period_id and self.category_id:
            if self.actual_period.location_id != self.category.location_id:
                errors["category"] = "category must belong to the actual period location."
            if self._state.adding and not self.category.is_active:
                errors["category"] = "Inactive categories cannot be used for new monthly input."
        if self.actual_period_id and self.actual_period.status in {
            RevenueActualPeriod.Status.FINALIZED,
            RevenueActualPeriod.Status.ARCHIVED,
        }:
            errors["actual_period"] = "Finalized or archived actual periods are read-only."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.actual_period_id} / {self.category_code_snapshot}"


class RevenuePerformanceSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actual_period = models.OneToOneField(
        RevenueActualPeriod,
        on_delete=models.CASCADE,
        related_name="performance_snapshot",
    )
    revenue_budget_period = models.ForeignKey(
        RevenueBudgetPeriod,
        on_delete=models.PROTECT,
        related_name="performance_snapshots",
    )
    labor_cost_budget_period = models.ForeignKey(
        LaborCostBudgetPeriod,
        on_delete=models.PROTECT,
        related_name="revenue_performance_snapshots",
    )
    labor_cost_estimate_period = models.ForeignKey(
        LaborCostEstimatePeriod,
        on_delete=models.PROTECT,
        related_name="revenue_performance_snapshots",
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="revenue_performance_snapshots")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    location_code_snapshot = models.CharField(max_length=50)
    location_name_snapshot = models.CharField(max_length=150)
    revenue_budget_total = models.DecimalField(max_digits=14, decimal_places=2)
    revenue_actual_total = models.DecimalField(max_digits=14, decimal_places=2)
    revenue_variance_amount = models.DecimalField(max_digits=14, decimal_places=2)
    revenue_attainment_percent = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    labor_budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    planned_labor_cost = models.DecimalField(max_digits=14, decimal_places=2)
    actual_labor_cost_estimate = models.DecimalField(max_digits=14, decimal_places=2)
    budget_labor_cost_ratio = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    planned_labor_cost_ratio_to_budget_revenue = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True
    )
    planned_labor_cost_ratio_to_actual_revenue = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True
    )
    actual_labor_cost_ratio = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    planned_vs_labor_budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    actual_vs_labor_budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    actual_vs_planned_labor_cost_amount = models.DecimalField(max_digits=14, decimal_places=2)
    budget_content_hash = models.CharField(max_length=64, blank=True)
    labor_budget_content_hash = models.CharField(max_length=64, blank=True)
    labor_estimate_content_hash = models.CharField(max_length=64, blank=True)
    content_hash = models.CharField(max_length=64)
    validation_fingerprint = models.CharField(max_length=64)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-month", "location_code_snapshot"]
        indexes = [models.Index(fields=["location", "year", "month"], name="revenue_perf_lookup_idx")]

    def __str__(self):
        return f"{self.location_code_snapshot} / {self.year}-{self.month:02d}"


class RevenuePerformanceLineSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    performance_snapshot = models.ForeignKey(
        RevenuePerformanceSnapshot,
        on_delete=models.CASCADE,
        related_name="line_snapshots",
    )
    category = models.ForeignKey(
        RevenueCategory,
        on_delete=models.SET_NULL,
        related_name="performance_line_snapshots",
        null=True,
        blank=True,
    )
    category_code_snapshot = models.CharField(max_length=50)
    category_name_snapshot = models.CharField(max_length=150)
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=14, decimal_places=2)
    variance_amount = models.DecimalField(max_digits=14, decimal_places=2)
    attainment_percent = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "category_code_snapshot", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["performance_snapshot", "category_code_snapshot"],
                name="uniq_revenue_perf_line",
            )
        ]

    def __str__(self):
        return f"{self.performance_snapshot_id} / {self.category_code_snapshot}"
