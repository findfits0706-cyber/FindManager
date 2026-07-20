import csv
import io
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.serializers import ValidationError as DRFValidationError

from apps.accounts.models import User

from .models import (
    LaborCostBudgetAllowanceSnapshot,
    LaborCostBudgetDailySummary,
    LaborCostBudgetPeriod,
    LaborCostBudgetPlanRecordSnapshot,
    LaborCostBudgetStaffSummary,
    LaborCostEstimatePeriod,
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftPublication,
    MonthlyShiftPublicationAssignment,
    MonthlyShiftPublicationSegment,
    MonthlyShiftSegment,
    StaffAllowanceAssignment,
    StaffCompensationProfile,
)
from .services import (
    HOUR_QUANT,
    ZERO_MONEY,
    _decimal,
    _decimal_payload,
    _labor_allowances_for_period,
    _labor_profiles_for_period,
    _month_range,
    _periods_overlap,
    _round_yen,
    _stable_sha256,
    build_labor_cost_preview,
    build_monthly_plan_content_hash,
    get_staff_allowances_for_period,
    get_staff_compensation_profile_for_date,
)

PERCENT_QUANT = Decimal("0.01")


def labor_cost_budget_period_metadata(period: LaborCostBudgetPeriod, preview: dict | None = None) -> dict:
    summary = (preview or {}).get("summary", {})

    def snapshot_count(summary_key: str, annotation: str, relation: str) -> int:
        if summary_key in summary:
            return summary[summary_key]
        if hasattr(period, annotation):
            return getattr(period, annotation)
        return getattr(period, relation).count() if period.pk else 0

    return {
        "labor_cost_budget_period_id": str(period.id),
        "location_id": str(period.location_id),
        "year": period.year,
        "month": period.month,
        "status": period.status,
        "source_monthly_shift_plan_id": str(
            period.source_monthly_shift_plan_id or (preview or {}).get("source_monthly_shift_plan") or ""
        )
        or None,
        "source_publication_id": str(period.source_publication_id or (preview or {}).get("source_publication") or "")
        or None,
        "content_hash": period.content_hash or (preview or {}).get("content_hash", ""),
        "validation_fingerprint": period.validation_fingerprint or (preview or {}).get("validation_fingerprint", ""),
        "plan_record_snapshot_count": snapshot_count(
            "plan_record_count", "plan_record_snapshot_total", "plan_record_snapshots"
        ),
        "staff_summary_count": snapshot_count("staff_summary_count", "budget_staff_summary_total", "staff_summaries"),
        "daily_summary_count": snapshot_count("daily_summary_count", "daily_summary_total", "daily_summaries"),
        "allowance_snapshot_count": snapshot_count(
            "allowance_snapshot_count", "budget_allowance_snapshot_total", "allowance_snapshots"
        ),
        "warning_count": summary.get("approval_warning_count", 0),
        "error_count": summary.get("approval_error_count", 0),
    }


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return ((numerator / denominator) * Decimal("100")).quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    staff: str | None = None,
    work_date: str | None = None,
    source_assignment: str | None = None,
    relevant_id: str | None = None,
) -> dict:
    result = {"severity": severity, "code": code, "message": message}
    for key, value in {
        "staff": staff,
        "work_date": work_date,
        "source_assignment": source_assignment,
        "relevant_id": relevant_id,
    }.items():
        if value:
            result[key] = value
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
        key=lambda value: (
            value.get("severity", ""),
            value.get("code", ""),
            value.get("staff", ""),
            value.get("work_date", ""),
            value.get("source_assignment", ""),
            value.get("relevant_id", ""),
            value.get("message", ""),
        ),
    )


def get_planned_compensation_profile_for_date(*, location, staff, target_date):
    return get_staff_compensation_profile_for_date(location=location, staff=staff, target_date=target_date)


def get_planned_allowances_for_period(*, location, staff, start_date, end_date):
    return get_staff_allowances_for_period(
        location=location,
        staff=staff,
        start_date=start_date,
        end_date=end_date,
    )


def _publication_assignments_queryset(*, lock: bool = False):
    segment_queryset = MonthlyShiftPublicationSegment.objects.select_related("work_type", "work_area").order_by(
        "start_offset_minutes", "display_order", "id"
    )
    assignment_queryset = MonthlyShiftPublicationAssignment.objects.select_related("staff", "source_assignment")
    if lock:
        assignment_queryset = assignment_queryset.select_for_update(of=("self",))
        segment_queryset = segment_queryset.select_for_update(of=("self",))
    return assignment_queryset.prefetch_related(
        Prefetch("segments", queryset=segment_queryset, to_attr="budget_segments")
    ).order_by("work_date", "staff_id", "id")


def _plan_assignments_queryset(*, lock: bool = False):
    segment_queryset = (
        MonthlyShiftSegment.objects.select_related("work_type", "work_area")
        .filter(is_active=True)
        .order_by("start_offset_minutes", "display_order", "id")
    )
    assignment_queryset = MonthlyShiftAssignment.objects.select_related("staff").filter(is_active=True)
    if lock:
        assignment_queryset = assignment_queryset.select_for_update(of=("self",))
        segment_queryset = segment_queryset.select_for_update(of=("self",))
    return assignment_queryset.prefetch_related(
        Prefetch("segments", queryset=segment_queryset, to_attr="budget_segments")
    ).order_by("work_date", "staff_id", "id")


def get_labor_cost_plan_source(period: LaborCostBudgetPeriod, *, lock: bool = False) -> dict:
    publication_queryset = MonthlyShiftPublication.objects.select_related("location", "monthly_shift_plan").filter(
        location_id=period.location_id,
        year=period.year,
        month=period.month,
        is_active=True,
        withdrawn_at__isnull=True,
    )
    if lock:
        publication_queryset = publication_queryset.select_for_update(of=("self",))
    publication = publication_queryset.order_by("-published_at", "-version", "id").first()
    if publication is not None:
        if lock:
            MonthlyShiftPlan.objects.select_for_update(of=("self",)).get(pk=publication.monthly_shift_plan_id)
        publication = (
            MonthlyShiftPublication.objects.select_related("location", "monthly_shift_plan")
            .prefetch_related(
                Prefetch(
                    "assignments", queryset=_publication_assignments_queryset(lock=lock), to_attr="budget_assignments"
                )
            )
            .get(pk=publication.pk)
        )
        return {
            "plan_source": "published",
            "plan": publication.monthly_shift_plan,
            "publication": publication,
            "assignments": publication.budget_assignments,
            "source_content_hash": publication.content_hash,
        }

    plan_queryset = MonthlyShiftPlan.objects.select_related("location").filter(
        location_id=period.location_id,
        year=period.year,
        month=period.month,
        is_active=True,
    )
    if lock:
        plan_queryset = plan_queryset.select_for_update(of=("self",))
    plan = plan_queryset.order_by("created_at", "id").first()
    if plan is None:
        return {
            "plan_source": "unavailable",
            "plan": None,
            "publication": None,
            "assignments": [],
            "source_content_hash": "",
        }
    plan = (
        MonthlyShiftPlan.objects.select_related("location")
        .prefetch_related(
            Prefetch("assignments", queryset=_plan_assignments_queryset(lock=lock), to_attr="budget_assignments")
        )
        .get(pk=plan.pk)
    )
    if plan.workflow_status == MonthlyShiftPlan.WorkflowStatus.CONFIRMED:
        plan_source = "confirmed"
        source_content_hash = plan.confirmed_content_hash or build_monthly_plan_content_hash(plan)
    else:
        plan_source = "draft"
        source_content_hash = build_monthly_plan_content_hash(plan)
    return {
        "plan_source": plan_source,
        "plan": plan,
        "publication": None,
        "assignments": plan.budget_assignments,
        "source_content_hash": source_content_hash,
    }


def _normalized_source_assignment(source: dict, assignment) -> dict:
    published = source["plan_source"] == "published"
    segments = assignment.budget_segments
    return {
        "monthly_shift_plan": str(source["plan"].id),
        "monthly_shift_assignment": str(assignment.source_assignment_id if published else assignment.id),
        "publication": str(source["publication"].id) if published else None,
        "publication_assignment": str(assignment.id) if published else None,
        "source_assignment": str(assignment.id),
        "staff": str(assignment.staff_id),
        "staff_object": assignment.staff,
        "staff_display_name": assignment.staff_display_name_snapshot if published else assignment.staff.display_name,
        "employee_code": assignment.employee_code_snapshot if published else assignment.staff.employee_code,
        "work_date": assignment.work_date.isoformat(),
        "source_warning_count": assignment.warning_count_snapshot if published else 0,
        "segments": [
            {
                "id": str(segment.id),
                "source_segment": str(segment.source_segment_id) if published else str(segment.id),
                "start_offset_minutes": segment.start_offset_minutes,
                "end_offset_minutes": segment.end_offset_minutes,
                "is_break": segment.work_type_is_break_snapshot,
            }
            for segment in segments
        ],
    }


