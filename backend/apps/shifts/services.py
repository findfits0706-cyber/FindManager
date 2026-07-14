import calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Max, Q, Value, When
from django.utils import timezone
from rest_framework.serializers import ValidationError as DRFValidationError

from apps.accounts.constants import ROLE_SHIFT_MANAGER, ROLE_SUPERVISOR, ROLE_SYSTEM_ADMIN
from apps.accounts.models import User
from apps.accounts.services import create_audit_event
from apps.operations.models import Location, StaffCapability, StaffLocation, WorkArea, WorkType, WorkTypeAvailability

from .models import (
    AttendanceCorrectionRequest,
    AttendanceEvent,
    AttendanceRecord,
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftPublication,
    MonthlyShiftPublicationAssignment,
    MonthlyShiftPublicationSegment,
    MonthlyShiftSegment,
    ShiftChangeRequest,
    ShiftPattern,
    ShiftPatternSegment,
    ShiftRequestItem,
    ShiftRequestPeriod,
    ShiftRequestSubmission,
    WeeklyShiftTemplate,
    WeeklyShiftTemplateEntry,
)

MANAGE_ROLES = {ROLE_SYSTEM_ADMIN, ROLE_SHIFT_MANAGER}
VIEW_ROLES = MANAGE_ROLES | {ROLE_SUPERVISOR}
IMMUTABLE_LOCATION_MESSAGE = "拠点は作成後変更できません。別拠点用に複製してください。"
DUPLICATE_CHILD_ID_MESSAGE = "同じ子要素IDが複数回指定されています。"


IMMUTABLE_ASSIGNMENT_CELL_MESSAGE = (
    "月間表・日付・スタッフは作成後変更できません。勤務を解除して新しく作成してください。"
)
INACTIVE_MONTHLY_PLAN_MESSAGE = "無効な月間表には書き込みできません。"
MONTHLY_PLAN_EDIT_LOCK_MESSAGE = "確定または公開済みの月間シフトは編集できません。確定解除してから編集してください。"
MONTHLY_PLAN_CONFIRM_WARNING_MESSAGE = "警告があるため確定できません。警告を確認してから実行してください。"
MONTHLY_PLAN_PUBLISH_WARNING_MESSAGE = "警告があるため公開できません。警告を確認してから実行してください。"
MONTHLY_PLAN_STALE_HASH_MESSAGE = "確定後に月間シフトの内容が変更されています。確定解除して再確定してください。"
MONTHLY_PLAN_ACTIVE_PUBLICATION_MESSAGE = "公開中の月間シフトがあるため操作できません。"
DEFAULT_INTEGRITY_MESSAGE = "重複または不正なデータです。"
SHIFT_PATTERN_DUPLICATE_MESSAGE = "同じ拠点・コードの勤務パターンが既に存在します。"
WEEKLY_TEMPLATE_DUPLICATE_MESSAGE = "同じ拠点・コードの週間テンプレートが既に存在します。"
MONTHLY_PLAN_DUPLICATE_MESSAGE = "同じ拠点・年月の月間表が既に存在します。"
MONTHLY_ASSIGNMENT_DUPLICATE_MESSAGE = "同じスタッフ・日付の勤務が既に登録されています。"


def user_has_any_role(user: User, roles: set[str]) -> bool:
    return user.is_authenticated and any(user.has_role(role) for role in roles)


def can_manage_shifts(user: User) -> bool:
    return user_has_any_role(user, MANAGE_ROLES)


def can_view_shifts(user: User) -> bool:
    return user_has_any_role(user, VIEW_ROLES)


EVENT_MAP = {
    "shift_pattern": {
        "create": "shift_pattern_created",
        "update": "shift_pattern_updated",
        "deactivate": "shift_pattern_deactivated",
        "reactivate": "shift_pattern_reactivated",
        "duplicate": "shift_pattern_duplicated",
    },
    "weekly_shift_template": {
        "create": "weekly_shift_template_created",
        "update": "weekly_shift_template_updated",
        "deactivate": "weekly_shift_template_deactivated",
        "reactivate": "weekly_shift_template_reactivated",
        "duplicate": "weekly_shift_template_duplicated",
    },
    "monthly_shift_plan": {
        "create": "monthly_shift_plan_created",
        "update": "monthly_shift_plan_updated",
        "deactivate": "monthly_shift_plan_deactivated",
        "reactivate": "monthly_shift_plan_reactivated",
        "confirm": "monthly_shift_plan_confirmed",
        "reopen": "monthly_shift_plan_reopened",
        "publish": "monthly_shift_publication_created",
        "withdraw": "monthly_shift_publication_withdrawn",
    },
    "monthly_shift_assignment": {
        "create": "monthly_shift_assignment_created",
        "update": "monthly_shift_assignment_updated",
        "deactivate": "monthly_shift_assignment_deactivated",
        "reactivate": "monthly_shift_assignment_reactivated",
    },
    "monthly_shift_template": {
        "apply": "monthly_shift_template_applied",
    },
    "shift_request_period": {
        "create": "shift_request_period_created",
        "update": "shift_request_period_updated",
        "open": "shift_request_period_opened",
        "close": "shift_request_period_closed",
        "reopen": "shift_request_period_reopened",
        "archive": "shift_request_period_archived",
    },
    "shift_request_submission": {
        "save": "shift_request_submission_saved",
        "submit": "shift_request_submission_submitted",
        "unsubmit": "shift_request_submission_unsubmitted",
        "return": "shift_request_submission_returned",
        "lock": "shift_request_submission_locked",
        "unlock": "shift_request_submission_unlocked",
    },
    "shift_change_request": {
        "create": "shift_change_request_created",
        "update": "shift_change_request_updated",
        "submit": "shift_change_request_submitted",
        "cancel": "shift_change_request_cancelled",
        "approve": "shift_change_request_approved",
        "reject": "shift_change_request_rejected",
        "apply": "shift_change_request_applied",
        "close": "shift_change_request_closed",
    },
    "attendance_record": {
        "create": "attendance_record_created",
        "clock_in": "attendance_clock_in",
        "break_start": "attendance_break_start",
        "break_end": "attendance_break_end",
        "clock_out": "attendance_clock_out",
        "manual_adjust": "attendance_manual_adjusted",
        "confirm": "attendance_confirmed",
        "unconfirm": "attendance_unconfirmed",
        "void": "attendance_voided",
    },
    "attendance_correction": {
        "create": "attendance_correction_created",
        "update": "attendance_correction_updated",
        "submit": "attendance_correction_submitted",
        "cancel": "attendance_correction_cancelled",
        "approve": "attendance_correction_approved",
        "reject": "attendance_correction_rejected",
        "apply": "attendance_correction_applied",
    },
}


def _drf_validation(
    exc: DjangoValidationError | IntegrityError,
    *,
    integrity_message: str = DEFAULT_INTEGRITY_MESSAGE,
):
    if isinstance(exc, DjangoValidationError):
        return DRFValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        )
    return DRFValidationError({"non_field_errors": [integrity_message]})


def record_shift_event(*, entity: str, action: str, actor: User, request, metadata: dict):
    create_audit_event(
        event_type=EVENT_MAP[entity][action],
        actor=actor,
        request=request,
        metadata=metadata,
    )


def shift_pattern_metadata(pattern: ShiftPattern, source_id=None) -> dict:
    data = {
        "id": str(pattern.id),
        "location_id": str(pattern.location_id),
        "code": pattern.code,
        "segment_count": pattern.segments.filter(is_active=True).count(),
    }
    if source_id:
        data["source_id"] = str(source_id)
        data["new_id"] = str(pattern.id)
    return data


def weekly_template_metadata(template: WeeklyShiftTemplate, source_id=None) -> dict:
    active_entries = template.entries.filter(is_active=True)
    data = {
        "id": str(template.id),
        "location_id": str(template.location_id),
        "code": template.code,
        "entry_count": active_entries.count(),
        "staff_count": active_entries.values("staff_id").distinct().count(),
    }
    if source_id:
        data["source_id"] = str(source_id)
        data["new_id"] = str(template.id)
    return data


def _validate_pattern_segments(pattern: ShiftPattern, segments: list[ShiftPatternSegment]):
    active_segments = [segment for segment in segments if segment.is_active]
    if pattern.is_active and not active_segments:
        raise DRFValidationError({"segments": "Active shift patterns require at least one active segment."})
    if not pattern.location.is_active:
        raise DRFValidationError({"location": "Inactive locations cannot be assigned."})

    if active_segments:
        first_start = min(segment.start_offset_minutes for segment in active_segments)
        last_end = max(segment.end_offset_minutes for segment in active_segments)
        if last_end - first_start > 1440:
            raise DRFValidationError({"segments": "A shift pattern cannot span more than 24 hours."})

    for segment in active_segments:
        try:
            segment.full_clean(exclude=["shift_pattern"] if not segment.shift_pattern_id else None)
        except DjangoValidationError as exc:
            raise _drf_validation(exc) from exc
        if (
            not WorkTypeAvailability.objects.filter(
                work_type_id=segment.work_type_id,
                location_id=pattern.location_id,
                is_active=True,
                work_type__is_active=True,
                location__is_active=True,
            )
            .filter(Q(work_area__isnull=True) | Q(work_area_id=segment.work_area_id))
            .exists()
        ):
            raise DRFValidationError({"segments": "Work type availability is missing for a segment."})

    ordered = sorted(active_segments, key=lambda item: (item.start_offset_minutes, item.end_offset_minutes))
    for index, current in enumerate(ordered):
        for other in ordered[index + 1 :]:
            if current.end_offset_minutes <= other.start_offset_minutes:
                break
            if current.work_type.is_break or other.work_type.is_break:
                raise DRFValidationError({"segments": "Break segments cannot overlap other segments."})
            if not (current.work_type.can_overlap or other.work_type.can_overlap):
                raise DRFValidationError({"segments": "Shift pattern segments cannot overlap."})


def _segment_from_payload(pattern: ShiftPattern, payload: dict, existing: ShiftPatternSegment | None = None):
    segment = existing or ShiftPatternSegment(shift_pattern=pattern)
    for field in ["work_type", "work_area", "start_offset_minutes", "end_offset_minutes", "display_order", "notes"]:
        if field not in payload:
            continue
        value = payload[field]
        if field == "work_type":
            value = value if isinstance(value, WorkType) else WorkType.objects.get(pk=value)
        if field == "work_area":
            value = value if isinstance(value, WorkArea) or value is None else WorkArea.objects.get(pk=value)
        setattr(segment, field, value)
    segment.shift_pattern = pattern
    return segment


def _validate_immutable_location(instance, validated_data: dict):
    if instance is None or "location" not in validated_data:
        return
    incoming = validated_data["location"]
    incoming_id = getattr(incoming, "id", incoming)
    if str(incoming_id) != str(instance.location_id):
        raise DRFValidationError({"location": IMMUTABLE_LOCATION_MESSAGE})


def save_shift_pattern(*, instance: ShiftPattern | None, validated_data: dict, segments_data: list[dict] | None):
    try:
        with transaction.atomic():
            _validate_immutable_location(instance, validated_data)
            pattern = instance or ShiftPattern()
            for field, value in validated_data.items():
                setattr(pattern, field, value)
            if instance is None:
                pattern.is_active = True
            pattern.full_clean()
            pattern.save()

            if segments_data is not None:
                existing = {str(item.id): item for item in pattern.segments.select_related("work_type", "work_area")}
                seen_ids = set()
                validation_segments = []
                save_segments = []
                for payload in segments_data:
                    child_id = str(payload.get("id")) if payload.get("id") else None
                    if child_id:
                        if child_id in seen_ids:
                            raise DRFValidationError({"segments": DUPLICATE_CHILD_ID_MESSAGE})
                        if child_id not in existing:
                            raise DRFValidationError({"segments": "Segment ID does not belong to this shift pattern."})
                        segment = _segment_from_payload(pattern, payload, existing[child_id])
                        seen_ids.add(child_id)
                    else:
                        segment = _segment_from_payload(pattern, payload)
                    segment.is_active = True
                    validation_segments.append(segment)
                    save_segments.append(segment)
                for child_id, segment in existing.items():
                    if child_id in seen_ids:
                        continue
                    if segment.is_active:
                        segment.is_active = False
                        validation_segments.append(segment)
                        save_segments.append(segment)
                _validate_pattern_segments(pattern, validation_segments)
                for segment in save_segments:
                    if segment.is_active:
                        segment.full_clean()
                    segment.save()
            else:
                _validate_pattern_segments(pattern, list(pattern.segments.select_related("work_type", "work_area")))
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc, integrity_message=SHIFT_PATTERN_DUPLICATE_MESSAGE) from exc
    return pattern


def duplicate_shift_pattern(source: ShiftPattern, *, code: str, name: str, short_name: str):
    try:
        with transaction.atomic():
            pattern = ShiftPattern.objects.create(
                location=source.location,
                code=code,
                name=name,
                short_name=short_name,
                description=source.description,
                display_order=source.display_order,
                is_active=True,
            )
            for segment in source.segments.filter(is_active=True).order_by("start_offset_minutes", "display_order"):
                ShiftPatternSegment.objects.create(
                    shift_pattern=pattern,
                    work_type=segment.work_type,
                    work_area=segment.work_area,
                    start_offset_minutes=segment.start_offset_minutes,
                    end_offset_minutes=segment.end_offset_minutes,
                    display_order=segment.display_order,
                    notes=segment.notes,
                )
            _validate_pattern_segments(pattern, list(pattern.segments.select_related("work_type", "work_area")))
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc, integrity_message=SHIFT_PATTERN_DUPLICATE_MESSAGE) from exc
    return pattern


def _validate_weekly_entries(template: WeeklyShiftTemplate, entries: list[WeeklyShiftTemplateEntry]):
    if not template.location.is_active:
        raise DRFValidationError({"location": "Inactive locations cannot be assigned."})
    seen = set()
    for entry in [item for item in entries if item.is_active]:
        try:
            entry.full_clean(exclude=["weekly_shift_template"] if not entry.weekly_shift_template_id else None)
        except DjangoValidationError as exc:
            raise _drf_validation(exc, integrity_message=WEEKLY_TEMPLATE_DUPLICATE_MESSAGE) from exc
        key = (entry.weekday, entry.staff_id)
        if key in seen:
            raise DRFValidationError({"entries": "A staff member cannot have multiple active patterns on one weekday."})
        seen.add(key)
        if entry.shift_pattern.location_id != template.location_id:
            raise DRFValidationError({"entries": "Entry shift pattern location must match template location."})
        if not StaffLocation.objects.filter(
            staff_id=entry.staff_id,
            location_id=template.location_id,
            is_active=True,
            staff__is_active=True,
            location__is_active=True,
        ).exists():
            raise DRFValidationError({"entries": "Entry staff must belong to the template location."})


def _entry_from_payload(template: WeeklyShiftTemplate, payload: dict, existing: WeeklyShiftTemplateEntry | None = None):
    entry = existing or WeeklyShiftTemplateEntry(weekly_shift_template=template)
    for field in ["weekday", "staff", "shift_pattern", "notes", "display_order"]:
        if field not in payload:
            continue
        value = payload[field]
        if field == "staff":
            value = value if isinstance(value, User) else User.objects.get(pk=value)
        if field == "shift_pattern":
            value = value if isinstance(value, ShiftPattern) else ShiftPattern.objects.get(pk=value)
        setattr(entry, field, value)
    entry.weekly_shift_template = template
    return entry


def save_weekly_template(
    *,
    instance: WeeklyShiftTemplate | None,
    validated_data: dict,
    entries_data: list[dict] | None,
):
    try:
        with transaction.atomic():
            _validate_immutable_location(instance, validated_data)
            template = instance or WeeklyShiftTemplate()
            for field, value in validated_data.items():
                setattr(template, field, value)
            if instance is None:
                template.is_active = True
            template.full_clean()
            template.save()

            if entries_data is not None:
                existing = {str(item.id): item for item in template.entries.select_related("staff", "shift_pattern")}
                seen_ids = set()
                validation_entries = []
                save_entries = []
                for payload in entries_data:
                    child_id = str(payload.get("id")) if payload.get("id") else None
                    if child_id:
                        if child_id in seen_ids:
                            raise DRFValidationError({"entries": DUPLICATE_CHILD_ID_MESSAGE})
                        if child_id not in existing:
                            raise DRFValidationError({"entries": "Entry ID does not belong to this weekly template."})
                        entry = _entry_from_payload(template, payload, existing[child_id])
                        seen_ids.add(child_id)
                    else:
                        entry = _entry_from_payload(template, payload)
                    entry.is_active = True
                    validation_entries.append(entry)
                    save_entries.append(entry)
                for child_id, entry in existing.items():
                    if child_id in seen_ids:
                        continue
                    if entry.is_active:
                        entry.is_active = False
                        validation_entries.append(entry)
                        save_entries.append(entry)
                _validate_weekly_entries(template, validation_entries)
                for entry in save_entries:
                    if entry.is_active:
                        entry.full_clean()
                    entry.save()
            else:
                _validate_weekly_entries(template, list(template.entries.select_related("staff", "shift_pattern")))
    except (DjangoValidationError, IntegrityError, User.DoesNotExist, ShiftPattern.DoesNotExist) as exc:
        if isinstance(exc, (DjangoValidationError, IntegrityError)):
            raise _drf_validation(exc, integrity_message=WEEKLY_TEMPLATE_DUPLICATE_MESSAGE) from exc
        raise DRFValidationError({"entries": "Invalid entry reference."}) from exc
    return template


def duplicate_weekly_template(source: WeeklyShiftTemplate, *, code: str, name: str):
    try:
        with transaction.atomic():
            template = WeeklyShiftTemplate.objects.create(
                location=source.location,
                code=code,
                name=name,
                description=source.description,
                display_order=source.display_order,
                is_active=True,
            )
            for entry in source.entries.filter(is_active=True).order_by("staff__display_name", "weekday"):
                WeeklyShiftTemplateEntry.objects.create(
                    weekly_shift_template=template,
                    weekday=entry.weekday,
                    staff=entry.staff,
                    shift_pattern=entry.shift_pattern,
                    notes=entry.notes,
                    display_order=entry.display_order,
                )
            _validate_weekly_entries(template, list(template.entries.select_related("staff", "shift_pattern")))
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc, integrity_message=WEEKLY_TEMPLATE_DUPLICATE_MESSAGE) from exc
    return template


def validate_and_reactivate_pattern(pattern: ShiftPattern):
    original_is_active = pattern.is_active
    try:
        with transaction.atomic():
            pattern.is_active = True
            _validate_pattern_segments(pattern, list(pattern.segments.select_related("work_type", "work_area")))
            pattern.full_clean()
            pattern.save(update_fields=["is_active", "updated_at"])
    except (DjangoValidationError, IntegrityError) as exc:
        pattern.is_active = original_is_active
        raise _drf_validation(exc, integrity_message=SHIFT_PATTERN_DUPLICATE_MESSAGE) from exc
    except DRFValidationError:
        pattern.is_active = original_is_active
        raise
    return pattern


def validate_and_reactivate_template(template: WeeklyShiftTemplate):
    original_is_active = template.is_active
    try:
        with transaction.atomic():
            template.is_active = True
            _validate_weekly_entries(template, list(template.entries.select_related("staff", "shift_pattern")))
            template.full_clean()
            template.save(update_fields=["is_active", "updated_at"])
    except (DjangoValidationError, IntegrityError) as exc:
        template.is_active = original_is_active
        raise _drf_validation(exc, integrity_message=WEEKLY_TEMPLATE_DUPLICATE_MESSAGE) from exc
    except DRFValidationError:
        template.is_active = original_is_active
        raise
    return template


