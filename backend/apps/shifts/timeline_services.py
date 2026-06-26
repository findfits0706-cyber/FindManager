from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from django.db.models import Prefetch, Q
from rest_framework.serializers import ValidationError

from apps.accounts.models import User
from apps.operations.models import StaffLocation

from .models import MonthlyShiftAssignment, MonthlyShiftPlan, MonthlyShiftSegment
from .services import build_capability_lookup, month_dates, monthly_assignment_warning_count

WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]


def _parse_date_param(params, name: str) -> date:
    value = params.get(name)
    if not value:
        raise ValidationError({name: "This query parameter is required."})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({name: "Invalid ISO date."}) from exc


def _parse_bool_param(params, name: str, default: bool) -> bool:
    value = params.get(name)
    if value is None or value == "":
        return default
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValidationError({name: "Use true or false."})


def _parse_uuid_param(params, name: str) -> str | None:
    value = params.get(name)
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValidationError({name: "Invalid UUID."}) from exc


def _timeline_dates(plan: MonthlyShiftPlan, params) -> list[date]:
    requested_from = _parse_date_param(params, "date_from")
    requested_to = _parse_date_param(params, "date_to")
    if requested_from > requested_to:
        raise ValidationError({"date_to": "date_to must be on or after date_from."})
    if (requested_to - requested_from).days + 1 > 7:
        raise ValidationError({"date_to": "Timeline range cannot exceed 7 days."})

    plan_days = month_dates(plan.year, plan.month)
    plan_start, plan_end = plan_days[0], plan_days[-1]
    if requested_to < plan_start or requested_from > plan_end:
        raise ValidationError({"date_from": "Timeline range must overlap the monthly shift plan month."})

    effective_from = max(requested_from, plan_start)
    effective_to = min(requested_to, plan_end)
    return [effective_from + timedelta(days=offset) for offset in range((effective_to - effective_from).days + 1)]


def _assign_lanes(segments: list[MonthlyShiftSegment]) -> dict[str, tuple[int, int]]:
    ordered = sorted(
        segments,
        key=lambda item: (item.start_offset_minutes, item.end_offset_minutes, item.display_order, str(item.id)),
    )
    lane_ends: list[int] = []
    lane_by_id: dict[str, int] = {}
    for segment in ordered:
        lane = None
        for index, end in enumerate(lane_ends):
            if end <= segment.start_offset_minutes:
                lane = index
                break
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(segment.end_offset_minutes)
        else:
            lane_ends[lane] = segment.end_offset_minutes
        lane_by_id[str(segment.id)] = lane
    lane_count = max(len(lane_ends), 1)
    return {segment_id: (lane, lane_count) for segment_id, lane in lane_by_id.items()}


