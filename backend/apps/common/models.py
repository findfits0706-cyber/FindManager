import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "ログイン成功"
        LOGIN_FAILED = "login_failed", "ログイン失敗"
        LOGOUT = "logout", "ログアウト"
        PASSWORD_CHANGED = "password_changed", "パスワード変更"
        TEMPORARY_PASSWORD_SET = "temporary_password_set", "一時パスワード設定"
        ACCOUNT_CREATED = "account_created", "アカウント作成"
        ACCOUNT_UPDATED = "account_updated", "アカウント更新"
        ACCOUNT_DEACTIVATED = "account_deactivated", "アカウント無効化"
        ACCOUNT_REACTIVATED = "account_reactivated", "アカウント再有効化"
        ROLE_CHANGED = "role_changed", "権限変更"

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
