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
        STAFF_LOCATION_CREATED = "staff_location_created", "Staff location created"
        STAFF_LOCATION_UPDATED = "staff_location_updated", "Staff location updated"
        STAFF_LOCATION_DEACTIVATED = "staff_location_deactivated", "Staff location deactivated"
        STAFF_CAPABILITY_CREATED = "staff_capability_created", "Staff capability created"
        STAFF_CAPABILITY_UPDATED = "staff_capability_updated", "Staff capability updated"
        STAFF_CAPABILITY_DEACTIVATED = "staff_capability_deactivated", "Staff capability deactivated"

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