def deactivate_instance(instance):
    if isinstance(instance, ShiftPattern):
        reference_count = WeeklyShiftTemplateEntry.objects.filter(
            shift_pattern=instance,
            is_active=True,
            weekly_shift_template__is_active=True,
        ).count()
        if reference_count:
            raise DRFValidationError(
                {"shift_pattern": f"有効な週間テンプレートから参照されています（{reference_count}件）。"}
            )
    instance.is_active = False
    instance.save(update_fields=["is_active", "updated_at"])


def seed_shifts(dev_users: dict[str, User]) -> None:
    location = Location.objects.get(code="main")
    gym_area = WorkArea.objects.get(location=location, code="gym")
    front_area = WorkArea.objects.get(location=location, code="front")
    gym_work = WorkType.objects.get(code="gym_duty")
    front_work = WorkType.objects.get(code="front_duty")
    break_work = WorkType.objects.get(code="break")

    availability, created = WorkTypeAvailability.objects.get_or_create(
        work_type=break_work,
        location=location,
        work_area=None,
    )
    if created:
        availability.is_active = True
        availability.save(update_fields=["is_active", "updated_at"])

    seeds = [
        (
            "gym_early",
            "ジム早番",
            "早番",
            [
                (gym_work, gym_area, 510, 720, 10),
                (break_work, None, 720, 780, 20),
                (front_work, front_area, 780, 900, 30),
                (gym_work, gym_area, 900, 1050, 40),
            ],
        ),
        (
            "gym_late",
            "ジム遅番",
            "遅番",
            [
                (front_work, front_area, 780, 960, 10),
                (break_work, None, 960, 1020, 20),
                (gym_work, gym_area, 1020, 1260, 30),
            ],
        ),
        (
            "front_early",
            "フロント早番",
            "フロント早",
            [
                (front_work, front_area, 510, 720, 10),
                (break_work, None, 720, 780, 20),
                (front_work, front_area, 780, 1020, 30),
            ],
        ),
    ]
    patterns = {}
    for index, (code, name, short_name, segments) in enumerate(seeds, start=1):
        pattern, created = ShiftPattern.objects.get_or_create(
            location=location,
            code=code,
            defaults={
                "name": name,
                "short_name": short_name,
                "description": "開発用サンプル",
                "display_order": index * 10,
                "is_active": True,
            },
        )
        if not created:
            pattern.name = name
            pattern.short_name = short_name
            pattern.description = "開発用サンプル"
            pattern.display_order = index * 10
            pattern.save(update_fields=["name", "short_name", "description", "display_order", "updated_at"])
        patterns[code] = pattern

        for work_type, work_area, start, end, order in segments:
            segment = (
                ShiftPatternSegment.objects.filter(
                    shift_pattern=pattern,
                    work_type=work_type,
                    work_area=work_area,
                    start_offset_minutes=start,
                    end_offset_minutes=end,
                )
                .order_by("-is_active", "created_at")
                .first()
            )
            if segment is None:
                ShiftPatternSegment.objects.create(
                    shift_pattern=pattern,
                    work_type=work_type,
                    work_area=work_area,
                    start_offset_minutes=start,
                    end_offset_minutes=end,
                    display_order=order,
                    notes="",
                    is_active=True,
                )
            else:
                segment.display_order = order
                segment.notes = ""
                segment.save(update_fields=["display_order", "notes", "updated_at"])

    template, created = WeeklyShiftTemplate.objects.get_or_create(
        location=location,
        code="standard_week",
        defaults={
            "name": "標準週間テンプレート",
            "description": "開発用サンプル",
            "display_order": 10,
            "is_active": True,
        },
    )
    if not created:
        template.name = "標準週間テンプレート"
        template.description = "開発用サンプル"
        template.display_order = 10
        template.save(update_fields=["name", "description", "display_order", "updated_at"])

    assignment_seed = {
        "system_admin": [
            patterns["gym_early"],
            patterns["gym_early"],
            None,
            patterns["gym_late"],
            patterns["gym_late"],
        ],
        "shift_manager": [patterns["gym_late"], None, patterns["front_early"], patterns["front_early"], None],
        "staff": [patterns["front_early"], patterns["gym_early"], patterns["gym_early"], None, patterns["gym_late"]],
    }
    for role, weekly_patterns in assignment_seed.items():
        staff = dev_users[role]
        for weekday, pattern in enumerate(weekly_patterns):
            if pattern is None:
                continue
            entry = (
                WeeklyShiftTemplateEntry.objects.filter(
                    weekly_shift_template=template,
                    staff=staff,
                    weekday=weekday,
                )
                .order_by("-is_active", "created_at")
                .first()
            )
            if entry is None:
                WeeklyShiftTemplateEntry.objects.create(
                    weekly_shift_template=template,
                    staff=staff,
                    weekday=weekday,
                    shift_pattern=pattern,
                    notes="",
                    display_order=weekday * 10,
                    is_active=True,
                )
            else:
                entry.shift_pattern = pattern
                entry.notes = ""
                entry.display_order = weekday * 10
                entry.save(update_fields=["shift_pattern", "notes", "display_order", "updated_at"])


IMMUTABLE_PLAN_FIELDS_MESSAGE = "拠点・年月は作成後変更できません。新しい月間表を作成してください。"
MONTHLY_SEGMENT_DUPLICATE_MESSAGE = "同じセグメントIDが複数回指定されています。"
ASSISTED_WARNING = "補助付き対応の業務が含まれています。"
TRAINEE_WARNING = "研修中対応の業務が含まれています。"


@dataclass
class GenerationCandidate:
    work_date: date
    entry: WeeklyShiftTemplateEntry
    pattern: ShiftPattern
    action: str
    existing: MonthlyShiftAssignment | None
    issues: list[dict]


def month_dates(year: int, month: int) -> list[date]:
    return [date(year, month, day) for day in range(1, calendar.monthrange(year, month)[1] + 1)]


def _plan_bounds(plan: MonthlyShiftPlan) -> tuple[date, date]:
    days = month_dates(plan.year, plan.month)
    return days[0], days[-1]


def _active_on(queryset, target_date: date):
    return queryset.filter(
        valid_from__lte=target_date,
        is_active=True,
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=target_date))


def ensure_active_monthly_plan(plan: MonthlyShiftPlan):
    if not plan.is_active:
        raise DRFValidationError({"monthly_shift_plan": INACTIVE_MONTHLY_PLAN_MESSAGE})


def ensure_monthly_plan_editable(plan: MonthlyShiftPlan):
    ensure_active_monthly_plan(plan)
    if plan.workflow_status != MonthlyShiftPlan.WorkflowStatus.DRAFT:
        raise DRFValidationError({"monthly_shift_plan": MONTHLY_PLAN_EDIT_LOCK_MESSAGE})


def _ordered_capabilities(queryset, location: Location):
    return queryset.annotate(
        location_priority=Case(
            When(location=location, then=Value(0)),
            When(location__isnull=True, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by("location_priority", "display_order", "created_at")


def active_capability_for(staff: User, work_type: WorkType, location: Location, work_date: date):
    queryset = StaffCapability.objects.filter(staff=staff, work_type=work_type).filter(
        Q(location=location) | Q(location__isnull=True)
    )
    return _ordered_capabilities(_active_on(queryset, work_date), location).first()


def build_capability_lookup(
    *,
    assignments: list[MonthlyShiftAssignment],
    location: Location,
    start_date: date,
    end_date: date,
    segments_attr: str | None = None,
) -> dict[tuple[str, str], list[StaffCapability]]:
    def assignment_segments(assignment: MonthlyShiftAssignment):
        if segments_attr:
            return getattr(assignment, segments_attr, [])
        return assignment.segments.all()

    required_pairs = {
        (item.staff_id, segment.work_type_id)
        for item in assignments
        for segment in assignment_segments(item)
        if segment.is_active and segment.work_type.requires_capability
    }
    if not required_pairs:
        return {}
    staff_ids = {staff_id for staff_id, _work_type_id in required_pairs}
    work_type_ids = {work_type_id for _staff_id, work_type_id in required_pairs}
    capabilities = (
        StaffCapability.objects.filter(
            staff_id__in=staff_ids,
            work_type_id__in=work_type_ids,
            is_active=True,
            valid_from__lte=end_date,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start_date))
        .filter(Q(location=location) | Q(location__isnull=True))
        .annotate(
            location_priority=Case(
                When(location=location, then=Value(0)),
                When(location__isnull=True, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("staff_id", "work_type_id", "location_priority", "display_order", "created_at")
    )
    result: dict[tuple[str, str], list[StaffCapability]] = {}
    for capability in capabilities:
        key = (str(capability.staff_id), str(capability.work_type_id))
        result.setdefault(key, []).append(capability)
    return result


def active_capability_from_lookup(
    lookup: dict[tuple[str, str], list[StaffCapability]],
    *,
    staff_id,
    work_type_id,
    work_date: date,
) -> StaffCapability | None:
    for capability in lookup.get((str(staff_id), str(work_type_id)), []):
        if capability.valid_from <= work_date and (
            capability.valid_until is None or capability.valid_until >= work_date
        ):
            return capability
    return None


def monthly_assignment_warning_count(
    assignment: MonthlyShiftAssignment,
    capability_lookup: dict[tuple[str, str], list[StaffCapability]],
    *,
    segments_attr: str | None = None,
) -> int:
    warning_levels = {StaffCapability.Level.ASSISTED, StaffCapability.Level.TRAINEE}
    warning_count = 0
    segments = getattr(assignment, segments_attr, []) if segments_attr else assignment.segments.all()
    for segment in segments:
        if not segment.is_active or not segment.work_type.requires_capability:
            continue
        capability = active_capability_from_lookup(
            capability_lookup,
            staff_id=assignment.staff_id,
            work_type_id=segment.work_type_id,
            work_date=assignment.work_date,
        )
        if capability is not None and capability.level in warning_levels:
            warning_count += 1
    return warning_count


def shift_request_period_metadata(period: ShiftRequestPeriod) -> dict:
    return {
        "period_id": str(period.id),
        "location_id": str(period.location_id),
        "year": period.year,
        "month": period.month,
        "status": period.status,
    }


def shift_request_submission_metadata(submission: ShiftRequestSubmission) -> dict:
    return {
        "period_id": str(submission.request_period_id),
        "submission_id": str(submission.id),
        "staff_id": str(submission.staff_id),
        "status": submission.status,
        "item_count": submission.items.filter(is_active=True).count(),
    }


def get_shift_request_lookup(
    location: Location, year: int, month: int, staff_ids
) -> dict[tuple[str, str], list[ShiftRequestItem]]:
    staff_ids = {str(staff_id) for staff_id in staff_ids}
    if not staff_ids:
        return {}
    queryset = (
        ShiftRequestItem.objects.filter(
            is_active=True,
            submission__staff_id__in=staff_ids,
            submission__status__in=[
                ShiftRequestSubmission.Status.SUBMITTED,
                ShiftRequestSubmission.Status.LOCKED,
            ],
            submission__request_period__location=location,
            submission__request_period__year=year,
            submission__request_period__month=month,
            submission__request_period__status__in=[
                ShiftRequestPeriod.Status.OPEN,
                ShiftRequestPeriod.Status.CLOSED,
                ShiftRequestPeriod.Status.ARCHIVED,
            ],
            submission__request_period__is_active=True,
        )
        .select_related("submission", "work_type", "work_area")
        .order_by("submission__staff_id", "work_date", "request_type", "start_offset_minutes", "id")
    )
    result: dict[tuple[str, str], list[ShiftRequestItem]] = {}
    for item in queryset:
        if item.work_date is None:
            continue
        key = (str(item.submission.staff_id), item.work_date.isoformat())
        result.setdefault(key, []).append(item)
    return result


def get_shift_request_info_lookup(
    location: Location,
    year: int,
    month: int,
    staff_ids,
) -> dict[tuple[str, str], list[ShiftRequestItem]]:
    staff_ids = {str(staff_id) for staff_id in staff_ids}
    if not staff_ids:
        return {}
    queryset = (
        ShiftRequestItem.objects.filter(
            is_active=True,
            submission__staff_id__in=staff_ids,
            submission__status__in=[
                ShiftRequestSubmission.Status.DRAFT,
                ShiftRequestSubmission.Status.SUBMITTED,
                ShiftRequestSubmission.Status.LOCKED,
            ],
            submission__request_period__location=location,
            submission__request_period__year=year,
            submission__request_period__month=month,
            submission__request_period__is_active=True,
        )
        .select_related("submission", "work_type", "work_area")
        .order_by("submission__staff_id", "work_date", "request_type", "start_offset_minutes", "id")
    )
    result: dict[tuple[str, str], list[ShiftRequestItem]] = {}
    for item in queryset:
        if item.work_date is None:
            continue
        result.setdefault((str(item.submission.staff_id), item.work_date.isoformat()), []).append(item)
    return result


def _ranges_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def validate_assignment_against_shift_requests(
    assignment: MonthlyShiftAssignment,
    segments: list[MonthlyShiftSegment],
    request_lookup: dict[tuple[str, str], list[ShiftRequestItem]],
) -> list[dict]:
    issues = []
    items = request_lookup.get((str(assignment.staff_id), assignment.work_date.isoformat()), [])
    active_segments = [segment for segment in segments if segment.is_active]
    if active_segments:
        assignment_start = min(segment.start_offset_minutes for segment in active_segments)
        assignment_end = max(segment.end_offset_minutes for segment in active_segments)
    else:
        assignment_start = None
        assignment_end = None
    for item in items:
        if item.request_type == ShiftRequestItem.RequestType.DAY_OFF:
            issues.append(
                {
                    "severity": "warning",
                    "code": "requested_day_off",
                    "message": "希望休の日に勤務が割り当てられています。",
                }
            )
        elif item.request_type == ShiftRequestItem.RequestType.UNAVAILABLE:
            if item.start_offset_minutes is None or item.end_offset_minutes is None:
                continue
            overlaps_assignment = (
                assignment_start is not None
                and assignment_end is not None
                and _ranges_overlap(
                    assignment_start, assignment_end, item.start_offset_minutes, item.end_offset_minutes
                )
            )
            overlaps_segment = any(
                _ranges_overlap(
                    segment.start_offset_minutes,
                    segment.end_offset_minutes,
                    item.start_offset_minutes,
                    item.end_offset_minutes,
                )
                for segment in active_segments
            )
            if overlaps_assignment or overlaps_segment:
                issues.append(
                    {
                        "severity": "warning",
                        "code": "requested_unavailable_time",
                        "message": "勤務不可時間帯と重なっています。",
                    }
                )
        elif item.request_type == ShiftRequestItem.RequestType.PREFER_TIME:
            issues.append(
                {
                    "severity": "info",
                    "code": "preferred_work_time",
                    "message": "勤務希望時間があります。",
                }
            )
    return issues


def shift_request_items_for_display(items: list[ShiftRequestItem]) -> list[dict]:
    return [
        {
            "id": str(item.id),
            "request_type": item.request_type,
            "work_date": item.work_date.isoformat() if item.work_date else None,
            "start_offset_minutes": item.start_offset_minutes,
            "end_offset_minutes": item.end_offset_minutes,
            "work_type": str(item.work_type_id) if item.work_type_id else None,
            "work_type_name": item.work_type.name if item.work_type_id else "",
            "work_area": str(item.work_area_id) if item.work_area_id else None,
            "work_area_name": item.work_area.name if item.work_area_id else "",
            "priority": item.priority,
            "reason": item.reason,
            "notes": item.notes,
        }
        for item in items
    ]


def shift_request_period_date_range(period: ShiftRequestPeriod) -> tuple[date, date]:
    return (
        date(period.year, period.month, 1),
        date(period.year, period.month, calendar.monthrange(period.year, period.month)[1]),
    )


def count_shift_request_target_staff(period: ShiftRequestPeriod) -> int:
    start_date, end_date = shift_request_period_date_range(period)
    return (
        StaffLocation.objects.filter(
            location=period.location,
            is_active=True,
            valid_from__lte=end_date,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start_date))
        .values("staff_id")
        .distinct()
        .count()
    )


def get_shift_request_target_staff_counts(periods: list[ShiftRequestPeriod]) -> dict[str, int]:
    if not periods:
        return {}
    ranges = {str(period.id): shift_request_period_date_range(period) for period in periods}
    min_start = min(start for start, _end in ranges.values())
    max_end = max(end for _start, end in ranges.values())
    location_ids = {period.location_id for period in periods}
    staff_locations = list(
        StaffLocation.objects.filter(
            location_id__in=location_ids,
            is_active=True,
            valid_from__lte=max_end,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=min_start))
        .values("location_id", "staff_id", "valid_from", "valid_until")
    )
    counts = {}
    for period in periods:
        start_date, end_date = ranges[str(period.id)]
        staff_ids = {
            item["staff_id"]
            for item in staff_locations
            if item["location_id"] == period.location_id
            and item["valid_from"] <= end_date
            and (item["valid_until"] is None or item["valid_until"] >= start_date)
        }
        counts[str(period.id)] = len(staff_ids)
    return counts


def is_shift_request_period_open(period: ShiftRequestPeriod, *, now=None) -> bool:
    now = now or timezone.now()
    return (
        period.is_active
        and period.status == ShiftRequestPeriod.Status.OPEN
        and period.opens_at <= now <= period.closes_at
    )


def can_edit_shift_request_submission(submission: ShiftRequestSubmission, *, now=None) -> bool:
    return is_shift_request_period_open(submission.request_period, now=now) and submission.status in {
        ShiftRequestSubmission.Status.DRAFT,
        ShiftRequestSubmission.Status.RETURNED,
    }


def can_submit_shift_request_submission(submission: ShiftRequestSubmission, *, now=None) -> bool:
    return can_edit_shift_request_submission(submission, now=now)


def ensure_staff_belongs_to_period(staff: User, period: ShiftRequestPeriod):
    if not (
        StaffLocation.objects.filter(
            staff=staff,
            location=period.location,
            is_active=True,
            valid_from__lte=date(period.year, period.month, calendar.monthrange(period.year, period.month)[1]),
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=date(period.year, period.month, 1)))
        .exists()
    ):
        raise DRFValidationError({"request_period": "対象拠点の提出期間ではありません。"})


def get_or_create_shift_request_submission(*, period: ShiftRequestPeriod, staff: User) -> ShiftRequestSubmission:
    ensure_staff_belongs_to_period(staff, period)
    submission, _created = ShiftRequestSubmission.objects.get_or_create(
        request_period=period,
        staff=staff,
        defaults={"status": ShiftRequestSubmission.Status.DRAFT},
    )
    return submission


def save_shift_request_period(*, instance: ShiftRequestPeriod | None, validated_data: dict, actor: User):
    try:
        period = instance or ShiftRequestPeriod(created_by=actor)
        if instance is not None and period.status == ShiftRequestPeriod.Status.ARCHIVED:
            raise DRFValidationError({"status": "Archived periods cannot be edited."})
        for field, value in validated_data.items():
            if field == "status":
                raise DRFValidationError({"status": "statusはaction endpointで変更してください。"})
            setattr(period, field, value)
        period.updated_by = actor
        if not period.name:
            period.name = f"{period.year}年{period.month}月 希望提出"
        period.full_clean()
        period.save()
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc, integrity_message="同じ拠点・年月の有効な希望提出期間が既に存在します。") from exc
    return period


def set_shift_request_period_active(period: ShiftRequestPeriod, *, is_active: bool, actor: User) -> ShiftRequestPeriod:
    try:
        period.is_active = is_active
        period.updated_by = actor
        period.full_clean()
        period.save(update_fields=["is_active", "updated_by", "updated_at"])
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc, integrity_message="同じ拠点・年月の有効な希望提出期間が既に存在します。") from exc
    return period