def _allowance_overlap_codes(assignments: list[StaffAllowanceAssignment]) -> set[str]:
    overlaps = set()
    by_code = defaultdict(list)
    for assignment in assignments:
        by_code[assignment.code].append(assignment)
    for code, items in by_code.items():
        ordered = sorted(items, key=lambda item: (item.valid_from, item.valid_to or date.max, str(item.id)))
        for index, current in enumerate(ordered):
            if any(
                _periods_overlap(current.valid_from, current.valid_to, other.valid_from, other.valid_to)
                for other in ordered[index + 1 :]
            ):
                overlaps.add(code)
                break
    return overlaps


def _allowance_seed(period: LaborCostBudgetPeriod, assignment: StaffAllowanceAssignment, source_item: dict) -> dict:
    return {
        "budget_period": str(period.id),
        "staff": str(assignment.staff_id),
        "staff_display_name_snapshot": source_item["staff_display_name"],
        "employee_code_snapshot": source_item["employee_code"],
        "allowance_assignment": str(assignment.id),
        "code_snapshot": assignment.code,
        "name_snapshot": assignment.name,
        "allowance_type_snapshot": assignment.allowance_type,
        "amount_snapshot": assignment.amount,
        "quantity": ZERO_MONEY,
        "planned_amount": ZERO_MONEY,
        "warning_count": 0,
        "warnings": [],
    }


def _planned_record_item(
    *,
    period: LaborCostBudgetPeriod,
    source: dict,
    source_item: dict,
    profiles: list[StaffCompensationProfile],
    allowances: list[StaffAllowanceAssignment],
    overlap_codes: set[str],
    allowance_accumulators: dict[str, dict],
) -> dict:
    work_date = date.fromisoformat(source_item["work_date"])
    issues = []
    valid_segments = []
    for segment in source_item["segments"]:
        start = segment["start_offset_minutes"]
        end = segment["end_offset_minutes"]
        if start < 0 or start >= 2880 or end <= 0 or end > 2880 or end <= start:
            issues.append(
                _error(
                    "invalid_planned_segment",
                    "予定シフトに不正な勤務segmentがあります。",
                    staff=source_item["staff"],
                    work_date=source_item["work_date"],
                    source_assignment=source_item["source_assignment"],
                    relevant_id=segment["id"],
                )
            )
            continue
        valid_segments.append(segment)
    work_segments = sorted(
        [segment for segment in valid_segments if not segment["is_break"]],
        key=lambda item: (item["start_offset_minutes"], item["end_offset_minutes"], item["id"]),
    )
    previous_end = None
    for segment in work_segments:
        if previous_end is not None and segment["start_offset_minutes"] < previous_end:
            issues.append(
                _warning(
                    "shift_assignment_warning",
                    "予定勤務segmentが重複しています。",
                    staff=source_item["staff"],
                    work_date=source_item["work_date"],
                    source_assignment=source_item["source_assignment"],
                )
            )
            break
        previous_end = segment["end_offset_minutes"]
    planned_minutes = sum(segment["end_offset_minutes"] - segment["start_offset_minutes"] for segment in work_segments)
    planned_hours = (Decimal(planned_minutes) / Decimal(60)).quantize(HOUR_QUANT, rounding=ROUND_HALF_UP)
    if planned_minutes == 0:
        issues.append(
            _warning(
                "no_planned_worked_minutes",
                "予定勤務分が0分です。",
                staff=source_item["staff"],
                work_date=source_item["work_date"],
                source_assignment=source_item["source_assignment"],
            )
        )
    if source_item["source_warning_count"]:
        issues.append(
            _warning(
                "source_publication_with_warnings",
                "公開シフトにwarningがあります。",
                staff=source_item["staff"],
                work_date=source_item["work_date"],
                source_assignment=source_item["source_assignment"],
            )
        )

    matching_profiles = [
        profile
        for profile in profiles
        if profile.valid_from <= work_date and (profile.valid_to is None or profile.valid_to >= work_date)
    ]
    profile = matching_profiles[0] if matching_profiles else None
    if planned_minutes > 0 and not matching_profiles:
        issues.append(
            _error(
                "compensation_profile_missing",
                "対象日の勤務単価が未設定です。",
                staff=source_item["staff"],
                work_date=source_item["work_date"],
                source_assignment=source_item["source_assignment"],
            )
        )
    if len(matching_profiles) > 1:
        issues.append(
            _error(
                "compensation_profile_overlap",
                "対象日に有効な勤務単価が複数あります。",
                staff=source_item["staff"],
                work_date=source_item["work_date"],
                source_assignment=source_item["source_assignment"],
                relevant_id=str(matching_profiles[0].id),
            )
        )

    planned_base_pay = ZERO_MONEY
    planned_daily_allowance = ZERO_MONEY
    try:
        if profile is not None:
            if profile.employment_type == StaffCompensationProfile.EmploymentType.HOURLY:
                planned_base_pay = _round_yen(
                    (Decimal(planned_minutes) / Decimal(60)) * _decimal(profile.base_hourly_rate)
                )
            elif profile.employment_type == StaffCompensationProfile.EmploymentType.MONTHLY_FIXED:
                issues.append(
                    _warning(
                        "monthly_fixed_not_prorated",
                        "月額固定額は日割りせず月次summaryへ1回だけ加算します。",
                        staff=source_item["staff"],
                        work_date=source_item["work_date"],
                        source_assignment=source_item["source_assignment"],
                        relevant_id=str(profile.id),
                    )
                )
            else:
                issues.append(
                    _warning(
                        "employment_type_other",
                        "その他雇用区分は予定基本原価を自動計算しません。",
                        staff=source_item["staff"],
                        work_date=source_item["work_date"],
                        source_assignment=source_item["source_assignment"],
                        relevant_id=str(profile.id),
                    )
                )
        active_allowances = [
            assignment
            for assignment in allowances
            if assignment.valid_from <= work_date and (assignment.valid_to is None or assignment.valid_to >= work_date)
        ]
        by_code = defaultdict(list)
        for assignment in active_allowances:
            by_code[assignment.code].append(assignment)
        for code, matching_allowances in by_code.items():
            if code in overlap_codes or len(matching_allowances) > 1:
                issues.append(
                    _error(
                        "allowance_assignment_overlap",
                        f"手当コード {code} の有効期間が重複しています。",
                        staff=source_item["staff"],
                        work_date=source_item["work_date"],
                        source_assignment=source_item["source_assignment"],
                        relevant_id=str(matching_allowances[0].id),
                    )
                )
                continue
            assignment = matching_allowances[0]
            amount = ZERO_MONEY
            quantity = ZERO_MONEY
            if assignment.allowance_type == StaffAllowanceAssignment.AllowanceType.PER_WORKED_DAY and planned_minutes:
                amount = _round_yen(_decimal(assignment.amount))
                quantity = Decimal("1")
            elif (
                assignment.allowance_type == StaffAllowanceAssignment.AllowanceType.PER_WORKED_HOUR and planned_minutes
            ):
                amount = _round_yen((Decimal(planned_minutes) / Decimal(60)) * _decimal(assignment.amount))
                quantity = planned_hours
            if quantity:
                planned_daily_allowance += amount
                accumulator = allowance_accumulators.setdefault(
                    str(assignment.id), _allowance_seed(period, assignment, source_item)
                )
                accumulator["quantity"] += quantity
                accumulator["planned_amount"] += amount
    except (InvalidOperation, ArithmeticError) as exc:
        issues.append(
            _error(
                "decimal_calculation_error",
                f"Decimal計算でエラーが発生しました: {exc}",
                staff=source_item["staff"],
                work_date=source_item["work_date"],
                source_assignment=source_item["source_assignment"],
            )
        )

    issues = _dedupe_issues(issues)
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    errors = [issue for issue in issues if issue["severity"] == "error"]
    offsets = valid_segments or source_item["segments"]
    return {
        "budget_period": str(period.id),
        "location": str(period.location_id),
        "location_code": period.location.code,
        "location_name": period.location.name,
        "staff": source_item["staff"],
        "staff_display_name": source_item["staff_display_name"],
        "employee_code": source_item["employee_code"],
        "work_date": source_item["work_date"],
        "monthly_shift_plan": source_item["monthly_shift_plan"],
        "monthly_shift_assignment": source_item["monthly_shift_assignment"],
        "publication": source_item["publication"],
        "publication_assignment": source_item["publication_assignment"],
        "source_assignment": source_item["source_assignment"],
        "plan_source_snapshot": source["plan_source"],
        "staff_compensation_profile": str(profile.id) if profile else None,
        "employment_type_snapshot": profile.employment_type if profile else "",
        "base_hourly_rate_snapshot": profile.base_hourly_rate if profile else None,
        "fixed_monthly_amount_snapshot": profile.fixed_monthly_amount if profile else None,
        "planned_start_offset_minutes": min((item["start_offset_minutes"] for item in offsets), default=None),
        "planned_end_offset_minutes": max((item["end_offset_minutes"] for item in offsets), default=None),
        "planned_worked_minutes": planned_minutes,
        "planned_hours_decimal": planned_hours,
        "planned_base_pay": planned_base_pay,
        "planned_daily_allowance": planned_daily_allowance,
        "planned_total": planned_base_pay + planned_daily_allowance,
        "warning_count": len(warnings),
        "warnings": warnings,
        "error_count": len(errors),
        "errors": errors,
        "issues": issues,
        "segments": source_item["segments"],
    }


