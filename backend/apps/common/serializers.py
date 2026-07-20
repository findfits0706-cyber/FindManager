from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_display_name = serializers.CharField(source="actor.display_name", allow_null=True, read_only=True)
    target_display_name = serializers.CharField(source="target_user.display_name", allow_null=True, read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "event_type",
            "actor",
            "actor_display_name",
            "target_user",
            "target_display_name",
            "occurred_at",
            "ip_address",
            "user_agent",
            "metadata",
        ]
        read_only_fields = fields