def set_shift_request_period_status(
    period: ShiftRequestPeriod, status_value: str, *, actor: User
) -> ShiftRequestPeriod:
    transitions = {
        ShiftRequestPeriod.Status.OPEN: {ShiftRequestPeriod.Status.DRAFT, ShiftRequestPeriod.Status.CLOSED},
        ShiftRequestPeriod.Status.CLOSED: {ShiftRequestPeriod.Status.OPEN},
        ShiftRequestPeriod.Status.ARCHIVED: {ShiftRequestPeriod.Status.CLOSED},
    }
    if status_value not in transitions or period.status not in transitions[status_value]:
        raise DRFValidationError({"status": "Invalid status transition."})
    period.status = status_value
    period.updated_by = actor
    period.save(update_fields=["status", "updated_by", "updated_at"])
    return period


def save_shift_request_submission(
    *,
    submission: ShiftRequestSubmission,
    notes: str,
    items_data: list[dict],
    actor: User,
) -> ShiftRequestSubmission:
    with transaction.atomic():
        submission = (
            ShiftRequestSubmission.objects.select_for_update()
            .select_related("request_period", "request_period__location", "staff")
            .get(pk=submission.pk)
        )
        if not can_edit_shift_request_submission(submission):
            raise DRFValidationError({"submission": "希望提出は編集できません。"})
        submission.items.filter(is_active=True).update(is_active=False)
        submission.notes = notes
        submission.save(update_fields=["notes", "updated_at"])
        for payload in items_data:
            item = ShiftRequestItem(submission=submission, **payload)
            item.full_clean()
            item.save()
    return submission


def submit_shift_request_submission(*, submission: ShiftRequestSubmission, actor: User):
    with transaction.atomic():
        submission = (
            ShiftRequestSubmission.objects.select_for_update().select_related("request_period").get(pk=submission.pk)
        )
        if not can_submit_shift_request_submission(submission):
            raise DRFValidationError({"submission": "希望提出は提出できません。"})
        now = timezone.now()
        submission.status = ShiftRequestSubmission.Status.SUBMITTED
        submission.submitted_at = now
        submission.submitted_by = actor
        submission.return_reason = ""
        submission.save(update_fields=["status", "submitted_at", "submitted_by", "return_reason", "updated_at"])
    return submission


def unsubmit_shift_request_submission(*, submission: ShiftRequestSubmission, actor: User):
    with transaction.atomic():
        submission = (
            ShiftRequestSubmission.objects.select_for_update().select_related("request_period").get(pk=submission.pk)
        )
        if (
            not is_shift_request_period_open(submission.request_period)
            or submission.status != ShiftRequestSubmission.Status.SUBMITTED
        ):
            raise DRFValidationError({"submission": "提出取消できません。"})
        submission.status = ShiftRequestSubmission.Status.DRAFT
        submission.save(update_fields=["status", "updated_at"])
    return submission


def return_shift_request_submission(*, submission: ShiftRequestSubmission, actor: User, reason: str):
    if not reason.strip():
        raise DRFValidationError({"reason": "差戻し理由を入力してください。"})
    submission = (
        ShiftRequestSubmission.objects.select_for_update()
        .select_related("request_period", "request_period__location", "staff")
        .get(pk=submission.pk)
    )
    submission.status = ShiftRequestSubmission.Status.RETURNED
    submission.returned_at = timezone.now()
    submission.returned_by = actor
    submission.return_reason = reason.strip()
    submission.save(update_fields=["status", "returned_at", "returned_by", "return_reason", "updated_at"])
    return submission


def lock_shift_request_submission(*, submission: ShiftRequestSubmission, actor: User):
    submission = (
        ShiftRequestSubmission.objects.select_for_update()
        .select_related("request_period", "request_period__location", "staff")
        .get(pk=submission.pk)
    )
    submission.status = ShiftRequestSubmission.Status.LOCKED
    submission.save(update_fields=["status", "updated_at"])
    return submission


def unlock_shift_request_submission(*, submission: ShiftRequestSubmission, actor: User):
    submission = (
        ShiftRequestSubmission.objects.select_for_update()
        .select_related("request_period", "request_period__location", "staff")
        .get(pk=submission.pk)
    )
    submission.status = ShiftRequestSubmission.Status.RETURNED
    submission.save(update_fields=["status", "updated_at"])
    return submission


SHIFT_CHANGE_OPEN_STATUSES = {
    ShiftChangeRequest.Status.DRAFT,
    ShiftChangeRequest.Status.SUBMITTED,
    ShiftChangeRequest.Status.APPROVED,
}
SHIFT_CHANGE_TERMINAL_STATUSES = {
    ShiftChangeRequest.Status.REJECTED,
    ShiftChangeRequest.Status.CANCELLED,
    ShiftChangeRequest.Status.APPLIED,
    ShiftChangeRequest.Status.CLOSED,
}


def shift_change_request_metadata(change_request: ShiftChangeRequest, *, reason: str = "") -> dict:
    data = {
        "change_request_id": str(change_request.id),
        "request_type": change_request.request_type,
        "status": change_request.status,
        "location_id": str(change_request.location_id),
        "plan_id": str(change_request.monthly_shift_plan_id),
        "publication_id": str(change_request.publication_id),
        "publication_assignment_id": (
            str(change_request.publication_assignment_id) if change_request.publication_assignment_id else None
        ),
        "requester_id": str(change_request.requester_id),
        "target_staff_id": str(change_request.target_staff_id),
        "requested_staff_id": str(change_request.requested_staff_id) if change_request.requested_staff_id else None,
        "work_date": change_request.work_date.isoformat(),
    }
    if reason:
        data["reason"] = reason
    return data


def can_edit_shift_change_request(change_request: ShiftChangeRequest, *, actor: User | None = None) -> bool:
    if change_request.status != ShiftChangeRequest.Status.DRAFT:
        return False
    if actor is None:
        return True
    return change_request.requester_id == actor.id


def can_submit_shift_change_request(change_request: ShiftChangeRequest, *, actor: User | None = None) -> bool:
    if change_request.status != ShiftChangeRequest.Status.DRAFT:
        return False
    if actor is None:
        return True
    return change_request.requester_id == actor.id


def can_cancel_shift_change_request(
    change_request: ShiftChangeRequest, *, actor: User | None = None, manager: bool = False
) -> bool:
    if manager:
        return change_request.status in SHIFT_CHANGE_OPEN_STATUSES
    if actor is None or change_request.requester_id != actor.id:
        return False
    return change_request.status in {ShiftChangeRequest.Status.DRAFT, ShiftChangeRequest.Status.SUBMITTED}


def can_approve_shift_change_request(change_request: ShiftChangeRequest, *, actor: User | None = None) -> bool:
    return (
        actor is not None and can_manage_shifts(actor) and change_request.status == ShiftChangeRequest.Status.SUBMITTED
    )


def can_apply_shift_change_request(change_request: ShiftChangeRequest, *, actor: User | None = None) -> bool:
    return (
        actor is not None
        and can_manage_shifts(actor)
        and change_request.status == ShiftChangeRequest.Status.APPROVED
        and change_request.request_type != ShiftChangeRequest.RequestType.NOTE
    )


def shift_change_requests_for_display(change_requests: list[ShiftChangeRequest]) -> list[dict]:
    return [
        {
            "id": str(item.id),
            "request_type": item.request_type,
            "status": item.status,
            "priority": item.priority,
            "requested_staff": str(item.requested_staff_id) if item.requested_staff_id else None,
            "requested_staff_display_name": item.requested_staff.display_name if item.requested_staff_id else "",
            "requested_work_date": item.requested_work_date.isoformat() if item.requested_work_date else None,
            "requested_start_offset_minutes": item.requested_start_offset_minutes,
            "requested_end_offset_minutes": item.requested_end_offset_minutes,
            "reason": item.reason,
            "manager_note": item.manager_note,
            "applied_at": item.applied_at,
        }
        for item in change_requests
    ]


def get_shift_change_request_lookup(
    plan: MonthlyShiftPlan,
    staff_ids: set,
) -> dict[tuple[str, str], list[ShiftChangeRequest]]:
    if not staff_ids:
        return {}
    requests = (
        ShiftChangeRequest.objects.filter(
            monthly_shift_plan=plan,
            target_staff_id__in=staff_ids,
            is_active=True,
            status__in=[
                ShiftChangeRequest.Status.DRAFT,
                ShiftChangeRequest.Status.SUBMITTED,
                ShiftChangeRequest.Status.APPROVED,
                ShiftChangeRequest.Status.APPLIED,
            ],
        )
        .select_related("requested_staff", "requester", "target_staff", "publication_assignment")
        .order_by("work_date", "created_at")
    )
    result: dict[tuple[str, str], list[ShiftChangeRequest]] = {}
    for item in requests:
        result.setdefault((str(item.target_staff_id), item.work_date.isoformat()), []).append(item)
    return result


def get_shift_change_request_assignment_lookup(
    publication_assignment_ids: list,
) -> dict[str, list[ShiftChangeRequest]]:
    if not publication_assignment_ids:
        return {}
    requests = (
        ShiftChangeRequest.objects.filter(
            publication_assignment_id__in=publication_assignment_ids,
            is_active=True,
            status__in=SHIFT_CHANGE_OPEN_STATUSES,
        )
        .select_related("requested_staff", "requester", "target_staff")
        .order_by("created_at")
    )
    result: dict[str, list[ShiftChangeRequest]] = {}
    for item in requests:
        result.setdefault(str(item.publication_assignment_id), []).append(item)
    return result


def shift_change_request_summary(plan: MonthlyShiftPlan) -> dict:
    requests = ShiftChangeRequest.objects.filter(monthly_shift_plan=plan, is_active=True)
    return {
        "open_count": requests.filter(status__in=SHIFT_CHANGE_OPEN_STATUSES).count(),
        "applied_count": requests.filter(status=ShiftChangeRequest.Status.APPLIED).count(),
        "needs_republish": requests.filter(status=ShiftChangeRequest.Status.APPLIED).exists()
        and not plan.publications.filter(is_active=True).exists(),
    }


ATTENDANCE_CORRECTION_OPEN_STATUSES = {
    AttendanceCorrectionRequest.Status.DRAFT,
    AttendanceCorrectionRequest.Status.SUBMITTED,
    AttendanceCorrectionRequest.Status.APPROVED,
}
ATTENDANCE_CORRECTION_TERMINAL_STATUSES = {
    AttendanceCorrectionRequest.Status.REJECTED,
    AttendanceCorrectionRequest.Status.CANCELLED,
    AttendanceCorrectionRequest.Status.APPLIED,
}


def _location_timezone(location: Location) -> ZoneInfo:
    return ZoneInfo(location.timezone or "Asia/Tokyo")


