import io
import json
import logging
import uuid
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.test_accounts import BaseAPITestCase
from apps.common.logging import SafeJsonFormatter
from apps.common.models import AuditEvent
from apps.operations.services import seed_operations

PRODUCTION_SETTINGS = {
    "DEBUG": False,
    "ENVIRONMENT": "production",
    "SECRET_KEY": "production-test-secret-key-with-more-than-thirty-two-characters",
    "ALLOWED_HOSTS": ["manager.example.jp"],
    "CSRF_TRUSTED_ORIGINS": ["https://manager.example.jp"],
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "SECURE_SSL_REDIRECT": True,
    "SECURE_HSTS_SECONDS": 31536000,
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
    "SECURE_HSTS_PRELOAD": True,
    "STATIC_ROOT": Path("/tmp/findmanager-static"),
    "MEDIA_ROOT": Path("/tmp/findmanager-media"),
}


def collect_keys(value):
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in collect_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in collect_keys(item)}
    return set()


class TestHealthReadinessAndErrors(BaseAPITestCase):
    def test_health_and_readiness_are_public_and_minimal(self):
        client = APIClient()
        health = client.get("/api/v1/health/")
        readiness = client.get("/api/v1/readiness/")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json(), {"status": "ready"})

    @patch("apps.common.readiness.database_is_ready", return_value=False)
    def test_readiness_returns_503_without_internal_details(self, _database):
        response = APIClient().get("/api/v1/readiness/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "not_ready"})

    def test_request_id_accepts_safe_value_and_replaces_unsafe_value(self):
        client = APIClient()
        accepted = client.get("/api/v1/health/", HTTP_X_REQUEST_ID="deploy-check_2026.07")
        self.assertEqual(accepted["X-Request-ID"], "deploy-check_2026.07")

        replaced = client.get("/api/v1/health/", HTTP_X_REQUEST_ID="bad request id\r\nsecret")
        self.assertNotEqual(replaced["X-Request-ID"], "bad request id\r\nsecret")
        uuid.UUID(replaced["X-Request-ID"])

    def test_api_errors_include_compatible_envelope_and_request_id(self):
        client = self.force_client(self.staff)
        response = client.get("/api/v1/system/status/", HTTP_X_REQUEST_ID="permission-test")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "permission_denied")
        self.assertEqual(response.data["request_id"], "permission-test")
        self.assertIn("detail", response.data)
        self.assertIn("message", response.data)
        self.assertIn("errors", response.data)

        not_found = client.get("/api/v1/no-such-endpoint/", HTTP_X_REQUEST_ID="missing-test")
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.json()["code"], "not_found")
        self.assertEqual(not_found.json()["request_id"], "missing-test")

    @patch("apps.common.views.SystemStatusView.get", side_effect=RuntimeError("private stack detail"))
    def test_production_500_has_no_stack_trace(self, _get):
        response = self.force_client(self.system_admin).get(
            "/api/v1/system/status/",
            HTTP_X_REQUEST_ID="server-error-test",
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], "server_error")
        self.assertEqual(response.data["request_id"], "server-error-test")
        self.assertNotIn("private stack detail", json.dumps(response.data))

    def test_json_formatter_uses_allowlist_and_omits_sensitive_extras(self):
        record = logging.LogRecord("findmanager.request", logging.INFO, __file__, 1, "request_completed", (), None)
        record.request_id = "log-test"
        record.method = "POST"
        record.path = "/api/v1/auth/login/"
        record.status = 200
        record.password = "DoNotLog123!"
        record.session_id = "private-session"
        record.revenue_amount = "999999"
        payload = json.loads(SafeJsonFormatter().format(record))
        self.assertEqual(payload["request_id"], "log-test")
        self.assertEqual(payload["method"], "POST")
        serialized = json.dumps(payload)
        self.assertNotIn("DoNotLog123!", serialized)
        self.assertNotIn("private-session", serialized)
        self.assertNotIn("999999", serialized)


