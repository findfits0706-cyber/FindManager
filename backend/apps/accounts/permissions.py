from rest_framework.permissions import BasePermission

from .constants import ROLE_SHIFT_MANAGER, ROLE_SYSTEM_ADMIN


class CanViewStaffList(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (
            user.has_role(ROLE_SYSTEM_ADMIN)
            or user.has_role(ROLE_SHIFT_MANAGER)
            or user.has_perm("accounts.view_staff_list")
        )


class CanManageStaff(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (
            user.has_role(ROLE_SYSTEM_ADMIN) or user.has_perm("accounts.manage_staff_basic")
        )
