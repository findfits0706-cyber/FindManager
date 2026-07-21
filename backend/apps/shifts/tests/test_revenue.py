from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.test_accounts import BaseAPITestCase
from apps.common.models import AuditEvent
from apps.operations.models import Location
from apps.operations.services import seed_operations

from ..models import (
    LaborCostBudgetPeriod,
    LaborCostBudgetStaffSummary,
    LaborCostEstimatePeriod,
    LaborCostEstimateStaffSummary,
    RevenueActualLine,
    RevenueActualPeriod,
    RevenueBudgetLine,
    RevenueBudgetPeriod,
    RevenueCategory,
    RevenuePerformanceSnapshot,
)
from ..revenue_services import (
    build_revenue_actual_preview,
    build_revenue_budget_preview,
    get_labor_cost_budget_period_for_revenue,
    get_labor_cost_estimate_period_for_revenue,
    get_revenue_budget_period_for_month,
)


class RevenueBaseTestCase(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        users = {
            "system_admin": self.system_admin,
            "shift_manager": self.shift_manager,
            "supervisor": self.supervisor,
            "staff": self.staff,
            "viewer": self.viewer,
        }
        seed_operations(users)
        self.location = Location.objects.get(code="main")
        self.other_location = Location.objects.get(code="findfits")
        self.category = RevenueCategory.objects.create(
            location=self.location,
            code="membership",
            name="会費",
            short_name="会費",
            display_order=10,
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )

    def create_revenue_budget(
        self,
        *,
        amount=Decimal("1000000.00"),
        status=RevenueBudgetPeriod.Status.APPROVED,
        location=None,
        year=2026,
        month=7,
        category=None,
    ):
        location = location or self.location
        category = category or self.category
        period = RevenueBudgetPeriod.objects.create(
            location=location,
            year=year,
            month=month,
            name="売上予算",
            status=status,
            content_hash="revenue-budget-hash" if status == RevenueBudgetPeriod.Status.APPROVED else "",
            approved_at=timezone.now() if status == RevenueBudgetPeriod.Status.APPROVED else None,
            approved_by=self.system_admin if status == RevenueBudgetPeriod.Status.APPROVED else None,
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        RevenueBudgetLine.objects.create(
            budget_period=period,
            category=category,
            category_code_snapshot=category.code,
            category_name_snapshot=category.name,
            budget_amount=amount,
        )
        return period

    def create_labor_budget(
        self,
        *,
        budget=Decimal("300000.00"),
        planned=Decimal("250000.00"),
        status=LaborCostBudgetPeriod.Status.APPROVED,
        location=None,
        year=2026,
        month=7,
    ):
        location = location or self.location
        period = LaborCostBudgetPeriod.objects.create(
            location=location,
            year=year,
            month=month,
            name="人件費予算",
            budget_amount=budget,
            status=status,
            content_hash="labor-budget-hash" if status == LaborCostBudgetPeriod.Status.APPROVED else "",
            approved_at=timezone.now() if status == LaborCostBudgetPeriod.Status.APPROVED else None,
            approved_by=self.system_admin if status == LaborCostBudgetPeriod.Status.APPROVED else None,
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        if status == LaborCostBudgetPeriod.Status.APPROVED:
            LaborCostBudgetStaffSummary.objects.create(
                budget_period=period,
                staff=self.staff,
                staff_display_name_snapshot=self.staff.display_name,
                employee_code_snapshot=self.staff.employee_code,
                employment_type_snapshot="hourly",
                planned_worked_days=20,
                planned_worked_minutes=9600,
                planned_hours_decimal=Decimal("160.00"),
                planned_hourly_base_pay=planned,
                planned_total=planned,
            )
        return period

    def create_labor_estimate(
        self,
        *,
        total=Decimal("280000.00"),
        status=LaborCostEstimatePeriod.Status.FINALIZED,
        location=None,
        year=2026,
        month=7,
    ):
        location = location or self.location
        period = LaborCostEstimatePeriod.objects.create(
            location=location,
            year=year,
            month=month,
            name="概算人件費",
            status=status,
            content_hash="labor-estimate-hash" if status == LaborCostEstimatePeriod.Status.FINALIZED else "",
            finalized_at=timezone.now() if status == LaborCostEstimatePeriod.Status.FINALIZED else None,
            finalized_by=self.system_admin if status == LaborCostEstimatePeriod.Status.FINALIZED else None,
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        if status == LaborCostEstimatePeriod.Status.FINALIZED:
            LaborCostEstimateStaffSummary.objects.create(
                estimate_period=period,
                staff=self.staff,
                staff_display_name_snapshot=self.staff.display_name,
                employee_code_snapshot=self.staff.employee_code,
                employment_type_snapshot="hourly",
                worked_days=20,
                worked_minutes=9600,
                worked_hours_decimal=Decimal("160.00"),
                base_pay_total=total,
                estimated_total=total,
            )
        return period

    def create_actual(
        self,
        *,
        amount=Decimal("1100000.00"),
        revenue_budget=None,
        labor_budget=None,
        labor_estimate=None,
        status=RevenueActualPeriod.Status.DRAFT,
    ):
        period = RevenueActualPeriod.objects.create(
            location=self.location,
            year=2026,
            month=7,
            revenue_budget_period=revenue_budget,
            labor_cost_budget_period=labor_budget,
            labor_cost_estimate_period=labor_estimate,
            name="売上実績",
            status=status,
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        RevenueActualLine.objects.create(
            actual_period=period,
            category=self.category,
            category_code_snapshot=self.category.code,
            category_name_snapshot=self.category.name,
            actual_amount=amount,
        )
        return period

    def create_complete_actual(self, *, actual_amount=Decimal("1100000.00")):
        revenue_budget = self.create_revenue_budget()
        labor_budget = self.create_labor_budget()
        labor_estimate = self.create_labor_estimate()
        return self.create_actual(
            amount=actual_amount,
            revenue_budget=revenue_budget,
            labor_budget=labor_budget,
            labor_estimate=labor_estimate,
        )


class TestRevenueModels(RevenueBaseTestCase):
    def test_category_code_and_duplicate_constraints(self):
        invalid = RevenueCategory(
            location=self.location,
            code="bad code",
            name="Invalid",
            short_name="Invalid",
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        duplicate = RevenueCategory(
            location=self.location,
            code="membership",
            name="Duplicate",
            short_name="Duplicate",
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_budget_line_rejects_negative_mismatch_and_inactive_category(self):
        period = RevenueBudgetPeriod.objects.create(
            location=self.location,
            year=2026,
            month=7,
            name="Budget",
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        invalid = RevenueBudgetLine(
            budget_period=period,
            category=self.category,
            category_code_snapshot=self.category.code,
            category_name_snapshot=self.category.name,
            budget_amount=Decimal("-1.00"),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        other = RevenueCategory.objects.create(
            location=self.other_location,
            code="other",
            name="Other",
            short_name="Other",
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        invalid.category = other
        invalid.budget_amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        self.category.is_active = False
        self.category.save(update_fields=["is_active", "updated_at"])
        invalid.category = self.category
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_actual_period_related_month_must_match(self):
        budget = self.create_revenue_budget(year=2026, month=8)
        actual = RevenueActualPeriod(
            location=self.location,
            year=2026,
            month=7,
            revenue_budget_period=budget,
            name="Actual",
            created_by=self.system_admin,
            updated_by=self.system_admin,
        )
        with self.assertRaises(ValidationError):
            actual.full_clean()


class TestRevenueBudgetWorkflow(RevenueBaseTestCase):
    def test_category_api_create_update_deactivate_and_audit(self):
        client = self.force_client(self.system_admin)
        created = client.post(
            "/api/v1/revenue-categories/",
            {
                "location": str(self.location.id),
                "code": "school",
                "name": "スクール",
                "short_name": "スクール",
                "display_order": 20,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        updated = client.patch(
            f"/api/v1/revenue-categories/{created.data['id']}/",
            {"name": "スクール売上"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        deactivated = client.patch(
            f"/api/v1/revenue-categories/{created.data['id']}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(deactivated.status_code, 200, deactivated.data)
        self.assertTrue(AuditEvent.objects.filter(event_type="revenue_category_created").exists())
        self.assertTrue(AuditEvent.objects.filter(event_type="revenue_category_updated").exists())
        self.assertTrue(AuditEvent.objects.filter(event_type="revenue_category_deactivated").exists())

    def test_budget_create_line_preview_approve_readonly_reopen_archive(self):
        client = self.force_client(self.shift_manager)
        created = client.post(
            "/api/v1/revenue-budget-periods/",
            {"location": str(self.location.id), "year": 2026, "month": 7, "name": ""},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        period_id = created.data["id"]
        line = client.post(
            "/api/v1/revenue-budget-lines/",
            {
                "budget_period": period_id,
                "category": str(self.category.id),
                "budget_amount": "1000000.00",
            },
            format="json",
        )
        self.assertEqual(line.status_code, 201, line.data)
        preview = client.post(f"/api/v1/revenue-budget-periods/{period_id}/preview/", {}, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["summary"]["budget_total"], Decimal("1000000.00"))
        approved = client.post(
            f"/api/v1/revenue-budget-periods/{period_id}/approve/",
            {
                "validation_fingerprint": preview.data["validation_fingerprint"],
                "acknowledge_warnings": False,
            },
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(
            client.patch(f"/api/v1/revenue-budget-lines/{line.data['id']}/", {"budget_amount": "2"}).status_code,
            400,
        )
        self.assertEqual(
            client.patch(f"/api/v1/revenue-budget-periods/{period_id}/", {"name": "Changed"}).status_code,
            400,
        )
        self.assertEqual(client.post(f"/api/v1/revenue-budget-periods/{period_id}/archive/", {}).status_code, 400)
        reopened = client.post(f"/api/v1/revenue-budget-periods/{period_id}/reopen/", {}, format="json")
        self.assertEqual(reopened.status_code, 200)
        archived = client.post(f"/api/v1/revenue-budget-periods/{period_id}/archive/", {}, format="json")
        self.assertEqual(archived.status_code, 200)
        self.assertFalse(archived.data["is_active"])

    def test_budget_warning_requires_ack_and_fingerprint_must_match(self):
        period = self.create_revenue_budget(amount=Decimal("0.00"), status=RevenueBudgetPeriod.Status.DRAFT)
        client = self.force_client(self.system_admin)
        preview = client.post(f"/api/v1/revenue-budget-periods/{period.id}/preview/", {}, format="json")
        self.assertContains(preview, "revenue_budget_zero")
        mismatch = client.post(
            f"/api/v1/revenue-budget-periods/{period.id}/approve/",
            {"validation_fingerprint": "0" * 64, "acknowledge_warnings": True},
            format="json",
        )
        self.assertEqual(mismatch.status_code, 400)
        missing_ack = client.post(
            f"/api/v1/revenue-budget-periods/{period.id}/approve/",
            {
                "validation_fingerprint": preview.data["validation_fingerprint"],
                "acknowledge_warnings": False,
            },
            format="json",
        )
        self.assertEqual(missing_ack.status_code, 400)
        approved = client.post(
            f"/api/v1/revenue-budget-periods/{period.id}/approve/",
            {
                "validation_fingerprint": preview.data["validation_fingerprint"],
                "acknowledge_warnings": True,
            },
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)

    def test_budget_hash_and_fingerprint_are_deterministic(self):
        period = self.create_revenue_budget(status=RevenueBudgetPeriod.Status.DRAFT)
        first = build_revenue_budget_preview(period)
        RevenueBudgetLine.objects.filter(budget_period=period).update(display_order=999)
        second = build_revenue_budget_preview(period)
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(first["validation_fingerprint"], second["validation_fingerprint"])
        RevenueBudgetLine.objects.filter(budget_period=period).update(is_active=False)
        third = build_revenue_budget_preview(period)
        self.assertNotEqual(first["content_hash"], third["content_hash"])
        self.assertNotEqual(first["validation_fingerprint"], third["validation_fingerprint"])

    @patch("apps.shifts.services.create_audit_event", side_effect=RuntimeError("audit failed"))
    def test_category_audit_failure_rolls_back(self, _audit):
        client = self.force_client(self.system_admin)
        response = client.post(
            "/api/v1/revenue-categories/",
            {
                "location": str(self.location.id),
                "code": "rollback",
                "name": "Rollback",
                "short_name": "Rollback",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(RevenueCategory.objects.filter(code="rollback").exists())


class TestRevenueActualWorkflow(RevenueBaseTestCase):
    def test_source_priority_prefers_approved_and_finalized(self):
        revenue_budget = self.create_revenue_budget()
        labor_budget = self.create_labor_budget()
        labor_estimate = self.create_labor_estimate()
        actual = self.create_actual(
            revenue_budget=revenue_budget,
            labor_budget=labor_budget,
            labor_estimate=labor_estimate,
        )
        self.assertEqual(get_revenue_budget_period_for_month(actual)["status"], "approved")
        self.assertEqual(get_labor_cost_budget_period_for_revenue(actual)["status"], "approved")
        self.assertEqual(get_labor_cost_estimate_period_for_revenue(actual)["status"], "finalized")

    def test_live_fallback_is_previewable_but_finalize_is_blocked(self):
        revenue_budget = self.create_revenue_budget(status=RevenueBudgetPeriod.Status.REVIEW)
        labor_budget = self.create_labor_budget(status=LaborCostBudgetPeriod.Status.REVIEW)
        labor_estimate = self.create_labor_estimate(status=LaborCostEstimatePeriod.Status.REVIEW)
        actual = self.create_actual(
            revenue_budget=revenue_budget,
            labor_budget=labor_budget,
            labor_estimate=labor_estimate,
        )
        preview = build_revenue_actual_preview(actual)
        codes = {issue["code"] for issue in preview["issues"]}
        self.assertIn("revenue_budget_live_fallback", codes)
        self.assertIn("labor_cost_budget_live_fallback", codes)
        self.assertIn("labor_cost_estimate_live_fallback", codes)
        self.assertFalse(preview["can_finalize"])

    def test_calculates_revenue_and_labor_ratios_with_round_half_up(self):
        revenue_budget = self.create_revenue_budget(amount=Decimal("3.00"))
        labor_budget = self.create_labor_budget(budget=Decimal("1.00"), planned=Decimal("1.00"))
        labor_estimate = self.create_labor_estimate(total=Decimal("1.00"))
        actual = self.create_actual(
            amount=Decimal("2.00"),
            revenue_budget=revenue_budget,
            labor_budget=labor_budget,
            labor_estimate=labor_estimate,
        )
        summary = build_revenue_actual_preview(actual)["summary"]
        self.assertEqual(summary["revenue_variance_amount"], Decimal("-1.00"))
        self.assertEqual(summary["revenue_attainment_percent"], Decimal("66.67"))
        self.assertEqual(summary["budget_labor_cost_ratio"], Decimal("33.33"))
        self.assertEqual(summary["actual_labor_cost_ratio"], Decimal("50.00"))

    def test_zero_denominator_uses_zero_attainment_and_null_ratios(self):
        revenue_budget = self.create_revenue_budget(amount=Decimal("0.00"))
        labor_budget = self.create_labor_budget(budget=Decimal("0.00"), planned=Decimal("0.00"))
        labor_estimate = self.create_labor_estimate(total=Decimal("0.00"))
        actual = self.create_actual(
            amount=Decimal("0.00"),
            revenue_budget=revenue_budget,
            labor_budget=labor_budget,
            labor_estimate=labor_estimate,
        )
        preview = build_revenue_actual_preview(actual)
        self.assertEqual(preview["summary"]["revenue_attainment_percent"], Decimal("0.00"))
        self.assertIsNone(preview["summary"]["actual_labor_cost_ratio"])
        self.assertIn("revenue_budget_zero", {issue["code"] for issue in preview["warnings"]})

    def test_finalize_creates_snapshot_and_reopen_archive_flow(self):
        actual = self.create_complete_actual()
        client = self.force_client(self.system_admin)
        preview = client.post(f"/api/v1/revenue-actual-periods/{actual.id}/preview/", {}, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        finalized = client.post(
            f"/api/v1/revenue-actual-periods/{actual.id}/finalize/",
            {
                "validation_fingerprint": preview.data["validation_fingerprint"],
                "acknowledge_warnings": True,
            },
            format="json",
        )
        self.assertEqual(finalized.status_code, 200, finalized.data)
        self.assertEqual(finalized.data["status"], "finalized")
        snapshot = RevenuePerformanceSnapshot.objects.get(actual_period=actual)
        self.assertEqual(snapshot.revenue_actual_total, Decimal("1100000.00"))
        self.assertEqual(snapshot.planned_labor_cost, Decimal("250000.00"))
        self.assertEqual(snapshot.actual_labor_cost_estimate, Decimal("280000.00"))
        self.assertEqual(snapshot.line_snapshots.count(), 1)
        performance = client.get(f"/api/v1/revenue-actual-periods/{actual.id}/performance/")
        self.assertTrue(performance.data["is_snapshot"])
        self.assertEqual(client.post(f"/api/v1/revenue-actual-periods/{actual.id}/archive/", {}).status_code, 400)
        self.assertEqual(client.post(f"/api/v1/revenue-actual-periods/{actual.id}/reopen/", {}).status_code, 200)
        archived = client.post(f"/api/v1/revenue-actual-periods/{actual.id}/archive/", {})
        self.assertEqual(archived.status_code, 200)
        self.assertFalse(archived.data["is_active"])
        self.assertTrue(AuditEvent.objects.filter(event_type="revenue_actual_finalized").exists())

    def test_finalize_requires_warning_ack_and_current_fingerprint(self):
        actual = self.create_complete_actual()
        client = self.force_client(self.shift_manager)
        preview = client.post(f"/api/v1/revenue-actual-periods/{actual.id}/preview/", {}, format="json")
        self.assertGreater(preview.data["summary"]["warning_count"], 0)
        no_ack = client.post(
            f"/api/v1/revenue-actual-periods/{actual.id}/finalize/",
            {
                "validation_fingerprint": preview.data["validation_fingerprint"],
                "acknowledge_warnings": False,
            },
            format="json",
        )
        self.assertEqual(no_ack.status_code, 400)
        mismatch = client.post(
            f"/api/v1/revenue-actual-periods/{actual.id}/finalize/",
            {"validation_fingerprint": "f" * 64, "acknowledge_warnings": True},
            format="json",
        )
        self.assertEqual(mismatch.status_code, 400)

    @patch("apps.shifts.revenue_services.RevenuePerformanceLineSnapshot.objects.bulk_create", side_effect=RuntimeError)
    def test_snapshot_failure_rolls_back_finalize(self, _bulk_create):
        actual = self.create_complete_actual()
        client = self.force_client(self.system_admin)
        preview = client.post(f"/api/v1/revenue-actual-periods/{actual.id}/preview/", {}, format="json")
        response = client.post(
            f"/api/v1/revenue-actual-periods/{actual.id}/finalize/",
            {
                "validation_fingerprint": preview.data["validation_fingerprint"],
                "acknowledge_warnings": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 500)
        actual.refresh_from_db()
        self.assertEqual(actual.status, RevenueActualPeriod.Status.REVIEW)
        self.assertFalse(RevenuePerformanceSnapshot.objects.filter(actual_period=actual).exists())


class TestRevenuePermissionsCsvAndQueries(RevenueBaseTestCase):
    def test_financial_apis_are_restricted_before_payload_validation(self):
        endpoints = [
            "/api/v1/revenue-categories/",
            "/api/v1/revenue-budget-periods/",
            "/api/v1/revenue-budget-lines/",
            "/api/v1/revenue-actual-periods/",
            "/api/v1/revenue-actual-lines/",
            "/api/v1/financial-performance/",
        ]
        for role_user in [self.supervisor, self.staff, self.viewer]:
            client = self.force_client(role_user)
            for endpoint in endpoints:
                self.assertEqual(client.post(endpoint, {"invalid": True}, format="json").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/revenue-categories/").status_code, 403)
        self.assertEqual(self.force_client(self.shift_manager).get("/api/v1/revenue-categories/").status_code, 200)

    def test_financial_performance_and_csv(self):
        actual = self.create_complete_actual(actual_amount=Decimal("900000.00"))
        client = self.force_client(self.system_admin)
        dashboard = client.get(f"/api/v1/financial-performance/?location={self.location.id}&year=2026&month=7")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(dashboard.data["summary"]["revenue_actual_total"], Decimal("900000.00"))
        budget_csv = client.get(f"/api/v1/revenue-budget-periods/{actual.revenue_budget_period_id}/export-csv/")
        actual_csv = client.get(f"/api/v1/revenue-actual-periods/{actual.id}/export-csv/")
        self.assertEqual(budget_csv.status_code, 200)
        self.assertEqual(actual_csv.status_code, 200)
        self.assertTrue(budget_csv.content.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(actual_csv.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("text/csv", budget_csv["Content-Type"])
        self.assertIn("revenue_performance_", actual_csv["Content-Disposition"])
        self.assertTrue(AuditEvent.objects.filter(event_type="revenue_budget_exported").exists())
        self.assertTrue(AuditEvent.objects.filter(event_type="revenue_actual_exported").exists())

    def test_budget_preview_queries_do_not_scale_per_line(self):
        period = self.create_revenue_budget(status=RevenueBudgetPeriod.Status.DRAFT)
        with CaptureQueriesContext(connection) as one_context:
            build_revenue_budget_preview(period)
        for index in range(1, 20):
            category = RevenueCategory.objects.create(
                location=self.location,
                code=f"category_{index}",
                name=f"Category {index}",
                short_name=f"C{index}",
                display_order=index,
                created_by=self.system_admin,
                updated_by=self.system_admin,
            )
            RevenueBudgetLine.objects.create(
                budget_period=period,
                category=category,
                category_code_snapshot=category.code,
                category_name_snapshot=category.name,
                budget_amount=Decimal("100.00"),
            )
        with CaptureQueriesContext(connection) as many_context:
            build_revenue_budget_preview(period)
        self.assertLessEqual(len(many_context), len(one_context) + 1)

    def test_period_list_query_is_constant(self):
        self.create_revenue_budget()
        client = self.force_client(self.system_admin)
        with CaptureQueriesContext(connection) as query_context:
            response = client.get("/api/v1/revenue-budget-periods/?page_size=100")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(query_context), 8)