def _apply_monthly_planned_costs(
    *,
    period: LaborCostBudgetPeriod,
    records: list[dict],
    allowances_by_staff: dict[str, list[StaffAllowanceAssignment]],
    overlap_codes_by_staff: dict[str, set[str]],
    allowance_accumulators: dict[str, dict],
) -> tuple[dict[str, Decimal], dict[str, Decimal], list[dict]]:
    fixed_pay_by_staff = defaultdict(Decimal)
    fixed_allowance_by_staff = defaultdict(Decimal)
    issues = []
    first_record_by_staff = {}
    for record in records:
        first_record_by_staff.setdefault(record["staff"], record)
        if (
            record["employment_type_snapshot"] == StaffCompensationProfile.EmploymentType.MONTHLY_FIXED
            and record["fixed_monthly_amount_snapshot"] is not None
            and record["staff"] not in fixed_pay_by_staff
        ):
            fixed_pay_by_staff[record["staff"]] = _round_yen(_decimal(record["fixed_monthly_amount_snapshot"]))
    for staff_id, assignments in allowances_by_staff.items():
        first_record = first_record_by_staff.get(staff_id)
        if first_record is None:
            continue
        for assignment in assignments:
            if assignment.code in overlap_codes_by_staff.get(staff_id, set()):
                issues.append(
                    _error(
                        "allowance_assignment_overlap",
                        f"手当コード {assignment.code} の有効期間が重複しています。",
                        staff=staff_id,
                        source_assignment=first_record["source_assignment"],
                        relevant_id=str(assignment.id),
                    )
                )
                continue
            if assignment.allowance_type == StaffAllowanceAssignment.AllowanceType.FIXED_MONTHLY:
                amount = _round_yen(_decimal(assignment.amount))
                fixed_allowance_by_staff[staff_id] += amount
                accumulator = allowance_accumulators.setdefault(
                    str(assignment.id), _allowance_seed(period, assignment, first_record)
                )
                accumulator["quantity"] = Decimal("1")
                accumulator["planned_amount"] = amount
            elif assignment.allowance_type == StaffAllowanceAssignment.AllowanceType.MANUAL:
                accumulator = allowance_accumulators.setdefault(
                    str(assignment.id), _allowance_seed(period, assignment, first_record)
                )
                warning = _warning(
                    "manual_allowance_not_calculated",
                    "手入力手当は予定原価へ自動加算しません。",
                    staff=staff_id,
                    source_assignment=first_record["source_assignment"],
                    relevant_id=str(assignment.id),
                )
                accumulator["warnings"] = [warning]
                accumulator["warning_count"] = 1
                issues.append(warning)
    return fixed_pay_by_staff, fixed_allowance_by_staff, issues


def _actual_record_payload(snapshot) -> dict:
    return {
        "staff": str(snapshot.staff_id),
        "staff_display_name": snapshot.staff_display_name_snapshot,
        "employee_code": snapshot.employee_code_snapshot,
        "work_date": snapshot.work_date.isoformat(),
        "worked_minutes": snapshot.worked_minutes,
        "base_pay": snapshot.base_pay,
        "allowance_total": snapshot.allowance_total,
        "estimated_total": snapshot.estimated_total,
        "warning_count": snapshot.warning_count,
        "warnings": snapshot.warnings if isinstance(snapshot.warnings, list) else [],
        "error_count": snapshot.error_count,
        "errors": snapshot.errors if isinstance(snapshot.errors, list) else [],
    }


def get_current_actual_labor_cost_estimate(period: LaborCostBudgetPeriod) -> dict:
    base_queryset = LaborCostEstimatePeriod.objects.select_related("location").filter(
        location_id=period.location_id,
        year=period.year,
        month=period.month,
        is_active=True,
    )
    estimate_period = (
        base_queryset.filter(status=LaborCostEstimatePeriod.Status.FINALIZED)
        .order_by("-finalized_at", "-updated_at", "id")
        .first()
    )
    comparison_issues = []
    if estimate_period is not None:
        records = [
            _actual_record_payload(item)
            for item in estimate_period.record_snapshots.select_related("staff", "location").order_by(
                "work_date", "staff_id", "id"
            )
        ]
        staff_summaries = [
            {
                "staff": str(item.staff_id),
                "staff_display_name": item.staff_display_name_snapshot,
                "employee_code": item.employee_code_snapshot,
                "worked_minutes": item.worked_minutes,
                "base_pay_total": item.base_pay_total,
                "allowance_total": item.allowance_total,
                "estimated_total": item.estimated_total,
                "warning_count": item.warning_count,
                "error_count": item.error_count,
            }
            for item in estimate_period.staff_summaries.select_related("staff").order_by("staff_id", "id")
        ]
        return {
            "status": "finalized",
            "estimate_period": str(estimate_period.id),
            "content_hash": estimate_period.content_hash,
            "total": sum((item["estimated_total"] for item in staff_summaries), ZERO_MONEY),
            "records": records,
            "staff_summaries": staff_summaries,
            "comparison_issues": comparison_issues,
        }

    estimate_period = (
        base_queryset.filter(
            status__in=[
                LaborCostEstimatePeriod.Status.DRAFT,
                LaborCostEstimatePeriod.Status.REVIEW,
                LaborCostEstimatePeriod.Status.REOPENED,
            ]
        )
        .order_by("-updated_at", "id")
        .first()
    )
    if estimate_period is None:
        comparison_issues.append(_warning("actual_estimate_unavailable", "対象月の実績概算periodがありません。"))
        return {
            "status": "unavailable",
            "estimate_period": None,
            "content_hash": "",
            "total": ZERO_MONEY,
            "records": [],
            "staff_summaries": [],
            "comparison_issues": comparison_issues,
        }

    preview = build_labor_cost_preview(estimate_period)
    comparison_issues.append(_warning("actual_estimate_not_finalized", "実績概算が未確定です。"))
    if estimate_period.status == LaborCostEstimatePeriod.Status.REOPENED:
        comparison_issues.append(_warning("actual_estimate_reopened", "実績概算が再オープンされています。"))
    records = [
        {
            "staff": item["staff"],
            "staff_display_name": item["staff_display_name"],
            "employee_code": item["employee_code"],
            "work_date": item["work_date"],
            "worked_minutes": item["worked_minutes"],
            "base_pay": item["base_pay"],
            "allowance_total": item["allowance_total"],
            "estimated_total": item["estimated_total"],
            "warning_count": item["warning_count"],
            "warnings": item["warnings"],
            "error_count": item["error_count"],
            "errors": item["errors"],
        }
        for item in preview["record_snapshots"]
    ]
    staff_summaries = [
        {
            "staff": item["staff"],
            "staff_display_name": item["staff_display_name_snapshot"],
            "employee_code": item["employee_code_snapshot"],
            "worked_minutes": item["worked_minutes"],
            "base_pay_total": item["base_pay_total"],
            "allowance_total": item["allowance_total"],
            "estimated_total": item["estimated_total"],
            "warning_count": item["warning_count"],
            "error_count": item["error_count"],
        }
        for item in preview["staff_summaries"]
    ]
    return {
        "status": estimate_period.status,
        "estimate_period": str(estimate_period.id),
        "content_hash": preview["content_hash"],
        "total": preview["summary"]["estimated_total"],
        "records": records,
        "staff_summaries": staff_summaries,
        "comparison_issues": comparison_issues,
    }


def _budget_status(total: Decimal, budget: Decimal, warning: Decimal, critical: Decimal) -> tuple[str, Decimal | None]:
    if budget == 0:
        return ("normal" if total == 0 else "critical"), (Decimal("0.00") if total == 0 else None)
    ratio = ((total / budget) * Decimal("100")).quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)
    if ratio >= critical:
        return "critical", ratio
    if ratio >= warning:
        return "warning", ratio
    return "normal", ratio


def build_labor_cost_budget_variance(
    period: LaborCostBudgetPeriod,
    *,
    planned_total: Decimal,
    actual_total: Decimal,
) -> dict:
    budget_amount = _decimal(period.budget_amount)
    planned_total = _decimal(planned_total)
    actual_total = _decimal(actual_total)
    planned_budget_variance = planned_total - budget_amount
    actual_budget_variance = actual_total - budget_amount
    actual_plan_variance = actual_total - planned_total
    planned_status, planned_ratio = _budget_status(
        planned_total,
        budget_amount,
        _decimal(period.warning_threshold_percent),
        _decimal(period.critical_threshold_percent),
    )
    actual_status, actual_ratio = _budget_status(
        actual_total,
        budget_amount,
        _decimal(period.warning_threshold_percent),
        _decimal(period.critical_threshold_percent),
    )
    return {
        "budget_amount": budget_amount,
        "planned_total": planned_total,
        "actual_estimated_total": actual_total,
        "planned_budget_variance_amount": planned_budget_variance,
        "planned_budget_variance_percent": _percent(planned_budget_variance, budget_amount),
        "actual_budget_variance_amount": actual_budget_variance,
        "actual_budget_variance_percent": _percent(actual_budget_variance, budget_amount),
        "actual_plan_variance_amount": actual_plan_variance,
        "actual_plan_variance_percent": _percent(actual_plan_variance, planned_total),
        "planned_budget_ratio_percent": planned_ratio,
        "actual_budget_ratio_percent": actual_ratio,
        "planned_budget_status": planned_status,
        "actual_budget_status": actual_status,
    }


