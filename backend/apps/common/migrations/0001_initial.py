import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("login_success", "ログイン成功"),
                            ("login_failed", "ログイン失敗"),
                            ("logout", "ログアウト"),
                            ("password_changed", "パスワード変更"),
                            ("temporary_password_set", "一時パスワード設定"),
                            ("account_created", "アカウント作成"),
                            ("account_updated", "アカウント更新"),
                            ("account_deactivated", "アカウント無効化"),
                            ("account_reactivated", "アカウント再有効化"),
                            ("role_changed", "権限変更"),
                        ],
                        max_length=64,
                    ),
                ),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events_as_actor",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events_as_target",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-occurred_at"]},
        ),
    ]
