import uuid

import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.contrib.auth.models import UserManager
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False)),
                (
                    "username",
                    models.CharField(
                        error_messages={"unique": "A user with that username already exists."},
                        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                        max_length=150,
                        unique=True,
                        validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                        verbose_name="username",
                    ),
                ),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("is_staff", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("display_name", models.CharField(max_length=150)),
                ("employee_code", models.CharField(max_length=50, unique=True)),
                ("email", models.EmailField(blank=True, max_length=254)),
                (
                    "employment_status",
                    models.CharField(
                        choices=[
                            ("active", "在職"),
                            ("leave_of_absence", "休職"),
                            ("suspended", "停止"),
                            ("terminated", "退職"),
                        ],
                        default="active",
                        max_length=32,
                    ),
                ),
                ("hire_date", models.DateField(blank=True, null=True)),
                ("termination_date", models.DateField(blank=True, null=True)),
                ("must_change_password", models.BooleanField(default=True)),
                ("deactivated_at", models.DateTimeField(blank=True, null=True)),
                ("deactivation_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
                (
                    "deactivated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deactivated_users",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "permissions": [
                    ("view_staff_list", "Can view staff list"),
                    ("view_staff_detail", "Can view staff detail"),
                    ("manage_staff_basic", "Can manage non-admin staff"),
                    ("assign_limited_roles", "Can assign limited roles"),
                    ("deactivate_staff", "Can deactivate staff"),
                    ("reactivate_staff", "Can reactivate staff"),
                    ("set_temporary_password", "Can set temporary password"),
                ],
            },
            managers=[
                ("objects", UserManager()),
            ],
        ),
    ]