def _build_staff_summaries(records: list[dict], actual: dict, fixed_pay: dict, fixed_allowance: dict) -> list[dict]:
    summaries = {}
    for record in records:
        summary = summaries.setdefault(
            record["staff"],
            {
                "staff": record["staff"],
                "staff_display_name_snapshot": record["staff_display_name"],
                "employee_code_snapshot": record["employee_code"],
                "employment_type_snapshot": record["employment_type_snapshot"],
                "base_hourly_rate_snapshot": record["base_hourly_rate_snapshot"],
                "fixed_monthly_amount_snapshot": record["fixed_monthly_amount_snapshot"],
                "planned_worked_days": 0,
                "planned_worked_minutes": 0,
                "planned_hours_decimal": ZERO_MONEY,
                "planned_hourly_base_pay": ZERO_MONEY,
                "planned_fixed_monthly_pay": ZERO_MONEY,
                "planned_allowance_total": ZERO_MONEY,
                "planned_total": ZERO_MONEY,
                "actual_worked_minutes": 0,
                "actual_base_pay_total": ZERO_MONEY,
                "actual_allowance_total": ZERO_MONEY,
                "actual_estimated_total": ZERO_MONEY,
                "actual_plan_variance_amount": ZERO_MONEY,
                "actual_plan_variance_percent": None,
                "warning_count": 0,
                "error_count": 0,
            },
        )
        if (
            record["employment_type_snapshot"]
            and summary["employment_type_snapshot"] != record["employment_type_snapshot"]
        ):
            summary["employment_type_snapshot"] = "mixed"
            summary["base_hourly_rate_snapshot"] = None
            summary["fixed_monthly_amount_snapshot"] = None
        if record["planned_worked_minutes"]:
            summary["planned_worked_days"] += 1
        summary["planned_worked_minutes"] += record["planned_worked_minutes"]
        summary["planned_hours_decimal"] += record["planned_hours_decimal"]
        summary["planned_hourly_base_pay"] += record["planned_base_pay"]
        summary["planned_allowance_total"] += record["planned_daily_allowance"]
        summary["warning_count"] += record["warning_count"]
        summary["error_count"] += record["error_count"]
    for staff_id, summary in summaries.items():
        summary["planned_fixed_monthly_pay"] = fixed_pay.get(staff_id, ZERO_MONEY)
        summary["planned_allowance_total"] += fixed_allowance.get(staff_id, ZERO_MONEY)
        summary["planned_hours_decimal"] = summary["planned_hours_decimal"].quantize(HOUR_QUANT, rounding=ROUND_HALF_UP)
        summary["planned_total"] = (
            summary["planned_hourly_base_pay"]
            + summary["planned_fixed_monthly_pay"]
            + summary["planned_allowance_total"]
        )
    actual_by_staff = {item["staff"]: item for item in actual["staff_summaries"]}
    for staff_id in sorted(set(summaries) | set(actual_by_staff)):
        actual_summary = actual_by_staff.get(staff_id)
        if staff_id not in summaries and actual_summary:
            summaries[staff_id] = {
                "staff": staff_id,
                "staff_display_name_snapshot": actual_summary["staff_display_name"],
                "employee_code_snapshot": actual_summary["employee_code"],
                "employment_type_snapshot": "",
                "base_hourly_rate_snapshot": None,
                "fixed_monthly_amount_snapshot": None,
                "planned_worked_days": 0,
                "planned_worked_minutes": 0,
                "planned_hours_decimal": ZERO_MONEY,
                "planned_hourly_base_pay": ZERO_MONEY,
                "planned_fixed_monthly_pay": ZERO_MONEY,
                "planned_allowance_total": ZERO_MONEY,
                "planned_total": ZERO_MONEY,
                "actual_worked_minutes": 0,
                "actual_base_pay_total": ZERO_MONEY,
                "actual_allowance_total": ZERO_MONEY,
                "actual_estimated_total": ZERO_MONEY,
                "actual_plan_variance_amount": ZERO_MONEY,
                "actual_plan_variance_percent": None,
                "warning_count": 0,
                "error_count": 0,
            }
        summary = summaries[staff_id]
        if actual_summary:
            summary["actual_worked_minutes"] = actual_summary["worked_minutes"]
            summary["actual_base_pay_total"] = actual_summary["base_pay_total"]
            summary["actual_allowance_total"] = actual_summary["allowance_total"]
            summary["actual_estimated_total"] = actual_summary["estimated_total"]
            summary["warning_count"] += actual_summary["warning_count"]
            summary["error_count"] += actual_summary["error_count"]
        summary["actual_plan_variance_amount"] = summary["actual_estimated_total"] - summary["planned_total"]
        summary["actual_plan_variance_percent"] = _percent(
            summary["actual_plan_variance_amount"], summary["planned_total"]
        )
    return [summaries[key] for key in sorted(summaries)]


def _daily_totals_from_records(records: list[dict], summaries: list[dict], *, actual: bool) -> dict[str, dict]:
    totals = defaultdict(lambda: {"staff": set(), "minutes": 0, "total": ZERO_MONEY, "warning": 0, "error": 0})
    first_date_by_staff = {}
    record_total_by_staff = defaultdict(Decimal)
    for record in records:
        work_date = record["work_date"]
        staff_id = record["staff"]
        first_date_by_staff[staff_id] = min(first_date_by_staff.get(staff_id, work_date), work_date)
        if actual:
            minutes = record["worked_minutes"]
            total = record["estimated_total"]
        else:
            minutes = record["planned_worked_minutes"]
            total = record["planned_total"]
        if minutes:
            totals[work_date]["staff"].add(staff_id)
        totals[work_date]["minutes"] += minutes
        totals[work_date]["total"] += total
        totals[work_date]["warning"] += record.get("warning_count", 0)
        totals[work_date]["error"] += record.get("error_count", 0)
        record_total_by_staff[staff_id] += total
    for summary in summaries:
        staff_id = summary["staff"]
        expected = summary["actual_estimated_total"] if actual else summary["planned_total"]
        residual = expected - record_total_by_staff.get(staff_id, ZERO_MONEY)
        first_date = first_date_by_staff.get(staff_id)
        if residual and first_date:
            totals[first_date]["total"] += residual
    return totals


def _build_daily_summaries(records: list[dict], staff_summaries: list[dict], actual: dict) -> list[dict]:
    planned = _daily_totals_from_records(records, staff_summaries, actual=False)
    actual_totals = _daily_totals_from_records(actual["records"], staff_summaries, actual=True)
    result = []
    for work_date in sorted(set(planned) | set(actual_totals)):
        planned_item = planned[work_date]
        actual_item = actual_totals[work_date]
        variance = actual_item["total"] - planned_item["total"]
        result.append(
            {
                "work_date": work_date,
                "planned_staff_count": len(planned_item["staff"]),
                "planned_worked_minutes": planned_item["minutes"],
                "planned_total": planned_item["total"],
                "actual_staff_count": len(actual_item["staff"]),
                "actual_worked_minutes": actual_item["minutes"],
                "actual_estimated_total": actual_item["total"],
                "actual_plan_variance_amount": variance,
                "actual_plan_variance_percent": _percent(variance, planned_item["total"]),
                "warning_count": planned_item["warning"] + actual_item["warning"],
                "error_count": planned_item["error"] + actual_item["error"],
            }
        )
    return result


def _approval_issue_payload(issue: dict) -> dict:
    return {
        key: issue.get(key, "")
        for key in ["severity", "code", "message", "staff", "work_date", "source_assignment", "relevant_id"]
    }


