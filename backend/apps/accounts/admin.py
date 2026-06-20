from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "追加情報",
            {
                "fields": (
                    "display_name",
                    "employee_code",
                    "employment_status",
                    "hire_date",
                    "termination_date",
                    "must_change_password",
                    "deactivated_at",
                    "deactivated_by",
                    "deactivation_reason",
                )
            },
        ),
    )
    list_display = ("username", "display_name", "employee_code", "employment_status", "is_active")
