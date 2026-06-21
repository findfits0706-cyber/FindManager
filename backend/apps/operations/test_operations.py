from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.accounts.test_accounts import BaseAPITestCase
from apps.common.models import AuditEvent

from .models import Location, StaffCapability, StaffLocation, WorkArea, WorkCategory, WorkType, WorkTypeAvailability
from .services import seed_operations


class OperationsBaseTestCase(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        seed_operations(
            {
                "system_admin": self.system_admin,
                "shift_manager": self.shift_manager,
                "supervisor": self.supervisor,
                "staff": self.staff,
                "viewer": self.viewer,
            }
        )


class TestOperationModels(OperationsBaseTestCase):
    def test_location_code_unique(self):
        with self.assertRaises(IntegrityError):
            Location.objects.create(code="main", name="Dup", short_name="Dup")

    def test_work_area_code_unique_per_location(self):
        location = Location.objects.get(code="main")
        with self.assertRaises(IntegrityError):
            WorkArea.objects.create(location=location, code="gym", name="Duplicate")

    def test_work_type_availability_duplicate_null_work_area_blocked(self):
        work_type = WorkType.objects.get(code="meeting")
        location = Location.objects.get(code="main")
        WorkTypeAvailability.objects.create(work_type=work_type, location=location, work_area=None)
        duplicate = WorkTypeAvailability(work_type=work_type, location=location, work_area=None)
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_staff_location_duplicate_null_valid_until_blocked(self):
        location = Location.objects.get(code="main")
        duplicate = StaffLocation(
            staff=self.staff,
            location=location,
            valid_from=self.staff.staff_locations.first().valid_from,
            valid_until=None,
        )
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_staff_capability_duplicate_nulls_blocked(self):
        work_type = WorkType.objects.get(code="meeting")
        StaffCapability.objects.create(
            staff=self.staff,
            work_type=work_type,
            location=None,
            level=StaffCapability.Level.TRAINEE,
            valid_from=timezone.localdate(),
            valid_until=None,
        )
        duplicate = StaffCapability(
            staff=self.staff,
            work_type=work_type,
            location=None,
            level=StaffCapability.Level.ASSISTED,
            valid_from=timezone.localdate(),
            valid_until=None,
        )
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_staff_location_date_validation(self):
        instance = StaffLocation(
            staff=self.staff,
            location=Location.objects.get(code="findfits"),
            valid_from="2026-06-21",
            valid_until="2026-06-20",
        )
        with self.assertRaises(ValidationError):
            instance.clean()

    def test_primary_staff_location_overlap_conflict(self):
        location = Location.objects.get(code="findfits")
        existing = self.staff.staff_locations.first()
        instance = StaffLocation(
            staff=self.staff,
            location=location,
            is_primary=True,
            valid_from=existing.valid_from,
            valid_until=None,
        )
        with self.assertRaises(ValidationError):
            instance.clean()

    def test_staff_capability_overlap_conflict(self):
        existing = self.staff.staff_capabilities.first()
        instance = StaffCapability(
            staff=self.staff,
            work_type=existing.work_type,
            location=existing.location,
            level=StaffCapability.Level.TRAINEE,
            valid_from=existing.valid_from,
            valid_until=None,
        )
        with self.assertRaises(ValidationError):
            instance.clean()

    def test_work_type_validation_rules(self):
        work_type = WorkType(
            category=WorkCategory.objects.get(code="general"),
            code="invalid",
            name="Invalid",
            short_name="Invalid",
            default_duration_minutes=10,
            minimum_staff_count=0,
            maximum_staff_count=0,
        )
        with self.assertRaises(ValidationError):
            work_type.clean()


class TestOperationPermissions(OperationsBaseTestCase):
    def test_system_admin_can_manage_locations(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/locations/",
            {"code": "sub", "name": "支店", "short_name": "支店", "timezone": "Asia/Tokyo"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_shift_manager_cannot_create_location(self):
        client = self.force_client(self.shift_manager)
        response = client.post(
            "/api/v1/locations/",
            {"code": "sub", "name": "支店", "short_name": "支店", "timezone": "Asia/Tokyo"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_shift_manager_can_manage_staff_location(self):
        client = self.force_client(self.shift_manager)
        response = client.post(
            "/api/v1/staff-locations/",
            {
                "staff": str(self.supervisor.pk),
                "location": str(Location.objects.get(code="findfits").pk),
                "is_primary": False,
                "valid_from": "2026-06-21",
                "display_order": 20,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_supervisor_view_only(self):
        client = self.force_client(self.supervisor)
        response = client.patch(
            f"/api/v1/work-types/{WorkType.objects.get(code='gym_duty').pk}/",
            {"name": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_only_own_staff_locations(self):
        client = self.force_client(self.staff)
        response = client.get("/api/v1/staff-locations/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(str(item["staff"]) == str(self.staff.pk) for item in response.data["results"]))

    def test_viewer_only_own_capabilities(self):
        client = self.force_client(self.viewer)
        response = client.get("/api/v1/staff-capabilities/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(str(item["staff"]) == str(self.viewer.pk) for item in response.data["results"]))

    def test_staff_cannot_access_other_staff_detail(self):
        client = self.force_client(self.staff)
        other_capability = self.viewer.staff_capabilities.first()
        response = client.get(f"/api/v1/staff-capabilities/{other_capability.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_staff_cannot_view_inactive_master(self):
        location = Location.objects.get(code="findfits")
        location.is_active = False
        location.save(update_fields=["is_active", "updated_at"])
        client = self.force_client(self.staff)
        response = client.get(f"/api/v1/locations/{location.pk}/")
        self.assertEqual(response.status_code, 404)


class TestOperationApi(OperationsBaseTestCase):
    def test_location_list_filter(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/locations/?code=main")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_work_type_search_filter(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/work-types/?search=ジム")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_staff_capability_reference_date_filter(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/staff-capabilities/?reference_date=2026-06-21")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_patch_cannot_change_is_active(self):
        client = self.force_client(self.system_admin)
        response = client.patch(
            f"/api/v1/locations/{Location.objects.get(code='main').pk}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_cannot_set_is_active(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/locations/",
            {
                "code": "inactive",
                "name": "Inactive",
                "short_name": "Inactive",
                "timezone": "Asia/Tokyo",
                "is_active": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_deactivate_and_reactivate_location(self):
        client = self.force_client(self.system_admin)
        location = Location.objects.get(code="findpilates")
        deactivate = client.post(f"/api/v1/locations/{location.pk}/deactivate/", {}, format="json")
        self.assertEqual(deactivate.status_code, 200)
        reactivate = client.post(f"/api/v1/locations/{location.pk}/reactivate/", {}, format="json")
        self.assertEqual(reactivate.status_code, 200)

    def test_work_type_availability_reactivate(self):
        client = self.force_client(self.system_admin)
        availability = WorkTypeAvailability.objects.create(
            work_type=WorkType.objects.get(code="meeting"),
            location=Location.objects.get(code="main"),
            work_area=None,
            is_active=False,
        )
        response = client.post(f"/api/v1/work-type-availabilities/{availability.pk}/reactivate/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditEvent.objects.filter(event_type="work_type_availability_reactivated").exists())

    def test_staff_location_reactivate(self):
        client = self.force_client(self.shift_manager)
        staff_location = StaffLocation.objects.create(
            staff=self.staff,
            location=Location.objects.get(code="findpilates"),
            is_primary=False,
            valid_from="2026-07-01",
            valid_until=None,
            is_active=False,
        )
        response = client.post(f"/api/v1/staff-locations/{staff_location.pk}/reactivate/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditEvent.objects.filter(event_type="staff_location_reactivated").exists())

    def test_staff_capability_reactivate(self):
        client = self.force_client(self.shift_manager)
        capability = StaffCapability.objects.create(
            staff=self.staff,
            work_type=WorkType.objects.get(code="meeting"),
            location=Location.objects.get(code="main"),
            level="assisted",
            valid_from="2026-07-01",
            valid_until=None,
            is_active=False,
        )
        response = client.post(f"/api/v1/staff-capabilities/{capability.pk}/reactivate/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        capability.refresh_from_db()
        self.assertEqual(capability.approved_by_id, self.shift_manager.pk)
        self.assertIsNotNone(capability.approved_at)
        self.assertTrue(AuditEvent.objects.filter(event_type="staff_capability_reactivated").exists())

    def test_delete_api_absent(self):
        client = self.force_client(self.system_admin)
        response = client.delete(f"/api/v1/locations/{Location.objects.get(code='main').pk}/")
        self.assertEqual(response.status_code, 405)

    def test_staff_capability_approval_fields_are_read_only(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/staff-capabilities/",
            {
                "staff": str(self.supervisor.pk),
                "work_type": str(WorkType.objects.get(code="meeting").pk),
                "location": str(Location.objects.get(code="main").pk),
                "level": "assisted",
                "valid_from": "2026-06-21",
                "approved_by": str(self.shift_manager.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_audit_event_created_for_staff_capability(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/staff-capabilities/",
            {
                "staff": str(self.supervisor.pk),
                "work_type": str(WorkType.objects.get(code="meeting").pk),
                "location": str(Location.objects.get(code="main").pk),
                "level": "assisted",
                "valid_from": "2026-06-22",
                "display_order": 20,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created = StaffCapability.objects.get(id=response.data["id"])
        self.assertEqual(created.approved_by_id, self.system_admin.pk)
        self.assertIsNotNone(created.approved_at)
        self.assertTrue(AuditEvent.objects.filter(event_type="staff_capability_created").exists())

    def test_invalid_foreign_key_returns_400(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/staff-locations/",
            {
                "staff": "00000000-0000-0000-0000-000000000000",
                "location": str(Location.objects.get(code="main").pk),
                "is_primary": False,
                "valid_from": "2026-06-21",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_inactive_location_reference_returns_400(self):
        client = self.force_client(self.system_admin)
        location = Location.objects.get(code="findpilates")
        location.is_active = False
        location.save(update_fields=["is_active", "updated_at"])
        response = client.post(
            "/api/v1/work-areas/",
            {"location": str(location.pk), "code": "sub", "name": "Sub"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_my_staff_locations_endpoint(self):
        client = self.force_client(self.staff)
        response = client.get("/api/v1/my-staff-locations/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_my_capabilities_endpoint(self):
        client = self.force_client(self.staff)
        response = client.get("/api/v1/my-capabilities/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)


class TestSeedDevOperations(APITestCase):
    @override_settings(DEBUG=True)
    def test_seed_dev_is_idempotent(self):
        call_command("seed_dev")
        first_counts = (
            Location.objects.count(),
            WorkArea.objects.count(),
            WorkCategory.objects.count(),
            WorkType.objects.count(),
            StaffLocation.objects.count(),
            StaffCapability.objects.count(),
        )
        call_command("seed_dev")
        second_counts = (
            Location.objects.count(),
            WorkArea.objects.count(),
            WorkCategory.objects.count(),
            WorkType.objects.count(),
            StaffLocation.objects.count(),
            StaffCapability.objects.count(),
        )
        self.assertEqual(first_counts, second_counts)

    @override_settings(DEBUG=True)
    def test_seed_dev_keeps_existing_password_without_reset_flag(self):
        call_command("seed_dev")
        user = User.objects.get(username="staff")
        user.set_password("ExistingPassword123!")
        user.save()
        call_command("seed_dev")
        user.refresh_from_db()
        self.assertTrue(user.check_password("ExistingPassword123!"))