def build_labor_cost_budget_content_hash(
    period: LaborCostBudgetPeriod,
    *,
    source: dict | None = None,
    records: list[dict] | None = None,
    staff_summaries: list[dict] | None = None,
    allowance_snapshots: list[dict] | None = None,
    approval_issues: list[dict] | None = None,
) -> str:
    if any(value is None for value in [source, records, staff_summaries, allowance_snapshots, approval_issues]):
        return build_labor_cost_budget_preview(period)["content_hash"]
    planned_staff_ids = {item["staff"] for item in records}
    payload = {
        "period": {
            "location": str(period.location_id),
            "year": period.year,
            "month": period.month,
            "budget_amount": _decimal_payload(period.budget_amount),
            "warning_threshold_percent": _decimal_payload(period.warning_threshold_percent),
            "critical_threshold_percent": _decimal_payload(period.critical_threshold_percent),
        },
        "source": {
            "plan_source": source["plan_source"],
            "monthly_shift_plan": str(source["plan"].id) if source["plan"] else "",
            "publication": str(source["publication"].id) if source["publication"] else "",
            "source_content_hash": source["source_content_hash"],
        },
        "records": [
            {
                "location": item["location"],
                "staff": item["staff"],
                "work_date": item["work_date"],
                "monthly_shift_assignment": item["monthly_shift_assignment"] or "",
                "publication_assignment": item["publication_assignment"] or "",
                "segments": [
                    {
                        "id": segment["id"],
                        "source_segment": segment["source_segment"],
                        "start": segment["start_offset_minutes"],
                        "end": segment["end_offset_minutes"],
                        "is_break": segment["is_break"],
                    }
                    for segment in sorted(item["segments"], key=lambda value: value["id"])
                ],
                "compensation_profile": item["staff_compensation_profile"] or "",
                "employment_type": item["employment_type_snapshot"],
                "base_hourly_rate": _decimal_payload(item["base_hourly_rate_snapshot"]),
                "fixed_monthly_amount": _decimal_payload(item["fixed_monthly_amount_snapshot"]),
                "planned_worked_minutes": item["planned_worked_minutes"],
                "planned_hours_decimal": _decimal_payload(item["planned_hours_decimal"]),
                "planned_base_pay": _decimal_payload(item["planned_base_pay"]),
                "planned_daily_allowance": _decimal_payload(item["planned_daily_allowance"]),
                "planned_total": _decimal_payload(item["planned_total"]),
            }
            for item in sorted(records, key=lambda value: (value["location"], value["staff"], value["work_date"]))
        ],
        "staff_summaries": [
            {
                "staff": item["staff"],
                "employment_type": item["employment_type_snapshot"],
                "base_hourly_rate": _decimal_payload(item["base_hourly_rate_snapshot"]),
                "fixed_monthly_amount": _decimal_payload(item["fixed_monthly_amount_snapshot"]),
                "planned_worked_days": item["planned_worked_days"],
                "planned_worked_minutes": item["planned_worked_minutes"],
                "planned_hours_decimal": _decimal_payload(item["planned_hours_decimal"]),
                "planned_hourly_base_pay": _decimal_payload(item["planned_hourly_base_pay"]),
                "planned_fixed_monthly_pay": _decimal_payload(item["planned_fixed_monthly_pay"]),
                "planned_allowance_total": _decimal_payload(item["planned_allowance_total"]),
                "planned_total": _decimal_payload(item["planned_total"]),
            }
            for item in sorted(staff_summaries, key=lambda value: value["staff"])
            if item["staff"] in planned_staff_ids
        ],
        "allowances": [
            {
                "staff": item["staff"],
                "allowance_assignment": item["allowance_assignment"] or "",
                "code": item["code_snapshot"],
                "type": item["allowance_type_snapshot"],
                "amount": _decimal_payload(item["amount_snapshot"]),
                "quantity": _decimal_payload(item["quantity"]),
                "planned_amount": _decimal_payload(item["planned_amount"]),
            }
            for item in sorted(
                allowance_snapshots,
                key=lambda value: (value["staff"], value["code_snapshot"], value["allowance_assignment"] or ""),
            )
        ],
        "approval_issues": [_approval_issue_payload(issue) for issue in _dedupe_issues(approval_issues)],
    }
    return _stable_sha256(payload)


def build_labor_cost_budget_validation_fingerprint(
    period: LaborCostBudgetPeriod,
    *,
    approval_issues: list[dict] | None = None,
) -> str:
    if approval_issues is None:
        return build_labor_cost_budget_preview(period)["validation_fingerprint"]
    return _stable_sha256(
        {
            "period": str(period.id),
            "location": str(period.location_id),
            "year": period.year,
            "month": period.month,
            "approval_issues": [_approval_issue_payload(issue) for issue in _dedupe_issues(approval_issues)],
        }
    )


def _threshold_issues(variance: dict) -> tuple[list[dict], list[dict]]:
    approval_issues = []
    comparison_issues = []
    planned_status = variance["planned_budget_status"]
    actual_status = variance["actual_budget_status"]
    if planned_status == "warning":
        approval_issues.append(_warning("planned_budget_warning_threshold", "予定原価が予算警戒閾値に達しています。"))
    if planned_status == "critical":
        approval_issues.append(_warning("planned_budget_critical_threshold", "予定原価が予算超過閾値に達しています。"))
    if actual_status == "warning":
        comparison_issues.append(_warning("actual_budget_warning_threshold", "実績概算が予算警戒閾値に達しています。"))
    if actual_status == "critical":
        comparison_issues.append(_warning("actual_budget_critical_threshold", "実績概算が予算超過閾値に達しています。"))
    return approval_issues, comparison_issues


def build_labor_cost_budget_preview(period: LaborCostBudgetPeriod, *, lock_masters: bool = False) -> dict:
    if period.pk:
        period = LaborCostBudgetPeriod.objects.select_related(
            "location", "source_monthly_shift_plan", "source_publication", "created_by", "updated_by"
        ).get(pk=period.pk)
    source = get_labor_cost_plan_source(period, lock=lock_masters)
    approval_issues = []
    if period.budget_amount is None or period.budget_amount < 0:
        approval_issues.append(_error("budget_amount_invalid", "予算額は0以上で指定してください。"))
    if source["plan_source"] == "unavailable":
        approval_issues.append(_error("shift_source_unavailable", "対象月のシフトがありません。"))
    elif source["plan_source"] == "draft":
        approval_issues.append(_error("draft_shift_source", "draftシフトはpreviewのみ可能です。"))

    source_items = [
        _normalized_source_assignment(source, assignment)
        for assignment in source["assignments"]
        if assignment.work_date.year == period.year and assignment.work_date.month == period.month
    ]
    source_items.sort(key=lambda value: (value["staff"], value["work_date"], value["source_assignment"]))
    staff_ids = {item["staff"] for item in source_items}
    start_date, end_date = _month_range(period.year, period.month)
    profiles = _labor_profiles_for_period(
        location=period.location,
        staff_ids=staff_ids,
        start_date=start_date,
        end_date=end_date,
        lock_masters=lock_masters,
    )
    allowances = _labor_allowances_for_period(
        location=period.location,
        staff_ids=staff_ids,
        start_date=start_date,
        end_date=end_date,
        lock_masters=lock_masters,
    )
    profiles_by_staff = defaultdict(list)
    allowances_by_staff = defaultdict(list)
    for profile in profiles:
        profiles_by_staff[str(profile.staff_id)].append(profile)
    for allowance in allowances:
        allowances_by_staff[str(allowance.staff_id)].append(allowance)
    overlap_codes_by_staff = {
        staff_id: _allowance_overlap_codes(items) for staff_id, items in allowances_by_staff.items()
    }
    allowance_accumulators = {}
    records = [
        _planned_record_item(
            period=period,
            source=source,
            source_item=item,
            profiles=profiles_by_staff.get(item["staff"], []),
            allowances=allowances_by_staff.get(item["staff"], []),
            overlap_codes=overlap_codes_by_staff.get(item["staff"], set()),
            allowance_accumulators=allowance_accumulators,
        )
        for item in source_items
    ]
    if source["plan_source"] != "unavailable" and not any(item["planned_worked_minutes"] for item in records):
        approval_issues.append(_warning("no_planned_worked_minutes", "対象月の予定勤務分が0分です。"))
    fixed_pay, fixed_allowance, monthly_issues = _apply_monthly_planned_costs(
        period=period,
        records=records,
        allowances_by_staff=allowances_by_staff,
        overlap_codes_by_staff=overlap_codes_by_staff,
        allowance_accumulators=allowance_accumulators,
    )
    approval_issues.extend(monthly_issues)
    approval_issues.extend(issue for record in records for issue in record["issues"])
    allowance_snapshots = sorted(
        allowance_accumulators.values(),
        key=lambda value: (value["staff"], value["code_snapshot"], value["allowance_assignment"] or ""),
    )
    actual = get_current_actual_labor_cost_estimate(period)
    staff_summaries = _build_staff_summaries(records, actual, fixed_pay, fixed_allowance)
    daily_summaries = _build_daily_summaries(records, staff_summaries, actual)
    planned_total = sum((item["planned_total"] for item in staff_summaries), ZERO_MONEY)
    variance = build_labor_cost_budget_variance(
        period,
        planned_total=planned_total,
        actual_total=actual["total"],
    )
    threshold_approval, threshold_comparison = _threshold_issues(variance)
    approval_issues.extend(threshold_approval)
    comparison_issues = actual["comparison_issues"] + threshold_comparison
    approval_issues = _dedupe_issues(approval_issues)
    comparison_issues = _dedupe_issues(comparison_issues)
    content_hash = build_labor_cost_budget_content_hash(
        period,
        source=source,
        records=records,
        staff_summaries=staff_summaries,
        allowance_snapshots=allowance_snapshots,
        approval_issues=approval_issues,
    )
    validation_fingerprint = build_labor_cost_budget_validation_fingerprint(
        period,
        approval_issues=approval_issues,
    )
    approval_warning_count = sum(issue["severity"] == "warning" for issue in approval_issues)
    approval_error_count = sum(issue["severity"] == "error" for issue in approval_issues)
    summary = variance | {
        "plan_record_count": len(records),
        "staff_summary_count": len(staff_summaries),
        "daily_summary_count": len(daily_summaries),
        "allowance_snapshot_count": len(allowance_snapshots),
        "planned_worked_minutes": sum(item["planned_worked_minutes"] for item in records),
        "approval_warning_count": approval_warning_count,
        "approval_error_count": approval_error_count,
        "comparison_warning_count": sum(issue["severity"] == "warning" for issue in comparison_issues),
        "comparison_error_count": sum(issue["severity"] == "error" for issue in comparison_issues),
    }
    return {
        "period": str(period.id),
        "location": str(period.location_id),
        "location_name": period.location.name,
        "location_code": period.location.code,
        "year": period.year,
        "month": period.month,
        "status": period.status,
        "plan_source": source["plan_source"],
        "source_monthly_shift_plan": str(source["plan"].id) if source["plan"] else None,
        "source_publication": str(source["publication"].id) if source["publication"] else None,
        "source_content_hash": source["source_content_hash"],
        "actual_source_status": actual["status"],
        "actual_estimate_period": actual["estimate_period"],
        "actual_content_hash": actual["content_hash"],
        "content_hash": content_hash,
        "validation_fingerprint": validation_fingerprint,
        "approval_issues": approval_issues,
        "comparison_issues": comparison_issues,
        "summary": summary,
        "plan_records": records,
        "staff_summaries": staff_summaries,
        "daily_summaries": daily_summaries,
        "allowance_snapshots": allowance_snapshots,
        "actual_records": actual["records"],
        "can_approve": source["plan_source"] in {"published", "confirmed"} and approval_error_count == 0,
    }