def _normalize_occurred_at(occurred_at: datetime | None) -> datetime:
    value = occurred_at or timezone.now()
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _offset_for_datetime(location: Location, work_date: date, occurred_at: datetime) -> int:
    local_tz = _location_timezone(location)
    local_value = _normalize_occurred_at(occurred_at).astimezone(local_tz)
    local_midnight = datetime.combine(work_date, datetime.min.time(), tzinfo=local_tz)
    offset = int((local_value - local_midnight).total_seconds() // 60)
    rounded = int(round(offset / 15) * 15)
    if rounded < 0 or rounded > 2880:
        raise DRFValidationError({"occurred_at": "打刻時刻が対象勤務日の範囲外です。"})
    return rounded


def _scheduled_values_from_segments(segments) -> dict:
    items = list(segments)
    work_items = [item for item in items if not item.work_type_is_break_snapshot]
    start_values = [item.start_offset_minutes for item in items]
    end_values = [item.end_offset_minutes for item in items]
    return {
        "scheduled_start_offset_minutes": min(start_values, default=None),
        "scheduled_end_offset_minutes": max(end_values, default=None),
        "scheduled_worked_minutes": sum(item.end_offset_minutes - item.start_offset_minutes for item in work_items),
    }


def _active_publication_assignment(
    *,
    staff: User,
    location: Location,
    work_date: date,
) -> MonthlyShiftPublicationAssignment | None:
    return (
        MonthlyShiftPublicationAssignment.objects.filter(
            staff=staff,
            work_date=work_date,
            publication__location=location,
            publication__is_active=True,
            publication__withdrawn_at__isnull=True,
        )
        .select_related(
            "publication",
            "publication__monthly_shift_plan",
            "source_assignment",
        )
        .prefetch_related("segments")
        .order_by("-publication__version")
        .first()
    )


def _apply_schedule_snapshot(
    record: AttendanceRecord,
    publication_assignment: MonthlyShiftPublicationAssignment | None,
):
    if publication_assignment is None:
        record.monthly_shift_plan = None
        record.monthly_shift_assignment = None
        record.publication = None
        record.publication_assignment = None
        record.scheduled_start_offset_minutes = None
        record.scheduled_end_offset_minutes = None
        record.scheduled_pattern_name_snapshot = ""
        record.scheduled_pattern_short_name_snapshot = ""
        if record.source == AttendanceRecord.Source.SCHEDULED:
            record.source = AttendanceRecord.Source.UNSCHEDULED
        return
    record.monthly_shift_plan = publication_assignment.publication.monthly_shift_plan
    record.monthly_shift_assignment = publication_assignment.source_assignment
    record.publication = publication_assignment.publication
    record.publication_assignment = publication_assignment
    scheduled = _scheduled_values_from_segments(publication_assignment.segments.all())
    record.scheduled_start_offset_minutes = scheduled["scheduled_start_offset_minutes"]
    record.scheduled_end_offset_minutes = scheduled["scheduled_end_offset_minutes"]
    record.scheduled_pattern_name_snapshot = publication_assignment.pattern_name_snapshot
    record.scheduled_pattern_short_name_snapshot = publication_assignment.pattern_short_name_snapshot
    if record.source == AttendanceRecord.Source.UNSCHEDULED:
        record.source = AttendanceRecord.Source.SCHEDULED


def _scheduled_worked_minutes(record: AttendanceRecord) -> int | None:
    if record.publication_assignment_id:
        return _scheduled_values_from_segments(record.publication_assignment.segments.all())["scheduled_worked_minutes"]
    if record.monthly_shift_assignment_id:
        segments = record.monthly_shift_assignment.segments.filter(is_active=True)
        return sum(
            segment.end_offset_minutes - segment.start_offset_minutes
            for segment in segments
            if not segment.work_type_is_break_snapshot
        )
    if record.scheduled_start_offset_minutes is None or record.scheduled_end_offset_minutes is None:
        return None
    return max(record.scheduled_end_offset_minutes - record.scheduled_start_offset_minutes, 0)


def _record_status_from_actual(record: AttendanceRecord) -> str:
    if record.actual_clock_out_at:
        return AttendanceRecord.Status.CLOCKED_OUT
    if record.actual_clock_in_at:
        return AttendanceRecord.Status.CLOCKED_IN
    return AttendanceRecord.Status.OPEN


def _attendance_warnings(record: AttendanceRecord, *, open_break: bool = False) -> list[dict]:
    warnings = []
    if record.scheduled_start_offset_minutes is None or record.scheduled_end_offset_minutes is None:
        if record.actual_clock_in_at or record.actual_clock_out_at:
            warnings.append({"code": "unscheduled_work", "message": "予定外勤務です。"})
    else:
        if record.actual_clock_in_at is None:
            warnings.append({"code": "missing_clock_in", "message": "出勤打刻がありません。"})
        if record.actual_clock_in_at is not None and record.actual_clock_out_at is None:
            warnings.append({"code": "missing_clock_out", "message": "退勤打刻がありません。"})
    if open_break:
        warnings.append({"code": "open_break", "message": "終了していない休憩があります。"})
    if (
        record.scheduled_start_offset_minutes is not None
        and record.actual_start_offset_minutes is not None
        and record.actual_start_offset_minutes > record.scheduled_start_offset_minutes
    ):
        warnings.append({"code": "late_clock_in", "message": "予定より遅い出勤です。"})
    if (
        record.scheduled_end_offset_minutes is not None
        and record.actual_end_offset_minutes is not None
        and record.actual_end_offset_minutes < record.scheduled_end_offset_minutes
    ):
        warnings.append({"code": "early_clock_out", "message": "予定より早い退勤です。"})
    if record.difference_worked_minutes is not None and record.actual_clock_out_at is not None:
        if record.difference_worked_minutes > 0:
            warnings.append({"code": "longer_worked", "message": "予定より勤務時間が長くなっています。"})
        if record.difference_worked_minutes < 0:
            warnings.append({"code": "shorter_worked", "message": "予定より勤務時間が短くなっています。"})
    if record.status == AttendanceRecord.Status.CONFIRMED and warnings:
        warnings.append({"code": "confirmed_with_warnings", "message": "警告がある状態で確定されています。"})
    return warnings


def _event_metadata(record: AttendanceRecord) -> dict:
    return {
        "attendance_record_id": str(record.id),
        "location_id": str(record.location_id),
        "staff_id": str(record.staff_id),
        "work_date": record.work_date.isoformat(),
        "status": record.status,
        "source": record.source,
        "monthly_shift_assignment_id": (
            str(record.monthly_shift_assignment_id) if record.monthly_shift_assignment_id else None
        ),
        "publication_assignment_id": (
            str(record.publication_assignment_id) if record.publication_assignment_id else None
        ),
    }


def attendance_record_metadata(record: AttendanceRecord) -> dict:
    return _event_metadata(record)


def attendance_correction_metadata(correction: AttendanceCorrectionRequest) -> dict:
    record = correction.attendance_record
    return _event_metadata(record) | {
        "attendance_correction_request_id": str(correction.id),
        "status": correction.status,
    }


def attendance_record_summary(record: AttendanceRecord | None) -> dict | None:
    if record is None:
        return None
    return {
        "id": str(record.id),
        "status": record.status,
        "source": record.source,
        "actual_start_offset_minutes": record.actual_start_offset_minutes,
        "actual_end_offset_minutes": record.actual_end_offset_minutes,
        "break_minutes": record.break_minutes,
        "worked_minutes": record.worked_minutes,
        "difference_start_minutes": record.difference_start_minutes,
        "difference_end_minutes": record.difference_end_minutes,
        "difference_worked_minutes": record.difference_worked_minutes,
        "warning_count": record.warning_count,
        "warnings": record.warnings,
        "confirmed_at": record.confirmed_at,
    }


def _create_attendance_event(
    *,
    record: AttendanceRecord,
    event_type: str,
    occurred_at: datetime,
    source: str,
    actor: User,
    note: str = "",
    metadata: dict | None = None,
) -> AttendanceEvent:
    try:
        offset_minutes = _offset_for_datetime(record.location, record.work_date, occurred_at)
    except DRFValidationError:
        if source == AttendanceEvent.Source.SELF:
            raise
        offset_minutes = record.actual_start_offset_minutes or 0
    return AttendanceEvent.objects.create(
        attendance_record=record,
        event_type=event_type,
        occurred_at=_normalize_occurred_at(occurred_at),
        offset_minutes=offset_minutes,
        source=source,
        actor=actor,
        note=note,
        metadata=metadata or {},
    )


def build_or_get_attendance_record(
    *,
    staff: User,
    location: Location,
    work_date: date,
) -> tuple[AttendanceRecord, bool]:
    publication_assignment = _active_publication_assignment(staff=staff, location=location, work_date=work_date)
    defaults = {
        "source": AttendanceRecord.Source.SCHEDULED if publication_assignment else AttendanceRecord.Source.UNSCHEDULED,
    }
    record, created = AttendanceRecord.objects.get_or_create(
        location=location,
        staff=staff,
        work_date=work_date,
        is_active=True,
        defaults=defaults,
    )
    if publication_assignment and not record.publication_assignment_id:
        _apply_schedule_snapshot(record, publication_assignment)
        record.full_clean()
        record.save()
    elif created:
        _apply_schedule_snapshot(record, publication_assignment)
        record.full_clean()
        record.save()
    return record, created


def _ensure_attendance_record_self_operable(record: AttendanceRecord):
    if record.status == AttendanceRecord.Status.CONFIRMED:
        raise DRFValidationError({"status": "確定済み勤怠は本人操作できません。"})
    if record.status == AttendanceRecord.Status.VOID or not record.is_active:
        raise DRFValidationError({"status": "無効な勤怠は操作できません。"})


def _ensure_attendance_record_manager_operable(record: AttendanceRecord):
    if record.status == AttendanceRecord.Status.VOID or not record.is_active:
        raise DRFValidationError({"status": "無効な勤怠は操作できません。"})


def _has_event(record: AttendanceRecord, event_type: str) -> bool:
    return record.events.filter(event_type=event_type).exists()


def _has_open_break(record: AttendanceRecord) -> bool:
    balance = 0
    for event in record.events.order_by("occurred_at", "created_at"):
        if event.event_type == AttendanceEvent.EventType.BREAK_START:
            balance += 1
        elif event.event_type == AttendanceEvent.EventType.BREAK_END:
            balance -= 1
        if balance < 0:
            raise DRFValidationError({"event_type": "休憩開始前に休憩終了は登録できません。"})
    return balance > 0


def recalculate_attendance_record(record: AttendanceRecord) -> AttendanceRecord:
    record = (
        AttendanceRecord.objects.select_related(
            "location",
            "staff",
            "monthly_shift_assignment",
            "publication_assignment",
        )
        .prefetch_related("events", "publication_assignment__segments", "monthly_shift_assignment__segments")
        .get(pk=record.pk)
    )
    open_break = False
    if record.source not in {AttendanceRecord.Source.MANUAL, AttendanceRecord.Source.CORRECTED}:
        clock_in = None
        clock_out = None
        breaks: list[tuple[AttendanceEvent, AttendanceEvent]] = []
        pending_break = None
        for event in record.events.all():
            if event.event_type == AttendanceEvent.EventType.CLOCK_IN and clock_in is None:
                clock_in = event
            elif event.event_type == AttendanceEvent.EventType.CLOCK_OUT and clock_out is None:
                clock_out = event
            elif event.event_type == AttendanceEvent.EventType.BREAK_START:
                if pending_break is not None:
                    open_break = True
                pending_break = event
            elif event.event_type == AttendanceEvent.EventType.BREAK_END:
                if pending_break is None:
                    raise DRFValidationError({"event_type": "休憩開始前に休憩終了は登録できません。"})
                breaks.append((pending_break, event))
                pending_break = None
        if pending_break is not None:
            open_break = True
        record.actual_clock_in_at = clock_in.occurred_at if clock_in else None
        record.actual_clock_out_at = clock_out.occurred_at if clock_out else None
        record.actual_start_offset_minutes = clock_in.offset_minutes if clock_in else None
        record.actual_end_offset_minutes = clock_out.offset_minutes if clock_out else None
        record.break_minutes = sum(max(end.offset_minutes - start.offset_minutes, 0) for start, end in breaks)
    else:
        if record.actual_clock_in_at:
            record.actual_start_offset_minutes = _offset_for_datetime(
                record.location, record.work_date, record.actual_clock_in_at
            )
        if record.actual_clock_out_at:
            record.actual_end_offset_minutes = _offset_for_datetime(
                record.location, record.work_date, record.actual_clock_out_at
            )
    if record.actual_start_offset_minutes is not None and record.actual_end_offset_minutes is not None:
        if record.actual_start_offset_minutes >= record.actual_end_offset_minutes:
            raise DRFValidationError({"actual_clock_out_at": "退勤時刻は出勤時刻より後にしてください。"})
        duration = record.actual_end_offset_minutes - record.actual_start_offset_minutes
        if record.break_minutes > duration:
            raise DRFValidationError({"break_minutes": "休憩時間が勤務時間を超えています。"})
        record.worked_minutes = max(duration - record.break_minutes, 0)
    else:
        record.worked_minutes = 0
    scheduled_worked = _scheduled_worked_minutes(record)
    if record.scheduled_start_offset_minutes is not None and record.actual_start_offset_minutes is not None:
        record.difference_start_minutes = record.actual_start_offset_minutes - record.scheduled_start_offset_minutes
    else:
        record.difference_start_minutes = None
    if record.scheduled_end_offset_minutes is not None and record.actual_end_offset_minutes is not None:
        record.difference_end_minutes = record.actual_end_offset_minutes - record.scheduled_end_offset_minutes
    else:
        record.difference_end_minutes = None
    if scheduled_worked is not None and record.actual_clock_out_at is not None:
        record.difference_worked_minutes = record.worked_minutes - scheduled_worked
    else:
        record.difference_worked_minutes = None
    if record.status not in {AttendanceRecord.Status.CONFIRMED, AttendanceRecord.Status.VOID}:
        if record.correction_requests.filter(status__in=ATTENDANCE_CORRECTION_OPEN_STATUSES, is_active=True).exists():
            record.status = AttendanceRecord.Status.PENDING_CORRECTION
        elif open_break:
            record.status = AttendanceRecord.Status.ON_BREAK
        else:
            record.status = _record_status_from_actual(record)
    record.warnings = _attendance_warnings(record, open_break=open_break)
    record.warning_count = len(record.warnings)
    record.full_clean()
    record.save()
    return record


def add_self_attendance_event(
    *,
    record: AttendanceRecord,
    event_type: str,
    actor: User,
    occurred_at: datetime | None,
    note: str = "",
) -> AttendanceRecord:
    record = (
        AttendanceRecord.objects.select_for_update(of=("self",)).select_related("location", "staff").get(pk=record.pk)
    )
    _ensure_attendance_record_self_operable(record)
    if record.staff_id != actor.id:
        raise DRFValidationError({"attendance_record": "本人の勤怠のみ操作できます。"})
    occurred = _normalize_occurred_at(occurred_at)
    if event_type == AttendanceEvent.EventType.CLOCK_IN and _has_event(record, AttendanceEvent.EventType.CLOCK_IN):
        raise DRFValidationError({"event_type": "出勤打刻は既に登録されています。"})
    if event_type == AttendanceEvent.EventType.CLOCK_OUT:
        if _has_event(record, AttendanceEvent.EventType.CLOCK_OUT):
            raise DRFValidationError({"event_type": "退勤打刻は既に登録されています。"})
        if not _has_event(record, AttendanceEvent.EventType.CLOCK_IN):
            raise DRFValidationError({"event_type": "出勤打刻後に退勤してください。"})
        if _has_open_break(record):
            raise DRFValidationError({"event_type": "休憩終了後に退勤してください。"})
    if event_type == AttendanceEvent.EventType.BREAK_START:
        if not _has_event(record, AttendanceEvent.EventType.CLOCK_IN):
            raise DRFValidationError({"event_type": "出勤打刻後に休憩を開始してください。"})
        if _has_event(record, AttendanceEvent.EventType.CLOCK_OUT):
            raise DRFValidationError({"event_type": "退勤後は休憩を開始できません。"})
        if _has_open_break(record):
            raise DRFValidationError({"event_type": "開始中の休憩があります。"})
    if event_type == AttendanceEvent.EventType.BREAK_END and not _has_open_break(record):
        raise DRFValidationError({"event_type": "終了対象の休憩がありません。"})
    _create_attendance_event(
        record=record,
        event_type=event_type,
        occurred_at=occurred,
        source=AttendanceEvent.Source.SELF,
        actor=actor,
        note=note,
    )
    return recalculate_attendance_record(record)


def clock_in_attendance(
    *,
    staff: User,
    location: Location,
    work_date: date,
    actor: User,
    occurred_at: datetime | None,
    note: str = "",
) -> tuple[AttendanceRecord, bool]:
    record, created = build_or_get_attendance_record(staff=staff, location=location, work_date=work_date)
    record = add_self_attendance_event(
        record=record,
        event_type=AttendanceEvent.EventType.CLOCK_IN,
        actor=actor,
        occurred_at=occurred_at,
        note=note,
    )
    return record, created


def _set_manual_actuals(
    record: AttendanceRecord,
    *,
    actual_clock_in_at: datetime,
    actual_clock_out_at: datetime,
    break_minutes: int,
):
    actual_clock_in_at = _normalize_occurred_at(actual_clock_in_at)
    actual_clock_out_at = _normalize_occurred_at(actual_clock_out_at)
    if actual_clock_in_at >= actual_clock_out_at:
        raise DRFValidationError({"actual_clock_out_at": "退勤時刻は出勤時刻より後にしてください。"})
    start_offset = _offset_for_datetime(record.location, record.work_date, actual_clock_in_at)
    end_offset = _offset_for_datetime(record.location, record.work_date, actual_clock_out_at)
    if start_offset >= end_offset:
        raise DRFValidationError({"actual_clock_out_at": "退勤時刻は出勤時刻より後にしてください。"})
    if break_minutes < 0:
        raise DRFValidationError({"break_minutes": "0以上で指定してください。"})
    if break_minutes > end_offset - start_offset:
        raise DRFValidationError({"break_minutes": "休憩時間が勤務時間を超えています。"})
    record.actual_clock_in_at = actual_clock_in_at
    record.actual_clock_out_at = actual_clock_out_at
    record.actual_start_offset_minutes = start_offset
    record.actual_end_offset_minutes = end_offset
    record.break_minutes = break_minutes


def manual_adjust_attendance_record(
    *,
    record: AttendanceRecord,
    actor: User,
    actual_clock_in_at: datetime,
    actual_clock_out_at: datetime,
    break_minutes: int,
    manager_note: str = "",
) -> AttendanceRecord:
    record = (
        AttendanceRecord.objects.select_for_update(of=("self",)).select_related("location", "staff").get(pk=record.pk)
    )
    _ensure_attendance_record_manager_operable(record)
    if record.status == AttendanceRecord.Status.CONFIRMED:
        raise DRFValidationError({"status": "確定済み勤怠は確定解除後に修正してください。"})
    _set_manual_actuals(
        record,
        actual_clock_in_at=actual_clock_in_at,
        actual_clock_out_at=actual_clock_out_at,
        break_minutes=break_minutes,
    )
    record.source = AttendanceRecord.Source.MANUAL
    record.manager_note = manager_note
    record.status = AttendanceRecord.Status.CLOCKED_OUT
    record.save()
    _create_attendance_event(
        record=record,
        event_type=AttendanceEvent.EventType.MANUAL_ADJUSTMENT,
        occurred_at=timezone.now(),
        source=AttendanceEvent.Source.MANAGER,
        actor=actor,
        note=manager_note,
        metadata={
            "actual_clock_in_at": record.actual_clock_in_at.isoformat(),
            "actual_clock_out_at": record.actual_clock_out_at.isoformat(),
            "break_minutes": break_minutes,
        },
    )
    return recalculate_attendance_record(record)


def confirm_attendance_record(*, record: AttendanceRecord, actor: User, manager_note: str = "") -> AttendanceRecord:
    record = (
        AttendanceRecord.objects.select_for_update(of=("self",)).select_related("location", "staff").get(pk=record.pk)
    )
    _ensure_attendance_record_manager_operable(record)
    record.status = AttendanceRecord.Status.CONFIRMED
    record.confirmed_at = timezone.now()
    record.confirmed_by = actor
    if manager_note:
        record.manager_note = manager_note
    record.save(update_fields=["status", "confirmed_at", "confirmed_by", "manager_note", "updated_at"])
    _create_attendance_event(
        record=record,
        event_type=AttendanceEvent.EventType.CONFIRMED,
        occurred_at=record.confirmed_at,
        source=AttendanceEvent.Source.MANAGER,
        actor=actor,
        note=manager_note,
    )
    return recalculate_attendance_record(record)


def unconfirm_attendance_record(*, record: AttendanceRecord, actor: User, manager_note: str = "") -> AttendanceRecord:
    record = (
        AttendanceRecord.objects.select_for_update(of=("self",)).select_related("location", "staff").get(pk=record.pk)
    )
    if record.status != AttendanceRecord.Status.CONFIRMED:
        raise DRFValidationError({"status": "確定済み勤怠のみ解除できます。"})
    record.status = _record_status_from_actual(record)
    record.confirmed_at = None
    record.confirmed_by = None
    if manager_note:
        record.manager_note = manager_note
    record.save(update_fields=["status", "confirmed_at", "confirmed_by", "manager_note", "updated_at"])
    _create_attendance_event(
        record=record,
        event_type=AttendanceEvent.EventType.UNCONFIRMED,
        occurred_at=timezone.now(),
        source=AttendanceEvent.Source.MANAGER,
        actor=actor,
        note=manager_note,
    )
    return recalculate_attendance_record(record)


def void_attendance_record(*, record: AttendanceRecord, actor: User, manager_note: str = "") -> AttendanceRecord:
    record = (
        AttendanceRecord.objects.select_for_update(of=("self",)).select_related("location", "staff").get(pk=record.pk)
    )
    if record.status == AttendanceRecord.Status.VOID:
        raise DRFValidationError({"status": "既に無効です。"})
    record.status = AttendanceRecord.Status.VOID
    record.is_active = False
    if manager_note:
        record.manager_note = manager_note
    record.save(update_fields=["status", "is_active", "manager_note", "updated_at"])
    _create_attendance_event(
        record=record,
        event_type=AttendanceEvent.EventType.VOIDED,
        occurred_at=timezone.now(),
        source=AttendanceEvent.Source.MANAGER,
        actor=actor,
        note=manager_note,
    )
    return record


def save_attendance_correction_request(
    *,
    instance: AttendanceCorrectionRequest | None,
    attendance_record: AttendanceRecord | None,
    actor: User,
    validated_data: dict,
    submit: bool = False,
) -> AttendanceCorrectionRequest:
    creating = instance is None
    if creating:
        if attendance_record is None:
            raise DRFValidationError({"attendance_record": "勤怠を指定してください。"})
        record = (
            AttendanceRecord.objects.select_for_update(of=("self",))
            .select_related("location", "staff")
            .get(pk=attendance_record.pk)
        )
        _ensure_attendance_record_self_operable(record)
        if record.staff_id != actor.id:
            raise DRFValidationError({"attendance_record": "本人の勤怠のみ申請できます。"})
        list(
            AttendanceCorrectionRequest.objects.select_for_update()
            .filter(attendance_record=record, is_active=True, status__in=ATTENDANCE_CORRECTION_OPEN_STATUSES)
            .values_list("id", flat=True)
        )
        if AttendanceCorrectionRequest.objects.filter(
            attendance_record=record,
            is_active=True,
            status__in=ATTENDANCE_CORRECTION_OPEN_STATUSES,
        ).exists():
            raise DRFValidationError({"attendance_record": "未完了の修正申請が既にあります。"})
        correction = AttendanceCorrectionRequest(attendance_record=record, requester=actor)
    else:
        correction = (
            AttendanceCorrectionRequest.objects.select_for_update(of=("self",))
            .select_related("attendance_record", "attendance_record__location", "requester")
            .get(pk=instance.pk)
        )
        if correction.requester_id != actor.id:
            raise DRFValidationError({"attendance_record": "本人の修正申請のみ編集できます。"})
        if correction.status != AttendanceCorrectionRequest.Status.DRAFT:
            raise DRFValidationError({"status": "下書きのみ編集できます。"})
        record = correction.attendance_record
        _ensure_attendance_record_self_operable(record)
    for field in [
        "requested_clock_in_at",
        "requested_clock_out_at",
        "requested_break_minutes",
        "requested_staff_note",
        "reason",
    ]:
        if field in validated_data:
            setattr(correction, field, validated_data[field])
    if submit:
        correction.status = AttendanceCorrectionRequest.Status.SUBMITTED
        correction.submitted_at = timezone.now()
    correction.full_clean()
    correction.save()
    if submit:
        record.status = AttendanceRecord.Status.PENDING_CORRECTION
        record.save(update_fields=["status", "updated_at"])
    return correction


def submit_attendance_correction_request(
    *, correction: AttendanceCorrectionRequest, actor: User
) -> AttendanceCorrectionRequest:
    correction = (
        AttendanceCorrectionRequest.objects.select_for_update(of=("self",))
        .select_related("attendance_record", "attendance_record__location", "requester")
        .get(pk=correction.pk)
    )
    if correction.requester_id != actor.id:
        raise DRFValidationError({"attendance_correction": "本人の修正申請のみ提出できます。"})
    if correction.status != AttendanceCorrectionRequest.Status.DRAFT:
        raise DRFValidationError({"status": "下書きのみ提出できます。"})
    _ensure_attendance_record_self_operable(correction.attendance_record)
    correction.status = AttendanceCorrectionRequest.Status.SUBMITTED
    correction.submitted_at = timezone.now()
    correction.save(update_fields=["status", "submitted_at", "updated_at"])
    record = correction.attendance_record
    record.status = AttendanceRecord.Status.PENDING_CORRECTION
    record.save(update_fields=["status", "updated_at"])
    return correction


def cancel_attendance_correction_request(
    *, correction: AttendanceCorrectionRequest, actor: User
) -> AttendanceCorrectionRequest:
    correction = (
        AttendanceCorrectionRequest.objects.select_for_update(of=("self",))
        .select_related("attendance_record", "attendance_record__location", "requester")
        .get(pk=correction.pk)
    )
    if correction.requester_id != actor.id:
        raise DRFValidationError({"attendance_correction": "本人の修正申請のみ取消できます。"})
    if correction.status not in ATTENDANCE_CORRECTION_OPEN_STATUSES:
        raise DRFValidationError({"status": "取消できる状態ではありません。"})
    correction.status = AttendanceCorrectionRequest.Status.CANCELLED
    correction.cancelled_at = timezone.now()
    correction.cancelled_by = actor
    correction.save(update_fields=["status", "cancelled_at", "cancelled_by", "updated_at"])
    recalculate_attendance_record(correction.attendance_record)
    return correction


def approve_attendance_correction_request(
    *, correction: AttendanceCorrectionRequest, actor: User, manager_note: str = ""
) -> AttendanceCorrectionRequest:
    correction = (
        AttendanceCorrectionRequest.objects.select_for_update(of=("self",))
        .select_related("attendance_record", "attendance_record__location", "requester")
        .get(pk=correction.pk)
    )
    if correction.status != AttendanceCorrectionRequest.Status.SUBMITTED:
        raise DRFValidationError({"status": "submittedのみ承認できます。"})
    correction.status = AttendanceCorrectionRequest.Status.APPROVED
    correction.approved_at = timezone.now()
    correction.approved_by = actor
    if manager_note:
        correction.manager_note = manager_note
    correction.save(update_fields=["status", "approved_at", "approved_by", "manager_note", "updated_at"])
    return correction


def reject_attendance_correction_request(
    *, correction: AttendanceCorrectionRequest, actor: User, manager_note: str
) -> AttendanceCorrectionRequest:
    if not manager_note.strip():
        raise DRFValidationError({"manager_note": "却下理由を入力してください。"})
    correction = (
        AttendanceCorrectionRequest.objects.select_for_update(of=("self",))
        .select_related("attendance_record", "attendance_record__location", "requester")
        .get(pk=correction.pk)
    )
    if correction.status not in {
        AttendanceCorrectionRequest.Status.SUBMITTED,
        AttendanceCorrectionRequest.Status.APPROVED,
    }:
        raise DRFValidationError({"status": "却下できる状態ではありません。"})
    correction.status = AttendanceCorrectionRequest.Status.REJECTED
    correction.rejected_at = timezone.now()
    correction.rejected_by = actor
    correction.manager_note = manager_note.strip()
    correction.save(update_fields=["status", "rejected_at", "rejected_by", "manager_note", "updated_at"])
    recalculate_attendance_record(correction.attendance_record)
    return correction


def apply_attendance_correction_request(
    *, correction: AttendanceCorrectionRequest, actor: User, manager_note: str = ""
) -> AttendanceCorrectionRequest:
    correction = (
        AttendanceCorrectionRequest.objects.select_for_update(of=("self",))
        .select_related("attendance_record", "attendance_record__location", "requester")
        .get(pk=correction.pk)
    )
    if correction.status != AttendanceCorrectionRequest.Status.APPROVED:
        raise DRFValidationError({"status": "approvedのみ反映できます。"})
    record = (
        AttendanceRecord.objects.select_for_update(of=("self",))
        .select_related("location", "staff")
        .get(pk=correction.attendance_record_id)
    )
    _ensure_attendance_record_manager_operable(record)
    if record.status == AttendanceRecord.Status.CONFIRMED:
        raise DRFValidationError({"status": "確定済み勤怠は確定解除後に修正してください。"})
    clock_in = correction.requested_clock_in_at or record.actual_clock_in_at
    clock_out = correction.requested_clock_out_at or record.actual_clock_out_at
    if not clock_in or not clock_out:
        raise DRFValidationError({"requested_clock_out_at": "出勤・退勤時刻を指定してください。"})
    _set_manual_actuals(
        record,
        actual_clock_in_at=clock_in,
        actual_clock_out_at=clock_out,
        break_minutes=correction.requested_break_minutes
        if correction.requested_break_minutes is not None
        else record.break_minutes,
    )
    record.source = AttendanceRecord.Source.CORRECTED
    if correction.requested_staff_note:
        record.staff_note = correction.requested_staff_note
    if manager_note:
        record.manager_note = manager_note
        correction.manager_note = manager_note
    record.status = AttendanceRecord.Status.CLOCKED_OUT
    record.save()
    _create_attendance_event(
        record=record,
        event_type=AttendanceEvent.EventType.CORRECTION_APPLIED,
        occurred_at=timezone.now(),
        source=AttendanceEvent.Source.MANAGER,
        actor=actor,
        note=manager_note,
        metadata={"attendance_correction_request_id": str(correction.id)},
    )
    correction.status = AttendanceCorrectionRequest.Status.APPLIED
    correction.applied_at = timezone.now()
    correction.applied_by = actor
    correction.save(update_fields=["status", "applied_at", "applied_by", "manager_note", "updated_at"])
    recalculate_attendance_record(record)
    return correction


def get_attendance_lookup(
    *,
    staff_ids: set | list,
    date_from: date,
    date_to: date,
    location: Location | None = None,
    monthly_shift_plan: MonthlyShiftPlan | None = None,
    publication_assignment_ids: list | None = None,
) -> dict:
    queryset = AttendanceRecord.objects.filter(
        staff_id__in=staff_ids,
        work_date__gte=date_from,
        work_date__lte=date_to,
        is_active=True,
    ).select_related("staff", "location")
    if location is not None:
        queryset = queryset.filter(location=location)
    if monthly_shift_plan is not None:
        queryset = queryset.filter(Q(monthly_shift_plan=monthly_shift_plan) | Q(monthly_shift_plan__isnull=True))
    if publication_assignment_ids is not None:
        queryset = queryset.filter(
            Q(publication_assignment_id__in=publication_assignment_ids) | Q(publication_assignment_id__isnull=True)
        )
    records = list(queryset)
    by_staff_date = {(str(item.staff_id), item.work_date.isoformat()): item for item in records}
    by_monthly_assignment = {
        str(item.monthly_shift_assignment_id): item for item in records if item.monthly_shift_assignment_id
    }
    by_publication_assignment = {
        str(item.publication_assignment_id): item for item in records if item.publication_assignment_id
    }
    return {
        "records": records,
        "by_staff_date": by_staff_date,
        "by_monthly_assignment": by_monthly_assignment,
        "by_publication_assignment": by_publication_assignment,
    }


def get_attendance_summary(records: list[AttendanceRecord]) -> dict:
    return {
        "record_count": len(records),
        "confirmed_count": sum(1 for item in records if item.status == AttendanceRecord.Status.CONFIRMED),
        "warning_count": sum(item.warning_count for item in records),
        "worked_minutes": sum(item.worked_minutes for item in records),
        "break_minutes": sum(item.break_minutes for item in records),
    }


def _ensure_active_publication_assignment(publication_assignment: MonthlyShiftPublicationAssignment):
    publication = publication_assignment.publication
    if not publication.is_active or publication.withdrawn_at is not None:
        raise DRFValidationError({"publication_assignment": "公開中の勤務のみ変更申請できます。"})


def _ensure_staff_location(staff: User, location: Location, work_date: date, *, field: str):
    if not staff.is_login_allowed():
        raise DRFValidationError({field: "有効なスタッフを指定してください。"})
    exists = (
        StaffLocation.objects.filter(
            staff=staff,
            location=location,
            is_active=True,
            staff__is_active=True,
            location__is_active=True,
            valid_from__lte=work_date,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=work_date))
        .exists()
    )
    if not exists:
        raise DRFValidationError({field: "対象拠点に有効所属しているスタッフを指定してください。"})