def _display_range(segments: list[MonthlyShiftSegment]) -> dict:
    if not segments:
        return {
            "earliest_start_offset": None,
            "latest_end_offset": None,
            "suggested_start_offset": 360,
            "suggested_end_offset": 1440,
        }
    earliest = min(segment.start_offset_minutes for segment in segments)
    latest = max(segment.end_offset_minutes for segment in segments)
    suggested_start = max(0, min(360, (earliest // 60) * 60))
    suggested_end = min(2880, max(1440, ((latest + 59) // 60) * 60))
    return {
        "earliest_start_offset": earliest,
        "latest_end_offset": latest,
        "suggested_start_offset": suggested_start,
        "suggested_end_offset": suggested_end,
    }


def _segment_payload(segment: MonthlyShiftSegment, lane: int, lane_count: int) -> dict:
    return {
        "id": str(segment.id),
        "work_type": str(segment.work_type_id),
        "work_area": str(segment.work_area_id) if segment.work_area_id else None,
        "work_type_name": segment.work_type_name_snapshot,
        "work_type_short_name": segment.work_type_short_name_snapshot,
        "work_type_color_key": segment.work_type_color_key_snapshot,
        "work_type_is_break": segment.work_type_is_break_snapshot,
        "work_area_name": segment.work_area_name_snapshot,
        "start_offset_minutes": segment.start_offset_minutes,
        "end_offset_minutes": segment.end_offset_minutes,
        "duration_minutes": segment.duration_minutes,
        "display_order": segment.display_order,
        "notes": segment.notes,
        "lane": lane,
        "lane_count": lane_count,
    }


def build_timeline_response(plan: MonthlyShiftPlan, params) -> dict:
    dates = _timeline_dates(plan, params)
    start_date, end_date = dates[0], dates[-1]
    date_keys = [item.isoformat() for item in dates]
    staff_search = params.get("staff_search", "").strip()
    assigned_only = _parse_bool_param(params, "assigned_only", True)
    include_breaks = _parse_bool_param(params, "include_breaks", True)
    work_type_id = _parse_uuid_param(params, "work_type")
    work_area_id = _parse_uuid_param(params, "work_area")

    visible_segment_queryset = MonthlyShiftSegment.objects.filter(is_active=True).select_related("work_type")
    if work_type_id:
        visible_segment_queryset = visible_segment_queryset.filter(work_type_id=work_type_id)
    if work_area_id:
        visible_segment_queryset = visible_segment_queryset.filter(work_area_id=work_area_id)
    if not include_breaks:
        visible_segment_queryset = visible_segment_queryset.filter(work_type_is_break_snapshot=False)

    assignments = list(
        MonthlyShiftAssignment.objects.filter(
            monthly_shift_plan=plan,
            is_active=True,
            work_date__gte=start_date,
            work_date__lte=end_date,
        )
        .select_related("staff")
        .prefetch_related(
            Prefetch(
                "segments",
                queryset=visible_segment_queryset.order_by("start_offset_minutes", "display_order"),
                to_attr="timeline_segments",
            ),
            Prefetch(
                "segments",
                queryset=MonthlyShiftSegment.objects.filter(is_active=True)
                .select_related("work_type")
                .order_by("start_offset_minutes", "display_order"),
                to_attr="all_active_segments",
            ),
        )
        .order_by("work_date", "display_order", "staff__employee_code", "staff__display_name")
    )
    assignments = [assignment for assignment in assignments if assignment.timeline_segments]
    assignment_staff_ids = {assignment.staff_id for assignment in assignments}

    staff_ids = set(assignment_staff_ids)
    if not assigned_only:
        staff_ids.update(
            StaffLocation.objects.filter(
                location=plan.location,
                is_active=True,
                location__is_active=True,
                valid_from__lte=end_date,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start_date))
            .values_list("staff_id", flat=True)
        )

    staff_queryset = User.objects.filter(id__in=staff_ids)
    if staff_search:
        staff_queryset = staff_queryset.filter(
            Q(display_name__icontains=staff_search)
            | Q(username__icontains=staff_search)
            | Q(employee_code__icontains=staff_search)
        )
    staff_list = list(staff_queryset.order_by("employee_code", "display_name", "username"))
    staff_id_set = {staff.id for staff in staff_list}

    assignments = [assignment for assignment in assignments if assignment.staff_id in staff_id_set]
    capability_lookup = build_capability_lookup(
        assignments=assignments,
        location=plan.location,
        start_date=start_date,
        end_date=end_date,
        segments_attr="all_active_segments",
    )

    assignments_by_staff_date = {
        (assignment.staff_id, assignment.work_date.isoformat()): assignment for assignment in assignments
    }
    visible_segments = [segment for assignment in assignments for segment in assignment.timeline_segments]
    range_data = _display_range(visible_segments)
    legend_seen = set()
    legend = []
    summary = {
        "staff_count": len(staff_list),
        "assignment_count": 0,
        "segment_count": 0,
        "work_minutes": 0,
        "break_minutes": 0,
    }

    rows = []
    for staff in staff_list:
        days = {}
        for date_key in date_keys:
            assignment = assignments_by_staff_date.get((staff.id, date_key))
            if assignment is None:
                days[date_key] = {"assignment": None, "segments": []}
                continue
            segments = list(assignment.timeline_segments)
            lanes = _assign_lanes(segments)
            segment_payloads = []
            for segment in sorted(
                segments, key=lambda item: (item.start_offset_minutes, item.display_order, str(item.id))
            ):
                lane, lane_count = lanes[str(segment.id)]
                segment_payloads.append(_segment_payload(segment, lane, lane_count))
                key = (
                    str(segment.work_type_id),
                    segment.work_type_name_snapshot,
                    segment.work_type_color_key_snapshot,
                    segment.work_type_is_break_snapshot,
                )
                if key not in legend_seen:
                    legend_seen.add(key)
                    legend.append(
                        {
                            "work_type": str(segment.work_type_id),
                            "name": segment.work_type_name_snapshot,
                            "short_name": segment.work_type_short_name_snapshot,
                            "color_key": segment.work_type_color_key_snapshot,
                            "is_break": segment.work_type_is_break_snapshot,
                        }
                    )
                summary["segment_count"] += 1
                if segment.work_type_is_break_snapshot:
                    summary["break_minutes"] += segment.duration_minutes
                else:
                    summary["work_minutes"] += segment.duration_minutes
            summary["assignment_count"] += 1
            days[date_key] = {
                "assignment": {
                    "id": str(assignment.id),
                    "pattern_name": assignment.pattern_name_snapshot,
                    "pattern_short_name": assignment.pattern_short_name_snapshot,
                    "source_type": assignment.source_type,
                    "is_customized": assignment.is_customized,
                    "notes": assignment.notes,
                    "warning_count": monthly_assignment_warning_count(
                        assignment,
                        capability_lookup,
                        segments_attr="all_active_segments",
                    ),
                },
                "segments": segment_payloads,
            }
        rows.append(
            {
                "staff": str(staff.id),
                "staff_display_name": staff.display_name,
                "employee_code": staff.employee_code,
                "days": days,
            }
        )

    return {
        "plan": {
            "id": str(plan.id),
            "location": str(plan.location_id),
            "location_name": plan.location.name,
            "year": plan.year,
            "month": plan.month,
            "name": plan.name,
        },
        "range": {
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "day_count": len(dates),
            **range_data,
        },
        "dates": [
            {
                "date": item.isoformat(),
                "day": item.day,
                "weekday": item.weekday(),
                "weekday_label": WEEKDAY_LABELS[item.weekday()],
                "is_saturday": item.weekday() == 5,
                "is_sunday": item.weekday() == 6,
            }
            for item in dates
        ],
        "rows": rows,
        "legend": legend,
        "summary": summary,
    }