def build_labor_cost_budget_plan_record_snapshots(
    period: LaborCostBudgetPeriod, *, preview: dict | None = None
) -> list[LaborCostBudgetPlanRecordSnapshot]:
    preview = preview or build_labor_cost_budget_preview(period)
    return [
        LaborCostBudgetPlanRecordSnapshot(
            budget_period=period,
            location_id=item["location"],
            staff_id=item["staff"],
            work_date=date.fromisoformat(item["work_date"]),
            monthly_shift_plan_id=item["monthly_shift_plan"],
            monthly_shift_assignment_id=item["monthly_shift_assignment"],
            publication_id=item["publication"],
            publication_assignment_id=item["publication_assignment"],
            location_code_snapshot=item["location_code"],
            location_name_snapshot=item["location_name"],
            staff_display_name_snapshot=item["staff_display_name"],
            employee_code_snapshot=item["employee_code"],
            plan_source_snapshot=item["plan_source_snapshot"],
            employment_type_snapshot=item["employment_type_snapshot"],
            base_hourly_rate_snapshot=item["base_hourly_rate_snapshot"],
            fixed_monthly_amount_snapshot=item["fixed_monthly_amount_snapshot"],
            planned_start_offset_minutes=item["planned_start_offset_minutes"],
            planned_end_offset_minutes=item["planned_end_offset_minutes"],
            planned_worked_minutes=item["planned_worked_minutes"],
            planned_hours_decimal=item["planned_hours_decimal"],
            planned_base_pay=item["planned_base_pay"],
            planned_daily_allowance=item["planned_daily_allowance"],
            planned_total=item["planned_total"],
            warning_count=item["warning_count"],
            warnings=item["warnings"],
            error_count=item["error_count"],
            errors=item["errors"],
        )
        for item in preview["plan_records"]
    ]


def build_labor_cost_budget_staff_summaries(
    period: LaborCostBudgetPeriod, *, preview: dict | None = None
) -> list[LaborCostBudgetStaffSummary]:
    preview = preview or build_labor_cost_budget_preview(period)
    return [
        LaborCostBudgetStaffSummary(
            budget_period=period,
            staff_id=item["staff"],
            staff_display_name_snapshot=item["staff_display_name_snapshot"],
            employee_code_snapshot=item["employee_code_snapshot"],
            employment_type_snapshot=item["employment_type_snapshot"],
            base_hourly_rate_snapshot=item["base_hourly_rate_snapshot"],
            fixed_monthly_amount_snapshot=item["fixed_monthly_amount_snapshot"],
            planned_worked_days=item["planned_worked_days"],
            planned_worked_minutes=item["planned_worked_minutes"],
            planned_hours_decimal=item["planned_hours_decimal"],
            planned_hourly_base_pay=item["planned_hourly_base_pay"],
            planned_fixed_monthly_pay=item["planned_fixed_monthly_pay"],
            planned_allowance_total=item["planned_allowance_total"],
            planned_total=item["planned_total"],
            actual_worked_minutes=item["actual_worked_minutes"],
            actual_base_pay_total=item["actual_base_pay_total"],
            actual_allowance_total=item["actual_allowance_total"],
            actual_estimated_total=item["actual_estimated_total"],
            actual_plan_variance_amount=item["actual_plan_variance_amount"],
            actual_plan_variance_percent=item["actual_plan_variance_percent"],
            warning_count=item["warning_count"],
            error_count=item["error_count"],
        )
        for item in preview["staff_summaries"]
    ]


def build_labor_cost_budget_daily_summaries(
    period: LaborCostBudgetPeriod, *, preview: dict | None = None
) -> list[LaborCostBudgetDailySummary]:
    preview = preview or build_labor_cost_budget_preview(period)
    return [
        LaborCostBudgetDailySummary(
            budget_period=period,
            work_date=date.fromisoformat(item["work_date"]),
            planned_staff_count=item["planned_staff_count"],
            planned_worked_minutes=item["planned_worked_minutes"],
            planned_total=item["planned_total"],
            actual_staff_count=item["actual_staff_count"],
            actual_worked_minutes=item["actual_worked_minutes"],
            actual_estimated_total=item["actual_estimated_total"],
            actual_plan_variance_amount=item["actual_plan_variance_amount"],
            actual_plan_variance_percent=item["actual_plan_variance_percent"],
            warning_count=item["warning_count"],
            error_count=item["error_count"],
        )
        for item in preview["daily_summaries"]
    ]


def build_labor_cost_budget_allowance_snapshots(
    period: LaborCostBudgetPeriod, *, preview: dict | None = None
) -> list[LaborCostBudgetAllowanceSnapshot]:
    preview = preview or build_labor_cost_budget_preview(period)
    return [
        LaborCostBudgetAllowanceSnapshot(
            budget_period=period,
            staff_id=item["staff"],
            staff_display_name_snapshot=item["staff_display_name_snapshot"],
            employee_code_snapshot=item["employee_code_snapshot"],
            allowance_assignment_id=item["allowance_assignment"],
            code_snapshot=item["code_snapshot"],
            name_snapshot=item["name_snapshot"],
            allowance_type_snapshot=item["allowance_type_snapshot"],
            amount_snapshot=item["amount_snapshot"],
            quantity=item["quantity"],
            planned_amount=item["planned_amount"],
            warning_count=item["warning_count"],
            warnings=item["warnings"],
        )
        for item in preview["allowance_snapshots"]
    ]


