from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    Location,
    StaffCapability,
    StaffLocation,
    WorkArea,
    WorkCategory,
    WorkType,
    WorkTypeAvailability,
)

FORBIDDEN_INPUT_FIELDS = {
    "is_active": "Use deactivate/reactivate actions instead of updating is_active directly.",
}


class ActiveGuardSerializer(serializers.ModelSerializer):
    read_only_field_names: tuple[str, ...] = ()

    def _run_model_clean(self, attrs):
        model_class = self.Meta.model
        values = {}
        if self.instance:
            for field in self.instance._meta.fields:
                values[field.name] = getattr(self.instance, field.name)
                if field.attname != field.name:
                    values[field.attname] = getattr(self.instance, field.attname)
        values.update(attrs)
        instance = model_class(**values)
        if self.instance:
            instance.pk = self.instance.pk
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc

    def validate(self, attrs):
        errors = {}
        for field in FORBIDDEN_INPUT_FIELDS:
            if field in self.initial_data:
                errors[field] = FORBIDDEN_INPUT_FIELDS[field]
        for field in self.read_only_field_names:
            if field in self.initial_data:
                errors[field] = f"{field} is read-only."
        if errors:
            raise serializers.ValidationError(errors)
        self._run_model_clean(attrs)
        return attrs


class LocationSerializer(ActiveGuardSerializer):
    class Meta:
        model = Location
        fields = "__all__"


class WorkAreaSerializer(ActiveGuardSerializer):
    class Meta:
        model = WorkArea
        fields = "__all__"


class WorkCategorySerializer(ActiveGuardSerializer):
    class Meta:
        model = WorkCategory
        fields = "__all__"


class WorkTypeSerializer(ActiveGuardSerializer):
    class Meta:
        model = WorkType
        fields = "__all__"


class WorkTypeAvailabilitySerializer(ActiveGuardSerializer):
    class Meta:
        model = WorkTypeAvailability
        fields = "__all__"


class StaffLocationSerializer(ActiveGuardSerializer):
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = StaffLocation
        fields = "__all__"


class StaffCapabilitySerializer(ActiveGuardSerializer):
    read_only_field_names = ("approved_by", "approved_at")
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    work_type_name = serializers.CharField(source="work_type.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    approved_by_display_name = serializers.CharField(source="approved_by.display_name", read_only=True)

    class Meta:
        model = StaffCapability
        fields = "__all__"


class DeactivateSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(default=True)


class ReactivateSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(default=True)


class MyStaffLocationSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = StaffLocation
        fields = [
            "id",
            "location_name",
            "is_primary",
            "valid_from",
            "valid_until",
            "is_active",
        ]


class MyStaffCapabilitySerializer(serializers.ModelSerializer):
    work_type_name = serializers.CharField(source="work_type.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    approved_by_display_name = serializers.CharField(source="approved_by.display_name", read_only=True)

    class Meta:
        model = StaffCapability
        fields = [
            "id",
            "work_type_name",
            "location_name",
            "level",
            "valid_from",
            "valid_until",
            "approved_by_display_name",
            "approved_at",
            "notes",
            "is_active",
        ]