class TestSystemStatusAuditAndPermissions(BaseAPITestCase):
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

    def test_system_status_is_admin_only_and_contains_safe_summary(self):
        for user in [self.shift_manager, self.supervisor, self.staff, self.viewer]:
            self.assertEqual(self.force_client(user).get("/api/v1/system/status/").status_code, 403)
        self.assertEqual(APIClient().get("/api/v1/system/status/").status_code, 403)

        response = self.force_client(self.system_admin).get("/api/v1/system/status/")
        self.assertEqual(response.status_code, 200)
        expected = {
            "backend_version",
            "environment",
            "api_health",
            "api_readiness",
            "migration_status",
            "database_status",
            "last_audit_event_at",
            "active_location_count",
            "active_staff_count",
            "pending_request_count",
            "unclosed_attendance_period_count",
            "unfinalized_labor_estimate_period_count",
            "unapproved_labor_budget_period_count",
            "unfinalized_revenue_actual_period_count",
        }
        self.assertEqual(set(response.data), expected)
        forbidden = {"secret_key", "database_url", "password", "session", "revenue_lines"}
        self.assertTrue(forbidden.isdisjoint(collect_keys(response.data)))

    def test_audit_list_is_admin_only_paginated_and_query_bounded(self):
        for index in range(30):
            AuditEvent.objects.create(
                event_type=AuditEvent.EventType.LOGIN_SUCCESS,
                actor=self.system_admin,
                metadata={"index": index},
            )
        for user in [self.shift_manager, self.supervisor, self.staff, self.viewer]:
            self.assertEqual(self.force_client(user).get("/api/v1/audit-events/").status_code, 403)

        client = self.force_client(self.system_admin)
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/api/v1/audit-events/?page_size=25")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 30)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertLessEqual(len(queries), 8)

    def test_major_api_role_matrix_and_financial_confidentiality(self):
        matrix = {
            "/api/v1/locations/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 200,
                "staff": 200,
                "viewer": 200,
            },
            "/api/v1/monthly-shift-plans/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 200,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/shift-request-periods/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 200,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/shift-change-requests/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 200,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/attendance-records/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 200,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/attendance-closing-periods/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 200,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/staff-compensation-profiles/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 403,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/labor-cost-budget-periods/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 403,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/revenue-categories/": {
                "system_admin": 200,
                "shift_manager": 200,
                "supervisor": 403,
                "staff": 403,
                "viewer": 403,
            },
            "/api/v1/financial-performance/?year=2026&month=7": {
                "system_admin": 400,
                "shift_manager": 400,
                "supervisor": 403,
                "staff": 403,
                "viewer": 403,
            },
        }
        users = {
            "system_admin": self.system_admin,
            "shift_manager": self.shift_manager,
            "supervisor": self.supervisor,
            "staff": self.staff,
            "viewer": self.viewer,
        }
        confidential_keys = {
            "base_hourly_rate",
            "fixed_monthly_amount",
            "amount",
            "estimated_total",
            "budget_amount",
            "planned_labor_cost",
            "revenue_actual_total",
            "actual_labor_cost_ratio",
        }
        for url, expectations in matrix.items():
            for role, expected in expectations.items():
                response = self.force_client(users[role]).get(url)
                self.assertEqual(response.status_code, expected, f"{role} {url}")
                if expected == 403:
                    self.assertTrue(confidential_keys.isdisjoint(collect_keys(response.data)))
            self.assertEqual(APIClient().get(url).status_code, 403, f"anonymous {url}")

    def test_self_service_response_does_not_expose_financial_fields(self):
        response = self.force_client(self.staff).get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        forbidden = {
            "base_hourly_rate",
            "fixed_monthly_amount",
            "allowance_amount",
            "estimated_total",
            "labor_cost_budget",
            "planned_labor_cost",
            "revenue_amount",
            "labor_cost_ratio",
        }
        self.assertTrue(forbidden.isdisjoint(collect_keys(response.data)))


class TestDeploymentReadinessCommand(BaseAPITestCase):
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

    @override_settings(**PRODUCTION_SETTINGS)
    def test_full_readiness_command_passes_with_safe_configuration_and_seed_data(self):
        output = io.StringIO()
        call_command("check_deployment_readiness", stdout=output)
        self.assertIn("Deployment readiness checks passed.", output.getvalue())
        self.assertNotIn(PRODUCTION_SETTINGS["SECRET_KEY"], output.getvalue())

    @override_settings(**PRODUCTION_SETTINGS)
    def test_settings_only_mode_supports_ci_image_validation(self):
        output = io.StringIO()
        call_command("check_deployment_readiness", "--settings-only", stdout=output)
        self.assertIn("Deployment readiness checks passed.", output.getvalue())

    @override_settings(
        DEBUG=True,
        SECRET_KEY="dev-secret-key-change-me",
        ALLOWED_HOSTS=["*"],
        CSRF_TRUSTED_ORIGINS=[],
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        SECURE_SSL_REDIRECT=False,
        SECURE_HSTS_SECONDS=0,
    )
    def test_unsafe_configuration_fails_without_printing_secret(self):
        output = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("check_deployment_readiness", "--settings-only", stdout=output)
        self.assertIn("[ERROR]", output.getvalue())
        self.assertNotIn("dev-secret-key-change-me", output.getvalue())
