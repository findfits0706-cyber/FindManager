from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from apps.common.models import AuditEvent

from .constants import (
    ROLE_SHIFT_MANAGER,
    ROLE_STAFF,
    ROLE_SUPERVISOR,
    ROLE_SYSTEM_ADMIN,
    ROLE_VIEWER,
)
from .models import User
from .services import ensure_roles

PASSWORD = "DevPassword123!"


class BaseAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        ensure_roles()
        self.system_admin = self.create_user("system_admin", ROLE_SYSTEM_ADMIN, is_staff=True, is_superuser=True)
        self.shift_manager = self.create_user("shift_manager", ROLE_SHIFT_MANAGER)
        self.supervisor = self.create_user("supervisor", ROLE_SUPERVISOR)
        self.staff = self.create_user("staff", ROLE_STAFF)
        self.viewer = self.create_user("viewer", ROLE_VIEWER)

    def create_user(self, username, role, **extra):
        user = User.objects.create_user(
            username=username,
            password=PASSWORD,
            display_name=f"{username} user",
            employee_code=f"EMP-{username.upper()}",
            must_change_password=False,
            **extra,
        )
        user.groups.set(Group.objects.filter(name=role))
        return user

    def login(self, username="system_admin", password=PASSWORD):
        self.client.get("/api/v1/auth/csrf/")
        return self.client.post("/api/v1/auth/login/", {"username": username, "password": password}, format="json")


class TestAuth(BaseAPITestCase):
    def test_login_success(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["username"], "system_admin")
        self.assertTrue(AuditEvent.objects.filter(event_type="login_success").exists())

    def test_wrong_password(self):
        response = self.login(password="wrong")
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_inactive_user_rejected(self):
        self.staff.is_active = False
        self.staff.save()
        response = self.login("staff")
        self.assertEqual(response.status_code, 400)

    def test_suspended_user_rejected(self):
        self.staff.employment_status = User.EmploymentStatus.SUSPENDED
        self.staff.save()
        response = self.login("staff")
        self.assertEqual(response.status_code, 400)

    def test_terminated_user_rejected(self):
        self.staff.employment_status = User.EmploymentStatus.TERMINATED
        self.staff.is_active = False
        self.staff.save()
        response = self.login("staff")
        self.assertEqual(response.status_code, 400)

    def test_logout(self):
        self.login()
        response = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, 204)

    def test_me(self):
        self.login()
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "system_admin")

    def test_password_change_required_flag(self):
        self.staff.must_change_password = True
        self.staff.save()
        self.login("staff")
        response = self.client.get("/api/v1/auth/me/")
        self.assertTrue(response.data["must_change_password"])

    def test_password_change(self):
        self.login("staff")
        response = self.client.post(
            "/api/v1/auth/change-password/",
            {
                "current_password": PASSWORD,
                "new_password": "NewPassword123!",
                "new_password_confirm": "NewPassword123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.must_change_password)
        self.assertTrue(self.staff.check_password("NewPassword123!"))


class TestStaffPermissions(BaseAPITestCase):
    def test_staff_list_permissions(self):
        cases = [
            (self.system_admin, 200),
            (self.shift_manager, 200),
            (self.supervisor, 200),
            (self.staff, 403),
            (self.viewer, 403),
        ]
        for user, expected in cases:
            client = APIClient()
            client.force_authenticate(user=user)
            response = client.get("/api/v1/staff/")
            self.assertEqual(response.status_code, expected)

    def test_staff_create_permissions(self):
        payload = {
            "username": "newstaff",
            "display_name": "New Staff",
            "employee_code": "EMP-NEW",
            "employment_status": "active",
            "must_change_password": True,
            "roles": ["staff"],
            "temporary_password": "TempPass123!",
        }
        cases = [
            (self.system_admin, 201),
            (self.shift_manager, 201),
            (self.supervisor, 403),
            (self.staff, 403),
        ]
        for index, (user, expected) in enumerate(cases):
            payload["username"] = f"newstaff{index}"
            payload["employee_code"] = f"EMP-NEW-{index}"
            client = APIClient()
            client.force_authenticate(user=user)
            response = client.post("/api/v1/staff/", payload, format="json")
            self.assertEqual(response.status_code, expected)

    def test_non_admin_cannot_assign_system_admin(self):
        client = APIClient()
        client.force_authenticate(user=self.shift_manager)
        response = client.post(
            "/api/v1/staff/",
            {
                "username": "admin2",
                "display_name": "Admin 2",
                "employee_code": "EMP-A2",
                "employment_status": "active",
                "must_change_password": True,
                "roles": ["system_admin"],
                "temporary_password": "TempPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_deactivate_self(self):
        client = APIClient()
        client.force_authenticate(user=self.system_admin)
        response = client.post(
            f"/api/v1/staff/{self.system_admin.pk}/deactivate/",
            {"reason": "self", "employment_status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_deactivate_last_system_admin(self):
        client = APIClient()
        client.force_authenticate(user=self.shift_manager)
        response = client.post(
            f"/api/v1/staff/{self.system_admin.pk}/deactivate/",
            {"reason": "test", "employment_status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_staff_deactivate_and_reject_new_login(self):
        self.login()
        client = APIClient()
        client.force_authenticate(user=self.system_admin)
        response = client.post(
            f"/api/v1/staff/{self.staff.pk}/deactivate/",
            {"reason": "stop", "employment_status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        login_response = self.login("staff")
        self.assertEqual(login_response.status_code, 400)

    def test_existing_sessions_invalidated_on_deactivate(self):
        client = APIClient()
        client.get("/api/v1/auth/csrf/")
        client.post("/api/v1/auth/login/", {"username": "staff", "password": PASSWORD}, format="json")
        self.assertEqual(Session.objects.count(), 1)
        admin_client = APIClient()
        admin_client.force_authenticate(user=self.system_admin)
        admin_client.post(
            f"/api/v1/staff/{self.staff.pk}/deactivate/",
            {"reason": "stop", "employment_status": "suspended"},
            format="json",
        )
        self.assertEqual(Session.objects.count(), 0)

    def test_staff_reactivate(self):
        self.staff.is_active = False
        self.staff.employment_status = User.EmploymentStatus.SUSPENDED
        self.staff.save()
        client = APIClient()
        client.force_authenticate(user=self.system_admin)
        response = client.post(
            f"/api/v1/staff/{self.staff.pk}/reactivate/",
            {"employment_status": "active"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_delete_not_allowed(self):
        client = APIClient()
        client.force_authenticate(user=self.system_admin)
        response = client.delete(f"/api/v1/staff/{self.staff.pk}/")
        self.assertEqual(response.status_code, 405)

    def test_audit_events_recorded(self):
        client = APIClient()
        client.force_authenticate(user=self.system_admin)
        client.patch(
            f"/api/v1/staff/{self.staff.pk}/",
            {"display_name": "Updated", "roles": ["staff"]},
            format="json",
        )
        self.assertTrue(AuditEvent.objects.filter(event_type="account_updated").exists())
