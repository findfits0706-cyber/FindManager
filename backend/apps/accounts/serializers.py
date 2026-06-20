from django.contrib.auth import password_validation
from django.contrib.auth.models import Group
from rest_framework import serializers

from .constants import ROLE_CHOICES, ROLE_SYSTEM_ADMIN
from .models import User


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
            "roles",
            "temporary_password",
        ]
        read_only_fields = ["id", "is_active"]

    def validate_roles(self, value):
        if not value:
            raise serializers.ValidationError("少なくとも1つの権限グループを指定してください。")
        return sorted(set(value))

    def validate(self, attrs):
        request = self.context["request"]
        actor = request.user
        target = self.instance
        roles = attrs.get("roles")
        if roles is not None:
            if not actor.has_role(ROLE_SYSTEM_ADMIN) and ROLE_SYSTEM_ADMIN in roles:
                raise serializers.ValidationError({"roles": "system_admin権限は付与できません。"})
            if target and actor.pk == target.pk and roles != target.role_keys and not actor.has_role(ROLE_SYSTEM_ADMIN):
                raise serializers.ValidationError({"roles": "自分自身の権限昇格はできません。"})
        temp_password = attrs.get("temporary_password")
        if self.instance is None and not temp_password:
            raise serializers.ValidationError({"temporary_password": "新規作成時は一時パスワードが必須です。"})
        if temp_password:
            password_validation.validate_password(temp_password)
        return attrs

    def create(self, validated_data):
        roles = validated_data.pop("roles")
        temporary_password = validated_data.pop("temporary_password")
        user = User.objects.create(**validated_data, is_active=True)
        user.set_password(temporary_password)
        user.must_change_password = validated_data.get("must_change_password", True)
        user.save()
        user.groups.set(Group.objects.filter(name__in=roles))
        return user

    def update(self, instance, validated_data):
        roles = validated_data.pop("roles", None)
        temporary_password = validated_data.pop("temporary_password", None)
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