def _ensure_no_open_shift_change_duplicate(change_request: ShiftChangeRequest):
    if not change_request.publication_assignment_id or change_request.status not in SHIFT_CHANGE_OPEN_STATUSES:
        return
    duplicate = ShiftChangeRequest.objects.filter(
        publication_assignment=change_request.publication_assignment,
        status__in=SHIFT_CHANGE_OPEN_STATUSES,
        is_active=True,
    )
    if change_request.pk:
        duplicate = duplicate.exclude(pk=change_request.pk)
    if duplicate.exists():
        raise DRFValidationError({"publication_assignment": "この勤務には未完了の変更申請が既にあります。"})


def _snapshot_original_shift(change_request: ShiftChangeRequest):
    assignment = change_request.publication_assignment
    segments = list(assignment.segments.all()) if assignment else []
    change_request.original_start_offset_minutes = min(
        (segment.start_offset_minutes for segment in segments),
        default=None,
    )
    change_request.original_end_offset_minutes = max((segment.end_offset_minutes for segment in segments), default=None)
    change_request.original_pattern_name_snapshot = assignment.pattern_name_snapshot if assignment else ""
    change_request.original_pattern_short_name_snapshot = assignment.pattern_short_name_snapshot if assignment else ""


def _validate_shift_change_request(change_request: ShiftChangeRequest, *, creating: bool = False):
    if creating:
        _ensure_active_publication_assignment(change_request.publication_assignment)
    if change_request.publication_assignment_id:
        assignment = change_request.publication_assignment
        if assignment.publication_id != change_request.publication_id:
            raise DRFValidationError({"publication_assignment": "publicationとpublication_assignmentが一致しません。"})
        if assignment.publication.monthly_shift_plan_id != change_request.monthly_shift_plan_id:
            raise DRFValidationError({"monthly_shift_plan": "monthly_shift_planが公開勤務と一致しません。"})
        if assignment.publication.location_id != change_request.location_id:
            raise DRFValidationError({"location": "locationが公開勤務と一致しません。"})
        if assignment.work_date != change_request.work_date:
            raise DRFValidationError({"work_date": "work_dateが公開勤務と一致しません。"})
        if assignment.staff_id != change_request.target_staff_id:
            raise DRFValidationError({"target_staff": "target_staffが公開勤務と一致しません。"})
    if change_request.request_type == ShiftChangeRequest.RequestType.MANAGER_ADJUSTMENT:
        if change_request.requester_id and not can_manage_shifts(change_request.requester):
            raise DRFValidationError({"request_type": "manager_adjustmentは管理者のみ作成できます。"})
    elif not change_request.publication_assignment_id:
        raise DRFValidationError({"publication_assignment": "publication_assignmentは必須です。"})
    if (
        change_request.request_type == ShiftChangeRequest.RequestType.SWAP_SHIFT
        and not change_request.requested_staff_id
    ):
        raise DRFValidationError({"requested_staff": "swap_shiftにはrequested_staffが必須です。"})
    if change_request.request_type == ShiftChangeRequest.RequestType.CHANGE_TIME:
        if change_request.requested_start_offset_minutes is None or change_request.requested_end_offset_minutes is None:
            raise DRFValidationError({"requested_start_offset_minutes": "change_timeには希望時間が必須です。"})
    if change_request.request_type == ShiftChangeRequest.RequestType.CHANGE_ASSIGNMENT:
        if not change_request.requested_shift_pattern_id and not change_request.requested_notes.strip():
            raise DRFValidationError({"requested_shift_pattern": "勤務パターンまたは備考を指定してください。"})
    if change_request.requested_staff_id:
        _ensure_staff_location(
            change_request.requested_staff,
            change_request.location,
            change_request.requested_work_date or change_request.work_date,
            field="requested_staff",
        )
    try:
        change_request.full_clean()
    except DjangoValidationError as exc:
        raise _drf_validation(exc) from exc
    _ensure_no_open_shift_change_duplicate(change_request)


def save_shift_change_request(
    *,
    instance: ShiftChangeRequest | None,
    validated_data: dict,
    actor: User,
    self_service: bool,
    submit: bool = False,
) -> ShiftChangeRequest:
    try:
        creating = instance is None
        change_request = instance or ShiftChangeRequest(requester=actor, submitted_by=None)
        if not creating and change_request.status in SHIFT_CHANGE_TERMINAL_STATUSES:
            raise DRFValidationError({"status": "完了済みの変更申請は編集できません。"})
        if self_service and not creating and not can_edit_shift_change_request(change_request, actor=actor):
            raise DRFValidationError({"status": "下書き以外は本人編集できません。"})
        publication_assignment = validated_data.get("publication_assignment")
        if publication_assignment is not None:
            change_request.publication_assignment = publication_assignment
            change_request.publication = publication_assignment.publication
            change_request.monthly_shift_plan = publication_assignment.publication.monthly_shift_plan
            change_request.location = publication_assignment.publication.location
            change_request.work_date = publication_assignment.work_date
            change_request.target_staff = publication_assignment.staff
            if creating:
                _snapshot_original_shift(change_request)
        if creating and not publication_assignment:
            raise DRFValidationError({"publication_assignment": "publication_assignmentは必須です。"})
        if self_service and change_request.target_staff_id != actor.id:
            raise DRFValidationError({"publication_assignment": "本人の公開シフトのみ申請できます。"})
        for field in [
            "request_type",
            "priority",
            "requested_staff",
            "requested_work_date",
            "requested_shift_pattern",
            "requested_start_offset_minutes",
            "requested_end_offset_minutes",
            "requested_notes",
            "reason",
            "manager_note",
        ]:
            if field in validated_data:
                setattr(change_request, field, validated_data[field])
        if self_service and change_request.request_type == ShiftChangeRequest.RequestType.MANAGER_ADJUSTMENT:
            raise DRFValidationError({"request_type": "manager_adjustmentは本人APIでは作成できません。"})
        if submit:
            change_request.status = ShiftChangeRequest.Status.SUBMITTED
            change_request.submitted_at = timezone.now()
            change_request.submitted_by = actor
        elif creating:
            change_request.status = ShiftChangeRequest.Status.DRAFT
        _validate_shift_change_request(change_request, creating=creating)
        change_request.save()
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc) from exc
    return change_request


def submit_shift_change_request(*, change_request: ShiftChangeRequest, actor: User) -> ShiftChangeRequest:
    change_request = ShiftChangeRequest.objects.select_for_update(of=("self",)).get(pk=change_request.pk)
    if not can_submit_shift_change_request(change_request, actor=actor):
        raise DRFValidationError({"status": "提出できる状態ではありません。"})
    _validate_shift_change_request(change_request)
    change_request.status = ShiftChangeRequest.Status.SUBMITTED
    change_request.submitted_at = timezone.now()
    change_request.submitted_by = actor
    change_request.save(update_fields=["status", "submitted_at", "submitted_by", "updated_at"])
    return change_request


def cancel_shift_change_request(
    *, change_request: ShiftChangeRequest, actor: User, manager: bool = False, manager_note: str = ""
) -> ShiftChangeRequest:
    change_request = ShiftChangeRequest.objects.select_for_update(of=("self",)).get(pk=change_request.pk)
    if not can_cancel_shift_change_request(change_request, actor=actor, manager=manager):
        raise DRFValidationError({"status": "取消できる状態ではありません。"})
    change_request.status = ShiftChangeRequest.Status.CANCELLED
    change_request.cancelled_at = timezone.now()
    change_request.cancelled_by = actor
    if manager_note:
        change_request.manager_note = manager_note
    change_request.save(update_fields=["status", "cancelled_at", "cancelled_by", "manager_note", "updated_at"])
    return change_request


def approve_shift_change_request(
    *, change_request: ShiftChangeRequest, actor: User, validated_data: dict
) -> ShiftChangeRequest:
    change_request = ShiftChangeRequest.objects.select_for_update(of=("self",)).get(pk=change_request.pk)
    if change_request.status != ShiftChangeRequest.Status.SUBMITTED:
        raise DRFValidationError({"status": "submittedのみ承認できます。"})
    for field in [
        "requested_staff",
        "requested_work_date",
        "requested_shift_pattern",
        "requested_start_offset_minutes",
        "requested_end_offset_minutes",
        "manager_note",
    ]:
        if field in validated_data:
            setattr(change_request, field, validated_data[field])
    _validate_shift_change_request(change_request)
    change_request.status = ShiftChangeRequest.Status.APPROVED
    change_request.approved_at = timezone.now()
    change_request.approved_by = actor
    change_request.save(
        update_fields=[
            "requested_staff",
            "requested_work_date",
            "requested_shift_pattern",
            "requested_start_offset_minutes",
            "requested_end_offset_minutes",
            "manager_note",
            "status",
            "approved_at",
            "approved_by",
            "updated_at",
        ]
    )
    return change_request


def reject_shift_change_request(*, change_request: ShiftChangeRequest, actor: User, manager_note: str):
    if not manager_note.strip():
        raise DRFValidationError({"manager_note": "却下理由を入力してください。"})
    change_request = ShiftChangeRequest.objects.select_for_update(of=("self",)).get(pk=change_request.pk)
    if change_request.status not in {ShiftChangeRequest.Status.SUBMITTED, ShiftChangeRequest.Status.APPROVED}:
        raise DRFValidationError({"status": "却下できる状態ではありません。"})
    change_request.status = ShiftChangeRequest.Status.REJECTED
    change_request.rejected_at = timezone.now()
    change_request.rejected_by = actor
    change_request.manager_note = manager_note.strip()
    change_request.save(update_fields=["status", "rejected_at", "rejected_by", "manager_note", "updated_at"])
    return change_request


def close_shift_change_request(*, change_request: ShiftChangeRequest, actor: User, manager_note: str = ""):
    change_request = ShiftChangeRequest.objects.select_for_update(of=("self",)).get(pk=change_request.pk)
    if change_request.status in SHIFT_CHANGE_TERMINAL_STATUSES:
        raise DRFValidationError({"status": "完了済みです。"})
    if change_request.request_type != ShiftChangeRequest.RequestType.NOTE:
        raise DRFValidationError({"request_type": "closeはnote申請のみ利用できます。"})
    change_request.status = ShiftChangeRequest.Status.CLOSED
    if manager_note:
        change_request.manager_note = manager_note
    change_request.save(update_fields=["status", "manager_note", "updated_at"])
    return change_request


def _active_monthly_segments(assignment: MonthlyShiftAssignment) -> list[MonthlyShiftSegment]:
    return list(assignment.segments.select_related("work_type", "work_area").filter(is_active=True))


def _assignment_collision_exists(
    plan: MonthlyShiftPlan,
    *,
    staff: User,
    work_date: date,
    exclude_ids: set[str] | None = None,
) -> bool:
    queryset = MonthlyShiftAssignment.objects.filter(
        monthly_shift_plan=plan,
        staff=staff,
        work_date=work_date,
        is_active=True,
    )
    if exclude_ids:
        queryset = queryset.exclude(id__in=exclude_ids)
    return queryset.exists()


def _validate_assignment_after_change(assignment: MonthlyShiftAssignment, segments: list[MonthlyShiftSegment]):
    issues = validate_monthly_assignment(assignment, segments, validate_current_masters=True)
    errors = [issue for issue in issues if issue["severity"] == "error"]
    if errors:
        raise DRFValidationError({"warnings": errors})
    assignment.full_clean()
    for segment in segments:
        if segment.is_active:
            segment.full_clean()
    return issues


def _assign_monthly_assignment_staff(
    assignment: MonthlyShiftAssignment,
    *,
    staff: User,
    actor: User,
):
    _ensure_staff_location(staff, assignment.monthly_shift_plan.location, assignment.work_date, field="requested_staff")
    if _assignment_collision_exists(
        assignment.monthly_shift_plan,
        staff=staff,
        work_date=assignment.work_date,
        exclude_ids={str(assignment.id)},
    ):
        raise DRFValidationError({"requested_staff": "指定スタッフは同日に勤務があります。"})
    assignment.staff = staff
    assignment.source_type = MonthlyShiftAssignment.SourceType.MANUAL
    assignment.is_customized = True
    assignment.updated_by = actor
    _validate_assignment_after_change(assignment, _active_monthly_segments(assignment))
    assignment.save(update_fields=["staff", "source_type", "is_customized", "updated_by", "updated_at"])


def _drop_shift_assignment(assignment: MonthlyShiftAssignment, *, actor: User):
    assignment.is_active = False
    assignment.source_type = MonthlyShiftAssignment.SourceType.MANUAL
    assignment.is_customized = True
    assignment.updated_by = actor
    assignment.save(update_fields=["is_active", "source_type", "is_customized", "updated_by", "updated_at"])


