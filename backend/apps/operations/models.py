import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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

    def clean(self):
        if self.maximum_staff_count is not None and self.maximum_staff_count < self.minimum_staff_count:
            raise ValidationError(
                {"maximum_staff_count": ("maximum_staff_count must be greater than or equal to minimum_staff_count.")}
            )

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
            )
        ]

    def clean(self):
        if self.work_area and self.work_area.location_id != self.location_id:
            raise ValidationError({"work_area": "work_area must belong to the selected location."})


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
            )
        ]

    def clean(self):
        if self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError({"valid_until": "valid_until must be on or after valid_from."})
        if self.is_primary and self.is_active:
            today = timezone.localdate()
            if self.valid_from <= today and (self.valid_until is None or self.valid_until >= today):
                conflict = StaffLocation.objects.filter(
                    staff=self.staff,
                    is_primary=True,
                    is_active=True,
                    valid_from__lte=today,
                ).filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=today))
                if self.pk:
                    conflict = conflict.exclude(pk=self.pk)
                if conflict.exists():
                    raise ValidationError({"is_primary": "Only one active primary location is allowed at a time."})


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
            )
        ]

    def clean(self):
        if self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError({"valid_until": "valid_until must be on or after valid_from."})
