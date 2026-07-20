from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F, Q

from apps.accounts.constants import ROLE_SHIFT_MANAGER, ROLE_SYSTEM_ADMIN
from apps.accounts.models import User
from apps.operations.models import Location, WorkArea, WorkCategory, WorkType
from apps.shifts.models import (
    AttendanceClosingPeriod,
    LaborCostBudgetPeriod,
    LaborCostEstimatePeriod,
    RevenueActualPeriod,
    RevenueBudgetPeriod,
)

from ...readiness import database_is_ready, migrations_are_current


@dataclass(frozen=True)
class CheckResult:
    level: str
    name: str
    message: str


class Command(BaseCommand):
    help = "Validate settings, infrastructure, operational masters, and snapshot integrity before deployment."

    def add_arguments(self, parser):
        parser.add_argument(
            "--settings-only",
            action="store_true",
            help="Skip production data checks; intended for immutable image and CI configuration validation.",
        )

    def handle(self, *args, **options):
        results = self._settings_and_infrastructure_checks()
        if not options["settings_only"] and database_is_ready():
            results.extend(self._data_checks())

        styles = {
            "success": self.style.SUCCESS,
            "warning": self.style.WARNING,
            "error": self.style.ERROR,
        }
        for result in results:
            self.stdout.write(styles[result.level](f"[{result.level.upper()}] {result.name}: {result.message}"))

        errors = sum(result.level == "error" for result in results)
        warnings = sum(result.level == "warning" for result in results)
        successes = sum(result.level == "success" for result in results)
        self.stdout.write(f"Summary: {successes} success, {warnings} warning, {errors} error")
        if errors:
            raise CommandError("Deployment readiness checks failed.")
        self.stdout.write(self.style.SUCCESS("Deployment readiness checks passed."))

    def _result(self, condition, name, success, failure, *, warning=False):
        return CheckResult(
            "success" if condition else "warning" if warning else "error",
            name,
            success if condition else failure,
        )

    def _settings_and_infrastructure_checks(self):
        secret_is_safe = bool(
            settings.SECRET_KEY
            and len(settings.SECRET_KEY) >= 32
            and settings.SECRET_KEY not in {"dev-secret-key-change-me", "change-me"}
        )
        allowed_hosts_safe = bool(settings.ALLOWED_HOSTS and "*" not in settings.ALLOWED_HOSTS)
        db_ready = database_is_ready()
        return [
            self._result(not settings.DEBUG, "DEBUG", "disabled", "must be disabled for production"),
            self._result(secret_is_safe, "SECRET_KEY", "configured", "missing, weak, or development value"),
            self._result(
                allowed_hosts_safe,
                "ALLOWED_HOSTS",
                "restricted hosts configured",
                "missing or wildcard host",
            ),
            self._result(
                bool(settings.CSRF_TRUSTED_ORIGINS),
                "CSRF_TRUSTED_ORIGINS",
                "configured",
                "no trusted frontend origin configured",
            ),
            self._result(settings.SESSION_COOKIE_SECURE, "SESSION_COOKIE_SECURE", "enabled", "must be enabled"),
            self._result(settings.CSRF_COOKIE_SECURE, "CSRF_COOKIE_SECURE", "enabled", "must be enabled"),
            self._result(settings.SECURE_SSL_REDIRECT, "SECURE_SSL_REDIRECT", "enabled", "must be enabled"),
            self._result(settings.SECURE_HSTS_SECONDS > 0, "HSTS", "enabled", "SECURE_HSTS_SECONDS must be positive"),
            self._result(
                settings.SECURE_HSTS_INCLUDE_SUBDOMAINS,
                "HSTS subdomains",
                "enabled",
                "not enabled; confirm subdomain HTTPS coverage before enabling",
                warning=True,
            ),
            self._result(
                settings.SECURE_HSTS_PRELOAD,
                "HSTS preload",
                "enabled",
                "not enabled; preload is optional until domain requirements are confirmed",
                warning=True,
            ),
            self._result(db_ready, "database", "connection succeeded", "connection failed"),
            self._result(
                db_ready and migrations_are_current(),
                "migrations",
                "all migrations applied",
                "database unavailable or migrations pending",
            ),
            self._result(bool(settings.STATIC_ROOT), "static files", "STATIC_ROOT configured", "STATIC_ROOT missing"),
            self._result(bool(settings.MEDIA_ROOT), "media files", "MEDIA_ROOT configured", "MEDIA_ROOT missing"),
        ]

    def _duplicate_period_count(self):
        models = [
            AttendanceClosingPeriod,
            LaborCostEstimatePeriod,
            LaborCostBudgetPeriod,
            RevenueBudgetPeriod,
            RevenueActualPeriod,
        ]
        return sum(
            model.objects.filter(is_active=True)
            .values("location_id", "year", "month")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .count()
            for model in models
        )

    def _snapshot_integrity_count(self):
        attendance = AttendanceClosingPeriod.objects.filter(status=AttendanceClosingPeriod.Status.CLOSED).filter(
            Q(closed_at__isnull=True) | Q(content_hash="")
        )
        estimates = LaborCostEstimatePeriod.objects.filter(status=LaborCostEstimatePeriod.Status.FINALIZED).filter(
            Q(finalized_at__isnull=True) | Q(content_hash="")
        )
        labor_budgets = LaborCostBudgetPeriod.objects.filter(status=LaborCostBudgetPeriod.Status.APPROVED).filter(
            Q(approved_at__isnull=True) | Q(content_hash="")
        )
        revenue_budgets = RevenueBudgetPeriod.objects.filter(status=RevenueBudgetPeriod.Status.APPROVED).filter(
            Q(approved_at__isnull=True) | Q(content_hash="")
        )
        revenue_actuals = RevenueActualPeriod.objects.filter(status=RevenueActualPeriod.Status.FINALIZED).filter(
            Q(finalized_at__isnull=True)
            | Q(content_hash="")
            | Q(performance_snapshot__isnull=True)
            | ~Q(content_hash=F("performance_snapshot__content_hash"))
        )
        return sum(
            queryset.distinct().count()
            for queryset in [attendance, estimates, labor_budgets, revenue_budgets, revenue_actuals]
        )

    def _data_checks(self):
        admin_count = User.objects.filter(is_active=True, is_superuser=True).count()
        active_location_count = Location.objects.filter(is_active=True).count()
        missing_masters = [
            name
            for name, exists in [
                ("WorkArea", WorkArea.objects.filter(is_active=True).exists()),
                ("WorkCategory", WorkCategory.objects.filter(is_active=True).exists()),
                ("WorkType", WorkType.objects.filter(is_active=True).exists()),
            ]
            if not exists
        ]
        duplicate_count = self._duplicate_period_count()
        snapshot_errors = self._snapshot_integrity_count()
        forced_password_count = User.objects.filter(is_active=True, must_change_password=True).count()
        admin_password_risk = User.objects.filter(
            is_active=True,
            must_change_password=True,
            groups__name=ROLE_SYSTEM_ADMIN,
        ).count()
        missing_finance_roles = [
            role for role in [ROLE_SYSTEM_ADMIN, ROLE_SHIFT_MANAGER] if not Group.objects.filter(name=role).exists()
        ]
        return [
            self._result(admin_count > 0, "administrator", "active administrator exists", "no active administrator"),
            self._result(
                active_location_count > 0,
                "active locations",
                f"{active_location_count} active location(s)",
                "no active location",
            ),
            self._result(
                not missing_masters,
                "required masters",
                "required operational masters exist",
                f"missing active masters: {', '.join(missing_masters)}",
            ),
            self._result(
                duplicate_count == 0,
                "active periods",
                "no duplicate active month",
                f"{duplicate_count} duplicate active period group(s)",
            ),
            self._result(
                snapshot_errors == 0,
                "snapshot integrity",
                "workflow state and snapshot metadata are consistent",
                f"{snapshot_errors} inconsistent finalized/approved period(s)",
            ),
            self._result(
                admin_password_risk == 0,
                "administrator password lifecycle",
                "no administrator requires initial password change",
                f"{admin_password_risk} administrator(s) still require password change",
            ),
            self._result(
                forced_password_count == 0,
                "staff password lifecycle",
                "no active account requires password change",
                f"{forced_password_count} active account(s) require password change",
                warning=True,
            ),
            self._result(
                not missing_finance_roles,
                "financial roles",
                "system_admin and shift_manager roles exist",
                f"missing role(s): {', '.join(missing_finance_roles)}",
            ),
        ]