def approve_labor_cost_budget(
    *,
    period: LaborCostBudgetPeriod,
    actor: User,
    acknowledge_warnings: bool,
    validation_fingerprint: str,
    manager_note: str = "",
) -> tuple[LaborCostBudgetPeriod, dict]:
    with transaction.atomic():
        period = (
            LaborCostBudgetPeriod.objects.select_for_update(of=("self",))
            .select_related("location", "source_monthly_shift_plan", "source_publication")
            .get(pk=period.pk)
        )
        if period.status == LaborCostBudgetPeriod.Status.ARCHIVED or not period.is_active:
            raise DRFValidationError({"status": "アーカイブ済みの予算periodは操作できません。"})
        if period.status not in {
            LaborCostBudgetPeriod.Status.DRAFT,
            LaborCostBudgetPeriod.Status.REVIEW,
            LaborCostBudgetPeriod.Status.REOPENED,
        }:
            raise DRFValidationError({"status": "draft、review、reopenedの予算periodのみ承認できます。"})
        preview = build_labor_cost_budget_preview(period, lock_masters=True)
        if preview["plan_source"] not in {"published", "confirmed"}:
            raise DRFValidationError({"source": "公開済みまたは確定済みシフトが必要です。"})
        if not validation_fingerprint or validation_fingerprint != preview["validation_fingerprint"]:
            raise DRFValidationError({"validation_fingerprint": "最新のpreview結果と一致しません。"})
        if preview["summary"]["approval_error_count"]:
            raise DRFValidationError({"approval_issues": "errorがあるため予算を承認できません。"})
        if preview["summary"]["approval_warning_count"] and not acknowledge_warnings:
            raise DRFValidationError({"acknowledge_warnings": "warningがあるため確認チェックが必要です。"})

        period.plan_record_snapshots.all().delete()
        period.staff_summaries.all().delete()
        period.daily_summaries.all().delete()
        period.allowance_snapshots.all().delete()
        LaborCostBudgetPlanRecordSnapshot.objects.bulk_create(
            build_labor_cost_budget_plan_record_snapshots(period, preview=preview)
        )
        LaborCostBudgetStaffSummary.objects.bulk_create(
            build_labor_cost_budget_staff_summaries(period, preview=preview)
        )
        LaborCostBudgetDailySummary.objects.bulk_create(
            build_labor_cost_budget_daily_summaries(period, preview=preview)
        )
        LaborCostBudgetAllowanceSnapshot.objects.bulk_create(
            build_labor_cost_budget_allowance_snapshots(period, preview=preview)
        )
        if (
            period.plan_record_snapshots.count() != len(preview["plan_records"])
            or period.staff_summaries.count() != len(preview["staff_summaries"])
            or period.daily_summaries.count() != len(preview["daily_summaries"])
            or period.allowance_snapshots.count() != len(preview["allowance_snapshots"])
        ):
            raise DRFValidationError({"snapshot_integrity_error": "予定原価snapshotの保存件数が一致しません。"})
        period.source_monthly_shift_plan_id = preview["source_monthly_shift_plan"]
        period.source_publication_id = preview["source_publication"]
        period.status = LaborCostBudgetPeriod.Status.APPROVED
        period.content_hash = preview["content_hash"]
        period.validation_fingerprint = preview["validation_fingerprint"]
        period.approved_at = timezone.now()
        period.approved_by = actor
        period.updated_by = actor
        if manager_note:
            period.description = manager_note
        period.full_clean()
        period.save()
        return period, preview


def reopen_labor_cost_budget(
    *, period: LaborCostBudgetPeriod, actor: User, manager_note: str = ""
) -> LaborCostBudgetPeriod:
    with transaction.atomic():
        period = (
            LaborCostBudgetPeriod.objects.select_for_update(of=("self",))
            .select_related("location", "source_monthly_shift_plan", "source_publication")
            .get(pk=period.pk)
        )
        if period.status != LaborCostBudgetPeriod.Status.APPROVED:
            raise DRFValidationError({"status": "承認済みの予算periodのみ再オープンできます。"})
        period.status = LaborCostBudgetPeriod.Status.REOPENED
        period.reopened_at = timezone.now()
        period.reopened_by = actor
        period.updated_by = actor
        if manager_note:
            period.description = manager_note
        period.full_clean()
        period.save()
        return period


def archive_labor_cost_budget(
    *, period: LaborCostBudgetPeriod, actor: User, manager_note: str = ""
) -> LaborCostBudgetPeriod:
    with transaction.atomic():
        period = (
            LaborCostBudgetPeriod.objects.select_for_update(of=("self",))
            .select_related("location", "source_monthly_shift_plan", "source_publication")
            .get(pk=period.pk)
        )
        if period.status == LaborCostBudgetPeriod.Status.APPROVED:
            raise DRFValidationError({"status": "承認済みの予算periodは再オープンしてからアーカイブしてください。"})
        if period.status == LaborCostBudgetPeriod.Status.ARCHIVED or not period.is_active:
            raise DRFValidationError({"status": "既にアーカイブ済みです。"})
        period.status = LaborCostBudgetPeriod.Status.ARCHIVED
        period.is_active = False
        period.updated_by = actor
        if manager_note:
            period.description = manager_note
        period.full_clean()
        period.save()
        return period


def _approved_plan_payload(period: LaborCostBudgetPeriod) -> dict:
    records = [
        {
            "budget_period": str(period.id),
            "location": str(item.location_id),
            "location_code": item.location_code_snapshot,
            "location_name": item.location_name_snapshot,
            "staff": str(item.staff_id),
            "staff_display_name": item.staff_display_name_snapshot,
            "employee_code": item.employee_code_snapshot,
            "work_date": item.work_date.isoformat(),
            "monthly_shift_plan": str(item.monthly_shift_plan_id) if item.monthly_shift_plan_id else None,
            "monthly_shift_assignment": (
                str(item.monthly_shift_assignment_id) if item.monthly_shift_assignment_id else None
            ),
            "publication": str(item.publication_id) if item.publication_id else None,
            "publication_assignment": str(item.publication_assignment_id) if item.publication_assignment_id else None,
            "plan_source_snapshot": item.plan_source_snapshot,
            "employment_type_snapshot": item.employment_type_snapshot,
            "base_hourly_rate_snapshot": item.base_hourly_rate_snapshot,
            "fixed_monthly_amount_snapshot": item.fixed_monthly_amount_snapshot,
            "planned_start_offset_minutes": item.planned_start_offset_minutes,
            "planned_end_offset_minutes": item.planned_end_offset_minutes,
            "planned_worked_minutes": item.planned_worked_minutes,
            "planned_hours_decimal": item.planned_hours_decimal,
            "planned_base_pay": item.planned_base_pay,
            "planned_daily_allowance": item.planned_daily_allowance,
            "planned_total": item.planned_total,
            "warning_count": item.warning_count,
            "warnings": item.warnings if isinstance(item.warnings, list) else [],
            "error_count": item.error_count,
            "errors": item.errors if isinstance(item.errors, list) else [],
        }
        for item in period.plan_record_snapshots.select_related(
            "location",
            "staff",
            "monthly_shift_plan",
            "monthly_shift_assignment",
            "publication",
            "publication_assignment",
        ).order_by("work_date", "staff_id", "id")
    ]
    staff_summaries = [
        {
            "staff": str(item.staff_id),
            "staff_display_name_snapshot": item.staff_display_name_snapshot,
            "employee_code_snapshot": item.employee_code_snapshot,
            "employment_type_snapshot": item.employment_type_snapshot,
            "base_hourly_rate_snapshot": item.base_hourly_rate_snapshot,
            "fixed_monthly_amount_snapshot": item.fixed_monthly_amount_snapshot,
            "planned_worked_days": item.planned_worked_days,
            "planned_worked_minutes": item.planned_worked_minutes,
            "planned_hours_decimal": item.planned_hours_decimal,
            "planned_hourly_base_pay": item.planned_hourly_base_pay,
            "planned_fixed_monthly_pay": item.planned_fixed_monthly_pay,
            "planned_allowance_total": item.planned_allowance_total,
            "planned_total": item.planned_total,
            "actual_worked_minutes": item.actual_worked_minutes,
            "actual_base_pay_total": item.actual_base_pay_total,
            "actual_allowance_total": item.actual_allowance_total,
            "actual_estimated_total": item.actual_estimated_total,
            "actual_plan_variance_amount": item.actual_plan_variance_amount,
            "actual_plan_variance_percent": item.actual_plan_variance_percent,
            "warning_count": item.warning_count,
            "error_count": item.error_count,
        }
        for item in period.staff_summaries.select_related("staff").order_by("staff_id", "id")
    ]
    daily_summaries = [
        {
            "work_date": item.work_date.isoformat(),
            "planned_staff_count": item.planned_staff_count,
            "planned_worked_minutes": item.planned_worked_minutes,
            "planned_total": item.planned_total,
            "actual_staff_count": item.actual_staff_count,
            "actual_worked_minutes": item.actual_worked_minutes,
            "actual_estimated_total": item.actual_estimated_total,
            "actual_plan_variance_amount": item.actual_plan_variance_amount,
            "actual_plan_variance_percent": item.actual_plan_variance_percent,
            "warning_count": item.warning_count,
            "error_count": item.error_count,
        }
        for item in period.daily_summaries.order_by("work_date", "id")
    ]
    allowances = [
        {
            "staff": str(item.staff_id),
            "staff_display_name_snapshot": item.staff_display_name_snapshot,
            "employee_code_snapshot": item.employee_code_snapshot,
            "allowance_assignment": str(item.allowance_assignment_id) if item.allowance_assignment_id else None,
            "code_snapshot": item.code_snapshot,
            "name_snapshot": item.name_snapshot,
            "allowance_type_snapshot": item.allowance_type_snapshot,
            "amount_snapshot": item.amount_snapshot,
            "quantity": item.quantity,
            "planned_amount": item.planned_amount,
            "warning_count": item.warning_count,
            "warnings": item.warnings if isinstance(item.warnings, list) else [],
        }
        for item in period.allowance_snapshots.select_related("staff", "allowance_assignment").order_by(
            "staff_id", "code_snapshot", "id"
        )
    ]
    return {
        "records": records,
        "staff_summaries": staff_summaries,
        "daily_summaries": daily_summaries,
        "allowance_snapshots": allowances,
    }


