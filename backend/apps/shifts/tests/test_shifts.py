from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.accounts.test_accounts import BaseAPITestCase
from apps.common.models import AuditEvent
from apps.operations.models import Location, StaffCapability, StaffLocation, WorkArea, WorkType, WorkTypeAvailability
from apps.operations.services import seed_operations

from ..models import (
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftSegment,
    ShiftPattern,
    ShiftPatternSegment,
    WeeklyShiftTemplate,
    WeeklyShiftTemplateEntry,
)
from ..services import seed_shifts


class ShiftsBaseTestCase(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.dev_users = {
            "system_admin": self.system_admin,
            "shift_manager": self.shift_manager,
            "supervisor": self.supervisor,
            "staff": self.staff,
            "viewer": self.viewer,
        }
        seed_operations(self.dev_users)
        seed_shifts(self.dev_users)
        self.location = Location.objects.get(code="main")
        self.gym_area = WorkArea.objects.get(location=self.location, code="gym")
        self.gym_work = WorkType.objects.get(code="gym_duty")
        self.break_work = WorkType.objects.get(code="break")

    def pattern_payload(self, code="api_pattern"):
        return {
            "location": str(self.location.id),
            "code": code,
            "name": "API勤務",
            "short_name": "API",
            "description": "",
            "display_order": 90,
            "segments": [
                {
                    "work_type": str(self.gym_work.id),
                    "work_area": str(self.gym_area.id),
                    "start_offset_minutes": 540,
                    "end_offset_minutes": 720,
                    "display_order": 10,
                    "notes": "",
                }
            ],
        }


class TestShiftPatternModels(ShiftsBaseTestCase):
    def test_code_unique_per_location(self):
        pattern = ShiftPattern(location=self.location, code="gym_early", name="Dup", short_name="Dup")
        with self.assertRaises(ValidationError):
            pattern.full_clean()

    def test_same_code_allowed_in_different_location(self):
        location = Location.objects.get(code="findfits")
        pattern = ShiftPattern(location=location, code="gym_early", name="Other", short_name="Other")
        pattern.full_clean()

    def test_segment_time_validation(self):
        pattern = ShiftPattern.objects.get(code="gym_early")
        segment = ShiftPatternSegment(
            shift_pattern=pattern,
            work_type=self.gym_work,
            work_area=self.gym_area,
            start_offset_minutes=541,
            end_offset_minutes=600,
        )
        with self.assertRaises(ValidationError):
            segment.clean()

    def test_next_day_segment_is_allowed(self):
        pattern = ShiftPattern.objects.get(code="gym_early")
        segment = ShiftPatternSegment(
            shift_pattern=pattern,
            work_type=self.gym_work,
            work_area=self.gym_area,
            start_offset_minutes=1380,
            end_offset_minutes=1500,
        )
        segment.clean()

    def test_missing_work_type_availability_is_rejected(self):
        pattern = ShiftPattern.objects.get(code="gym_early")
        WorkTypeAvailability.objects.filter(work_type=self.gym_work, location=self.location).update(is_active=False)
        segment = ShiftPatternSegment(
            shift_pattern=pattern,
            work_type=self.gym_work,
            work_area=self.gym_area,
            start_offset_minutes=540,
            end_offset_minutes=600,
        )
        with self.assertRaises(ValidationError):
            segment.clean()


class TestShiftPatternApi(ShiftsBaseTestCase):
    def test_system_admin_and_shift_manager_can_create_patterns(self):
        response = self.force_client(self.system_admin).post(
            "/api/v1/shift-patterns/",
            self.pattern_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.force_client(self.shift_manager)
            .post(
                "/api/v1/shift-patterns/",
                self.pattern_payload(code="manager_pattern"),
                format="json",
            )
            .status_code,
            201,
        )

    def test_supervisor_and_staff_permissions(self):
        supervisor = self.force_client(self.supervisor)
        self.assertEqual(supervisor.get("/api/v1/shift-patterns/").status_code, 200)
        response = supervisor.post("/api/v1/shift-patterns/", self.pattern_payload(), format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.force_client(self.staff).get("/api/v1/shift-patterns/").status_code, 403)
        self.assertEqual(self.force_client(self.viewer).get("/api/v1/shift-patterns/").status_code, 403)

    def test_nested_update_logically_deactivates_removed_segment(self):
        client = self.force_client(self.system_admin)
        created = client.post("/api/v1/shift-patterns/", self.pattern_payload(), format="json")
        segment_id = created.data["segments"][0]["id"]
        update = self.pattern_payload()
        update["segments"] = [
            {
                "id": segment_id,
                "work_type": str(self.gym_work.id),
                "work_area": str(self.gym_area.id),
                "start_offset_minutes": 600,
                "end_offset_minutes": 720,
                "display_order": 10,
                "notes": "",
            },
            {
                "work_type": str(self.gym_work.id),
                "work_area": str(self.gym_area.id),
                "start_offset_minutes": 720,
                "end_offset_minutes": 780,
                "display_order": 20,
                "notes": "",
            },
        ]
        response = client.patch(f"/api/v1/shift-patterns/{created.data['id']}/", update, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = client.patch(
            f"/api/v1/shift-patterns/{created.data['id']}/",
            {**update, "segments": [update["segments"][0]]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        active_count = ShiftPatternSegment.objects.filter(
            shift_pattern_id=created.data["id"],
            is_active=True,
        ).count()
        self.assertEqual(active_count, 1)

    def test_duplicate_deactivate_reactivate_and_audit(self):
        client = self.force_client(self.system_admin)
        source = ShiftPattern.objects.get(code="gym_early")
        duplicate = client.post(
            f"/api/v1/shift-patterns/{source.id}/duplicate/",
            {"code": "gym_early_copy", "name": "コピー", "short_name": "コピー"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 201)
        self.assertTrue(AuditEvent.objects.filter(event_type="shift_pattern_duplicated").exists())
        deactivate = client.post(f"/api/v1/shift-patterns/{duplicate.data['id']}/deactivate/", {}, format="json")
        reactivate = client.post(f"/api/v1/shift-patterns/{duplicate.data['id']}/reactivate/", {}, format="json")
        self.assertEqual(deactivate.status_code, 200)
        self.assertEqual(reactivate.status_code, 200)

    def test_filters_search_delete_and_foreign_child_rejected(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/shift-patterns/?search=早番&is_active=true")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)
        self.assertEqual(client.delete(f"/api/v1/shift-patterns/{ShiftPattern.objects.first().id}/").status_code, 405)
        other_segment = ShiftPattern.objects.get(code="gym_late").segments.first()
        payload = self.pattern_payload()
        payload["segments"][0]["id"] = str(other_segment.id)
        response = client.post("/api/v1/shift-patterns/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_list_omits_segments_and_detail_includes_segments(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/shift-patterns/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("segments", response.data["results"][0])
        detail = client.get(f"/api/v1/shift-patterns/{ShiftPattern.objects.get(code='gym_early').id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("segments", detail.data)

    def test_location_change_and_duplicate_child_id_are_rejected(self):
        client = self.force_client(self.system_admin)
        pattern = ShiftPattern.objects.get(code="gym_early")
        other_location = Location.objects.get(code="findfits")
        response = client.patch(
            f"/api/v1/shift-patterns/{pattern.id}/",
            {"location": str(other_location.id), "name": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        segment = pattern.segments.filter(is_active=True).first()
        payload = self.pattern_payload()
        payload["segments"] = [
            {**payload["segments"][0], "id": str(segment.id)},
            {**payload["segments"][0], "id": str(segment.id)},
        ]
        response = client.patch(f"/api/v1/shift-patterns/{pattern.id}/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_inactive_invalid_segment_history_does_not_block_update_but_reactivation_fails(self):
        client = self.force_client(self.system_admin)
        pattern = ShiftPattern.objects.get(code="gym_early")
        stale = ShiftPatternSegment.objects.create(
            shift_pattern=pattern,
            work_type=self.gym_work,
            work_area=self.gym_area,
            start_offset_minutes=1200,
            end_offset_minutes=1260,
            is_active=False,
        )
        self.gym_work.is_active = False
        self.gym_work.save(update_fields=["is_active", "updated_at"])
        active_segment = pattern.segments.filter(is_active=True).exclude(id=stale.id).first()
        payload = self.pattern_payload()
        payload["segments"][0]["id"] = str(active_segment.id)
        payload["segments"][0]["work_type"] = str(WorkType.objects.get(code="front_duty").id)
        payload["segments"][0]["work_area"] = str(WorkArea.objects.get(location=self.location, code="front").id)
        response = client.patch(f"/api/v1/shift-patterns/{pattern.id}/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        payload["segments"][0]["id"] = str(stale.id)
        payload["segments"][0]["work_type"] = str(self.gym_work.id)
        payload["segments"][0]["work_area"] = str(self.gym_area.id)
        response = client.patch(f"/api/v1/shift-patterns/{pattern.id}/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_omitted_inactive_segment_history_is_not_resaved(self):
        client = self.force_client(self.system_admin)
        pattern = ShiftPattern.objects.get(code="gym_early")
        stale = ShiftPatternSegment.objects.create(
            shift_pattern=pattern,
            work_type=self.gym_work,
            work_area=self.gym_area,
            start_offset_minutes=1200,
            end_offset_minutes=1260,
            is_active=False,
        )
        stale_updated_at = stale.updated_at
        segments = []
        active_segments = list(pattern.segments.filter(is_active=True).order_by("start_offset_minutes"))
        for index, segment in enumerate(active_segments):
            segments.append(
                {
                    "id": str(segment.id),
                    "work_type": str(segment.work_type_id),
                    "work_area": str(segment.work_area_id) if segment.work_area_id else None,
                    "start_offset_minutes": segment.start_offset_minutes,
                    "end_offset_minutes": segment.end_offset_minutes,
                    "display_order": segment.display_order,
                    "notes": "updated" if index == 0 else segment.notes,
                }
            )
        response = client.patch(f"/api/v1/shift-patterns/{pattern.id}/", {"segments": segments}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        stale.refresh_from_db()
        self.assertEqual(stale.updated_at, stale_updated_at)

    def test_reactivate_invalid_pattern_returns_400_and_keeps_inactive(self):
        client = self.force_client(self.system_admin)
        pattern = ShiftPattern.objects.get(code="gym_late")
        pattern.is_active = False
        pattern.save(update_fields=["is_active", "updated_at"])
        pattern.segments.update(is_active=False)
        response = client.post(f"/api/v1/shift-patterns/{pattern.id}/reactivate/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        pattern.refresh_from_db()
        self.assertFalse(pattern.is_active)
        self.assertFalse(
            AuditEvent.objects.filter(event_type="shift_pattern_reactivated", metadata__id=str(pattern.id)).exists()
        )

    def test_referenced_pattern_deactivate_is_rejected_and_unreferenced_allowed(self):
        client = self.force_client(self.system_admin)
        referenced = ShiftPattern.objects.get(code="gym_early")
        response = client.post(f"/api/v1/shift-patterns/{referenced.id}/deactivate/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        source = ShiftPattern.objects.get(code="front_early")
        duplicate = client.post(
            f"/api/v1/shift-patterns/{source.id}/duplicate/",
            {"code": "front_free", "name": "Free", "short_name": "Free"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 201)
        response = client.post(f"/api/v1/shift-patterns/{duplicate.data['id']}/deactivate/", {}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_duplicate_code_and_audit_failure_rollback(self):
        client = self.force_client(self.system_admin)
        source = ShiftPattern.objects.get(code="front_early")
        response = client.post(
            f"/api/v1/shift-patterns/{source.id}/duplicate/",
            {"code": "gym_early", "name": "Dup", "short_name": "Dup"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        with patch("apps.shifts.views.record_shift_event", side_effect=RuntimeError("audit failed")):
            response = client.post("/api/v1/shift-patterns/", self.pattern_payload(code="audit_fail"), format="json")
        self.assertGreaterEqual(response.status_code, 500)
        self.assertFalse(ShiftPattern.objects.filter(code="audit_fail").exists())


class TestWeeklyTemplateApi(ShiftsBaseTestCase):
    def template_payload(self, code="api_week"):
        return {
            "location": str(self.location.id),
            "code": code,
            "name": "API週間",
            "description": "",
            "display_order": 90,
            "entries": [
                {
                    "weekday": 0,
                    "staff": str(self.staff.id),
                    "shift_pattern": str(ShiftPattern.objects.get(code="gym_early").id),
                    "notes": "",
                    "display_order": 10,
                }
            ],
        }

    def test_nested_create_update_and_row_removal(self):
        client = self.force_client(self.shift_manager)
        created = client.post("/api/v1/weekly-shift-templates/", self.template_payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        entry_id = created.data["entries"][0]["id"]
        update = self.template_payload()
        update["entries"] = [{**update["entries"][0], "id": entry_id, "weekday": 1}]
        response = client.patch(f"/api/v1/weekly-shift-templates/{created.data['id']}/", update, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = client.patch(
            f"/api/v1/weekly-shift-templates/{created.data['id']}/",
            {**update, "entries": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        active_count = WeeklyShiftTemplateEntry.objects.filter(
            weekly_shift_template_id=created.data["id"],
            is_active=True,
        ).count()
        self.assertEqual(active_count, 0)

    def test_duplicate_and_staff_filter(self):
        client = self.force_client(self.system_admin)
        source = WeeklyShiftTemplate.objects.get(code="standard_week")
        duplicate = client.post(
            f"/api/v1/weekly-shift-templates/{source.id}/duplicate/",
            {"code": "standard_week_copy", "name": "標準週間テンプレート コピー"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 201)
        self.assertTrue(AuditEvent.objects.filter(event_type="weekly_shift_template_duplicated").exists())
        response = client.get(f"/api/v1/weekly-shift-templates/?staff={self.staff.id}")
        self.assertGreaterEqual(response.data["count"], 1)

    def test_supervisor_read_only_staff_denied_and_delete_absent(self):
        template = WeeklyShiftTemplate.objects.get(code="standard_week")
        self.assertEqual(self.force_client(self.supervisor).get("/api/v1/weekly-shift-templates/").status_code, 200)
        supervisor_update = self.force_client(self.supervisor).patch(
            f"/api/v1/weekly-shift-templates/{template.id}/",
            {"name": "x"},
            format="json",
        )
        self.assertEqual(supervisor_update.status_code, 403)
        self.assertEqual(self.force_client(self.viewer).get("/api/v1/weekly-shift-templates/").status_code, 403)
        self.assertEqual(self.force_client(self.staff).get("/api/v1/weekly-shift-templates/").status_code, 403)
        delete_response = self.force_client(self.system_admin).delete(f"/api/v1/weekly-shift-templates/{template.id}/")
        self.assertEqual(delete_response.status_code, 405)

    def test_entry_validation_rules(self):
        other_location = Location.objects.get(code="findfits")
        pattern = ShiftPattern.objects.create(location=other_location, code="other", name="Other", short_name="Other")
        entry = WeeklyShiftTemplateEntry(
            weekly_shift_template=WeeklyShiftTemplate.objects.get(code="standard_week"),
            weekday=7,
            staff=self.staff,
            shift_pattern=pattern,
        )
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_list_omits_entries_and_detail_includes_entries(self):
        client = self.force_client(self.system_admin)
        response = client.get("/api/v1/weekly-shift-templates/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("entries", response.data["results"][0])
        template_id = WeeklyShiftTemplate.objects.get(code="standard_week").id
        detail = client.get(f"/api/v1/weekly-shift-templates/{template_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("entries", detail.data)

    def test_location_change_duplicate_child_id_and_reactivate_validation(self):
        client = self.force_client(self.system_admin)
        template = WeeklyShiftTemplate.objects.get(code="standard_week")
        other_location = Location.objects.get(code="findfits")
        response = client.patch(
            f"/api/v1/weekly-shift-templates/{template.id}/",
            {"location": str(other_location.id), "name": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        entry = template.entries.filter(is_active=True).first()
        payload = self.template_payload()
        payload["entries"] = [
            {**payload["entries"][0], "id": str(entry.id)},
            {**payload["entries"][0], "id": str(entry.id)},
        ]
        response = client.patch(f"/api/v1/weekly-shift-templates/{template.id}/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        template.is_active = False
        template.save(update_fields=["is_active", "updated_at"])
        ShiftPattern.objects.filter(id=entry.shift_pattern_id).update(is_active=False)
        response = client.post(f"/api/v1/weekly-shift-templates/{template.id}/reactivate/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        template.refresh_from_db()
        self.assertFalse(template.is_active)

    def test_inactive_invalid_entry_history_does_not_block_update_but_reactivation_fails(self):
        client = self.force_client(self.system_admin)
        template = WeeklyShiftTemplate.objects.get(code="standard_week")
        stale = template.entries.filter(is_active=True).first()
        stale.is_active = False
        stale.save(update_fields=["is_active", "updated_at"])
        stale.staff.is_active = False
        stale.staff.save(update_fields=["is_active", "updated_at"])
        replacement_staff = self.staff if stale.staff_id != self.staff.id else self.shift_manager
        payload = self.template_payload(code=template.code)
        payload["entries"][0]["weekday"] = 6
        payload["entries"][0]["staff"] = str(replacement_staff.id)
        response = client.patch(f"/api/v1/weekly-shift-templates/{template.id}/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        payload["entries"][0]["id"] = str(stale.id)
        payload["entries"][0]["staff"] = str(stale.staff_id)
        response = client.patch(f"/api/v1/weekly-shift-templates/{template.id}/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_omitted_inactive_entry_history_is_not_resaved(self):
        client = self.force_client(self.system_admin)
        template = WeeklyShiftTemplate.objects.get(code="standard_week")
        pattern = ShiftPattern.objects.get(code="gym_early")
        stale = WeeklyShiftTemplateEntry.objects.create(
            weekly_shift_template=template,
            weekday=6,
            staff=self.supervisor,
            shift_pattern=pattern,
            is_active=False,
        )
        stale_updated_at = stale.updated_at
        entries = []
        active_entries = list(template.entries.filter(is_active=True).order_by("staff_id", "weekday"))
        for index, entry in enumerate(active_entries):
            entries.append(
                {
                    "id": str(entry.id),
                    "weekday": entry.weekday,
                    "staff": str(entry.staff_id),
                    "shift_pattern": str(entry.shift_pattern_id),
                    "notes": "updated" if index == 0 else entry.notes,
                    "display_order": entry.display_order,
                }
            )
        response = client.patch(f"/api/v1/weekly-shift-templates/{template.id}/", {"entries": entries}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        stale.refresh_from_db()
        self.assertEqual(stale.updated_at, stale_updated_at)

    def test_duplicate_code_and_audit_failure_rollback(self):
        client = self.force_client(self.system_admin)
        source = WeeklyShiftTemplate.objects.get(code="standard_week")
        response = client.post(
            f"/api/v1/weekly-shift-templates/{source.id}/duplicate/",
            {"code": "standard_week", "name": "Dup"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        with patch("apps.shifts.views.record_shift_event", side_effect=RuntimeError("audit failed")):
            response = client.post(
                "/api/v1/weekly-shift-templates/",
                self.template_payload(code="audit_week"),
                format="json",
            )
        self.assertGreaterEqual(response.status_code, 500)
        self.assertFalse(WeeklyShiftTemplate.objects.filter(code="audit_week").exists())


class TestMonthlyShiftApi(ShiftsBaseTestCase):
    def plan_payload(self, year=2026, month=7, suffix=""):
        return {
            "location": str(self.location.id),
            "year": year,
            "month": month,
            "name": f"{year}年{month}月 本館シフト{suffix}",
            "notes": "",
        }

    def create_plan(self, year=2026, month=7):
        return MonthlyShiftPlan.objects.create(
            location=self.location,
            year=year,
            month=month,
            name=f"{year}年{month}月 本館シフト",
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )

    def assignment_payload(self, plan, staff=None, work_date="2026-07-01", pattern_code="gym_early"):
        return {
            "monthly_shift_plan": str(plan.id),
            "work_date": work_date,
            "staff": str((staff or self.staff).id),
            "shift_pattern": str(ShiftPattern.objects.get(code=pattern_code).id),
            "notes": "",
        }

    def test_plan_permissions_immutability_deactivate_and_reactivate_conflict(self):
        admin = self.force_client(self.system_admin)
        response = admin.post("/api/v1/monthly-shift-plans/", self.plan_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            self.force_client(self.shift_manager)
            .post("/api/v1/monthly-shift-plans/", self.plan_payload(month=8), format="json")
            .status_code,
            201,
        )
        plan = MonthlyShiftPlan.objects.get(year=2026, month=7)
        supervisor_response = self.force_client(self.supervisor).post(
            "/api/v1/monthly-shift-plans/",
            self.plan_payload(month=9),
            format="json",
        )
        self.assertEqual(supervisor_response.status_code, 403)
        self.assertEqual(self.force_client(self.staff).get("/api/v1/monthly-shift-plans/").status_code, 403)
        self.assertEqual(
            admin.patch(f"/api/v1/monthly-shift-plans/{plan.id}/", {"month": 9}, format="json").status_code, 400
        )
        self.assertEqual(admin.delete(f"/api/v1/monthly-shift-plans/{plan.id}/").status_code, 405)
        self.assertEqual(
            admin.post(f"/api/v1/monthly-shift-plans/{plan.id}/deactivate/", {}, format="json").status_code, 200
        )
        MonthlyShiftPlan.objects.create(
            location=self.location,
            year=2026,
            month=7,
            name="Replacement",
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        self.assertEqual(
            admin.post(f"/api/v1/monthly-shift-plans/{plan.id}/reactivate/", {}, format="json").status_code, 400
        )
        self.assertTrue(AuditEvent.objects.filter(event_type="monthly_shift_plan_created").exists())

    def test_assignment_pattern_copy_snapshots_validation_warnings_and_segment_history(self):
        client = self.force_client(self.system_admin)
        plan = self.create_plan()
        created = client.post(
            "/api/v1/monthly-shift-assignments/",
            self.assignment_payload(plan, staff=self.staff),
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        assignment = MonthlyShiftAssignment.objects.get(id=created.data["id"])
        self.assertEqual(assignment.source_type, "manual")
        self.assertEqual(assignment.pattern_short_name_snapshot, "早番")
        first_segment = assignment.segments.filter(is_active=True).first()
        old_work_type_name = first_segment.work_type_name_snapshot
        first_segment.work_type.name = "Changed Work"
        first_segment.work_type.save(update_fields=["name", "updated_at"])
        first_segment.refresh_from_db()
        self.assertEqual(first_segment.work_type_name_snapshot, old_work_type_name)

        stale = MonthlyShiftSegment.objects.create(
            monthly_shift_assignment=assignment,
            work_type=self.gym_work,
            work_area=self.gym_area,
            work_type_name_snapshot=self.gym_work.name,
            work_type_short_name_snapshot=self.gym_work.short_name,
            work_type_color_key_snapshot=self.gym_work.color_key,
            work_type_is_break_snapshot=self.gym_work.is_break,
            work_area_name_snapshot=self.gym_area.name,
            start_offset_minutes=1200,
            end_offset_minutes=1260,
            is_active=False,
        )
        stale_updated_at = stale.updated_at
        detail = client.get(f"/api/v1/monthly-shift-assignments/{assignment.id}/")
        segments = [
            {
                "id": item["id"],
                "work_type": item["work_type"],
                "work_area": item["work_area"],
                "start_offset_minutes": item["start_offset_minutes"],
                "end_offset_minutes": item["end_offset_minutes"],
                "display_order": item["display_order"],
                "notes": item["notes"],
            }
            for item in detail.data["segments"]
            if item["is_active"]
        ]
        segments[0]["notes"] = "custom"
        updated = client.patch(
            f"/api/v1/monthly-shift-assignments/{assignment.id}/",
            {"segments": segments},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        stale.refresh_from_db()
        self.assertEqual(stale.updated_at, stale_updated_at)
        self.assertTrue(MonthlyShiftAssignment.objects.get(id=assignment.id).is_customized)

        trial = WorkType.objects.get(code="trial")
        pattern = ShiftPattern.objects.create(location=self.location, code="trial_shift", name="Trial", short_name="TR")
        ShiftPatternSegment.objects.create(
            shift_pattern=pattern,
            work_type=trial,
            work_area=self.gym_area,
            start_offset_minutes=600,
            end_offset_minutes=660,
        )
        warning_response = client.post(
            "/api/v1/monthly-shift-assignments/",
            self.assignment_payload(plan, staff=self.staff, work_date="2026-07-02", pattern_code="trial_shift"),
            format="json",
        )
        self.assertEqual(warning_response.status_code, 201, warning_response.data)
        self.assertEqual(warning_response.data["warnings"][0]["code"], "assisted_capability")
        error_response = client.post(
            "/api/v1/monthly-shift-assignments/",
            self.assignment_payload(plan, staff=self.shift_manager, work_date="2026-07-03", pattern_code="trial_shift"),
            format="json",
        )
        self.assertEqual(error_response.status_code, 400)

    def test_template_preview_apply_modes_matrix_and_reactivation(self):
        client = self.force_client(self.system_admin)
        plan = self.create_plan()
        template = WeeklyShiftTemplate.objects.get(code="standard_week")
        StaffCapability.objects.get_or_create(
            staff=self.staff,
            work_type=WorkType.objects.get(code="front_duty"),
            location=self.location,
            valid_from=timezone.localdate(),
            valid_until=None,
            defaults={
                "level": StaffCapability.Level.INDEPENDENT,
                "approved_by": self.system_admin,
                "approved_at": timezone.now(),
            },
        )
        preview = client.post(
            f"/api/v1/monthly-shift-plans/{plan.id}/preview-template-generation/",
            {"weekly_shift_template": str(template.id), "existing_mode": "skip_existing", "invalid_mode": "strict"},
            format="json",
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertGreater(preview.data["summary"]["candidate_count"], 0)
        apply_response = client.post(
            f"/api/v1/monthly-shift-plans/{plan.id}/apply-template/",
            {"weekly_shift_template": str(template.id), "existing_mode": "skip_existing", "invalid_mode": "strict"},
            format="json",
        )
        self.assertEqual(apply_response.status_code, 200, apply_response.data)
        first_count = MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, is_active=True).count()
        repeat = client.post(
            f"/api/v1/monthly-shift-plans/{plan.id}/apply-template/",
            {"weekly_shift_template": str(template.id), "existing_mode": "skip_existing", "invalid_mode": "strict"},
            format="json",
        )
        self.assertEqual(repeat.status_code, 200, repeat.data)
        self.assertEqual(
            MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, is_active=True).count(), first_count
        )
        manual = MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, source_type="template").first()
        manual.source_type = "manual"
        manual.is_customized = True
        manual.save(update_fields=["source_type", "is_customized", "updated_at"])
        replace_preview = client.post(
            f"/api/v1/monthly-shift-plans/{plan.id}/preview-template-generation/",
            {
                "weekly_shift_template": str(template.id),
                "existing_mode": "replace_template_generated",
                "invalid_mode": "strict",
            },
            format="json",
        )
        self.assertEqual(replace_preview.status_code, 200)
        self.assertGreaterEqual(replace_preview.data["summary"]["skip_manual_count"], 1)
        matrix = client.get(f"/api/v1/monthly-shift-plans/{plan.id}/matrix/")
        self.assertEqual(matrix.status_code, 200)
        self.assertEqual(len(matrix.data["dates"]), 31)
        self.assertTrue(any(item["is_saturday"] for item in matrix.data["dates"]))
        self.assertTrue(any(item["is_sunday"] for item in matrix.data["dates"]))
        assignment = MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, is_active=True).first()
        deactivate = client.post(f"/api/v1/monthly-shift-assignments/{assignment.id}/deactivate/", {}, format="json")
        self.assertEqual(deactivate.status_code, 200)
        conflict = client.post(
            "/api/v1/monthly-shift-assignments/",
            self.assignment_payload(plan, staff=assignment.staff, work_date=assignment.work_date.isoformat()),
            format="json",
        )
        self.assertEqual(conflict.status_code, 201, conflict.data)
        reactivate = client.post(f"/api/v1/monthly-shift-assignments/{assignment.id}/reactivate/", {}, format="json")
        self.assertEqual(reactivate.status_code, 400)

    def test_assignment_rejects_date_location_and_availability_failures(self):
        client = self.force_client(self.system_admin)
        plan = self.create_plan()
        outside = client.post(
            "/api/v1/monthly-shift-assignments/",
            self.assignment_payload(plan, work_date="2026-08-01"),
            format="json",
        )
        self.assertEqual(outside.status_code, 400)
        StaffLocation.objects.filter(staff=self.staff, location=self.location).update(valid_until="2026-06-30")
        no_location = client.post(
            "/api/v1/monthly-shift-assignments/",
            self.assignment_payload(plan, work_date="2026-07-04"),
            format="json",
        )
        self.assertEqual(no_location.status_code, 400)
        StaffLocation.objects.filter(staff=self.staff, location=self.location).update(valid_until=None)
        WorkTypeAvailability.objects.filter(work_type=self.gym_work, location=self.location).update(is_active=False)
        no_availability = client.post(
            "/api/v1/monthly-shift-assignments/",
            self.assignment_payload(plan, work_date="2026-07-05"),
            format="json",
        )
        self.assertEqual(no_availability.status_code, 400)


class TestSeedDevShifts(APITestCase):
    @override_settings(DEBUG=True)
    def test_seed_dev_is_idempotent_for_shifts(self):
        call_command("seed_dev")
        first_counts = (
            ShiftPattern.objects.count(),
            ShiftPatternSegment.objects.count(),
            WeeklyShiftTemplate.objects.count(),
            WeeklyShiftTemplateEntry.objects.count(),
        )
        call_command("seed_dev")
        second_counts = (
            ShiftPattern.objects.count(),
            ShiftPatternSegment.objects.count(),
            WeeklyShiftTemplate.objects.count(),
            WeeklyShiftTemplateEntry.objects.count(),
        )
        self.assertEqual(first_counts, second_counts)

    @override_settings(DEBUG=True)
    def test_seed_dev_keeps_passwords(self):
        call_command("seed_dev")
        user = User.objects.get(username="staff")
        user.set_password("ExistingPassword123!")
        user.save()
        call_command("seed_dev")
        user.refresh_from_db()
        self.assertTrue(user.check_password("ExistingPassword123!"))

    @override_settings(DEBUG=True)
    def test_seed_dev_does_not_reactivate_disabled_shift_records(self):
        call_command("seed_dev")
        pattern = ShiftPattern.objects.get(code="gym_early")
        segment = pattern.segments.filter(is_active=True).first()
        template = WeeklyShiftTemplate.objects.get(code="standard_week")
        entry = template.entries.filter(is_active=True).first()
        availability = WorkTypeAvailability.objects.get(work_type__code="break", location__code="main", work_area=None)
        for item in [pattern, segment, template, entry, availability]:
            item.is_active = False
            item.save(update_fields=["is_active", "updated_at"])
        first_counts = (
            ShiftPattern.objects.count(),
            ShiftPatternSegment.objects.count(),
            WeeklyShiftTemplate.objects.count(),
            WeeklyShiftTemplateEntry.objects.count(),
        )
        ShiftPatternSegment.objects.create(
            shift_pattern=pattern,
            work_type=segment.work_type,
            work_area=segment.work_area,
            start_offset_minutes=segment.start_offset_minutes,
            end_offset_minutes=segment.end_offset_minutes,
            is_active=False,
        )
        WeeklyShiftTemplateEntry.objects.create(
            weekly_shift_template=template,
            staff=entry.staff,
            weekday=entry.weekday,
            shift_pattern=entry.shift_pattern,
            is_active=False,
        )
        call_command("seed_dev")
        for item in [pattern, segment, template, entry, availability]:
            item.refresh_from_db()
            self.assertFalse(item.is_active)
        self.assertGreaterEqual(ShiftPatternSegment.objects.count(), first_counts[1])
        self.assertGreaterEqual(WeeklyShiftTemplateEntry.objects.count(), first_counts[3])
