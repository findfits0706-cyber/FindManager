import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "在職"
        LEAVE_OF_ABSENCE = "leave_of_absence", "休職"
        SUSPENDED = "suspended", "停止"
        TERMINATED = "terminated", "退職"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=150)
    employee_code = models.CharField(max_length=50, unique=True)
    email = models.EmailField(blank=True)
    employment_status = models.CharField(
        max_length=32,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    hire_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    must_change_password = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deactivated_users",
    )
    deactivation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ["display_name", "employee_code"]

    class Meta:
        permissions = [
            ("view_staff_list", "Can view staff list"),
            ("view_staff_detail", "Can view staff detail"),
            ("manage_staff_basic", "Can manage non-admin staff"),
            ("assign_limited_roles", "Can assign limited roles"),
            ("deactivate_staff", "Can deactivate staff"),
            ("reactivate_staff", "Can reactivate staff"),
            ("set_temporary_password", "Can set temporary password"),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.username})"

    @property
    def role_keys(self):
        if not hasattr(self, "_role_keys_cache"):
            self._role_keys_cache = tuple(self.groups.order_by("name").values_list("name", flat=True))
        return list(self._role_keys_cache)

    def has_role(self, role: str) -> bool:
        return role in self.role_keys

    def is_login_allowed(self) -> bool:
        return self.is_active and self.employment_status in {
            self.EmploymentStatus.ACTIVE,
            self.EmploymentStatus.LEAVE_OF_ABSENCE,
        }
