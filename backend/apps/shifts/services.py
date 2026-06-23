from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.serializers import ValidationError as DRFValidationError

from apps.accounts.constants import ROLE_SHIFT_MANAGER, ROLE_SUPERVISOR, ROLE_SYSTEM_ADMIN
from apps.accounts.models import User
from apps.accounts.services import create_audit_event
from apps.operations.models import Location, StaffLocation, WorkArea, WorkType, WorkTypeAvailability

from .models import ShiftPattern, ShiftPatternSegment, WeeklyShiftTemplate, WeeklyShiftTemplateEntry

MANAGE_ROLES = {ROLE_SYSTEM_ADMIN, ROLE_SHIFT_MANAGER}
VIEW_ROLES = MANAGE_ROLES | {ROLE_SUPERVISOR}
IMMUTABLE_LOCATION_MESSAGE = "拠点は作成後変更できません。別拠点用に複製してください。"
DUPLICATE_CHILD_ID_MESSAGE = "同じ子要素IDが複数回指定されています。"


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
}


def _drf_validation(exc: DjangoValidationError | IntegrityError):
    if isinstance(exc, DjangoValidationError):
        return DRFValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        )
    return DRFValidationError({"non_field_errors": ["Duplicate or invalid data."]})


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
        raise _drf_validation(exc) from exc
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
        raise _drf_validation(exc) from exc
    return pattern


def _validate_weekly_entries(template: WeeklyShiftTemplate, entries: list[WeeklyShiftTemplateEntry]):
    if not template.location.is_active:
        raise DRFValidationError({"location": "Inactive locations cannot be assigned."})
    seen = set()
    for entry in [item for item in entries if item.is_active]:
        try:
            entry.full_clean(exclude=["weekly_shift_template"] if not entry.weekly_shift_template_id else None)
        except DjangoValidationError as exc:
            raise _drf_validation(exc) from exc
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
            raise _drf_validation(exc) from exc
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
        raise _drf_validation(exc) from exc
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
        raise _drf_validation(exc) from exc
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
        raise _drf_validation(exc) from exc
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
