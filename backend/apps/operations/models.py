import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ActiveOrderedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["display_order", "created_at"]


class Location(ActiveOrderedModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Tokyo")

    class Meta(ActiveOrderedModel.Meta):
        verbose_name = "Location"
        verbose_name_plural = "Locations"

    def __str__(self):
        return f"{self.name} ({self.code})"


class WorkArea(ActiveOrderedModel):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="work_areas")
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta(ActiveOrderedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["location", "code"], name="unique_work_area_code_per_location")]

    def clean(self):
        if self.location_id and not self.location.is_active:
            raise ValidationError({"location": "Inactive locations cannot be assigned."})

    def __str__(self):
        return f"{self.location.short_name} / {self.name}"


class WorkCategory(ActiveOrderedModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta(ActiveOrderedModel.Meta):
        verbose_name = "Work category"
        verbose_name_plural = "Work categories"

    def __str__(self):
        return self.name


class WorkType(ActiveOrderedModel):
    class ColorKey(models.TextChoices):
        SLATE = "slate", "slate"
        BLUE = "blue", "blue"
        GREEN = "green", "green"
        AMBER = "amber", "amber"
        RED = "red", "red"
        VIOLET = "violet", "violet"
        CYAN = "cyan", "cyan"
        PINK = "pink", "pink"

    category = models.ForeignKey(WorkCategory, on_delete=models.PROTECT, related_name="work_types")
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    default_duration_minutes = models.PositiveIntegerField(default=60)
    minimum_staff_count = models.PositiveIntegerField(default=1)
    maximum_staff_count = models.PositiveIntegerField(null=True, blank=True)
    color_key = models.CharField(max_length=20, choices=ColorKey.choices, default=ColorKey.SLATE)
    requires_capability = models.BooleanField(default=False)
    can_overlap = models.BooleanField(default=False)
    is_break = models.BooleanField(default=False)
    is_bookable = models.BooleanField(default=False)
    requires_customer = models.BooleanField(default=False)

    class Meta(ActiveOrderedModel.Meta):
        verbose_name = "Work type"
        verbose_name_plural = "Work types"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(default_duration_minutes__gt=0),
                name="work_type_duration_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_staff_count__gte=1),
                name="work_type_minimum_staff_at_least_one",
            ),
            models.CheckConstraint(
                condition=models.Q(maximum_staff_count__isnull=True)
                | models.Q(maximum_staff_count__gte=models.F("minimum_staff_count")),
                name="work_type_maximum_staff_gte_minimum",
            ),
        ]

    def clean(self):
        errors = {}
        if self.category_id and not self.category.is_active:
            errors["category"] = "Inactive categories cannot be assigned."
        if self.default_duration_minutes <= 0:
            errors["default_duration_minutes"] = "default_duration_minutes must be greater than 0."
        elif self.default_duration_minutes % 15 != 0:
            errors["default_duration_minutes"] = "default_duration_minutes must be in 15-minute increments."
        if self.minimum_staff_count < 1:
            errors["minimum_staff_count"] = "minimum_staff_count must be at least 1."
        if self.maximum_staff_count is not None and self.maximum_staff_count < self.minimum_staff_count:
            errors["maximum_staff_count"] = "maximum_staff_count must be greater than or equal to minimum_staff_count."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class WorkTypeAvailability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, related_name="availabilities")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="work_type_availabilities")
    work_area = models.ForeignKey(
        WorkArea,
        on_delete=models.PROTECT,
        related_name="work_type_availabilities",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["work_type", "location", "work_area"],
                name="unique_work_type_availability",
                nulls_distinct=False,
            )
        ]

    def clean(self):
        errors = {}
        if self.work_type_id and not self.work_type.is_active:
            errors["work_type"] = "Inactive work types cannot be assigned."
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.work_area_id:
            if not self.work_area.is_active:
                errors["work_area"] = "Inactive work areas cannot be assigned."
            elif self.work_area.location_id != self.location_id:
                errors["work_area"] = "work_area must belong to the selected location."
        duplicate_query = WorkTypeAvailability.objects.filter(
            work_type_id=self.work_type_id,
            location_id=self.location_id,
            work_area_id=self.work_area_id,
        )
        if self.pk:
            duplicate_query = duplicate_query.exclude(pk=self.pk)
        if duplicate_query.exists():
            errors["non_field_errors"] = "This work type availability already exists."
        if errors:
            raise ValidationError(errors)