def _change_assignment_time(
    assignment: MonthlyShiftAssignment,
    *,
    start_offset_minutes: int,
    end_offset_minutes: int,
    actor: User,
):
    segments = _active_monthly_segments(assignment)
    if not segments:
        raise DRFValidationError({"segments": "変更対象の勤務内訳がありません。"})
    target = next((segment for segment in segments if not segment.work_type_is_break_snapshot), segments[0])
    target.start_offset_minutes = start_offset_minutes
    target.end_offset_minutes = end_offset_minutes
    assignment.source_type = MonthlyShiftAssignment.SourceType.MANUAL
    assignment.is_customized = True
    assignment.updated_by = actor
    _validate_assignment_after_change(assignment, segments)
    assignment.save(update_fields=["source_type", "is_customized", "updated_by", "updated_at"])
    target.save(update_fields=["start_offset_minutes", "end_offset_minutes", "updated_at"])


def _replace_assignment_pattern(
    assignment: MonthlyShiftAssignment,
    *,
    pattern: ShiftPattern | None,
    notes: str,
    actor: User,
):
    active_segments = _active_monthly_segments(assignment)
    save_segments = []
    validation_segments = active_segments
    if pattern is not None:
        if pattern.location_id != assignment.monthly_shift_plan.location_id:
            raise DRFValidationError({"requested_shift_pattern": "勤務パターンの拠点が一致しません。"})
        for segment in active_segments:
            segment.is_active = False
            save_segments.append(segment)
        new_segments = _segments_from_pattern(pattern, assignment)
        validation_segments = new_segments
        save_segments.extend(new_segments)
        assignment.source_shift_pattern = pattern
        assignment.pattern_code_snapshot = pattern.code
        assignment.pattern_name_snapshot = pattern.name
        assignment.pattern_short_name_snapshot = pattern.short_name
    if notes:
        assignment.notes = notes
    assignment.source_type = MonthlyShiftAssignment.SourceType.MANUAL
    assignment.is_customized = True
    assignment.updated_by = actor
    _validate_assignment_after_change(assignment, validation_segments)
    assignment.save(
        update_fields=[
            "source_shift_pattern",
            "pattern_code_snapshot",
            "pattern_name_snapshot",
            "pattern_short_name_snapshot",
            "notes",
            "source_type",
            "is_customized",
            "updated_by",
            "updated_at",
        ]
    )
    for segment in save_segments:
        segment.monthly_shift_assignment = assignment
        segment.save()


def _swap_shift_assignment(assignment: MonthlyShiftAssignment, *, change_request: ShiftChangeRequest, actor: User):
    requested_staff = change_request.requested_staff
    if requested_staff is None:
        raise DRFValidationError({"requested_staff": "swap_shiftにはrequested_staffが必須です。"})
    _ensure_staff_location(
        requested_staff,
        assignment.monthly_shift_plan.location,
        assignment.work_date,
        field="requested_staff",
    )
    other_date = change_request.requested_work_date or assignment.work_date
    other = (
        MonthlyShiftAssignment.objects.select_for_update(of=("self",))
        .filter(
            monthly_shift_plan=assignment.monthly_shift_plan,
            staff=requested_staff,
            work_date=other_date,
            is_active=True,
        )
        .exclude(pk=assignment.pk)
        .first()
    )
    if other is None:
        _assign_monthly_assignment_staff(assignment, staff=requested_staff, actor=actor)
        return
    if _assignment_collision_exists(
        assignment.monthly_shift_plan,
        staff=assignment.staff,
        work_date=other.work_date,
        exclude_ids={str(assignment.id), str(other.id)},
    ):
        raise DRFValidationError({"requested_staff": "交換先の日付に対象スタッフの勤務があります。"})
    if other.work_date == assignment.work_date:
        other.is_active = False
        other.save(update_fields=["is_active", "updated_at"])
        assignment.staff = requested_staff
        assignment.source_type = MonthlyShiftAssignment.SourceType.MANUAL
        assignment.is_customized = True
        assignment.updated_by = actor
        _validate_assignment_after_change(assignment, _active_monthly_segments(assignment))
        assignment.save(update_fields=["staff", "source_type", "is_customized", "updated_by", "updated_at"])
        other.staff = change_request.target_staff
        other.is_active = True
        other.source_type = MonthlyShiftAssignment.SourceType.MANUAL
        other.is_customized = True
        other.updated_by = actor
        _validate_assignment_after_change(other, _active_monthly_segments(other))
        other.save(update_fields=["staff", "is_active", "source_type", "is_customized", "updated_by", "updated_at"])
        return
    assignment.staff = requested_staff
    assignment.source_type = MonthlyShiftAssignment.SourceType.MANUAL
    assignment.is_customized = True
    assignment.updated_by = actor
    _validate_assignment_after_change(assignment, _active_monthly_segments(assignment))
    assignment.save(update_fields=["staff", "source_type", "is_customized", "updated_by", "updated_at"])
    other.staff = change_request.target_staff
    other.source_type = MonthlyShiftAssignment.SourceType.MANUAL
    other.is_customized = True
    other.updated_by = actor
    _validate_assignment_after_change(other, _active_monthly_segments(other))
    other.save(update_fields=["staff", "source_type", "is_customized", "updated_by", "updated_at"])


def apply_shift_change_request(
    *, change_request: ShiftChangeRequest, actor: User, manager_note: str = ""
) -> tuple[ShiftChangeRequest, MonthlyShiftPublication]:
    try:
        change_request = (
            ShiftChangeRequest.objects.select_for_update(of=("self",))
            .select_related(
                "location",
                "monthly_shift_plan",
                "publication",
                "publication_assignment",
                "publication_assignment__source_assignment",
                "requested_staff",
                "requested_shift_pattern",
                "target_staff",
            )
            .get(pk=change_request.pk)
        )
        if change_request.status != ShiftChangeRequest.Status.APPROVED:
            raise DRFValidationError({"status": "approvedのみ反映できます。"})
        if change_request.request_type == ShiftChangeRequest.RequestType.NOTE:
            raise DRFValidationError({"request_type": "noteは反映不要です。closeしてください。"})
        if not change_request.publication.is_active or change_request.publication.withdrawn_at is not None:
            raise DRFValidationError({"publication": "公開中の申請のみ反映できます。"})
        plan = MonthlyShiftPlan.objects.select_for_update(of=("self",)).get(pk=change_request.monthly_shift_plan_id)
        assignment = (
            MonthlyShiftAssignment.objects.select_for_update(of=("self",))
            .select_related("monthly_shift_plan", "monthly_shift_plan__location", "staff")
            .get(pk=change_request.publication_assignment.source_assignment_id)
        )
        if assignment.monthly_shift_plan_id != plan.id:
            raise DRFValidationError({"publication_assignment": "元勤務が月間表と一致しません。"})
        if not assignment.is_active and change_request.request_type != ShiftChangeRequest.RequestType.DROP_SHIFT:
            raise DRFValidationError({"publication_assignment": "元勤務が解除済みです。"})
        if change_request.request_type == ShiftChangeRequest.RequestType.DROP_SHIFT:
            if change_request.requested_staff_id:
                _assign_monthly_assignment_staff(assignment, staff=change_request.requested_staff, actor=actor)
            else:
                _drop_shift_assignment(assignment, actor=actor)
        elif change_request.request_type == ShiftChangeRequest.RequestType.COVER_REQUEST:
            if not change_request.requested_staff_id:
                raise DRFValidationError({"requested_staff": "代行者未定のため反映できません。"})
            _assign_monthly_assignment_staff(assignment, staff=change_request.requested_staff, actor=actor)
        elif change_request.request_type == ShiftChangeRequest.RequestType.SWAP_SHIFT:
            _swap_shift_assignment(assignment, change_request=change_request, actor=actor)
        elif change_request.request_type == ShiftChangeRequest.RequestType.CHANGE_TIME:
            _change_assignment_time(
                assignment,
                start_offset_minutes=change_request.requested_start_offset_minutes,
                end_offset_minutes=change_request.requested_end_offset_minutes,
                actor=actor,
            )
        elif change_request.request_type == ShiftChangeRequest.RequestType.CHANGE_ASSIGNMENT:
            _replace_assignment_pattern(
                assignment,
                pattern=change_request.requested_shift_pattern,
                notes=change_request.requested_notes,
                actor=actor,
            )
        elif change_request.request_type == ShiftChangeRequest.RequestType.MANAGER_ADJUSTMENT:
            if change_request.requested_staff_id:
                _assign_monthly_assignment_staff(assignment, staff=change_request.requested_staff, actor=actor)
            if change_request.requested_start_offset_minutes is not None:
                _change_assignment_time(
                    assignment,
                    start_offset_minutes=change_request.requested_start_offset_minutes,
                    end_offset_minutes=change_request.requested_end_offset_minutes,
                    actor=actor,
                )
            if change_request.requested_shift_pattern_id or change_request.requested_notes.strip():
                _replace_assignment_pattern(
                    assignment,
                    pattern=change_request.requested_shift_pattern,
                    notes=change_request.requested_notes,
                    actor=actor,
                )
        withdrawn_publication = withdraw_monthly_shift_publication(
            plan=plan,
            actor=actor,
            reason=f"change_request_applied:{change_request.id}",
        )
        change_request.status = ShiftChangeRequest.Status.APPLIED
        change_request.applied_at = timezone.now()
        change_request.applied_by = actor
        if manager_note:
            change_request.manager_note = manager_note
        change_request.save(update_fields=["status", "applied_at", "applied_by", "manager_note", "updated_at"])
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc, integrity_message=MONTHLY_ASSIGNMENT_DUPLICATE_MESSAGE) from exc
    return change_request, withdrawn_publication


def _validate_assignment_cell_immutable(instance: MonthlyShiftAssignment | None, validated_data: dict):
    if instance is None:
        return
    errors = {}
    for field in ["monthly_shift_plan", "work_date", "staff"]:
        if field not in validated_data:
            continue
        incoming = validated_data[field]
        incoming_value = getattr(incoming, "id", incoming)
        current_value = (
            getattr(instance, f"{field}_id") if field in {"monthly_shift_plan", "staff"} else getattr(instance, field)
        )
        if str(incoming_value) != str(current_value):
            errors[field] = IMMUTABLE_ASSIGNMENT_CELL_MESSAGE
    if errors:
        raise DRFValidationError(errors)


def _validate_plan_immutable(instance: MonthlyShiftPlan | None, validated_data: dict):
    if instance is None:
        return
    errors = {}
    for field in ["location", "year", "month"]:
        if field not in validated_data:
            continue
        incoming = validated_data[field]
        incoming_value = getattr(incoming, "id", incoming)
        current_value = getattr(instance, f"{field}_id") if field == "location" else getattr(instance, field)
        if str(incoming_value) != str(current_value):
            errors[field] = IMMUTABLE_PLAN_FIELDS_MESSAGE
    if errors:
        raise DRFValidationError(errors)


def _validate_active_monthly_plan_unique(plan: MonthlyShiftPlan):
    if not plan.is_active:
        return
    duplicate = MonthlyShiftPlan.objects.filter(
        location_id=plan.location_id,
        year=plan.year,
        month=plan.month,
        is_active=True,
    )
    if plan.pk:
        duplicate = duplicate.exclude(pk=plan.pk)
    if duplicate.exists():
        raise DRFValidationError({"non_field_errors": [MONTHLY_PLAN_DUPLICATE_MESSAGE]})


def _validate_active_monthly_assignment_unique(assignment: MonthlyShiftAssignment):
    if not assignment.is_active:
        return
    duplicate = MonthlyShiftAssignment.objects.filter(
        monthly_shift_plan_id=assignment.monthly_shift_plan_id,
        work_date=assignment.work_date,
        staff_id=assignment.staff_id,
        is_active=True,
    )
    if assignment.pk:
        duplicate = duplicate.exclude(pk=assignment.pk)
    if duplicate.exists():
        raise DRFValidationError({"non_field_errors": [MONTHLY_ASSIGNMENT_DUPLICATE_MESSAGE]})


def save_monthly_plan(*, instance: MonthlyShiftPlan | None, validated_data: dict, actor: User):
    try:
        if instance is not None:
            ensure_monthly_plan_editable(instance)
        _validate_plan_immutable(instance, validated_data)
        plan = instance or MonthlyShiftPlan(created_by=actor)
        for field, value in validated_data.items():
            setattr(plan, field, value)
        plan.updated_by = actor
        if instance is None:
            plan.is_active = True
            if not plan.name:
                plan.name = f"{plan.year}年{plan.month}月 {plan.location.name}シフト"
        _validate_active_monthly_plan_unique(plan)
        plan.full_clean()
        plan.save()
    except (DjangoValidationError, IntegrityError) as exc:
        raise _drf_validation(exc, integrity_message=MONTHLY_PLAN_DUPLICATE_MESSAGE) from exc
    return plan


def monthly_plan_metadata(plan: MonthlyShiftPlan) -> dict:
    return {
        "plan_id": str(plan.id),
        "location_id": str(plan.location_id),
        "year": plan.year,
        "month": plan.month,
        "assignment_count": plan.assignments.filter(is_active=True).count(),
    }


def monthly_assignment_metadata(assignment: MonthlyShiftAssignment) -> dict:
    return {
        "assignment_id": str(assignment.id),
        "plan_id": str(assignment.monthly_shift_plan_id),
        "work_date": assignment.work_date.isoformat(),
        "staff_id": str(assignment.staff_id),
        "source_type": assignment.source_type,
    }


def _snapshot_segment(segment: MonthlyShiftSegment):
    _snapshot_work_type(segment)
    _snapshot_work_area(segment)


def _snapshot_work_type(segment: MonthlyShiftSegment):
    segment.work_type_name_snapshot = segment.work_type.name
    segment.work_type_short_name_snapshot = segment.work_type.short_name
    segment.work_type_color_key_snapshot = segment.work_type.color_key
    segment.work_type_is_break_snapshot = segment.work_type.is_break


def _snapshot_work_area(segment: MonthlyShiftSegment):
    segment.work_area_name_snapshot = segment.work_area.name if segment.work_area_id else ""


def _segments_from_pattern(pattern: ShiftPattern, assignment: MonthlyShiftAssignment) -> list[MonthlyShiftSegment]:
    result = []
    for source in (
        pattern.segments.filter(is_active=True)
        .select_related("work_type", "work_area")
        .order_by("start_offset_minutes", "display_order")
    ):
        segment = MonthlyShiftSegment(
            monthly_shift_assignment=assignment,
            source_pattern_segment=source,
            work_type=source.work_type,
            work_area=source.work_area,
            start_offset_minutes=source.start_offset_minutes,
            end_offset_minutes=source.end_offset_minutes,
            display_order=source.display_order,
            notes=source.notes,
            is_active=True,
        )
        _snapshot_segment(segment)
        result.append(segment)
    return result


def _assignment_from_pattern(
    *,
    plan: MonthlyShiftPlan,
    work_date: date,
    staff: User,
    pattern: ShiftPattern,
    source_type: str,
    actor: User,
    source_entry: WeeklyShiftTemplateEntry | None = None,
    notes: str = "",
    existing: MonthlyShiftAssignment | None = None,
) -> tuple[MonthlyShiftAssignment, list[MonthlyShiftSegment]]:
    assignment = existing or MonthlyShiftAssignment(monthly_shift_plan=plan, created_by=actor)
    assignment.monthly_shift_plan = plan
    assignment.work_date = work_date
    assignment.staff = staff
    assignment.source_type = source_type
    assignment.source_weekly_template_entry = source_entry
    assignment.source_shift_pattern = pattern
    assignment.pattern_code_snapshot = pattern.code
    assignment.pattern_name_snapshot = pattern.name
    assignment.pattern_short_name_snapshot = pattern.short_name
    assignment.notes = notes
    assignment.is_customized = False
    assignment.updated_by = actor
    assignment.is_active = True
    return assignment, _segments_from_pattern(pattern, assignment)


def _segment_from_monthly_payload(
    assignment: MonthlyShiftAssignment,
    payload: dict,
    existing: MonthlyShiftSegment | None = None,
):
    segment = existing or MonthlyShiftSegment(monthly_shift_assignment=assignment)
    original_work_type_id = existing.work_type_id if existing else None
    original_work_area_id = existing.work_area_id if existing else None
    for field in ["work_type", "work_area", "start_offset_minutes", "end_offset_minutes", "display_order", "notes"]:
        if field not in payload:
            continue
        value = payload[field]
        if field == "work_type":
            value = value if isinstance(value, WorkType) else WorkType.objects.get(pk=value)
        if field == "work_area":
            value = value if isinstance(value, WorkArea) or value is None else WorkArea.objects.get(pk=value)
        setattr(segment, field, value)
    segment.monthly_shift_assignment = assignment
    segment.source_pattern_segment = None if existing is None else segment.source_pattern_segment
    if existing is None:
        _snapshot_segment(segment)
    else:
        if str(original_work_type_id) != str(segment.work_type_id):
            _snapshot_work_type(segment)
        if str(original_work_area_id or "") != str(segment.work_area_id or ""):
            _snapshot_work_area(segment)
    return segment


def _capability_issues(staff: User, work_type: WorkType, location: Location, work_date: date) -> list[dict]:
    if not work_type.requires_capability:
        return []
    capability = active_capability_for(staff, work_type, location, work_date)
    if capability is None:
        return [
            {
                "severity": "error",
                "code": "missing_capability",
                "message": "対象日に必要なスタッフ対応可能業務がありません。",
            }
        ]
    if capability.level == StaffCapability.Level.ASSISTED:
        return [{"severity": "warning", "code": "assisted_capability", "message": ASSISTED_WARNING}]
    if capability.level == StaffCapability.Level.TRAINEE:
        return [{"severity": "warning", "code": "trainee_capability", "message": TRAINEE_WARNING}]
    return []


@dataclass
class PublicationValidationContext:
    plan: MonthlyShiftPlan
    start_date: date
    end_date: date
    staff_locations: dict[str, list[StaffLocation]]
    availability_keys: set[tuple[str, str | None]]
    capability_lookup: dict[tuple[str, str], list[StaffCapability]]


def build_publication_validation_context(
    *,
    plan: MonthlyShiftPlan,
    assignments: list[MonthlyShiftAssignment],
) -> PublicationValidationContext:
    start_date, end_date = _plan_bounds(plan)
    staff_ids = {assignment.staff_id for assignment in assignments}
    work_type_ids = set()
    work_area_ids = set()
    for assignment in assignments:
        for segment in getattr(assignment, "active_segments", []):
            work_type_ids.add(segment.work_type_id)
            if segment.work_area_id:
                work_area_ids.add(segment.work_area_id)

    staff_locations: dict[str, list[StaffLocation]] = {}
    if staff_ids:
        locations = (
            StaffLocation.objects.filter(
                staff_id__in=staff_ids,
                location_id=plan.location_id,
                is_active=True,
                staff__is_active=True,
                location__is_active=True,
                valid_from__lte=end_date,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start_date))
            .order_by("staff_id", "valid_from", "id")
        )
        for staff_location in locations:
            staff_locations.setdefault(str(staff_location.staff_id), []).append(staff_location)

    availability_keys: set[tuple[str, str | None]] = set()
    if work_type_ids:
        availabilities = (
            WorkTypeAvailability.objects.filter(
                work_type_id__in=work_type_ids,
                location_id=plan.location_id,
                is_active=True,
                work_type__is_active=True,
                location__is_active=True,
            )
            .filter(Q(work_area__isnull=True) | Q(work_area_id__in=work_area_ids))
            .filter(Q(work_area__isnull=True) | Q(work_area__is_active=True))
            .order_by("work_type_id", "work_area_id", "id")
        )
        availability_keys = {
            (str(item.work_type_id), str(item.work_area_id) if item.work_area_id else None) for item in availabilities
        }

    return PublicationValidationContext(
        plan=plan,
        start_date=start_date,
        end_date=end_date,
        staff_locations=staff_locations,
        availability_keys=availability_keys,
        capability_lookup=build_capability_lookup(
            assignments=assignments,
            location=plan.location,
            start_date=start_date,
            end_date=end_date,
            segments_attr="active_segments",
        ),
    )


