import csv
import io
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.serializers import ValidationError as DRFValidationError

from apps.accounts.models import User

from .labor_budget_services import build_labor_cost_budget_preview, get_labor_cost_budget_variance
from .models import (
    LaborCostBudgetPeriod,
    LaborCostEstimatePeriod,
    RevenueActualLine,
    RevenueActualPeriod,
    RevenueBudgetLine,
    RevenueBudgetPeriod,
    RevenueCategory,
    RevenuePerformanceLineSnapshot,
    RevenuePerformanceSnapshot,
)
from .services import ZERO_MONEY, _decimal, _decimal_payload, _stable_sha256, build_labor_cost_preview

PERCENT_QUANT = Decimal("0.01")
HIGH_LABOR_COST_RATIO_PERCENT = Decimal("40.00")


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return ((numerator / denominator) * Decimal("100")).quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    category: str | None = None,
    related_period_id: str | None = None,
) -> dict:
    result = {"severity": severity, "code": code, "message": message}
    if category:
        result["category"] = category
    if related_period_id:
        result["related_period_id"] = related_period_id
    return result


def _warning(code: str, message: str, **context) -> dict:
    return _issue("warning", code, message, **context)


def _error(code: str, message: str, **context) -> dict:
    return _issue("error", code, message, **context)


