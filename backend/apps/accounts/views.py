from django.contrib.auth import login, logout, update_session_auth_hash
from django.db.models import Q
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.models import AuditEvent

from .constants import ROLE_SHIFT_MANAGER, ROLE_SYSTEM_ADMIN
from .models import User
from .permissions import CanManageStaff, CanViewStaffList
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    StaffDeactivateSerializer,
    StaffListSerializer,
    StaffReactivateSerializer,
    StaffWriteSerializer,
    TemporaryPasswordSerializer,
)
from .services import (
    can_assign_roles,
    create_audit_event,
    invalidate_user_sessions,
    is_last_system_admin,
)


class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            create_audit_event(
                event_type=AuditEvent.EventType.LOGIN_FAILED,
                request=request,
                metadata={"username": username},
            )
            return Response({"detail": "ユーザー名またはパスワードが正しくありません。"}, status=400)

        if not user.check_password(password) or not user.is_login_allowed():
            create_audit_event(
                event_type=AuditEvent.EventType.LOGIN_FAILED,
                target_user=user,
                request=request,
            )
            return Response({"detail": "ユーザー名またはパスワードが正しくありません。"}, status=400)

        login(request, user)
        request.session.cycle_key()
        create_audit_event(
            event_type=AuditEvent.EventType.LOGIN_SUCCESS,
            actor=user,
            target_user=user,
            request=request,
        )
        return Response({"user": MeSerializer(user).data})


class LogoutView(APIView):
    def post(self, request):
        actor = request.user if request.user.is_authenticated else None
        if actor:
            create_audit_event(
                event_type=AuditEvent.EventType.LOGOUT,
                actor=actor,
                target_user=actor,
                request=request,
            )
        logout(request)
        return Response(status=204)


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        update_session_auth_hash(request, user)
        request.session.cycle_key()
        create_audit_event(
            event_type=AuditEvent.EventType.PASSWORD_CHANGED,
            actor=user,
            target_user=user,
            request=request,
        )
        return Response({"detail": "パスワードを変更しました。"})


