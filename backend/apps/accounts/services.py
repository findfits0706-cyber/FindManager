from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.common.models import AuditEvent

from .constants import (
    ROLE_CHOICES,
    ROLE_SHIFT_MANAGER,
    ROLE_STAFF,
    ROLE_SUPERVISOR,
    ROLE_SYSTEM_ADMIN,
    ROLE_VIEWER,
)
from .models import User

ROLE_PERMISSION_MAP = {
    ROLE_SYSTEM_ADMIN: [
        "add_user",
        "change_user",
        "view_user",
        "view_staff_list",
        "view_staff_detail",
        "manage_staff_basic",
        "assign_limited_roles",
        "deactivate_staff",
        "reactivate_staff",
        "set_temporary_password",
    ],
    ROLE_SHIFT_MANAGER: [
        "add_user",
        "change_user",
        "view_user",
        "view_staff_list",
        "view_staff_detail",
        "manage_staff_basic",
        "assign_limited_roles",
        "deactivate_staff",
        "set_temporary_password",
    ],
    ROLE_SUPERVISOR: [
        "view_user",
        "view_staff_list",
        "view_staff_detail",
    ],
    ROLE_STAFF: [],
    ROLE_VIEWER: [],
}


def ensure_roles() -> None:
    permissions = Permission.objects.filter(
        content_type__app_label="accounts",
        codename__in={codename for values in ROLE_PERMISSION_MAP.values() for codename in values},
    )
    permission_map = {permission.codename: permission for permission in permissions}
    for role in ROLE_CHOICES:
        group, _ = Group.objects.get_or_create(name=role)
        group.permissions.set([permission_map[c] for c in ROLE_PERMISSION_MAP[role] if c in permission_map])


def get_request_meta(request) -> dict:
    return {
        "ip_address": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:1000],
    }


def create_audit_event(*, event_type, actor=None, target_user=None, request=None, metadata=None):
    meta = metadata or {}
    request_meta = get_request_meta(request) if request is not None else {}
    return AuditEvent.objects.create(
        event_type=event_type,
        actor=actor,
        target_user=target_user,
        metadata=meta,
        **request_meta,
    )


def invalidate_user_sessions(user: User) -> None:
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    for session in sessions:
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) == str(user.pk):
            session.delete()


def user_summary(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "employee_code": user.employee_code,
        "email": user.email,
        "employment_status": user.employment_status,
        "hire_date": user.hire_date.isoformat() if user.hire_date else None,
        "termination_date": user.termination_date.isoformat() if user.termination_date else None,
        "must_change_password": user.must_change_password,
        "is_active": user.is_active,
        "roles": user.role_keys,
    }


def can_assign_roles(actor: User, role_names: list[str]) -> bool:
    if actor.has_role(ROLE_SYSTEM_ADMIN):
        return True
    if actor.has_role(ROLE_SHIFT_MANAGER):
        return all(role in {ROLE_SHIFT_MANAGER, ROLE_SUPERVISOR, ROLE_STAFF, ROLE_VIEWER} for role in role_names)
    return False


def is_last_system_admin(user: User) -> bool:
    return (
        user.has_role(ROLE_SYSTEM_ADMIN)
        and User.objects.filter(groups__name=ROLE_SYSTEM_ADMIN, is_active=True).exclude(pk=user.pk).count() == 0
    )