def _is_active_for_date(valid_from: date, valid_until: date | None, target_date: date) -> bool:
    return valid_from <= target_date and (valid_until is None or valid_until >= target_date)


def _validation_issue(message: str, *, code: str = "validation_error") -> dict:
    return {"severity": "error", "code": code, "message": message}


def _has_staff_location(context: PublicationValidationContext, assignment: MonthlyShiftAssignment) -> bool:
    return any(
        _is_active_for_date(item.valid_from, item.valid_until, assignment.work_date)
        for item in context.staff_locations.get(str(assignment.staff_id), [])
    )


def _has_work_type_availability(context: PublicationValidationContext, segment: MonthlyShiftSegment) -> bool:
    work_type_id = str(segment.work_type_id)
    work_area_id = str(segment.work_area_id) if segment.work_area_id else None
    return (work_type_id, None) in context.availability_keys or (
        work_type_id,
        work_area_id,
    ) in context.availability_keys


def validate_assignments_for_publication(
    assignment: MonthlyShiftAssignment,
    segments: list[MonthlyShiftSegment],
    context: PublicationValidationContext,
) -> list[dict]:
    issues: list[dict] = []
    plan = context.plan
    if assignment.work_date.year != plan.year or assignment.work_date.month != plan.month:
        issues.append(_validation_issue("{'work_date': 'work_date must be within the monthly shift plan.'}"))
    if not assignment.staff.is_login_allowed():
        issues.append(_validation_issue("{'staff': 'Inactive staff cannot be assigned.'}"))
    if not _has_staff_location(context, assignment):
        issues.append(_validation_issue("{'staff': 'Staff must belong to the plan location on work_date.'}"))

    active_segments = [segment for segment in segments if segment.is_active]
    if assignment.is_active and not active_segments:
        issues.append(_validation_issue("{'segments': 'Active assignments require at least one active segment.'}"))
    if active_segments:
        first_start = min(segment.start_offset_minutes for segment in active_segments)
        last_end = max(segment.end_offset_minutes for segment in active_segments)
        if last_end - first_start > 1440:
            issues.append(_validation_issue("{'segments': 'An assignment cannot span more than 24 hours.'}"))

    for segment in active_segments:
        if not segment.work_type.is_active:
            issues.append(_validation_issue("{'work_type': 'Inactive work types cannot be assigned.'}"))
        if segment.work_area_id:
            if not segment.work_area.is_active:
                issues.append(_validation_issue("{'work_area': 'Inactive work areas cannot be assigned.'}"))
            elif segment.work_area.location_id != plan.location_id:
                issues.append(
                    _validation_issue("{'work_area': 'work_area must belong to the monthly shift plan location.'}")
                )
        if (
            segment.start_offset_minutes < 0
            or segment.start_offset_minutes >= 2880
            or segment.end_offset_minutes <= 0
            or segment.end_offset_minutes > 2880
            or segment.end_offset_minutes <= segment.start_offset_minutes
            or segment.start_offset_minutes % 15 != 0
            or segment.end_offset_minutes % 15 != 0
            or segment.end_offset_minutes - segment.start_offset_minutes > 1440
        ):
            issues.append(_validation_issue("{'segments': 'Invalid segment time range.'}"))
        if not _has_work_type_availability(context, segment):
            issues.append(_validation_issue("{'segments': 'Work type availability is missing for a segment.'}"))
        issues.extend(
            _capability_issues_from_lookup(
                context.capability_lookup,
                staff_id=assignment.staff_id,
                work_type=segment.work_type,
                location=plan.location,
                work_date=assignment.work_date,
            )
        )

    ordered = sorted(active_segments, key=lambda item: (item.start_offset_minutes, item.end_offset_minutes))
    for index, current in enumerate(ordered):
        for other in ordered[index + 1 :]:
            if current.end_offset_minutes <= other.start_offset_minutes:
                break
            if current.work_type.is_break or other.work_type.is_break:
                issues.append(_validation_issue("{'segments': 'Break segments cannot overlap other segments.'}"))
                continue
            if not (current.work_type.can_overlap or other.work_type.can_overlap):
                issues.append(_validation_issue("{'segments': 'Monthly shift segments cannot overlap.'}"))
    return issues


def _capability_issues_from_lookup(
    lookup: dict[tuple[str, str], list[StaffCapability]],
    *,
    staff_id,
    work_type: WorkType,
    location: Location,
    work_date: date,
) -> list[dict]:
    if not work_type.requires_capability:
        return []
    capability = active_capability_from_lookup(
        lookup,
        staff_id=staff_id,
        work_type_id=work_type.id,
        work_date=work_date,
    )
    if capability is None:
        return [
            {
                "severity": "error",
                "code": "missing_capability",
                "message": "対象日に必要なスタッフ対応可能業務がありません。",
            }
        ]
    if capability.level == StaffCapability.Level.ASSISTED:
        return [{"severity": "warning", "code": "assisted_capability", "message": ASSISTED_WARNING}]
    if capability.level == StaffCapability.Level.TRAINEE:
        return [{"severity": "warning", "code": "trainee_capability", "message": TRAINEE_WARNING}]
    return []


def validate_monthly_assignment(
    assignment: MonthlyShiftAssignment,
    segments: list[MonthlyShiftSegment],
    *,
    validate_current_masters: bool = True,
    shift_request_lookup: dict[tuple[str, str], list[ShiftRequestItem]] | None = None,
) -> list[dict]:
    issues: list[dict] = []
    plan = assignment.monthly_shift_plan
    if validate_current_masters:
        _validate_active_monthly_assignment_unique(assignment)
        try:
            assignment.full_clean()
        except DjangoValidationError as exc:
            raise _drf_validation(exc) from exc
        if not _active_on(
            StaffLocation.objects.filter(
                staff=assignment.staff,
                location=plan.location,
                staff__is_active=True,
                location__is_active=True,
            ),
            assignment.work_date,
        ).exists():
            raise DRFValidationError({"staff": "Staff must belong to the plan location on work_date."})
    elif assignment.work_date.year != plan.year or assignment.work_date.month != plan.month:
        raise DRFValidationError({"work_date": "work_date must be within the monthly shift plan."})

    active_segments = [segment for segment in segments if segment.is_active]
    if assignment.is_active and not active_segments:
        raise DRFValidationError({"segments": "Active assignments require at least one active segment."})
    if active_segments:
        first_start = min(segment.start_offset_minutes for segment in active_segments)
        last_end = max(segment.end_offset_minutes for segment in active_segments)
        if last_end - first_start > 1440:
            raise DRFValidationError({"segments": "An assignment cannot span more than 24 hours."})

    for segment in active_segments:
        if validate_current_masters:
            try:
                exclude = None
                if not segment.monthly_shift_assignment_id or segment.monthly_shift_assignment._state.adding:
                    exclude = ["monthly_shift_assignment"]
                segment.full_clean(exclude=exclude)
            except DjangoValidationError as exc:
                raise _drf_validation(exc) from exc
            if (
                not WorkTypeAvailability.objects.filter(
                    work_type_id=segment.work_type_id,
                    location_id=plan.location_id,
                    is_active=True,
                    work_type__is_active=True,
                    location__is_active=True,
                )
                .filter(Q(work_area__isnull=True) | Q(work_area_id=segment.work_area_id))
                .exists()
            ):
                raise DRFValidationError({"segments": "Work type availability is missing for a segment."})
            issues.extend(_capability_issues(assignment.staff, segment.work_type, plan.location, assignment.work_date))
        elif (
            segment.start_offset_minutes < 0
            or segment.start_offset_minutes >= 2880
            or segment.end_offset_minutes <= 0
            or segment.end_offset_minutes > 2880
            or segment.end_offset_minutes <= segment.start_offset_minutes
            or segment.start_offset_minutes % 15 != 0
            or segment.end_offset_minutes % 15 != 0
            or segment.end_offset_minutes - segment.start_offset_minutes > 1440
        ):
            raise DRFValidationError({"segments": "Invalid segment time range."})

    ordered = sorted(active_segments, key=lambda item: (item.start_offset_minutes, item.end_offset_minutes))
    for index, current in enumerate(ordered):
        for other in ordered[index + 1 :]:
            if current.end_offset_minutes <= other.start_offset_minutes:
                break
            if current.work_type.is_break or other.work_type.is_break:
                raise DRFValidationError({"segments": "Break segments cannot overlap other segments."})
            if not (current.work_type.can_overlap or other.work_type.can_overlap):
                raise DRFValidationError({"segments": "Monthly shift segments cannot overlap."})
    if shift_request_lookup is not None:
        issues.extend(validate_assignment_against_shift_requests(assignment, active_segments, shift_request_lookup))
    return issues


def _prefetched_active_assignments(plan: MonthlyShiftPlan) -> list[MonthlyShiftAssignment]:
    assignments = (
        MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, is_active=True)
        .select_related("staff", "source_shift_pattern")
        .prefetch_related(
            "segments__work_type",
            "segments__work_area",
        )
        .order_by("work_date", "display_order", "staff_id", "id")
    )
    result = list(assignments)
    for assignment in result:
        assignment.active_segments = [segment for segment in assignment.segments.all() if segment.is_active]
    return result