def _merge_current_actual(staff_summaries: list[dict], actual: dict) -> list[dict]:
    merged = {item["staff"]: dict(item) for item in staff_summaries}
    actual_by_staff = {item["staff"]: item for item in actual["staff_summaries"]}
    for staff_id in sorted(set(merged) | set(actual_by_staff)):
        actual_item = actual_by_staff.get(staff_id)
        if staff_id not in merged and actual_item:
            merged[staff_id] = {
                "staff": staff_id,
                "staff_display_name_snapshot": actual_item["staff_display_name"],
                "employee_code_snapshot": actual_item["employee_code"],
                "employment_type_snapshot": "",
                "base_hourly_rate_snapshot": None,
                "fixed_monthly_amount_snapshot": None,
                "planned_worked_days": 0,
                "planned_worked_minutes": 0,
                "planned_hours_decimal": ZERO_MONEY,
                "planned_hourly_base_pay": ZERO_MONEY,
                "planned_fixed_monthly_pay": ZERO_MONEY,
                "planned_allowance_total": ZERO_MONEY,
                "planned_total": ZERO_MONEY,
                "warning_count": 0,
                "error_count": 0,
            }
        item = merged[staff_id]
        item["actual_worked_minutes"] = actual_item["worked_minutes"] if actual_item else 0
        item["actual_base_pay_total"] = actual_item["base_pay_total"] if actual_item else ZERO_MONEY
        item["actual_allowance_total"] = actual_item["allowance_total"] if actual_item else ZERO_MONEY
        item["actual_estimated_total"] = actual_item["estimated_total"] if actual_item else ZERO_MONEY
        item["actual_plan_variance_amount"] = item["actual_estimated_total"] - item["planned_total"]
        item["actual_plan_variance_percent"] = _percent(item["actual_plan_variance_amount"], item["planned_total"])
    return [merged[key] for key in sorted(merged)]


def _merge_current_actual_daily(saved_daily: list[dict], staff_summaries: list[dict], actual: dict) -> list[dict]:
    planned = {item["work_date"]: item for item in saved_daily}
    actual_totals = _daily_totals_from_records(actual["records"], staff_summaries, actual=True)
    result = []
    for work_date in sorted(set(planned) | set(actual_totals)):
        planned_item = planned.get(work_date)
        actual_item = actual_totals[work_date]
        planned_total = planned_item["planned_total"] if planned_item else ZERO_MONEY
        actual_total = actual_item["total"]
        variance = actual_total - planned_total
        result.append(
            {
                "work_date": work_date,
                "planned_staff_count": planned_item["planned_staff_count"] if planned_item else 0,
                "planned_worked_minutes": planned_item["planned_worked_minutes"] if planned_item else 0,
                "planned_total": planned_total,
                "actual_staff_count": len(actual_item["staff"]),
                "actual_worked_minutes": actual_item["minutes"],
                "actual_estimated_total": actual_total,
                "actual_plan_variance_amount": variance,
                "actual_plan_variance_percent": _percent(variance, planned_total),
                "warning_count": (planned_item["warning_count"] if planned_item else 0) + actual_item["warning"],
                "error_count": (planned_item["error_count"] if planned_item else 0) + actual_item["error"],
            }
        )
    return result


def get_labor_cost_budget_variance(period: LaborCostBudgetPeriod) -> dict:
    period = LaborCostBudgetPeriod.objects.select_related(
        "location", "source_monthly_shift_plan", "source_publication"
    ).get(pk=period.pk)
    if period.status != LaborCostBudgetPeriod.Status.APPROVED:
        return build_labor_cost_budget_preview(period)
    planned = _approved_plan_payload(period)
    actual = get_current_actual_labor_cost_estimate(period)
    staff_summaries = _merge_current_actual(planned["staff_summaries"], actual)
    daily_summaries = _merge_current_actual_daily(planned["daily_summaries"], staff_summaries, actual)
    planned_total = sum((item["planned_total"] for item in planned["staff_summaries"]), ZERO_MONEY)
    summary = build_labor_cost_budget_variance(period, planned_total=planned_total, actual_total=actual["total"])
    _, threshold_comparison = _threshold_issues(summary)
    comparison_issues = _dedupe_issues(actual["comparison_issues"] + threshold_comparison)
    return {
        "period": str(period.id),
        "location": str(period.location_id),
        "location_name": period.location.name,
        "location_code": period.location.code,
        "year": period.year,
        "month": period.month,
        "status": period.status,
        "plan_source": (
            "published"
            if period.source_publication_id
            else "confirmed"
            if period.source_monthly_shift_plan_id
            else "unavailable"
        ),
        "source_monthly_shift_plan": (
            str(period.source_monthly_shift_plan_id) if period.source_monthly_shift_plan_id else None
        ),
        "source_publication": str(period.source_publication_id) if period.source_publication_id else None,
        "actual_source_status": actual["status"],
        "actual_estimate_period": actual["estimate_period"],
        "actual_content_hash": actual["content_hash"],
        "content_hash": period.content_hash,
        "validation_fingerprint": period.validation_fingerprint,
        "approval_issues": [],
        "comparison_issues": comparison_issues,
        "summary": summary
        | {
            "plan_record_count": len(planned["records"]),
            "staff_summary_count": len(staff_summaries),
            "daily_summary_count": len(daily_summaries),
            "allowance_snapshot_count": len(planned["allowance_snapshots"]),
        },
        "plan_records": planned["records"],
        "staff_summaries": staff_summaries,
        "daily_summaries": daily_summaries,
        "allowance_snapshots": planned["allowance_snapshots"],
        "actual_records": actual["records"],
        "can_approve": False,
    }


def _issue_codes(issues: list[dict]) -> str:
    return " ".join(sorted({issue.get("code", "") for issue in issues if issue.get("code")}))


def export_labor_cost_budget_csv(period: LaborCostBudgetPeriod) -> tuple[bytes, str, dict]:
    payload = get_labor_cost_budget_variance(period)
    planned = {(item["staff"], item["work_date"]): item for item in payload["plan_records"]}
    actual = {(item["staff"], item["work_date"]): item for item in payload["actual_records"]}
    rows = []
    for key in sorted(set(planned) | set(actual)):
        planned_item = planned.get(key, {})
        actual_item = actual.get(key, {})
        warnings = planned_item.get("warnings", []) + actual_item.get("warnings", [])
        errors = planned_item.get("errors", []) + actual_item.get("errors", [])
        rows.append(
            [
                payload["location_name"],
                f"{period.year}-{period.month:02d}",
                "承認済み" if period.status == LaborCostBudgetPeriod.Status.APPROVED else "未承認予算",
                payload["plan_source"],
                payload["actual_source_status"],
                planned_item.get("employee_code", actual_item.get("employee_code", "")),
                planned_item.get("staff_display_name", actual_item.get("staff_display_name", "")),
                key[1],
                planned_item.get("planned_worked_minutes", 0),
                _decimal_payload(planned_item.get("planned_hours_decimal", ZERO_MONEY)),
                _decimal_payload(planned_item.get("planned_base_pay", ZERO_MONEY)),
                _decimal_payload(planned_item.get("planned_daily_allowance", ZERO_MONEY)),
                _decimal_payload(planned_item.get("planned_total", ZERO_MONEY)),
                actual_item.get("worked_minutes", 0),
                _decimal_payload(actual_item.get("base_pay", ZERO_MONEY)),
                _decimal_payload(actual_item.get("allowance_total", ZERO_MONEY)),
                _decimal_payload(actual_item.get("estimated_total", ZERO_MONEY)),
                _decimal_payload(
                    _decimal(actual_item.get("estimated_total", ZERO_MONEY))
                    - _decimal(planned_item.get("planned_total", ZERO_MONEY))
                ),
                _decimal_payload(period.budget_amount),
                _decimal_payload(payload["summary"]["planned_budget_variance_amount"]),
                _decimal_payload(payload["summary"]["actual_budget_variance_amount"]),
                len(warnings),
                _issue_codes(warnings),
                len(errors),
                _issue_codes(errors),
            ]
        )
    header = [
        "拠点",
        "年月",
        "予算状態",
        "予定原価状態",
        "実績概算状態",
        "スタッフコード",
        "スタッフ名",
        "勤務日",
        "予定勤務分",
        "予定勤務時間",
        "予定基本原価",
        "予定手当",
        "予定原価合計",
        "実績勤務分",
        "実績基本概算",
        "実績手当概算",
        "実績概算合計",
        "予定実績差異",
        "予算額",
        "予定予算差異",
        "実績予算差異",
        "警告数",
        "警告コード",
        "エラー数",
        "エラーコード",
    ]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    filename = f"labor_cost_budget_{period.location.code}_{period.year}_{period.month:02d}.csv"
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    return (
        data,
        filename,
        {
            "plan_record_snapshot_count": len(payload["plan_records"]),
            "staff_summary_count": len(payload["staff_summaries"]),
            "daily_summary_count": len(payload["daily_summaries"]),
            "allowance_snapshot_count": len(payload["allowance_snapshots"]),
            "warning_count": sum(row[21] for row in rows),
            "error_count": sum(row[23] for row in rows),
        },
    )
