from rest_framework import serializers

from apps.accounts.constants import ROLE_SHIFT_MANAGER, ROLE_SYSTEM_ADMIN

from .models import (
    Location,
    StaffCapability,
    StaffLocation,
    WorkArea,
    WorkCategory,
    WorkType,
    WorkTypeAvailability,
)

FORBIDDEN_UPDATE_FIELDS = {
    "is_active": "Use deactivate/reactivate actions instead of updating is_active directly.",
}


class ActiveGuardSerializer(serializers.ModelSerializer):
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
        instance.clean()

    def validate(self, attrs):
        errors = {}
        if self.instance and "is_active" in self.initial_data:
            errors["is_active"] = FORBIDDEN_UPDATE_FIELDS["is_active"]
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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        staff = attrs.get("staff", instance.staff if instance else None)
        if staff and not staff.is_login_allowed():
            raise serializers.ValidationError({"staff": "Inactive staff cannot be assigned."})
        return attrs


class StaffCapabilitySerializer(ActiveGuardSerializer):
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    work_type_name = serializers.CharField(source="work_type.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    approved_by_display_name = serializers.CharField(source="approved_by.display_name", read_only=True)

    class Meta:
        model = StaffCapability
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        staff = attrs.get("staff", instance.staff if instance else None)
        work_type = attrs.get("work_type", instance.work_type if instance else None)
        approved_by = attrs.get("approved_by", instance.approved_by if instance else None)
        if staff and not staff.is_login_allowed():
            raise serializers.ValidationError({"staff": "Inactive staff cannot be assigned."})
        if work_type and not work_type.is_active:
            raise serializers.ValidationError({"work_type": "Inactive work types cannot be assigned."})
        if approved_by and not approved_by.is_login_allowed():
            raise serializers.ValidationError({"approved_by": "Approver must be able to log in."})
        if approved_by and not (approved_by.has_role(ROLE_SYSTEM_ADMIN) or approved_by.has_role(ROLE_SHIFT_MANAGER)):
            raise serializers.ValidationError({"approved_by": "Approver must be a system admin or shift manager."})
        return attrs


class DeactivateSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(default=True)


class ReactivateSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(default=True)


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
            "notes",
            "is_active",
        ]