def build_monthly_plan_content_hash(
    plan: MonthlyShiftPlan,
    assignments: list[MonthlyShiftAssignment] | None = None,
) -> str:
    assignments = assignments if assignments is not None else _prefetched_active_assignments(plan)
    ordered_assignments = sorted(
        assignments,
        key=lambda item: (
            item.work_date,
            item.display_order,
            str(item.staff_id),
            str(item.id),
        ),
    )
    for assignment in ordered_assignments:
        if not hasattr(assignment, "active_segments"):
            assignment.active_segments = [segment for segment in assignment.segments.all() if segment.is_active]
    payload = {
        "plan": {
            "id": str(plan.id),
            "location": str(plan.location_id),
            "year": plan.year,
            "month": plan.month,
            "name": plan.name,
            "notes": plan.notes,
        },
        "assignments": [
            {
                "id": str(assignment.id),
                "work_date": assignment.work_date.isoformat(),
                "staff": str(assignment.staff_id),
                "source_type": assignment.source_type,
                "pattern_code_snapshot": assignment.pattern_code_snapshot,
                "pattern_name_snapshot": assignment.pattern_name_snapshot,
                "pattern_short_name_snapshot": assignment.pattern_short_name_snapshot,
                "notes": assignment.notes,
                "is_customized": assignment.is_customized,
                "display_order": assignment.display_order,
                "segments": [
                    {
                        "id": str(segment.id),
                        "work_type": str(segment.work_type_id),
                        "work_area": str(segment.work_area_id) if segment.work_area_id else None,
                        "work_type_name_snapshot": segment.work_type_name_snapshot,
                        "work_type_short_name_snapshot": segment.work_type_short_name_snapshot,
                        "work_type_color_key_snapshot": segment.work_type_color_key_snapshot,
                        "work_type_is_break_snapshot": segment.work_type_is_break_snapshot,
                        "work_area_name_snapshot": segment.work_area_name_snapshot,
                        "start_offset_minutes": segment.start_offset_minutes,
                        "end_offset_minutes": segment.end_offset_minutes,
                        "display_order": segment.display_order,
                        "notes": segment.notes,
                    }
                    for segment in sorted(
                        getattr(assignment, "active_segments", []),
                        key=lambda item: (item.start_offset_minutes, item.display_order, str(item.id)),
                    )
                ],
            }
            for assignment in ordered_assignments
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def next_publication_version(plan: MonthlyShiftPlan) -> int:
    latest_version = (
        MonthlyShiftPublication.objects.filter(monthly_shift_plan=plan).aggregate(max_version=Max("version"))[
            "max_version"
        ]
        or 0
    )
    return latest_version + 1


def _validation_error_issue(exc: DRFValidationError, *, code: str = "validation_error") -> dict:
    return {"severity": "error", "code": code, "message": str(exc.detail)}


def build_validation_fingerprint(
    *,
    plan: MonthlyShiftPlan,
    content_hash: str,
    summary: dict,
    items: list[dict],
) -> str:
    payload = {
        "plan": str(plan.id),
        "workflow_status": plan.workflow_status,
        "content_hash": content_hash,
        "error_count": summary["error_count"],
        "warning_count": summary["warning_count"],
        "items": [
            {
                "assignment": item.get("assignment") or "",
                "work_date": item.get("work_date") or "",
                "staff": item.get("staff") or "",
                "issues": [
                    {
                        "severity": issue["severity"],
                        "code": issue["code"],
                        "message": issue["message"],
                    }
                    for issue in sorted(
                        item.get("issues", []),
                        key=lambda issue: (issue["severity"], issue["code"], issue["message"]),
                    )
                ],
            }
            for item in sorted(
                items,
                key=lambda item: (
                    item.get("assignment") or "",
                    item.get("work_date") or "",
                    item.get("staff") or "",
                ),
            )
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _publication_preview_response(
    *,
    plan: MonthlyShiftPlan,
    content_hash: str,
    confirmation_stale: bool,
    summary: dict,
    items: list[dict],
) -> dict:
    response = {
        "plan": str(plan.id),
        "workflow_status": plan.workflow_status,
        "content_hash": content_hash,
        "confirmed_content_hash": plan.confirmed_content_hash,
        "confirmation_stale": confirmation_stale,
        "next_publication_version": next_publication_version(plan),
        "summary": summary,
        "items": items,
        "can_confirm": (
            plan.workflow_status == MonthlyShiftPlan.WorkflowStatus.DRAFT
            and plan.is_active
            and summary["error_count"] == 0
            and summary["assignment_count"] > 0
        ),
        "can_publish": (
            plan.workflow_status == MonthlyShiftPlan.WorkflowStatus.CONFIRMED
            and summary["error_count"] == 0
            and not confirmation_stale
            and not plan.publications.filter(is_active=True).exists()
        ),
    }
    response["validation_fingerprint"] = build_validation_fingerprint(
        plan=plan,
        content_hash=content_hash,
        summary=summary,
        items=items,
    )
    return response


def build_publication_preview(
    plan: MonthlyShiftPlan,
    assignments: list[MonthlyShiftAssignment] | None = None,
) -> dict:
    ensure_active_monthly_plan(plan)
    assignments = assignments if assignments is not None else _prefetched_active_assignments(plan)
    content_hash = build_monthly_plan_content_hash(plan, assignments=assignments)
    confirmation_stale = (
        plan.workflow_status in {MonthlyShiftPlan.WorkflowStatus.CONFIRMED, MonthlyShiftPlan.WorkflowStatus.PUBLISHED}
        and content_hash != plan.confirmed_content_hash
    )
    validation_context = build_publication_validation_context(plan=plan, assignments=assignments)
    items = []
    summary = {
        "assignment_count": len(assignments),
        "staff_count": len({assignment.staff_id for assignment in assignments}),
        "segment_count": 0,
        "work_minutes": 0,
        "break_minutes": 0,
        "error_count": 0,
        "warning_count": 0,
    }
    if not assignments:
        summary["error_count"] = 1
        return _publication_preview_response(
            plan=plan,
            content_hash=content_hash,
            confirmation_stale=confirmation_stale,
            summary=summary,
            items=[
                {
                    "scope": "plan",
                    "issues": [
                        {
                            "severity": "error",
                            "code": "empty_plan",
                            "message": "公開対象の勤務がありません。",
                        }
                    ],
                }
            ],
        )

    for assignment in assignments:
        active_segments = assignment.active_segments
        issues = validate_assignments_for_publication(assignment, active_segments, validation_context)
        warning_count = monthly_assignment_warning_count(
            assignment,
            validation_context.capability_lookup,
            segments_attr="active_segments",
        )
        segment_count = len(active_segments)
        work_minutes = sum(
            segment.duration_minutes for segment in active_segments if not segment.work_type_is_break_snapshot
        )
        break_minutes = sum(
            segment.duration_minutes for segment in active_segments if segment.work_type_is_break_snapshot
        )
        summary["segment_count"] += segment_count
        summary["work_minutes"] += work_minutes
        summary["break_minutes"] += break_minutes
        summary["error_count"] += sum(1 for issue in issues if issue["severity"] == "error")
        summary["warning_count"] += sum(1 for issue in issues if issue["severity"] == "warning")
        if issues:
            items.append(
                {
                    "scope": "assignment",
                    "assignment": str(assignment.id),
                    "work_date": assignment.work_date.isoformat(),
                    "staff": str(assignment.staff_id),
                    "staff_display_name": assignment.staff.display_name,
                    "pattern_short_name": assignment.pattern_short_name_snapshot,
                    "warning_count": warning_count,
                    "segment_count": segment_count,
                    "issues": issues,
                }
            )
    return _publication_preview_response(
        plan=plan,
        content_hash=content_hash,
        confirmation_stale=confirmation_stale,
        summary=summary,
        items=items,
    )


def confirm_monthly_shift_plan(*, plan: MonthlyShiftPlan, actor: User, acknowledge_warnings: bool = False) -> dict:
    with transaction.atomic():
        plan = MonthlyShiftPlan.objects.select_for_update().select_related("location").get(pk=plan.pk)
        ensure_monthly_plan_editable(plan)
        assignments = _prefetched_active_assignments(plan)
        preview = build_publication_preview(plan, assignments=assignments)
        if preview["summary"]["error_count"]:
            raise DRFValidationError({"items": preview["items"]})
        if preview["summary"]["warning_count"] and not acknowledge_warnings:
            raise DRFValidationError({"warnings": MONTHLY_PLAN_CONFIRM_WARNING_MESSAGE})
        now = timezone.now()
        plan.workflow_status = MonthlyShiftPlan.WorkflowStatus.CONFIRMED
        plan.confirmed_at = now
        plan.confirmed_by = actor
        plan.confirmed_content_hash = preview["content_hash"]
        plan.updated_by = actor
        plan.save(
            update_fields=[
                "workflow_status",
                "confirmed_at",
                "confirmed_by",
                "confirmed_content_hash",
                "updated_by",
                "updated_at",
            ]
        )
    return preview


def reopen_monthly_shift_plan(*, plan: MonthlyShiftPlan, actor: User):
    with transaction.atomic():
        plan = MonthlyShiftPlan.objects.select_for_update().get(pk=plan.pk)
        ensure_active_monthly_plan(plan)
        if plan.workflow_status != MonthlyShiftPlan.WorkflowStatus.CONFIRMED:
            raise DRFValidationError({"workflow_status": "確定済みの月間シフトのみ確定解除できます。"})
        if plan.publications.filter(is_active=True).exists():
            raise DRFValidationError({"monthly_shift_plan": MONTHLY_PLAN_ACTIVE_PUBLICATION_MESSAGE})
        plan.workflow_status = MonthlyShiftPlan.WorkflowStatus.DRAFT
        plan.confirmed_at = None
        plan.confirmed_by = None
        plan.confirmed_content_hash = ""
        plan.updated_by = actor
        plan.save(
            update_fields=[
                "workflow_status",
                "confirmed_at",
                "confirmed_by",
                "confirmed_content_hash",
                "updated_by",
                "updated_at",
            ]
        )
    return plan


def _create_publication_snapshot(
    *,
    plan: MonthlyShiftPlan,
    actor: User,
    preview: dict,
    assignments: list[MonthlyShiftAssignment] | None = None,
) -> MonthlyShiftPublication:
    assignments = assignments if assignments is not None else _prefetched_active_assignments(plan)
    start_date, end_date = _plan_bounds(plan)
    capability_lookup = build_capability_lookup(
        assignments=assignments,
        location=plan.location,
        start_date=start_date,
        end_date=end_date,
        segments_attr="active_segments",
    )
    publication = MonthlyShiftPublication.objects.create(
        monthly_shift_plan=plan,
        version=next_publication_version(plan),
        content_hash=preview["content_hash"],
        location=plan.location,
        location_name_snapshot=plan.location.name,
        location_short_name_snapshot=plan.location.short_name,
        year=plan.year,
        month=plan.month,
        plan_name_snapshot=plan.name,
        plan_notes_snapshot=plan.notes,
        published_by=actor,
        published_at=timezone.now(),
        is_active=True,
    )
    for assignment in assignments:
        publication_assignment = MonthlyShiftPublicationAssignment.objects.create(
            publication=publication,
            source_assignment=assignment,
            work_date=assignment.work_date,
            staff=assignment.staff,
            staff_display_name_snapshot=assignment.staff.display_name,
            employee_code_snapshot=assignment.staff.employee_code,
            source_type=assignment.source_type,
            is_customized=assignment.is_customized,
            pattern_code_snapshot=assignment.pattern_code_snapshot,
            pattern_name_snapshot=assignment.pattern_name_snapshot,
            pattern_short_name_snapshot=assignment.pattern_short_name_snapshot,
            notes=assignment.notes,
            display_order=assignment.display_order,
            warning_count_snapshot=monthly_assignment_warning_count(
                assignment,
                capability_lookup,
                segments_attr="active_segments",
            ),
        )
        for segment in assignment.active_segments:
            MonthlyShiftPublicationSegment.objects.create(
                publication_assignment=publication_assignment,
                source_segment=segment,
                work_type=segment.work_type,
                work_area=segment.work_area,
                work_type_name_snapshot=segment.work_type_name_snapshot,
                work_type_short_name_snapshot=segment.work_type_short_name_snapshot,
                work_type_color_key_snapshot=segment.work_type_color_key_snapshot,
                work_type_is_break_snapshot=segment.work_type_is_break_snapshot,
                work_area_name_snapshot=segment.work_area_name_snapshot,
                start_offset_minutes=segment.start_offset_minutes,
                end_offset_minutes=segment.end_offset_minutes,
                display_order=segment.display_order,
                notes=segment.notes,
            )
    return publication


def publish_monthly_shift_plan(*, plan: MonthlyShiftPlan, actor: User, acknowledge_warnings: bool = False):
    try:
        with transaction.atomic():
            plan = MonthlyShiftPlan.objects.select_for_update().select_related("location").get(pk=plan.pk)
            ensure_active_monthly_plan(plan)
            if plan.workflow_status != MonthlyShiftPlan.WorkflowStatus.CONFIRMED:
                raise DRFValidationError({"workflow_status": "確定済みの月間シフトのみ公開できます。"})
            if plan.publications.filter(is_active=True).select_for_update().exists():
                raise DRFValidationError({"monthly_shift_plan": MONTHLY_PLAN_ACTIVE_PUBLICATION_MESSAGE})
            assignments = _prefetched_active_assignments(plan)
            preview = build_publication_preview(plan, assignments=assignments)
            if preview["content_hash"] != plan.confirmed_content_hash:
                raise DRFValidationError({"content_hash": MONTHLY_PLAN_STALE_HASH_MESSAGE})
            if preview["summary"]["error_count"]:
                raise DRFValidationError({"items": preview["items"]})
            if preview["summary"]["warning_count"] and not acknowledge_warnings:
                raise DRFValidationError({"warnings": MONTHLY_PLAN_PUBLISH_WARNING_MESSAGE})
            publication = _create_publication_snapshot(plan=plan, actor=actor, preview=preview, assignments=assignments)
            plan.workflow_status = MonthlyShiftPlan.WorkflowStatus.PUBLISHED
            plan.updated_by = actor
            plan.save(update_fields=["workflow_status", "updated_by", "updated_at"])
    except IntegrityError as exc:
        raise _drf_validation(
            exc,
            integrity_message="公開処理が競合しました。再読み込みしてから再実行してください。",
        ) from exc
    return publication, preview


def withdraw_monthly_shift_publication(*, plan: MonthlyShiftPlan, actor: User, reason: str):
    if not reason.strip():
        raise DRFValidationError({"reason": "公開取り下げ理由を入力してください。"})
    with transaction.atomic():
        plan = MonthlyShiftPlan.objects.select_for_update().get(pk=plan.pk)
        ensure_active_monthly_plan(plan)
        if plan.workflow_status != MonthlyShiftPlan.WorkflowStatus.PUBLISHED:
            raise DRFValidationError({"workflow_status": "公開済みの月間シフトのみ取り下げできます。"})
        publication = plan.publications.select_for_update().filter(is_active=True).first()
        if publication is None:
            raise DRFValidationError({"monthly_shift_plan": "公開中のスナップショットが見つかりません。"})
        publication.is_active = False
        publication.withdrawn_by = actor
        publication.withdrawn_at = timezone.now()
        publication.withdrawal_reason = reason.strip()
        publication.save(
            update_fields=[
                "is_active",
                "withdrawn_by",
                "withdrawn_at",
                "withdrawal_reason",
            ]
        )
        plan.workflow_status = MonthlyShiftPlan.WorkflowStatus.CONFIRMED
        plan.updated_by = actor
        plan.save(update_fields=["workflow_status", "updated_by", "updated_at"])
    return publication


def save_monthly_assignment(
    *,
    instance: MonthlyShiftAssignment | None,
    validated_data: dict,
    segments_data: list[dict] | None,
    shift_pattern: ShiftPattern | None,
    actor: User,
):
    try:
        with transaction.atomic():
            if instance is None and validated_data.get("monthly_shift_plan"):
                MonthlyShiftPlan.objects.select_for_update().get(pk=validated_data["monthly_shift_plan"].pk)
            elif instance is not None:
                MonthlyShiftPlan.objects.select_for_update().get(pk=instance.monthly_shift_plan_id)
            assignment = instance or MonthlyShiftAssignment(created_by=actor)
            _validate_assignment_cell_immutable(instance, validated_data)
            for field, value in validated_data.items():
                setattr(assignment, field, value)
            assignment.updated_by = actor
            if instance is None:
                assignment.is_active = True
                assignment.source_type = MonthlyShiftAssignment.SourceType.MANUAL
            ensure_monthly_plan_editable(assignment.monthly_shift_plan)

            save_segments: list[MonthlyShiftSegment]
            validation_segments: list[MonthlyShiftSegment]
            replacing_pattern = shift_pattern is not None
            if shift_pattern is not None:
                if (
                    assignment.monthly_shift_plan_id
                    and shift_pattern.location_id != assignment.monthly_shift_plan.location_id
                ):
                    raise DRFValidationError({"shift_pattern": "Shift pattern location must match plan location."})
                assignment.source_shift_pattern = shift_pattern
                assignment.pattern_code_snapshot = shift_pattern.code
                assignment.pattern_name_snapshot = shift_pattern.name
                assignment.pattern_short_name_snapshot = shift_pattern.short_name
                if instance is not None:
                    assignment.is_customized = True
                validation_segments = _segments_from_pattern(shift_pattern, assignment)
                save_segments = validation_segments
                for existing in assignment.segments.all() if assignment.pk else []:
                    if existing.is_active:
                        existing.is_active = False
                        save_segments.append(existing)
            elif segments_data is not None:
                existing = {
                    str(item.id): item
                    for item in assignment.segments.select_related("work_type", "work_area", "monthly_shift_assignment")
                }
                seen_ids = set()
                validation_segments = []
                save_segments = []
                for payload in segments_data:
                    child_id = str(payload.get("id")) if payload.get("id") else None
                    if child_id:
                        if child_id in seen_ids:
                            raise DRFValidationError({"segments": MONTHLY_SEGMENT_DUPLICATE_MESSAGE})
                        if child_id not in existing:
                            raise DRFValidationError({"segments": "Segment ID does not belong to this assignment."})
                        segment = _segment_from_monthly_payload(assignment, payload, existing[child_id])
                        seen_ids.add(child_id)
                    else:
                        segment = _segment_from_monthly_payload(assignment, payload)
                    segment.is_active = True
                    validation_segments.append(segment)
                    save_segments.append(segment)
                for child_id, segment in existing.items():
                    if child_id in seen_ids:
                        continue
                    if segment.is_active:
                        segment.is_active = False
                        validation_segments.append(segment)
                        save_segments.append(segment)
                if instance is not None:
                    assignment.is_customized = True
            else:
                validation_segments = list(assignment.segments.select_related("work_type", "work_area"))
                save_segments = []

            validate_current_masters = replacing_pattern or segments_data is not None or instance is None
            shift_request_lookup = get_shift_request_lookup(
                assignment.monthly_shift_plan.location,
                assignment.monthly_shift_plan.year,
                assignment.monthly_shift_plan.month,
                [assignment.staff_id],
            )
            warnings = validate_monthly_assignment(
                assignment,
                validation_segments,
                validate_current_masters=validate_current_masters,
                shift_request_lookup=shift_request_lookup,
            )
            error_issues = [issue for issue in warnings if issue["severity"] == "error"]
            if error_issues:
                raise DRFValidationError({"warnings": error_issues})
            if validate_current_masters:
                assignment.full_clean()
            assignment.save()
            for segment in save_segments:
                segment.monthly_shift_assignment = assignment
                if segment.is_active:
                    segment.full_clean()
                segment.save()
            assignment.validation_warnings = warnings
            assignment.replaced_pattern = replacing_pattern
    except (
        DjangoValidationError,
        IntegrityError,
        User.DoesNotExist,
        ShiftPattern.DoesNotExist,
        WorkType.DoesNotExist,
        WorkArea.DoesNotExist,
    ) as exc:
        if isinstance(exc, (DjangoValidationError, IntegrityError)):
            raise _drf_validation(exc, integrity_message=MONTHLY_ASSIGNMENT_DUPLICATE_MESSAGE) from exc
        raise DRFValidationError({"non_field_errors": "Invalid assignment reference."}) from exc
    return assignment


def validate_and_reactivate_monthly_plan(plan: MonthlyShiftPlan):
    original_is_active = plan.is_active
    try:
        with transaction.atomic():
            if plan.workflow_status != MonthlyShiftPlan.WorkflowStatus.DRAFT:
                raise DRFValidationError({"monthly_shift_plan": MONTHLY_PLAN_EDIT_LOCK_MESSAGE})
            plan.is_active = True
            _validate_active_monthly_plan_unique(plan)
            plan.full_clean()
            plan.save(update_fields=["is_active", "updated_at"])
    except (DjangoValidationError, IntegrityError) as exc:
        plan.is_active = original_is_active
        raise _drf_validation(exc, integrity_message=MONTHLY_PLAN_DUPLICATE_MESSAGE) from exc
    return plan


def validate_and_reactivate_monthly_assignment(assignment: MonthlyShiftAssignment):
    original_is_active = assignment.is_active
    try:
        with transaction.atomic():
            ensure_monthly_plan_editable(assignment.monthly_shift_plan)
            assignment.is_active = True
            warnings = validate_monthly_assignment(
                assignment, list(assignment.segments.select_related("work_type", "work_area"))
            )
            assignment.full_clean()
            assignment.save(update_fields=["is_active", "updated_at"])
            assignment.validation_warnings = warnings
    except (DjangoValidationError, IntegrityError) as exc:
        assignment.is_active = original_is_active
        raise _drf_validation(exc, integrity_message=MONTHLY_ASSIGNMENT_DUPLICATE_MESSAGE) from exc
    except DRFValidationError:
        assignment.is_active = original_is_active
        raise
    return assignment


def deactivate_monthly_instance(instance):
    plan = getattr(instance, "monthly_shift_plan", instance)
    ensure_monthly_plan_editable(plan)
    instance.is_active = False
    instance.save(update_fields=["is_active", "updated_at"])


def _candidate_issue_from_exception(exc: DRFValidationError) -> dict:
    return {"severity": "error", "code": "validation_error", "message": str(exc.detail)}


def _candidate_action(
    existing: MonthlyShiftAssignment | None,
    existing_mode: str,
) -> str:
    if existing is None:
        return "create"
    if existing_mode == "skip_existing":
        return "skip_existing"
    if existing.source_type == MonthlyShiftAssignment.SourceType.TEMPLATE and not existing.is_customized:
        return "replace"
    return "skip_manual"


def preview_template_generation(
    *,
    plan: MonthlyShiftPlan,
    weekly_template: WeeklyShiftTemplate,
    existing_mode: str,
    invalid_mode: str,
) -> dict:
    ensure_monthly_plan_editable(plan)
    if existing_mode not in {"skip_existing", "replace_template_generated"}:
        raise DRFValidationError({"existing_mode": "Invalid existing_mode."})
    if invalid_mode not in {"strict", "skip_invalid"}:
        raise DRFValidationError({"invalid_mode": "Invalid invalid_mode."})
    if not weekly_template.is_active:
        raise DRFValidationError({"weekly_shift_template": "Inactive templates cannot be applied."})
    if weekly_template.location_id != plan.location_id:
        raise DRFValidationError({"weekly_shift_template": "Template location must match plan location."})

    existing_by_cell = {
        (item.work_date, item.staff_id): item
        for item in plan.assignments.filter(is_active=True).prefetch_related("segments")
    }
    entries_by_weekday: dict[int, list[WeeklyShiftTemplateEntry]] = {}
    for entry in weekly_template.entries.filter(is_active=True).select_related("staff", "shift_pattern"):
        entries_by_weekday.setdefault(entry.weekday, []).append(entry)
    request_lookup = get_shift_request_lookup(
        plan.location,
        plan.year,
        plan.month,
        [entry.staff_id for entries in entries_by_weekday.values() for entry in entries],
    )

    candidates: list[GenerationCandidate] = []
    for work_date in month_dates(plan.year, plan.month):
        for entry in entries_by_weekday.get(work_date.weekday(), []):
            existing = existing_by_cell.get((work_date, entry.staff_id))
            action = _candidate_action(existing, existing_mode)
            issues = []
            if action in {"create", "replace"}:
                assignment, segments = _assignment_from_pattern(
                    plan=plan,
                    work_date=work_date,
                    staff=entry.staff,
                    pattern=entry.shift_pattern,
                    source_type=MonthlyShiftAssignment.SourceType.TEMPLATE,
                    actor=plan.updated_by,
                    source_entry=entry,
                    existing=existing if action == "replace" else None,
                )
                try:
                    issues.extend(
                        validate_monthly_assignment(
                            assignment,
                            segments,
                            shift_request_lookup=request_lookup,
                        )
                    )
                except DRFValidationError as exc:
                    issues.append(_candidate_issue_from_exception(exc))
            candidates.append(GenerationCandidate(work_date, entry, entry.shift_pattern, action, existing, issues))

    items = []
    summary = {
        "candidate_count": len(candidates),
        "create_count": 0,
        "replace_count": 0,
        "skip_existing_count": 0,
        "skip_manual_count": 0,
        "skip_invalid_count": 0,
        "error_count": 0,
        "warning_count": 0,
    }
    for candidate in candidates:
        has_error = any(issue["severity"] == "error" for issue in candidate.issues)
        action = candidate.action
        if has_error and invalid_mode == "skip_invalid" and action in {"create", "replace"}:
            action = "skip_invalid"
        if action == "create":
            summary["create_count"] += 1
        elif action == "replace":
            summary["replace_count"] += 1
        elif action == "skip_existing":
            summary["skip_existing_count"] += 1
        elif action == "skip_manual":
            summary["skip_manual_count"] += 1
        elif action == "skip_invalid":
            summary["skip_invalid_count"] += 1
        summary["error_count"] += sum(1 for issue in candidate.issues if issue["severity"] == "error")
        summary["warning_count"] += sum(1 for issue in candidate.issues if issue["severity"] == "warning")
        items.append(
            {
                "work_date": candidate.work_date.isoformat(),
                "staff": str(candidate.entry.staff_id),
                "staff_display_name": candidate.entry.staff.display_name,
                "shift_pattern": str(candidate.pattern.id),
                "shift_pattern_short_name": candidate.pattern.short_name,
                "action": action,
                "issues": candidate.issues,
            }
        )
    return {"summary": summary, "items": items}


def apply_template_generation(
    *,
    plan: MonthlyShiftPlan,
    weekly_template: WeeklyShiftTemplate,
    existing_mode: str,
    invalid_mode: str,
    actor: User,
):
    with transaction.atomic():
        plan = MonthlyShiftPlan.objects.select_for_update().get(pk=plan.pk)
        ensure_monthly_plan_editable(plan)
        list(plan.assignments.select_for_update().filter(is_active=True))
        preview = preview_template_generation(
            plan=plan,
            weekly_template=weekly_template,
            existing_mode=existing_mode,
            invalid_mode=invalid_mode,
        )
        if invalid_mode == "strict" and preview["summary"]["error_count"]:
            raise DRFValidationError({"items": "Template generation has errors."})

        created = replaced = skipped = 0
        entry_lookup = {
            (item.weekday, str(item.staff_id), str(item.shift_pattern_id)): item
            for item in weekly_template.entries.filter(is_active=True).select_related("staff", "shift_pattern")
        }
        existing_by_cell = {
            (item.work_date.isoformat(), str(item.staff_id)): item for item in plan.assignments.filter(is_active=True)
        }
        for item in preview["items"]:
            if any(issue["severity"] == "error" for issue in item["issues"]):
                skipped += 1
                continue
            if item["action"] not in {"create", "replace"}:
                skipped += 1
                continue
            work_date = date.fromisoformat(item["work_date"])
            entry = entry_lookup[(work_date.weekday(), item["staff"], item["shift_pattern"])]
            existing = existing_by_cell.get((item["work_date"], item["staff"])) if item["action"] == "replace" else None
            assignment, segments = _assignment_from_pattern(
                plan=plan,
                work_date=work_date,
                staff=entry.staff,
                pattern=entry.shift_pattern,
                source_type=MonthlyShiftAssignment.SourceType.TEMPLATE,
                actor=actor,
                source_entry=entry,
                existing=existing,
            )
            validate_monthly_assignment(assignment, segments)
            assignment.save()
            if existing:
                existing.segments.filter(is_active=True).update(is_active=False, updated_at=timezone.now())
            for segment in segments:
                segment.monthly_shift_assignment = assignment
                segment.save()
            if item["action"] == "create":
                created += 1
            else:
                replaced += 1

        plan.source_weekly_template = weekly_template
        plan.last_generated_at = timezone.now()
        plan.last_generated_by = actor
        plan.updated_by = actor
        plan.save(
            update_fields=[
                "source_weekly_template",
                "last_generated_at",
                "last_generated_by",
                "updated_by",
                "updated_at",
            ]
        )
        preview["summary"]["created_count"] = created
        preview["summary"]["replaced_count"] = replaced
        preview["summary"]["skipped_count"] = skipped
    return preview