class StaffViewSet(viewsets.ModelViewSet):
    queryset = User.objects.prefetch_related("groups").order_by("employee_code")
    serializer_class = StaffListSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in {"list"}:
            permission_classes = [CanViewStaffList]
        elif self.action in {"retrieve"}:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [CanManageStaff]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action in {"create", "partial_update"}:
            return StaffWriteSerializer
        if self.action == "deactivate":
            return StaffDeactivateSerializer
        if self.action == "reactivate":
            return StaffReactivateSerializer
        if self.action == "set_temporary_password":
            return TemporaryPasswordSerializer
        return StaffListSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.has_role(ROLE_SYSTEM_ADMIN) or user.has_role(ROLE_SHIFT_MANAGER):
            pass
        elif user.has_perm("accounts.view_staff_detail"):
            pass
        else:
            queryset = queryset.filter(pk=user.pk)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search) | Q(employee_code__icontains=search) | Q(username__icontains=search)
            )
        status_filter = self.request.query_params.get("employment_status")
        if status_filter:
            queryset = queryset.filter(employment_status=status_filter)
        role_filter = self.request.query_params.get("role")
        if role_filter:
            queryset = queryset.filter(groups__name=role_filter)
        ordering = self.request.query_params.get("ordering")
        allowed_ordering = {"display_name", "-display_name", "employee_code", "-employee_code", "username", "-username"}
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        return queryset.distinct()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.pk != instance.pk and not (
            request.user.has_role(ROLE_SYSTEM_ADMIN)
            or request.user.has_role(ROLE_SHIFT_MANAGER)
            or request.user.has_perm("accounts.view_staff_detail")
        ):
            return Response({"detail": "権限がありません。"}, status=403)
        return Response(StaffListSerializer(instance).data)

    def perform_create(self, serializer):
        roles = serializer.validated_data["roles"]
        if not can_assign_roles(self.request.user, roles):
            raise permissions.PermissionDenied("指定された権限グループを付与できません。")
        user = serializer.save()
        create_audit_event(
            event_type=AuditEvent.EventType.ACCOUNT_CREATED,
            actor=self.request.user,
            target_user=user,
            request=self.request,
            metadata={"roles": user.role_keys},
        )
        create_audit_event(
            event_type=AuditEvent.EventType.TEMPORARY_PASSWORD_SET,
            actor=self.request.user,
            target_user=user,
            request=self.request,
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        current_roles = instance.role_keys
        new_roles = serializer.validated_data.get("roles", current_roles)
        if not can_assign_roles(self.request.user, new_roles):
            raise permissions.PermissionDenied("指定された権限グループを付与できません。")
        user = serializer.save()
        create_audit_event(
            event_type=AuditEvent.EventType.ACCOUNT_UPDATED,
            actor=self.request.user,
            target_user=user,
            request=self.request,
        )
        if sorted(current_roles) != sorted(user.role_keys):
            create_audit_event(
                event_type=AuditEvent.EventType.ROLE_CHANGED,
                actor=self.request.user,
                target_user=user,
                request=self.request,
                metadata={"before": current_roles, "after": user.role_keys},
            )
        if "temporary_password" in serializer.validated_data:
            create_audit_event(
                event_type=AuditEvent.EventType.TEMPORARY_PASSWORD_SET,
                actor=self.request.user,
                target_user=user,
                request=self.request,
            )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        target = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if request.user.pk == target.pk:
            return Response({"detail": "自分自身は無効化できません。"}, status=400)
        if is_last_system_admin(target):
            return Response({"detail": "最後のsystem_adminは無効化できません。"}, status=400)
        if request.user.has_role(ROLE_SHIFT_MANAGER) and target.has_role(ROLE_SYSTEM_ADMIN):
            return Response({"detail": "system_adminは無効化できません。"}, status=403)
        target.employment_status = serializer.validated_data["employment_status"]
        target.is_active = False
        target.deactivated_at = timezone.now()
        target.deactivated_by = request.user
        target.deactivation_reason = serializer.validated_data["reason"]
        target.save()
        invalidate_user_sessions(target)
        create_audit_event(
            event_type=AuditEvent.EventType.ACCOUNT_DEACTIVATED,
            actor=request.user,
            target_user=target,
            request=request,
            metadata={"employment_status": target.employment_status},
        )
        return Response(StaffListSerializer(target).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        target = self.get_object()
        if not request.user.has_role(ROLE_SYSTEM_ADMIN):
            return Response({"detail": "system_adminのみ再有効化できます。"}, status=403)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target.employment_status = serializer.validated_data["employment_status"]
        target.is_active = True
        target.deactivated_at = None
        target.deactivated_by = None
        target.deactivation_reason = ""
        target.save()
        create_audit_event(
            event_type=AuditEvent.EventType.ACCOUNT_REACTIVATED,
            actor=request.user,
            target_user=target,
            request=request,
            metadata={"employment_status": target.employment_status},
        )
        return Response(StaffListSerializer(target).data)

    @action(detail=True, methods=["post"])
    def set_temporary_password(self, request, pk=None):
        target = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if request.user.has_role(ROLE_SHIFT_MANAGER) and target.has_role(ROLE_SYSTEM_ADMIN):
            return Response({"detail": "system_adminのパスワードは設定できません。"}, status=403)
        target.set_password(serializer.validated_data["temporary_password"])
        target.must_change_password = serializer.validated_data["must_change_password"]
        target.save(update_fields=["password", "must_change_password", "updated_at"])
        invalidate_user_sessions(target)
        create_audit_event(
            event_type=AuditEvent.EventType.TEMPORARY_PASSWORD_SET,
            actor=request.user,
            target_user=target,
            request=request,
        )
        return Response({"detail": "一時パスワードを設定しました。"})
