from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
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

    def force_client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


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
    def test_system_admin_can_list_staff(self):
        response = self.force_client(self.system_admin).get("/api/v1/staff/")
        self.assertEqual(response.status_code, 200)

    def test_shift_manager_can_list_staff(self):
        response = self.force_client(self.shift_manager).get("/api/v1/staff/")
        self.assertEqual(response.status_code, 200)

    def test_supervisor_can_list_staff_with_permission(self):
        response = self.force_client(self.supervisor).get("/api/v1/staff/")
        self.assertEqual(response.status_code, 200)

    def test_staff_and_viewer_cannot_list_staff(self):
        for user in (self.staff, self.viewer):
            with self.subTest(username=user.username):
                response = self.force_client(user).get("/api/v1/staff/")
                self.assertEqual(response.status_code, 403)

    def test_staff_list_serializes_multiple_users_and_groups(self):
        self.staff.groups.add(Group.objects.get(name=ROLE_VIEWER))

        response = self.force_client(self.system_admin).get("/api/v1/staff/?page_size=100")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 5)
        serialized_staff = next(item for item in response.data["results"] if item["id"] == str(self.staff.pk))
        self.assertEqual(serialized_staff["roles"], [ROLE_STAFF, ROLE_VIEWER])

    def test_staff_list_includes_inactive_staff(self):
        self.staff.is_active = False
        self.staff.employment_status = User.EmploymentStatus.SUSPENDED
        self.staff.save(update_fields=["is_active", "employment_status", "updated_at"])

        response = self.force_client(self.system_admin).get("/api/v1/staff/?page_size=100")

        self.assertEqual(response.status_code, 200)
        serialized_staff = next(item for item in response.data["results"] if item["id"] == str(self.staff.pk))
        self.assertFalse(serialized_staff["is_active"])
        self.assertEqual(serialized_staff["employment_status"], User.EmploymentStatus.SUSPENDED)

    def test_staff_list_handles_user_without_roles(self):
        roleless = User.objects.create_user(
            username="roleless",
            password=PASSWORD,
            display_name="Roleless User",
            employee_code="EMP-ROLELESS",
            must_change_password=False,
        )

        response = self.force_client(self.system_admin).get("/api/v1/staff/?page_size=100")

        self.assertEqual(response.status_code, 200)
        serialized_user = next(item for item in response.data["results"] if item["id"] == str(roleless.pk))
        self.assertEqual(serialized_user["roles"], [])

    def test_staff_list_keeps_paginated_response_shape(self):
        response = self.force_client(self.system_admin).get("/api/v1/staff/?page_size=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(len(response.data["results"]), 2)

    def test_staff_list_query_count_is_constant(self):
        def query_count():
            actor = User.objects.get(pk=self.system_admin.pk)
            client = self.force_client(actor)
            with CaptureQueriesContext(connection) as queries:
                response = client.get("/api/v1/staff/?page_size=100")
            self.assertEqual(response.status_code, 200)
            return len(queries)

        baseline = query_count()
        for index in range(15):
            self.create_user(f"additional_{index}", ROLE_STAFF)

        self.assertEqual(query_count(), baseline)

    def test_staff_create_permissions(self):
        payload = {
            "username": "newstaff",
            "display_name": "New Staff",
            "employee_code": "EMP-NEW",
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
        client = self.force_client(self.shift_manager)
        response = client.post(
            "/api/v1/staff/",
            {
                "username": "admin2",
                "display_name": "Admin 2",
                "employee_code": "EMP-A2",
                "must_change_password": True,
                "roles": ["system_admin"],
                "temporary_password": "TempPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_deactivate_self(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            f"/api/v1/staff/{self.system_admin.pk}/deactivate/",
            {"reason": "self", "employment_status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_deactivate_last_system_admin(self):
        client = self.force_client(self.shift_manager)
        response = client.post(
            f"/api/v1/staff/{self.system_admin.pk}/deactivate/",
            {"reason": "test", "employment_status": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_staff_deactivate_and_reject_new_login(self):
        self.login()
        client = self.force_client(self.system_admin)
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
        admin_client = self.force_client(self.system_admin)
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
        client = self.force_client(self.system_admin)
        response = client.post(
            f"/api/v1/staff/{self.staff.pk}/reactivate/",
            {"employment_status": "active"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_delete_not_allowed(self):
        client = self.force_client(self.system_admin)
        response = client.delete(f"/api/v1/staff/{self.staff.pk}/")
        self.assertEqual(response.status_code, 405)

    def test_audit_events_recorded(self):
        client = self.force_client(self.system_admin)
        client.patch(
            f"/api/v1/staff/{self.staff.pk}/",
            {"display_name": "Updated", "roles": ["staff"]},
            format="json",
        )
        self.assertTrue(AuditEvent.objects.filter(event_type="account_updated").exists())

    def test_created_staff_is_always_active(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/staff/",
            {
                "username": "createdstaff",
                "display_name": "Created Staff",
                "employee_code": "EMP-CREATED",
                "must_change_password": True,
                "roles": ["staff"],
                "temporary_password": "TempPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(username="createdstaff")
        self.assertTrue(created.is_active)
        self.assertEqual(created.employment_status, User.EmploymentStatus.ACTIVE)

    def test_create_rejects_employment_status_override(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/staff/",
            {
                "username": "badcreate",
                "display_name": "Bad Create",
                "employee_code": "EMP-BADCREATE",
                "employment_status": User.EmploymentStatus.SUSPENDED,
                "must_change_password": True,
                "roles": ["staff"],
                "temporary_password": "TempPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("employment_status", response.data)

    def test_patch_rejects_employment_status_update(self):
        client = self.force_client(self.system_admin)
        response = client.patch(
            f"/api/v1/staff/{self.staff.pk}/",
            {"employment_status": User.EmploymentStatus.SUSPENDED, "roles": ["staff"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("employment_status", response.data)

    def test_patch_rejects_is_active_update(self):
        client = self.force_client(self.system_admin)
        response = client.patch(
            f"/api/v1/staff/{self.staff.pk}/",
            {"is_active": False, "roles": ["staff"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("is_active", response.data)

    def test_patch_rejects_deactivation_fields_update(self):
        client = self.force_client(self.system_admin)
        response = client.patch(
            f"/api/v1/staff/{self.staff.pk}/",
            {
                "deactivated_at": "2026-06-21T00:00:00+09:00",
                "deactivated_by": str(self.system_admin.pk),
                "deactivation_reason": "manual",
                "roles": ["staff"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("deactivated_at", response.data)
        self.assertIn("deactivated_by", response.data)
        self.assertIn("deactivation_reason", response.data)

    def test_last_system_admin_role_cannot_be_removed(self):
        client = self.force_client(self.system_admin)
        response = client.patch(
            f"/api/v1/staff/{self.system_admin.pk}/",
            {"roles": ["shift_manager"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["roles"][0], "最後のsystem_admin権限は解除できません。")

    def test_system_admin_role_can_be_removed_when_multiple_admins_exist(self):
        another_admin = self.create_user("system_admin_2", ROLE_SYSTEM_ADMIN)
        client = self.force_client(self.system_admin)
        response = client.patch(
            f"/api/v1/staff/{another_admin.pk}/",
            {"roles": ["staff"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        another_admin.refresh_from_db()
        self.assertFalse(another_admin.has_role(ROLE_SYSTEM_ADMIN))

    def test_shift_manager_cannot_edit_system_admin(self):
        client = self.force_client(self.shift_manager)
        response = client.patch(
            f"/api/v1/staff/{self.system_admin.pk}/",
            {"display_name": "Edited by shift manager"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
