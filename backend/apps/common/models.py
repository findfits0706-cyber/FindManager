import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Login success"
        LOGIN_FAILED = "login_failed", "Login failed"
        LOGOUT = "logout", "Logout"
        PASSWORD_CHANGED = "password_changed", "Password changed"
        TEMPORARY_PASSWORD_SET = "temporary_password_set", "Temporary password set"
        ACCOUNT_CREATED = "account_created", "Account created"
        ACCOUNT_UPDATED = "account_updated", "Account updated"
        ACCOUNT_DEACTIVATED = "account_deactivated", "Account deactivated"
        ACCOUNT_REACTIVATED = "account_reactivated", "Account reactivated"
        ROLE_CHANGED = "role_changed", "Role changed"
        LOCATION_CREATED = "location_created", "Location created"
        LOCATION_UPDATED = "location_updated", "Location updated"
        LOCATION_DEACTIVATED = "location_deactivated", "Location deactivated"
        LOCATION_REACTIVATED = "location_reactivated", "Location reactivated"
        WORK_AREA_CREATED = "work_area_created", "Work area created"
        WORK_AREA_UPDATED = "work_area_updated", "Work area updated"
        WORK_AREA_DEACTIVATED = "work_area_deactivated", "Work area deactivated"
        WORK_AREA_REACTIVATED = "work_area_reactivated", "Work area reactivated"
        WORK_CATEGORY_CREATED = "work_category_created", "Work category created"
        WORK_CATEGORY_UPDATED = "work_category_updated", "Work category updated"
        WORK_CATEGORY_DEACTIVATED = "work_category_deactivated", "Work category deactivated"
        WORK_CATEGORY_REACTIVATED = "work_category_reactivated", "Work category reactivated"
        WORK_TYPE_CREATED = "work_type_created", "Work type created"
        WORK_TYPE_UPDATED = "work_type_updated", "Work type updated"
        WORK_TYPE_DEACTIVATED = "work_type_deactivated", "Work type deactivated"
        WORK_TYPE_REACTIVATED = "work_type_reactivated", "Work type reactivated"
        WORK_TYPE_AVAILABILITY_CREATED = "work_type_availability_created", "Work type availability created"
        WORK_TYPE_AVAILABILITY_UPDATED = "work_type_availability_updated", "Work type availability updated"
        WORK_TYPE_AVAILABILITY_DEACTIVATED = "work_type_availability_deactivated", "Work type availability deactivated"
        WORK_TYPE_AVAILABILITY_REACTIVATED = "work_type_availability_reactivated", "Work type availability reactivated"
        STAFF_LOCATION_CREATED = "staff_location_created", "Staff location created"
        STAFF_LOCATION_UPDATED = "staff_location_updated", "Staff location updated"
        STAFF_LOCATION_DEACTIVATED = "staff_location_deactivated", "Staff location deactivated"
        STAFF_LOCATION_REACTIVATED = "staff_location_reactivated", "Staff location reactivated"
        STAFF_CAPABILITY_CREATED = "staff_capability_created", "Staff capability created"
        STAFF_CAPABILITY_UPDATED = "staff_capability_updated", "Staff capability updated"
        STAFF_CAPABILITY_DEACTIVATED = "staff_capability_deactivated", "Staff capability deactivated"
        STAFF_CAPABILITY_REACTIVATED = "staff_capability_reactivated", "Staff capability reactivated"
        SHIFT_PATTERN_CREATED = "shift_pattern_created", "Shift pattern created"
        SHIFT_PATTERN_UPDATED = "shift_pattern_updated", "Shift pattern updated"
        SHIFT_PATTERN_DEACTIVATED = "shift_pattern_deactivated", "Shift pattern deactivated"
        SHIFT_PATTERN_REACTIVATED = "shift_pattern_reactivated", "Shift pattern reactivated"
        SHIFT_PATTERN_DUPLICATED = "shift_pattern_duplicated", "Shift pattern duplicated"
        WEEKLY_SHIFT_TEMPLATE_CREATED = "weekly_shift_template_created", "Weekly shift template created"
        WEEKLY_SHIFT_TEMPLATE_UPDATED = "weekly_shift_template_updated", "Weekly shift template updated"
        WEEKLY_SHIFT_TEMPLATE_DEACTIVATED = "weekly_shift_template_deactivated", "Weekly shift template deactivated"
        WEEKLY_SHIFT_TEMPLATE_REACTIVATED = "weekly_shift_template_reactivated", "Weekly shift template reactivated"
        WEEKLY_SHIFT_TEMPLATE_DUPLICATED = "weekly_shift_template_duplicated", "Weekly shift template duplicated"
        MONTHLY_SHIFT_PLAN_CREATED = "monthly_shift_plan_created", "Monthly shift plan created"
        MONTHLY_SHIFT_PLAN_UPDATED = "monthly_shift_plan_updated", "Monthly shift plan updated"
        MONTHLY_SHIFT_PLAN_DEACTIVATED = "monthly_shift_plan_deactivated", "Monthly shift plan deactivated"
        MONTHLY_SHIFT_PLAN_REACTIVATED = "monthly_shift_plan_reactivated", "Monthly shift plan reactivated"
        MONTHLY_SHIFT_PLAN_CONFIRMED = "monthly_shift_plan_confirmed", "Monthly shift plan confirmed"
        MONTHLY_SHIFT_PLAN_REOPENED = "monthly_shift_plan_reopened", "Monthly shift plan reopened"
        MONTHLY_SHIFT_PLAN_PUBLISHED = "monthly_shift_plan_published", "Monthly shift plan published"
        MONTHLY_SHIFT_PLAN_PUBLICATION_WITHDRAWN = (
            "monthly_shift_plan_publication_withdrawn",
            "Monthly shift plan publication withdrawn",
        )
        MONTHLY_SHIFT_ASSIGNMENT_CREATED = "monthly_shift_assignment_created", "Monthly shift assignment created"
        MONTHLY_SHIFT_ASSIGNMENT_UPDATED = "monthly_shift_assignment_updated", "Monthly shift assignment updated"
        MONTHLY_SHIFT_ASSIGNMENT_DEACTIVATED = (
            "monthly_shift_assignment_deactivated",
            "Monthly shift assignment deactivated",
        )
        MONTHLY_SHIFT_ASSIGNMENT_REACTIVATED = (
            "monthly_shift_assignment_reactivated",
            "Monthly shift assignment reactivated",
        )
        MONTHLY_SHIFT_TEMPLATE_APPLIED = "monthly_shift_template_applied", "Monthly shift template applied"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64, choices=EventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events_as_actor",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events_as_target",
    )
    occurred_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
