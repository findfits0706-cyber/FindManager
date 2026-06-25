import calendar
from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework.serializers import ValidationError as DRFValidationError

from apps.accounts.constants import ROLE_SHIFT_MANAGER, ROLE_SUPERVISOR, ROLE_SYSTEM_ADMIN
from apps.accounts.models import User
from apps.accounts.services import create_audit_event
from apps.operations.models import Location, StaffCapability, StaffLocation, WorkArea, WorkType, WorkTypeAvailability

from .models import (
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftSegment,
    ShiftPattern,
    ShiftPatternSegment,
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


def validate_monthly_assignment(
    assignment: MonthlyShiftAssignment,
    segments: list[MonthlyShiftSegment],
    *,
    validate_current_masters: bool = True,
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
    return issues


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
            ensure_active_monthly_plan(assignment.monthly_shift_plan)

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
            warnings = validate_monthly_assignment(
                assignment,
                validation_segments,
                validate_current_masters=validate_current_masters,
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
            ensure_active_monthly_plan(assignment.monthly_shift_plan)
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
    ensure_active_monthly_plan(plan)
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
                    issues.extend(validate_monthly_assignment(assignment, segments))
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
        ensure_active_monthly_plan(plan)
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