def _dedupe_issues(issues: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for issue in issues:
        key = tuple(sorted((key, str(value)) for key, value in issue.items()))
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return sorted(
        result,
        key=lambda item: (
            item.get("severity", ""),
            item.get("code", ""),
            item.get("category", ""),
            item.get("related_period_id", ""),
            item.get("message", ""),
        ),
    )


def _fingerprint_issue(issue: dict) -> dict:
    return {key: issue.get(key, "") for key in ["severity", "code", "message", "category", "related_period_id"]}


def _issue_counts(issues: list[dict]) -> tuple[int, int]:
    return (
        sum(1 for issue in issues if issue["severity"] == "warning"),
        sum(1 for issue in issues if issue["severity"] == "error"),
    )


def revenue_category_metadata(category: RevenueCategory, *, action: str) -> dict:
    return {
        "revenue_category_id": str(category.id),
        "location_id": str(category.location_id),
        "code": category.code,
        "is_active": category.is_active,
        "action": action,
    }


def revenue_budget_period_metadata(period: RevenueBudgetPeriod, preview: dict | None = None) -> dict:
    preview = preview or {}
    summary = preview.get("summary", {})
    return {
        "revenue_budget_period_id": str(period.id),
        "location_id": str(period.location_id),
        "year": period.year,
        "month": period.month,
        "status": period.status,
        "content_hash": period.content_hash or preview.get("content_hash", ""),
        "validation_fingerprint": period.validation_fingerprint or preview.get("validation_fingerprint", ""),
        "line_count": summary.get("line_count", getattr(period, "line_total", 0)),
        "warning_count": summary.get("warning_count", 0),
        "error_count": summary.get("error_count", 0),
    }


def revenue_actual_period_metadata(period: RevenueActualPeriod, preview: dict | None = None) -> dict:
    preview = preview or {}
    summary = preview.get("summary", {})
    return {
        "revenue_actual_period_id": str(period.id),
        "location_id": str(period.location_id),
        "year": period.year,
        "month": period.month,
        "status": period.status,
        "revenue_budget_period_id": str(period.revenue_budget_period_id or preview.get("revenue_budget_period") or "")
        or None,
        "labor_cost_budget_period_id": str(
            period.labor_cost_budget_period_id or preview.get("labor_cost_budget_period") or ""
        )
        or None,
        "labor_cost_estimate_period_id": str(
            period.labor_cost_estimate_period_id or preview.get("labor_cost_estimate_period") or ""
        )
        or None,
        "content_hash": period.content_hash or preview.get("content_hash", ""),
        "validation_fingerprint": period.validation_fingerprint or preview.get("validation_fingerprint", ""),
        "line_count": summary.get("line_count", getattr(period, "line_total", 0)),
        "warning_count": summary.get("warning_count", 0),
        "error_count": summary.get("error_count", 0),
    }


def _budget_line_payload(line: RevenueBudgetLine) -> dict:
    return {
        "id": str(line.id),
        "budget_period": str(line.budget_period_id),
        "category": str(line.category_id),
        "category_code_snapshot": line.category_code_snapshot,
        "category_name_snapshot": line.category_name_snapshot,
        "category_is_active": line.category.is_active,
        "category_location": str(line.category.location_id),
        "budget_amount": line.budget_amount,
        "notes": line.notes,
        "display_order": line.display_order,
        "is_active": line.is_active,
    }


def _actual_line_payload(line: RevenueActualLine) -> dict:
    return {
        "id": str(line.id),
        "actual_period": str(line.actual_period_id),
        "category": str(line.category_id),
        "category_code_snapshot": line.category_code_snapshot,
        "category_name_snapshot": line.category_name_snapshot,
        "category_is_active": line.category.is_active,
        "category_location": str(line.category.location_id),
        "actual_amount": line.actual_amount,
        "source": line.source,
        "notes": line.notes,
        "display_order": line.display_order,
        "is_active": line.is_active,
    }


def _budget_lines(period: RevenueBudgetPeriod) -> list[dict]:
    return [
        _budget_line_payload(line)
        for line in RevenueBudgetLine.objects.select_related("category", "budget_period")
        .filter(budget_period=period)
        .order_by("display_order", "category_code_snapshot", "id")
    ]


def _actual_lines(period: RevenueActualPeriod) -> list[dict]:
    return [
        _actual_line_payload(line)
        for line in RevenueActualLine.objects.select_related("category", "actual_period")
        .filter(actual_period=period)
        .order_by("display_order", "category_code_snapshot", "id")
    ]


def _budget_line_issues(period: RevenueBudgetPeriod, lines: list[dict]) -> list[dict]:
    issues = []
    active_lines = [line for line in lines if line["is_active"]]
    if not active_lines:
        issues.append(_error("revenue_category_missing", "有効な売上予算区分が1件以上必要です。"))
    seen_categories = set()
    for line in active_lines:
        category_id = line["category"]
        category_code = line["category_code_snapshot"]
        if category_id in seen_categories:
            issues.append(
                _error(
                    "revenue_category_duplicate",
                    "同じ売上区分が重複しています。",
                    category=category_code,
                )
            )
        seen_categories.add(category_id)
        if line["budget_amount"] < 0:
            issues.append(
                _error("revenue_budget_negative", "売上予算は0以上で指定してください。", category=category_code)
            )
        if not line["category_is_active"]:
            issues.append(
                _warning(
                    "revenue_category_inactive",
                    "無効化済み売上区分が含まれています。",
                    category=category_code,
                )
            )
        if line["category_location"] != str(period.location_id):
            issues.append(
                _error(
                    "revenue_category_location_mismatch",
                    "売上区分と予算periodの拠点が一致しません。",
                    category=category_code,
                )
            )
    return _dedupe_issues(issues)


def build_revenue_budget_content_hash(
    period: RevenueBudgetPeriod,
    *,
    lines: list[dict] | None = None,
    issues: list[dict] | None = None,
) -> str:
    if lines is None or issues is None:
        return build_revenue_budget_preview(period)["content_hash"]
    payload = {
        "period": {
            "location": str(period.location_id),
            "year": period.year,
            "month": period.month,
        },
        "lines": [
            {
                "category": line["category"],
                "category_code": line["category_code_snapshot"],
                "category_name": line["category_name_snapshot"],
                "budget_amount": _decimal_payload(line["budget_amount"]),
                "is_active": line["is_active"],
            }
            for line in sorted(lines, key=lambda item: (item["category"], item["id"]))
        ],
        "approval_issues": [_fingerprint_issue(issue) for issue in _dedupe_issues(issues)],
    }
    return _stable_sha256(payload)


def build_revenue_budget_validation_fingerprint(
    period: RevenueBudgetPeriod,
    *,
    issues: list[dict] | None = None,
) -> str:
    if issues is None:
        return build_revenue_budget_preview(period)["validation_fingerprint"]
    return _stable_sha256(
        {
            "period": str(period.id),
            "location": str(period.location_id),
            "year": period.year,
            "month": period.month,
            "issues": [_fingerprint_issue(issue) for issue in _dedupe_issues(issues)],
        }
    )


def build_revenue_budget_preview(period: RevenueBudgetPeriod) -> dict:
    if period.pk:
        period = RevenueBudgetPeriod.objects.select_related("location").get(pk=period.pk)
    lines = _budget_lines(period) if period.pk else []
    issues = _budget_line_issues(period, lines)
    active_lines = [line for line in lines if line["is_active"]]
    total = sum((_decimal(line["budget_amount"]) for line in active_lines), ZERO_MONEY)
    if total == 0:
        issues.append(_warning("revenue_budget_zero", "売上予算合計が0円です。"))
    issues = _dedupe_issues(issues)
    warning_count, error_count = _issue_counts(issues)
    content_hash = build_revenue_budget_content_hash(period, lines=lines, issues=issues)
    validation_fingerprint = build_revenue_budget_validation_fingerprint(period, issues=issues)
    return {
        "period": str(period.id),
        "location": str(period.location_id),
        "location_name": period.location.name,
        "location_code": period.location.code,
        "year": period.year,
        "month": period.month,
        "status": period.status,
        "content_hash": content_hash,
        "validation_fingerprint": validation_fingerprint,
        "lines": lines,
        "warnings": [issue for issue in issues if issue["severity"] == "warning"],
        "errors": [issue for issue in issues if issue["severity"] == "error"],
        "issues": issues,
        "summary": {
            "budget_total": total,
            "line_count": len(active_lines),
            "warning_count": warning_count,
            "error_count": error_count,
        },
        "can_approve": bool(active_lines) and error_count == 0,
    }


def approve_revenue_budget(
    *,
    period: RevenueBudgetPeriod,
    actor: User,
    acknowledge_warnings: bool,
    validation_fingerprint: str,
) -> tuple[RevenueBudgetPeriod, dict]:
    with transaction.atomic():
        period = (
            RevenueBudgetPeriod.objects.select_for_update(of=("self",)).select_related("location").get(pk=period.pk)
        )
        list(RevenueBudgetLine.objects.select_for_update(of=("self",)).filter(budget_period=period).order_by("id"))
        if period.status not in {
            RevenueBudgetPeriod.Status.DRAFT,
            RevenueBudgetPeriod.Status.REVIEW,
            RevenueBudgetPeriod.Status.REOPENED,
        }:
            raise DRFValidationError({"status": "draft/review/reopenedの売上予算のみ承認できます。"})
        preview = build_revenue_budget_preview(period)
        if not validation_fingerprint or validation_fingerprint != preview["validation_fingerprint"]:
            raise DRFValidationError({"validation_fingerprint": "最新のpreview結果と一致しません。"})
        if preview["summary"]["error_count"]:
            raise DRFValidationError({"errors": "errorがあるため承認できません。"})
        if preview["summary"]["warning_count"] and not acknowledge_warnings:
            raise DRFValidationError({"acknowledge_warnings": "warningの確認が必要です。"})
        if not preview["can_approve"]:
            raise DRFValidationError({"status": "売上予算を承認できる状態ではありません。"})
        period.status = RevenueBudgetPeriod.Status.APPROVED
        period.content_hash = preview["content_hash"]
        period.validation_fingerprint = preview["validation_fingerprint"]
        period.approved_at = timezone.now()
        period.approved_by = actor
        period.updated_by = actor
        period.full_clean()
        period.save(
            update_fields=[
                "status",
                "content_hash",
                "validation_fingerprint",
                "approved_at",
                "approved_by",
                "updated_by",
                "updated_at",
            ]
        )
        return period, preview


def reopen_revenue_budget(*, period: RevenueBudgetPeriod, actor: User) -> RevenueBudgetPeriod:
    with transaction.atomic():
        period = RevenueBudgetPeriod.objects.select_for_update(of=("self",)).get(pk=period.pk)
        if period.status != RevenueBudgetPeriod.Status.APPROVED:
            raise DRFValidationError({"status": "approvedの売上予算のみ再オープンできます。"})
        period.status = RevenueBudgetPeriod.Status.REOPENED
        period.reopened_at = timezone.now()
        period.reopened_by = actor
        period.updated_by = actor
        period.save(update_fields=["status", "reopened_at", "reopened_by", "updated_by", "updated_at"])
        return period


def archive_revenue_budget(*, period: RevenueBudgetPeriod, actor: User) -> RevenueBudgetPeriod:
    with transaction.atomic():
        period = RevenueBudgetPeriod.objects.select_for_update(of=("self",)).get(pk=period.pk)
        if period.status == RevenueBudgetPeriod.Status.APPROVED:
            raise DRFValidationError({"status": "approvedの売上予算は再オープン後にアーカイブしてください。"})
        if period.status == RevenueBudgetPeriod.Status.ARCHIVED or not period.is_active:
            raise DRFValidationError({"status": "既にアーカイブ済みです。"})
        period.status = RevenueBudgetPeriod.Status.ARCHIVED
        period.is_active = False
        period.updated_by = actor
        period.save(update_fields=["status", "is_active", "updated_by", "updated_at"])
        return period


def _matching_month(period, related) -> bool:
    return bool(
        related
        and related.location_id == period.location_id
        and related.year == period.year
        and related.month == period.month
        and related.is_active
    )


def get_revenue_budget_period_for_month(period: RevenueActualPeriod, *, lock: bool = False) -> dict:
    queryset = RevenueBudgetPeriod.objects.select_related("location").filter(
        location_id=period.location_id,
        year=period.year,
        month=period.month,
        is_active=True,
    )
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    explicit = period.revenue_budget_period if period.revenue_budget_period_id else None
    if _matching_month(period, explicit) and explicit.status == RevenueBudgetPeriod.Status.APPROVED:
        selected = queryset.filter(pk=explicit.pk).first()
        return {"status": "approved", "period": selected}
    approved = queryset.filter(status=RevenueBudgetPeriod.Status.APPROVED).order_by("-approved_at", "id").first()
    if approved:
        return {"status": "approved", "period": approved}
    live_statuses = [
        RevenueBudgetPeriod.Status.REVIEW,
        RevenueBudgetPeriod.Status.DRAFT,
        RevenueBudgetPeriod.Status.REOPENED,
    ]
    if _matching_month(period, explicit) and explicit.status in live_statuses:
        selected = queryset.filter(pk=explicit.pk).first()
    else:
        selected = queryset.filter(status__in=live_statuses).order_by("-updated_at", "id").first()
    return {"status": "live" if selected else "unavailable", "period": selected}


def get_labor_cost_budget_period_for_revenue(period: RevenueActualPeriod, *, lock: bool = False) -> dict:
    queryset = LaborCostBudgetPeriod.objects.select_related("location").filter(
        location_id=period.location_id,
        year=period.year,
        month=period.month,
        is_active=True,
    )
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    explicit = period.labor_cost_budget_period if period.labor_cost_budget_period_id else None
    if _matching_month(period, explicit) and explicit.status == LaborCostBudgetPeriod.Status.APPROVED:
        selected = queryset.filter(pk=explicit.pk).first()
        return {"status": "approved", "period": selected}
    approved = queryset.filter(status=LaborCostBudgetPeriod.Status.APPROVED).order_by("-approved_at", "id").first()
    if approved:
        return {"status": "approved", "period": approved}
    live_statuses = [
        LaborCostBudgetPeriod.Status.REVIEW,
        LaborCostBudgetPeriod.Status.DRAFT,
        LaborCostBudgetPeriod.Status.REOPENED,
    ]
    if _matching_month(period, explicit) and explicit.status in live_statuses:
        selected = queryset.filter(pk=explicit.pk).first()
    else:
        selected = queryset.filter(status__in=live_statuses).order_by("-updated_at", "id").first()
    return {"status": "live" if selected else "unavailable", "period": selected}


def get_labor_cost_estimate_period_for_revenue(period: RevenueActualPeriod, *, lock: bool = False) -> dict:
    queryset = LaborCostEstimatePeriod.objects.select_related("location").filter(
        location_id=period.location_id,
        year=period.year,
        month=period.month,
        is_active=True,
    )
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    explicit = period.labor_cost_estimate_period if period.labor_cost_estimate_period_id else None
    if _matching_month(period, explicit) and explicit.status == LaborCostEstimatePeriod.Status.FINALIZED:
        selected = queryset.filter(pk=explicit.pk).first()
        return {"status": "finalized", "period": selected}
    finalized = queryset.filter(status=LaborCostEstimatePeriod.Status.FINALIZED).order_by("-finalized_at", "id").first()
    if finalized:
        return {"status": "finalized", "period": finalized}
    live_statuses = [
        LaborCostEstimatePeriod.Status.REVIEW,
        LaborCostEstimatePeriod.Status.DRAFT,
        LaborCostEstimatePeriod.Status.REOPENED,
    ]
    if _matching_month(period, explicit) and explicit.status in live_statuses:
        selected = queryset.filter(pk=explicit.pk).first()
    else:
        selected = queryset.filter(status__in=live_statuses).order_by("-updated_at", "id").first()
    return {"status": "live" if selected else "unavailable", "period": selected}


def _revenue_budget_source(period: RevenueActualPeriod, *, lock: bool = False) -> dict:
    source = get_revenue_budget_period_for_month(period, lock=lock)
    budget_period = source["period"]
    if budget_period is None:
        return {
            "status": "unavailable",
            "period": None,
            "content_hash": "",
            "total": ZERO_MONEY,
            "lines": [],
            "issues": [],
        }
    preview = build_revenue_budget_preview(budget_period)
    return {
        "status": source["status"],
        "period": budget_period,
        "content_hash": budget_period.content_hash if source["status"] == "approved" else preview["content_hash"],
        "total": preview["summary"]["budget_total"],
        "lines": [line for line in preview["lines"] if line["is_active"]],
        "issues": preview["issues"],
    }


def _labor_budget_source(period: RevenueActualPeriod, *, lock: bool = False) -> dict:
    source = get_labor_cost_budget_period_for_revenue(period, lock=lock)
    labor_period = source["period"]
    if labor_period is None:
        return {
            "status": "unavailable",
            "period": None,
            "content_hash": "",
            "budget_amount": ZERO_MONEY,
            "planned_total": ZERO_MONEY,
            "issues": [],
        }
    payload = (
        get_labor_cost_budget_variance(labor_period)
        if source["status"] == "approved"
        else build_labor_cost_budget_preview(labor_period)
    )
    summary = payload["summary"]
    issues = list(payload.get("approval_issues", [])) + list(payload.get("comparison_issues", []))
    return {
        "status": source["status"],
        "period": labor_period,
        "content_hash": labor_period.content_hash if source["status"] == "approved" else payload["content_hash"],
        "budget_amount": summary["budget_amount"],
        "planned_total": summary["planned_total"],
        "issues": issues,
    }


def _labor_estimate_source(period: RevenueActualPeriod, *, lock: bool = False) -> dict:
    source = get_labor_cost_estimate_period_for_revenue(period, lock=lock)
    estimate_period = source["period"]
    if estimate_period is None:
        return {
            "status": "unavailable",
            "period": None,
            "content_hash": "",
            "total": ZERO_MONEY,
            "issues": [],
        }
    if source["status"] == "finalized":
        total = sum(
            (item.estimated_total for item in estimate_period.staff_summaries.only("estimated_total")),
            ZERO_MONEY,
        )
        return {
            "status": "finalized",
            "period": estimate_period,
            "content_hash": estimate_period.content_hash,
            "total": total,
            "issues": [],
        }
    preview = build_labor_cost_preview(estimate_period)
    return {
        "status": "live",
        "period": estimate_period,
        "content_hash": preview["content_hash"],
        "total": preview["summary"]["estimated_total"],
        "issues": preview["issues"],
    }


def _actual_line_issues(period: RevenueActualPeriod, lines: list[dict]) -> list[dict]:
    issues = []
    seen = set()
    for line in [item for item in lines if item["is_active"]]:
        code = line["category_code_snapshot"]
        if line["category"] in seen:
            issues.append(_error("category_duplicate", "同じ売上区分が重複しています。", category=code))
        seen.add(line["category"])
        if line["actual_amount"] < 0:
            issues.append(_error("revenue_actual_negative", "売上実績は0以上で指定してください。", category=code))
        if line["category_location"] != str(period.location_id):
            issues.append(
                _error("location_month_mismatch", "売上区分と実績periodの拠点が一致しません。", category=code)
            )
        if not line["category_is_active"]:
            issues.append(_warning("revenue_category_inactive", "無効化済み売上区分が含まれています。", category=code))
    return _dedupe_issues(issues)


def _source_issues(revenue_budget: dict, labor_budget: dict, labor_estimate: dict) -> list[dict]:
    issues = []
    source_specs = [
        (
            revenue_budget,
            "approved",
            "revenue_budget_not_approved",
            "承認済み売上予算が必要です。",
            "revenue_budget_live_fallback",
            "未承認の売上予算をpreviewへ使用しています。",
        ),
        (
            labor_budget,
            "approved",
            "labor_cost_budget_not_approved",
            "承認済み人件費予算が必要です。",
            "labor_cost_budget_live_fallback",
            "未承認の人件費予算をpreviewへ使用しています。",
        ),
        (
            labor_estimate,
            "finalized",
            "labor_cost_estimate_not_finalized",
            "確定済み実績概算人件費が必要です。",
            "labor_cost_estimate_live_fallback",
            "未確定の実績概算人件費をpreviewへ使用しています。",
        ),
    ]
    for source, required_status, error_code, error_message, warning_code, warning_message in source_specs:
        related_id = str(source["period"].id) if source["period"] else None
        if source["status"] != required_status:
            issues.append(_error(error_code, error_message, related_period_id=related_id))
            if source["status"] == "live":
                issues.append(_warning(warning_code, warning_message, related_period_id=related_id))
    if labor_budget["issues"]:
        issues.append(
            _warning(
                "labor_cost_budget_warning",
                "人件費予算previewに確認事項があります。",
                related_period_id=str(labor_budget["period"].id) if labor_budget["period"] else None,
            )
        )
    if labor_estimate["issues"]:
        issues.append(
            _warning(
                "labor_cost_estimate_warning",
                "概算人件費previewに確認事項があります。",
                related_period_id=str(labor_estimate["period"].id) if labor_estimate["period"] else None,
            )
        )
    return _dedupe_issues(issues)


def _performance_lines(budget_lines: list[dict], actual_lines: list[dict]) -> tuple[list[dict], list[dict]]:
    budget_by_code = {line["category_code_snapshot"]: line for line in budget_lines if line["is_active"]}
    actual_by_code = {line["category_code_snapshot"]: line for line in actual_lines if line["is_active"]}
    result = []
    issues = []
    for display_order, code in enumerate(sorted(set(budget_by_code) | set(actual_by_code)), start=1):
        budget_line = budget_by_code.get(code)
        actual_line = actual_by_code.get(code)
        budget_amount = _decimal(budget_line["budget_amount"] if budget_line else ZERO_MONEY)
        actual_amount = _decimal(actual_line["actual_amount"] if actual_line else ZERO_MONEY)
        line_issues = []
        if budget_line is None:
            line_issues.append(_warning("category_budget_missing", "区分別売上予算がありません。", category=code))
        if actual_line is None:
            line_issues.append(_warning("category_actual_missing", "区分別売上実績がありません。", category=code))
        if budget_amount == 0:
            line_issues.append(_warning("revenue_budget_zero", "区分別売上予算が0円です。", category=code))
        line_issues = _dedupe_issues(line_issues)
        warning_count, error_count = _issue_counts(line_issues)
        source_line = actual_line or budget_line
        result.append(
            {
                "category": source_line["category"] if source_line else None,
                "category_code_snapshot": code,
                "category_name_snapshot": source_line["category_name_snapshot"] if source_line else code,
                "budget_amount": budget_amount,
                "actual_amount": actual_amount,
                "variance_amount": actual_amount - budget_amount,
                "attainment_percent": _percent(actual_amount, budget_amount),
                "warning_count": warning_count,
                "warnings": [issue for issue in line_issues if issue["severity"] == "warning"],
                "error_count": error_count,
                "errors": [issue for issue in line_issues if issue["severity"] == "error"],
                "display_order": min(item["display_order"] for item in [budget_line, actual_line] if item is not None)
                if source_line
                else display_order,
            }
        )
        issues.extend(line_issues)
    return sorted(result, key=lambda item: (item["display_order"], item["category_code_snapshot"])), issues


def _performance_summary(
    *,
    revenue_budget_total: Decimal,
    revenue_actual_total: Decimal,
    labor_budget_amount: Decimal,
    planned_labor_cost: Decimal,
    actual_labor_cost_estimate: Decimal,
) -> dict:
    return {
        "revenue_budget_total": revenue_budget_total,
        "revenue_actual_total": revenue_actual_total,
        "revenue_variance_amount": revenue_actual_total - revenue_budget_total,
        "revenue_attainment_percent": (
            Decimal("0.00")
            if revenue_budget_total == 0 and revenue_actual_total == 0
            else _percent(revenue_actual_total, revenue_budget_total)
        ),
        "labor_budget_amount": labor_budget_amount,
        "planned_labor_cost": planned_labor_cost,
        "actual_labor_cost_estimate": actual_labor_cost_estimate,
        "budget_labor_cost_ratio": _percent(labor_budget_amount, revenue_budget_total),
        "planned_labor_cost_ratio_to_budget_revenue": _percent(planned_labor_cost, revenue_budget_total),
        "planned_labor_cost_ratio_to_actual_revenue": _percent(planned_labor_cost, revenue_actual_total),
        "actual_labor_cost_ratio": _percent(actual_labor_cost_estimate, revenue_actual_total),
        "planned_vs_labor_budget_amount": planned_labor_cost - labor_budget_amount,
        "actual_vs_labor_budget_amount": actual_labor_cost_estimate - labor_budget_amount,
        "actual_vs_planned_labor_cost_amount": actual_labor_cost_estimate - planned_labor_cost,
    }


def build_revenue_actual_content_hash(
    period: RevenueActualPeriod,
    *,
    lines: list[dict] | None = None,
    sources: dict | None = None,
    summary: dict | None = None,
    issues: list[dict] | None = None,
) -> str:
    if lines is None or sources is None or summary is None or issues is None:
        return build_revenue_actual_preview(period)["content_hash"]
    payload = {
        "period": {"location": str(period.location_id), "year": period.year, "month": period.month},
        "lines": [
            {
                "category": line["category"],
                "category_code": line["category_code_snapshot"],
                "actual_amount": _decimal_payload(line["actual_amount"]),
                "source": line["source"],
                "is_active": line["is_active"],
            }
            for line in sorted(lines, key=lambda item: (item["category"], item["id"]))
        ],
        "sources": {
            key: {
                "period": str(value["period"].id) if value["period"] else "",
                "status": value["status"],
                "content_hash": value["content_hash"],
            }
            for key, value in sorted(sources.items())
        },
        "summary": {
            key: _decimal_payload(value) if isinstance(value, Decimal) or value is None else value
            for key, value in sorted(summary.items())
            if key not in {"warning_count", "error_count", "line_count"}
        },
        "finalize_issues": [_fingerprint_issue(issue) for issue in _dedupe_issues(issues)],
    }
    return _stable_sha256(payload)


def build_revenue_actual_validation_fingerprint(
    period: RevenueActualPeriod,
    *,
    issues: list[dict] | None = None,
) -> str:
    if issues is None:
        return build_revenue_actual_preview(period)["validation_fingerprint"]
    return _stable_sha256(
        {
            "period": str(period.id),
            "location": str(period.location_id),
            "year": period.year,
            "month": period.month,
            "issues": [_fingerprint_issue(issue) for issue in _dedupe_issues(issues)],
        }
    )


def build_revenue_actual_preview(period: RevenueActualPeriod, *, lock_sources: bool = False) -> dict:
    if period.pk:
        period = RevenueActualPeriod.objects.select_related(
            "location",
            "revenue_budget_period",
            "labor_cost_budget_period",
            "labor_cost_estimate_period",
        ).get(pk=period.pk)
    lines = _actual_lines(period)
    issues = _actual_line_issues(period, lines)
    revenue_budget = _revenue_budget_source(period, lock=lock_sources)
    labor_budget = _labor_budget_source(period, lock=lock_sources)
    labor_estimate = _labor_estimate_source(period, lock=lock_sources)
    sources = {
        "revenue_budget": revenue_budget,
        "labor_budget": labor_budget,
        "labor_estimate": labor_estimate,
    }
    issues.extend(_source_issues(revenue_budget, labor_budget, labor_estimate))
    active_lines = [line for line in lines if line["is_active"]]
    try:
        revenue_actual_total = sum((_decimal(line["actual_amount"]) for line in active_lines), ZERO_MONEY)
        revenue_budget_total = _decimal(revenue_budget["total"])
        performance_lines, line_issues = _performance_lines(revenue_budget["lines"], lines)
        issues.extend(line_issues)
        summary = _performance_summary(
            revenue_budget_total=revenue_budget_total,
            revenue_actual_total=revenue_actual_total,
            labor_budget_amount=_decimal(labor_budget["budget_amount"]),
            planned_labor_cost=_decimal(labor_budget["planned_total"]),
            actual_labor_cost_estimate=_decimal(labor_estimate["total"]),
        )
    except (InvalidOperation, ArithmeticError, TypeError, ValueError):
        issues.append(_error("decimal_calculation_error", "売上・人件費率を計算できませんでした。"))
        performance_lines = []
        summary = _performance_summary(
            revenue_budget_total=ZERO_MONEY,
            revenue_actual_total=ZERO_MONEY,
            labor_budget_amount=ZERO_MONEY,
            planned_labor_cost=ZERO_MONEY,
            actual_labor_cost_estimate=ZERO_MONEY,
        )
    if summary["revenue_budget_total"] == 0:
        issues.append(_warning("revenue_budget_zero", "売上予算合計が0円のため一部割合を算出できません。"))
    if summary["revenue_actual_total"] == 0:
        issues.append(_warning("revenue_actual_zero", "売上実績合計が0円のため一部割合を算出できません。"))
    if summary["revenue_actual_total"] > summary["revenue_budget_total"]:
        issues.append(_warning("revenue_budget_below_actual", "売上実績が売上予算を上回っています。"))
    high_ratios = [
        summary["planned_labor_cost_ratio_to_actual_revenue"],
        summary["actual_labor_cost_ratio"],
    ]
    if any(value is not None and value >= HIGH_LABOR_COST_RATIO_PERCENT for value in high_ratios):
        issues.append(
            _warning(
                "labor_cost_ratio_high",
                f"人件費率が確認基準{HIGH_LABOR_COST_RATIO_PERCENT}%以上です。",
            )
        )
    issues = _dedupe_issues(issues)
    warning_count, error_count = _issue_counts(issues)
    summary |= {"line_count": len(active_lines), "warning_count": warning_count, "error_count": error_count}
    content_hash = build_revenue_actual_content_hash(
        period,
        lines=lines,
        sources=sources,
        summary=summary,
        issues=issues,
    )
    validation_fingerprint = build_revenue_actual_validation_fingerprint(period, issues=issues)
    return {
        "period": str(period.id),
        "location": str(period.location_id),
        "location_name": period.location.name,
        "location_code": period.location.code,
        "year": period.year,
        "month": period.month,
        "status": period.status,
        "revenue_budget_source_status": revenue_budget["status"],
        "labor_cost_budget_source_status": labor_budget["status"],
        "labor_cost_estimate_source_status": labor_estimate["status"],
        "revenue_budget_period": str(revenue_budget["period"].id) if revenue_budget["period"] else None,
        "labor_cost_budget_period": str(labor_budget["period"].id) if labor_budget["period"] else None,
        "labor_cost_estimate_period": str(labor_estimate["period"].id) if labor_estimate["period"] else None,
        "budget_content_hash": revenue_budget["content_hash"],
        "labor_budget_content_hash": labor_budget["content_hash"],
        "labor_estimate_content_hash": labor_estimate["content_hash"],
        "content_hash": content_hash,
        "validation_fingerprint": validation_fingerprint,
        "summary": summary,
        "lines": lines,
        "performance_lines": performance_lines,
        "warnings": [issue for issue in issues if issue["severity"] == "warning"],
        "errors": [issue for issue in issues if issue["severity"] == "error"],
        "issues": issues,
        "can_finalize": error_count == 0,
    }


def build_revenue_performance_snapshot(
    period: RevenueActualPeriod,
    *,
    preview: dict,
) -> RevenuePerformanceSnapshot:
    summary = preview["summary"]
    return RevenuePerformanceSnapshot(
        actual_period=period,
        revenue_budget_period_id=preview["revenue_budget_period"],
        labor_cost_budget_period_id=preview["labor_cost_budget_period"],
        labor_cost_estimate_period_id=preview["labor_cost_estimate_period"],
        location=period.location,
        year=period.year,
        month=period.month,
        location_code_snapshot=period.location.code,
        location_name_snapshot=period.location.name,
        revenue_budget_total=summary["revenue_budget_total"],
        revenue_actual_total=summary["revenue_actual_total"],
        revenue_variance_amount=summary["revenue_variance_amount"],
        revenue_attainment_percent=summary["revenue_attainment_percent"],
        labor_budget_amount=summary["labor_budget_amount"],
        planned_labor_cost=summary["planned_labor_cost"],
        actual_labor_cost_estimate=summary["actual_labor_cost_estimate"],
        budget_labor_cost_ratio=summary["budget_labor_cost_ratio"],
        planned_labor_cost_ratio_to_budget_revenue=summary["planned_labor_cost_ratio_to_budget_revenue"],
        planned_labor_cost_ratio_to_actual_revenue=summary["planned_labor_cost_ratio_to_actual_revenue"],
        actual_labor_cost_ratio=summary["actual_labor_cost_ratio"],
        planned_vs_labor_budget_amount=summary["planned_vs_labor_budget_amount"],
        actual_vs_labor_budget_amount=summary["actual_vs_labor_budget_amount"],
        actual_vs_planned_labor_cost_amount=summary["actual_vs_planned_labor_cost_amount"],
        budget_content_hash=preview["budget_content_hash"],
        labor_budget_content_hash=preview["labor_budget_content_hash"],
        labor_estimate_content_hash=preview["labor_estimate_content_hash"],
        content_hash=preview["content_hash"],
        validation_fingerprint=preview["validation_fingerprint"],
        warning_count=summary["warning_count"],
        warnings=preview["warnings"],
        error_count=summary["error_count"],
        errors=preview["errors"],
    )


def build_revenue_performance_line_snapshots(
    snapshot: RevenuePerformanceSnapshot,
    *,
    preview: dict,
) -> list[RevenuePerformanceLineSnapshot]:
    return [
        RevenuePerformanceLineSnapshot(
            performance_snapshot=snapshot,
            category_id=line["category"],
            category_code_snapshot=line["category_code_snapshot"],
            category_name_snapshot=line["category_name_snapshot"],
            budget_amount=line["budget_amount"],
            actual_amount=line["actual_amount"],
            variance_amount=line["variance_amount"],
            attainment_percent=line["attainment_percent"],
            warning_count=line["warning_count"],
            warnings=line["warnings"],
            error_count=line["error_count"],
            errors=line["errors"],
            display_order=line["display_order"],
        )
        for line in preview["performance_lines"]
    ]


def finalize_revenue_actual(
    *,
    period: RevenueActualPeriod,
    actor: User,
    acknowledge_warnings: bool,
    validation_fingerprint: str,
) -> tuple[RevenueActualPeriod, dict]:
    with transaction.atomic():
        period = (
            RevenueActualPeriod.objects.select_for_update(of=("self",))
            .select_related(
                "location",
                "revenue_budget_period",
                "labor_cost_budget_period",
                "labor_cost_estimate_period",
            )
            .get(pk=period.pk)
        )
        list(RevenueActualLine.objects.select_for_update(of=("self",)).filter(actual_period=period).order_by("id"))
        if period.status not in {
            RevenueActualPeriod.Status.DRAFT,
            RevenueActualPeriod.Status.REVIEW,
            RevenueActualPeriod.Status.REOPENED,
        }:
            raise DRFValidationError({"status": "draft/review/reopenedの売上実績のみ確定できます。"})
        preview = build_revenue_actual_preview(period, lock_sources=True)
        if not validation_fingerprint or validation_fingerprint != preview["validation_fingerprint"]:
            raise DRFValidationError({"validation_fingerprint": "最新のpreview結果と一致しません。"})
        if preview["summary"]["error_count"]:
            raise DRFValidationError({"errors": "errorがあるため確定できません。"})
        if preview["summary"]["warning_count"] and not acknowledge_warnings:
            raise DRFValidationError({"acknowledge_warnings": "warningの確認が必要です。"})
        period.revenue_budget_period_id = preview["revenue_budget_period"]
        period.labor_cost_budget_period_id = preview["labor_cost_budget_period"]
        period.labor_cost_estimate_period_id = preview["labor_cost_estimate_period"]
        RevenuePerformanceSnapshot.objects.filter(actual_period=period).delete()
        snapshot = build_revenue_performance_snapshot(period, preview=preview)
        snapshot.full_clean()
        snapshot.save()
        line_snapshots = build_revenue_performance_line_snapshots(snapshot, preview=preview)
        RevenuePerformanceLineSnapshot.objects.bulk_create(line_snapshots)
        if snapshot.line_snapshots.count() != len(preview["performance_lines"]):
            raise DRFValidationError({"snapshot": "snapshot_integrity_error"})
        period.status = RevenueActualPeriod.Status.FINALIZED
        period.content_hash = preview["content_hash"]
        period.validation_fingerprint = preview["validation_fingerprint"]
        period.finalized_at = timezone.now()
        period.finalized_by = actor
        period.updated_by = actor
        period.full_clean()
        period.save(
            update_fields=[
                "revenue_budget_period",
                "labor_cost_budget_period",
                "labor_cost_estimate_period",
                "status",
                "content_hash",
                "validation_fingerprint",
                "finalized_at",
                "finalized_by",
                "updated_by",
                "updated_at",
            ]
        )
        return period, preview


def reopen_revenue_actual(*, period: RevenueActualPeriod, actor: User) -> RevenueActualPeriod:
    with transaction.atomic():
        period = RevenueActualPeriod.objects.select_for_update(of=("self",)).get(pk=period.pk)
        if period.status != RevenueActualPeriod.Status.FINALIZED:
            raise DRFValidationError({"status": "finalizedの売上実績のみ再オープンできます。"})
        period.status = RevenueActualPeriod.Status.REOPENED
        period.reopened_at = timezone.now()
        period.reopened_by = actor
        period.updated_by = actor
        period.save(update_fields=["status", "reopened_at", "reopened_by", "updated_by", "updated_at"])
        return period


def archive_revenue_actual(*, period: RevenueActualPeriod, actor: User) -> RevenueActualPeriod:
    with transaction.atomic():
        period = RevenueActualPeriod.objects.select_for_update(of=("self",)).get(pk=period.pk)
        if period.status == RevenueActualPeriod.Status.FINALIZED:
            raise DRFValidationError({"status": "finalizedの売上実績は再オープン後にアーカイブしてください。"})
        if period.status == RevenueActualPeriod.Status.ARCHIVED or not period.is_active:
            raise DRFValidationError({"status": "既にアーカイブ済みです。"})
        period.status = RevenueActualPeriod.Status.ARCHIVED
        period.is_active = False
        period.updated_by = actor
        period.save(update_fields=["status", "is_active", "updated_by", "updated_at"])
        return period


def _snapshot_payload(snapshot: RevenuePerformanceSnapshot) -> dict:
    lines = [
        {
            "category": str(line.category_id) if line.category_id else None,
            "category_code_snapshot": line.category_code_snapshot,
            "category_name_snapshot": line.category_name_snapshot,
            "budget_amount": line.budget_amount,
            "actual_amount": line.actual_amount,
            "variance_amount": line.variance_amount,
            "attainment_percent": line.attainment_percent,
            "warning_count": line.warning_count,
            "warnings": line.warnings,
            "error_count": line.error_count,
            "errors": line.errors,
            "display_order": line.display_order,
        }
        for line in snapshot.line_snapshots.select_related("category").order_by(
            "display_order", "category_code_snapshot", "id"
        )
    ]
    summary_fields = [
        "revenue_budget_total",
        "revenue_actual_total",
        "revenue_variance_amount",
        "revenue_attainment_percent",
        "labor_budget_amount",
        "planned_labor_cost",
        "actual_labor_cost_estimate",
        "budget_labor_cost_ratio",
        "planned_labor_cost_ratio_to_budget_revenue",
        "planned_labor_cost_ratio_to_actual_revenue",
        "actual_labor_cost_ratio",
        "planned_vs_labor_budget_amount",
        "actual_vs_labor_budget_amount",
        "actual_vs_planned_labor_cost_amount",
        "warning_count",
        "error_count",
    ]
    return {
        "period": str(snapshot.actual_period_id),
        "location": str(snapshot.location_id),
        "location_name": snapshot.location_name_snapshot,
        "location_code": snapshot.location_code_snapshot,
        "year": snapshot.year,
        "month": snapshot.month,
        "status": RevenueActualPeriod.Status.FINALIZED,
        "revenue_budget_source_status": "approved",
        "labor_cost_budget_source_status": "approved",
        "labor_cost_estimate_source_status": "finalized",
        "revenue_budget_period": str(snapshot.revenue_budget_period_id),
        "labor_cost_budget_period": str(snapshot.labor_cost_budget_period_id),
        "labor_cost_estimate_period": str(snapshot.labor_cost_estimate_period_id),
        "budget_content_hash": snapshot.budget_content_hash,
        "labor_budget_content_hash": snapshot.labor_budget_content_hash,
        "labor_estimate_content_hash": snapshot.labor_estimate_content_hash,
        "content_hash": snapshot.content_hash,
        "validation_fingerprint": snapshot.validation_fingerprint,
        "summary": {field: getattr(snapshot, field) for field in summary_fields} | {"line_count": len(lines)},
        "performance_lines": lines,
        "warnings": snapshot.warnings,
        "errors": snapshot.errors,
        "issues": _dedupe_issues(list(snapshot.warnings) + list(snapshot.errors)),
        "can_finalize": False,
        "is_snapshot": True,
    }


def get_revenue_performance(period: RevenueActualPeriod) -> dict:
    if period.status == RevenueActualPeriod.Status.FINALIZED:
        snapshot = (
            RevenuePerformanceSnapshot.objects.select_related(
                "actual_period",
                "location",
                "revenue_budget_period",
                "labor_cost_budget_period",
                "labor_cost_estimate_period",
            )
            .filter(actual_period=period)
            .first()
        )
        if snapshot:
            return _snapshot_payload(snapshot)
    return build_revenue_actual_preview(period)


def get_financial_performance(*, location_id: str, year: int, month: int) -> dict:
    period = (
        RevenueActualPeriod.objects.select_related(
            "location",
            "revenue_budget_period",
            "labor_cost_budget_period",
            "labor_cost_estimate_period",
        )
        .filter(location_id=location_id, year=year, month=month, is_active=True)
        .order_by("-updated_at", "id")
        .first()
    )
    if period:
        return get_revenue_performance(period)
    return {
        "period": None,
        "location": str(location_id),
        "year": year,
        "month": month,
        "status": "unavailable",
        "revenue_budget_source_status": "unavailable",
        "labor_cost_budget_source_status": "unavailable",
        "labor_cost_estimate_source_status": "unavailable",
        "revenue_budget_period": None,
        "labor_cost_budget_period": None,
        "labor_cost_estimate_period": None,
        "content_hash": "",
        "validation_fingerprint": "",
        "summary": _performance_summary(
            revenue_budget_total=ZERO_MONEY,
            revenue_actual_total=ZERO_MONEY,
            labor_budget_amount=ZERO_MONEY,
            planned_labor_cost=ZERO_MONEY,
            actual_labor_cost_estimate=ZERO_MONEY,
        )
        | {"line_count": 0, "warning_count": 1, "error_count": 0},
        "performance_lines": [],
        "warnings": [_warning("revenue_actual_unavailable", "対象月の売上実績periodがありません。")],
        "errors": [],
        "issues": [_warning("revenue_actual_unavailable", "対象月の売上実績periodがありません。")],
        "can_finalize": False,
    }


def export_revenue_budget_csv(period: RevenueBudgetPeriod) -> tuple[bytes, str, dict]:
    preview = build_revenue_budget_preview(period)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["拠点", "年月", "状態", "売上区分コード", "売上区分", "売上予算", "有効", "警告数", "エラー数"])
    for line in preview["lines"]:
        writer.writerow(
            [
                preview["location_name"],
                f"{period.year}-{period.month:02d}",
                period.status,
                line["category_code_snapshot"],
                line["category_name_snapshot"],
                _decimal_payload(line["budget_amount"]),
                "yes" if line["is_active"] else "no",
                preview["summary"]["warning_count"],
                preview["summary"]["error_count"],
            ]
        )
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    filename = f"revenue_budget_{period.location.code}_{period.year}_{period.month:02d}.csv"
    return data, filename, preview["summary"]


