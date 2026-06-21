from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.test_accounts import BaseAPITestCase
from apps.common.models import AuditEvent

from .models import Location, StaffCapability, StaffLocation, WorkArea, WorkCategory, WorkType, WorkTypeAvailability
from .services import seed_operations


class TestOperationModels(BaseAPITestCase):
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

    def test_location_code_unique(self):
        with self.assertRaises(IntegrityError):
            Location.objects.create(code="main", name="Dup", short_name="Dup")

    def test_work_area_code_unique_per_location(self):
        location = Location.objects.get(code="main")
        with self.assertRaises(IntegrityError):
            WorkArea.objects.create(location=location, code="gym", name="Duplicate")

    def test_work_type_availability_duplicate_blocked(self):
        work_type = WorkType.objects.get(code="gym_duty")
        location = Location.objects.get(code="main")
        area = WorkArea.objects.get(location=location, code="gym")
        with self.assertRaises(IntegrityError):
            WorkTypeAvailability.objects.create(work_type=work_type, location=location, work_area=area)

    def test_staff_location_date_validation(self):
        instance = StaffLocation(
            staff=self.staff,
            location=Location.objects.get(code="findfits"),
            valid_from="2026-06-21",
            valid_until="2026-06-20",
        )
        with self.assertRaises(ValidationError):
            instance.clean()

    def test_primary_staff_location_conflict(self):
        location = Location.objects.get(code="findfits")
        instance = StaffLocation(
            staff=self.staff,
            location=location,
            is_primary=True,
            valid_from=self.staff.staff_locations.first().valid_from,
        )
        with self.assertRaises(ValidationError):
            instance.clean()

    def test_staff_capability_level_choice(self):
        capability = self.staff.staff_capabilities.first()
        self.assertIn(capability.level, dict(StaffCapability.Level.choices))

    def test_inactive_master_history_still_referenced(self):
        capability = self.staff.staff_capabilities.first()
        capability.work_type.is_active = False
        capability.work_type.save()
        capability.refresh_from_db()
        self.assertEqual(capability.work_type.code, "gym_duty")


class TestOperationPermissions(BaseAPITestCase):
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

    def test_system_admin_can_manage_locations(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/locations/",
            {"code": "sub", "name": "Sub Club", "short_name": "SUB", "timezone": "Asia/Tokyo"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_shift_manager_cannot_create_location(self):
        client = self.force_client(self.shift_manager)
        response = client.post(
            "/api/v1/locations/",
            {"code": "sub", "name": "Sub Club", "short_name": "SUB", "timezone": "Asia/Tokyo"},
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


class TestOperationApi(BaseAPITestCase):
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

    def test_location_list_filter(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/locations/?code=main")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_work_type_search_filter(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/work-types/?search=Gym")
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

    def test_deactivate_and_reactivate_location(self):
        client = self.force_client(self.system_admin)
        location = Location.objects.get(code="findpilates")
        deactivate = client.post(f"/api/v1/locations/{location.pk}/deactivate/", {}, format="json")
        self.assertEqual(deactivate.status_code, 200)
        reactivate = client.post(f"/api/v1/locations/{location.pk}/reactivate/", {}, format="json")
        self.assertEqual(reactivate.status_code, 200)

    def test_delete_api_absent(self):
        client = self.force_client(self.system_admin)
        response = client.delete(f"/api/v1/locations/{Location.objects.get(code='main').pk}/")
        self.assertEqual(response.status_code, 405)

    def test_audit_event_created_for_staff_capability(self):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/staff-capabilities/",
            {
                "staff": str(self.supervisor.pk),
                "work_type": str(WorkType.objects.get(code="meeting").pk),
                "location": str(Location.objects.get(code="main").pk),
                "level": "assisted",
                "valid_from": "2026-06-21",
                "approved_by": str(self.system_admin.pk),
                "display_order": 20,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditEvent.objects.filter(event_type="staff_capability_created").exists())

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