class StaffLocation(ActiveOrderedModel):
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="staff_locations")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="staff_locations")
    is_primary = models.BooleanField(default=False)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)

    class Meta(ActiveOrderedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "location", "valid_from", "valid_until"],
                name="unique_staff_location_period",
                nulls_distinct=False,
            )
        ]

    def clean(self):
        errors = {}
        if self.staff_id and not self.staff.is_login_allowed():
            errors["staff"] = "Inactive staff cannot be assigned."
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.valid_until and self.valid_from > self.valid_until:
            errors["valid_until"] = "valid_until must be on or after valid_from."

        if self.is_active:
            overlapping_periods = StaffLocation.objects.filter(
                staff_id=self.staff_id,
                location_id=self.location_id,
                is_active=True,
                valid_from__lte=self.valid_until or self.valid_from,
            ).filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=self.valid_from))
            if self.valid_until is None:
                overlapping_periods = StaffLocation.objects.filter(
                    staff_id=self.staff_id,
                    location_id=self.location_id,
                    is_active=True,
                ).filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=self.valid_from))
            if self.pk:
                overlapping_periods = overlapping_periods.exclude(pk=self.pk)
            if overlapping_periods.exists():
                errors["non_field_errors"] = "This staff location period overlaps an existing active record."

            if self.is_primary:
                primary_overlap = StaffLocation.objects.filter(
                    staff_id=self.staff_id,
                    is_primary=True,
                    is_active=True,
                ).filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=self.valid_from))
                if self.valid_until is not None:
                    primary_overlap = primary_overlap.filter(valid_from__lte=self.valid_until)
                if self.pk:
                    primary_overlap = primary_overlap.exclude(pk=self.pk)
                if primary_overlap.exists():
                    errors["is_primary"] = "Primary location periods cannot overlap."

        if errors:
            raise ValidationError(errors)


class StaffCapability(ActiveOrderedModel):
    class Level(models.TextChoices):
        TRAINEE = "trainee", "trainee"
        ASSISTED = "assisted", "assisted"
        INDEPENDENT = "independent", "independent"
        TRAINER = "trainer", "trainer"

    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="staff_capabilities")
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, related_name="staff_capabilities")
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="staff_capabilities",
        null=True,
        blank=True,
    )
    level = models.CharField(max_length=20, choices=Level.choices)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_staff_capabilities",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(ActiveOrderedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "work_type", "location", "valid_from", "valid_until"],
                name="unique_staff_capability_period",
                nulls_distinct=False,
            )
        ]

    def clean(self):
        errors = {}
        if self.staff_id and not self.staff.is_login_allowed():
            errors["staff"] = "Inactive staff cannot be assigned."
        if self.work_type_id and not self.work_type.is_active:
            errors["work_type"] = "Inactive work types cannot be assigned."
        if self.location_id and not self.location.is_active:
            errors["location"] = "Inactive locations cannot be assigned."
        if self.valid_until and self.valid_from > self.valid_until:
            errors["valid_until"] = "valid_until must be on or after valid_from."

        if self.is_active:
            overlap_query = StaffCapability.objects.filter(
                staff_id=self.staff_id,
                work_type_id=self.work_type_id,
                location_id=self.location_id,
                is_active=True,
            ).filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=self.valid_from))
            if self.valid_until is not None:
                overlap_query = overlap_query.filter(valid_from__lte=self.valid_until)
            if self.pk:
                overlap_query = overlap_query.exclude(pk=self.pk)
            if overlap_query.exists():
                errors["non_field_errors"] = "This staff capability period overlaps an existing active record."
        if errors:
            raise ValidationError(errors)