def export_revenue_performance_csv(period: RevenueActualPeriod) -> tuple[bytes, str, dict]:
    payload = get_revenue_performance(period)
    summary = payload["summary"]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "拠点",
            "年月",
            "状態",
            "売上区分コード",
            "売上区分",
            "売上予算",
            "売上実績",
            "売上差異",
            "売上達成率",
            "人件費予算",
            "予定原価",
            "実績概算人件費",
            "予算人件費率",
            "予定人件費率（実績売上比）",
            "実績人件費率",
            "警告数",
            "エラー数",
        ]
    )
    rows = payload["performance_lines"] or [
        {
            "category_code_snapshot": "",
            "category_name_snapshot": "",
            "budget_amount": ZERO_MONEY,
            "actual_amount": ZERO_MONEY,
            "variance_amount": ZERO_MONEY,
            "attainment_percent": None,
        }
    ]
    for line in rows:
        writer.writerow(
            [
                payload.get("location_name", ""),
                f"{period.year}-{period.month:02d}",
                period.status,
                line["category_code_snapshot"],
                line["category_name_snapshot"],
                _decimal_payload(line["budget_amount"]),
                _decimal_payload(line["actual_amount"]),
                _decimal_payload(line["variance_amount"]),
                _decimal_payload(line["attainment_percent"]),
                _decimal_payload(summary["labor_budget_amount"]),
                _decimal_payload(summary["planned_labor_cost"]),
                _decimal_payload(summary["actual_labor_cost_estimate"]),
                _decimal_payload(summary["budget_labor_cost_ratio"]),
                _decimal_payload(summary["planned_labor_cost_ratio_to_actual_revenue"]),
                _decimal_payload(summary["actual_labor_cost_ratio"]),
                summary["warning_count"],
                summary["error_count"],
            ]
        )
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    filename = f"revenue_performance_{period.location.code}_{period.year}_{period.month:02d}.csv"
    return data, filename, summary


def export_revenue_actual_csv(period: RevenueActualPeriod) -> tuple[bytes, str, dict]:
    return export_revenue_performance_csv(period)
