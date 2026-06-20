from django.contrib.auth import password_validation
from django.contrib.auth.models import Group
from rest_framework import serializers

from .constants import ROLE_CHOICES, ROLE_SYSTEM_ADMIN
from .models import User
from .services import would_remove_last_system_admin

FORBIDDEN_CREATE_FIELDS = {
    "employment_status": "新規作成時に employment_status は指定できません。",
    "is_active": "新規作成時に is_active は指定できません。",
    "deactivated_at": "新規作成時に deactivated_at は指定できません。",
    "deactivated_by": "新規作成時に deactivated_by は指定できません。",
    "deactivation_reason": "新規作成時に deactivation_reason は指定できません。",
}

FORBIDDEN_UPDATE_FIELDS = {
    "employment_status": "employment_status は専用アクションでのみ変更できます。",
    "is_active": "is_active は専用アクションでのみ変更できます。",
    "deactivated_at": "deactivated_at は専用アクションでのみ変更できます。",
    "deactivated_by": "deactivated_by は専用アクションでのみ変更できます。",
    "deactivation_reason": "deactivation_reason は専用アクションでのみ変更できます。",
}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)
    new_password_confirm = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "確認用パスワードが一致しません。"})
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "現在のパスワードが正しくありません。"})
        password_validation.validate_password(attrs["new_password"], user=user)
        return attrs


class MeSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "employee_code",
            "email",
            "employment_status",
            "must_change_password",
            "roles",
            "permissions",
        ]

    def get_roles(self, obj):
        return obj.role_keys

    def get_permissions(self, obj):
        return sorted(obj.get_all_permissions())


class StaffListSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "display_name",
            "employee_code",
            "username",
            "email",
            "employment_status",
            "hire_date",
            "termination_date",
            "roles",
            "must_change_password",
            "is_active",
        ]

    def get_roles(self, obj):
        return obj.role_keys


class StaffWriteSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=ROLE_CHOICES),
        write_only=True,
    )
    temporary_password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "employee_code",
            "email",
            "employment_status",
            "hire_date",
            "termination_date",
            "must_change_password",
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "deactivation_reason",
            "roles",
            "temporary_password",
        ]
        read_only_fields = ["id", "deactivated_at", "deactivated_by", "deactivation_reason"]

    def validate_roles(self, value):
        if not value:
            raise serializers.ValidationError("少なくとも1つの権限グループを指定してください。")
        return sorted(set(value))

    def validate(self, attrs):
        request = self.context["request"]
        actor = request.user
        target = self.instance
        errors = {}
        forbidden_fields = FORBIDDEN_CREATE_FIELDS if target is None else FORBIDDEN_UPDATE_FIELDS
        for field_name, message in forbidden_fields.items():
            if field_name in self.initial_data:
                errors[field_name] = message
        roles = attrs.get("roles")
        if roles is not None:
            if not actor.has_role(ROLE_SYSTEM_ADMIN) and ROLE_SYSTEM_ADMIN in roles:
                errors["roles"] = "system_admin権限は付与できません。"
            if target and actor.pk == target.pk and roles != target.role_keys and not actor.has_role(ROLE_SYSTEM_ADMIN):
                errors["roles"] = "自分自身の権限昇格はできません。"
            if target and would_remove_last_system_admin(target, roles):
                errors["roles"] = "最後のsystem_admin権限は解除できません。"
        temp_password = attrs.get("temporary_password")
        if self.instance is None and not temp_password:
            errors["temporary_password"] = "新規作成時は一時パスワードが必須です。"
        if temp_password:
            password_validation.validate_password(temp_password)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        roles = validated_data.pop("roles")
        temporary_password = validated_data.pop("temporary_password")
        validated_data.pop("employment_status", None)
        validated_data.pop("is_active", None)
        user = User.objects.create(
            **validated_data,
            employment_status=User.EmploymentStatus.ACTIVE,
            is_active=True,
        )
        user.set_password(temporary_password)
        user.must_change_password = validated_data.get("must_change_password", True)
        user.save()
        user.groups.set(Group.objects.filter(name__in=roles))
        return user

    def update(self, instance, validated_data):
        roles = validated_data.pop("roles", None)
        temporary_password = validated_data.pop("temporary_password", None)
        for forbidden_field in FORBIDDEN_UPDATE_FIELDS:
            validated_data.pop(forbidden_field, None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if temporary_password:
            instance.set_password(temporary_password)
            instance.must_change_password = True
        instance.save()
        if roles is not None:
            instance.groups.set(Group.objects.filter(name__in=roles))
        return instance


class StaffDeactivateSerializer(serializers.Serializer):
    reason = serializers.CharField()
    employment_status = serializers.ChoiceField(
        choices=[User.EmploymentStatus.SUSPENDED, User.EmploymentStatus.TERMINATED]
    )


class StaffReactivateSerializer(serializers.Serializer):
    employment_status = serializers.ChoiceField(
        choices=[User.EmploymentStatus.ACTIVE, User.EmploymentStatus.LEAVE_OF_ABSENCE]
    )


class TemporaryPasswordSerializer(serializers.Serializer):
    temporary_password = serializers.CharField(trim_whitespace=False)
    must_change_password = serializers.BooleanField(default=True)

    def validate_temporary_password(self, value):
        password_validation.validate_password(value)
        return value
