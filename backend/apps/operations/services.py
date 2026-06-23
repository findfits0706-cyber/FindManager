from collections.abc import Iterable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.serializers import ValidationError as DRFValidationError

from apps.accounts.constants import (
    ROLE_SHIFT_MANAGER,
    ROLE_STAFF,
    ROLE_SUPERVISOR,
    ROLE_SYSTEM_ADMIN,
    ROLE_VIEWER,
)
from apps.accounts.models import User
from apps.accounts.services import create_audit_event

from .models import (
    Location,
    StaffCapability,
    StaffLocation,
    WorkArea,
    WorkCategory,
    WorkType,
    WorkTypeAvailability,
)

MASTER_ADMIN_ROLES = {ROLE_SYSTEM_ADMIN}
MASTER_INACTIVE_VIEW_ROLES = {ROLE_SYSTEM_ADMIN, ROLE_SHIFT_MANAGER, ROLE_SUPERVISOR}
MASTER_ACTIVE_VIEW_ROLES = MASTER_INACTIVE_VIEW_ROLES | {ROLE_STAFF, ROLE_VIEWER}
STAFF_SELF_ROLES = {ROLE_STAFF, ROLE_VIEWER}


def user_has_any_role(user: User, roles: Iterable[str]) -> bool:
    return any(user.has_role(role) for role in roles)


def can_manage_masters(user: User) -> bool:
    return user.is_authenticated and user_has_any_role(user, MASTER_ADMIN_ROLES)


def can_view_master_records(user: User) -> bool:
    return user.is_authenticated and user_has_any_role(user, MASTER_ACTIVE_VIEW_ROLES)


def can_view_inactive_master_records(user: User) -> bool:
    return user.is_authenticated and user_has_any_role(user, MASTER_INACTIVE_VIEW_ROLES)


def can_manage_staff_relationships(user: User) -> bool:
    return user.is_authenticated and user_has_any_role(user, {ROLE_SYSTEM_ADMIN, ROLE_SHIFT_MANAGER})


def can_view_staff_relationships(user: User) -> bool:
    return user.is_authenticated and (
        can_manage_staff_relationships(user)
        or user.has_role(ROLE_SUPERVISOR)
        or user_has_any_role(user, STAFF_SELF_ROLES)
    )


def filter_queryset_for_user(queryset, user: User, staff_field: str = "staff"):
    if can_manage_staff_relationships(user) or user.has_role(ROLE_SUPERVISOR):
        return queryset
    if user_has_any_role(user, STAFF_SELF_ROLES):
        return queryset.filter(**{staff_field: user})
    return queryset.none()


def visible_master_queryset(queryset, user: User):
    if can_view_inactive_master_records(user):
        return queryset
    if not user_has_any_role(user, STAFF_SELF_ROLES):
        return queryset.none()

    model = queryset.model
    if model is Location:
        return queryset.filter(is_active=True)
    if model is WorkArea:
        return queryset.filter(is_active=True, location__is_active=True)
    if model is WorkCategory:
        return queryset.filter(is_active=True)
    if model is WorkType:
        return queryset.filter(is_active=True, category__is_active=True)
    if model is WorkTypeAvailability:
        return queryset.filter(
            is_active=True,
            work_type__is_active=True,
            location__is_active=True,
        ).filter(Q(work_area__isnull=True) | Q(work_area__is_active=True))
    return queryset.filter(is_active=True)


EVENT_MAP = {
    "location": {
        "create": "location_created",
        "update": "location_updated",
        "deactivate": "location_deactivated",
        "reactivate": "location_reactivated",
    },
    "work_area": {
        "create": "work_area_created",
        "update": "work_area_updated",
        "deactivate": "work_area_deactivated",
        "reactivate": "work_area_reactivated",
    },
    "work_category": {
        "create": "work_category_created",
        "update": "work_category_updated",
        "deactivate": "work_category_deactivated",
        "reactivate": "work_category_reactivated",
    },
    "work_type": {
        "create": "work_type_created",
        "update": "work_type_updated",
        "deactivate": "work_type_deactivated",
        "reactivate": "work_type_reactivated",
    },
    "work_type_availability": {
        "create": "work_type_availability_created",
        "update": "work_type_availability_updated",
        "deactivate": "work_type_availability_deactivated",
        "reactivate": "work_type_availability_reactivated",
    },
    "staff_location": {
        "create": "staff_location_created",
        "update": "staff_location_updated",
        "deactivate": "staff_location_deactivated",
        "reactivate": "staff_location_reactivated",
    },
    "staff_capability": {
        "create": "staff_capability_created",
        "update": "staff_capability_updated",
        "deactivate": "staff_capability_deactivated",
        "reactivate": "staff_capability_reactivated",
    },
}


def record_operations_event(*, entity: str, action: str, actor: User, request, metadata: dict, target_user=None):
    event_type = EVENT_MAP[entity][action]
    create_audit_event(
        event_type=event_type,
        actor=actor,
        target_user=target_user,
        request=request,
        metadata=metadata,
    )


def deactivate_instance(instance):
    instance.is_active = False
    instance.save(update_fields=["is_active", "updated_at"])


def reactivate_instance(instance):
    instance.is_active = True
    instance.save(update_fields=["is_active", "updated_at"])


def validate_and_reactivate(instance, extra_updates: dict | None = None):
    extra_updates = extra_updates or {}
    original_values = {"is_active": instance.is_active}
    original_values.update({field_name: getattr(instance, field_name) for field_name in extra_updates})

    try:
        with transaction.atomic():
            instance.is_active = True
            for field_name, value in extra_updates.items():
                setattr(instance, field_name, value)
            instance.full_clean()
            update_fields = ["is_active", "updated_at", *extra_updates.keys()]
            instance.save(update_fields=list(dict.fromkeys(update_fields)))
    except DjangoValidationError as exc:
        for field_name, value in original_values.items():
            setattr(instance, field_name, value)
        raise DRFValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        ) from exc

    return instance


def seed_operations(dev_users: dict[str, User]) -> None:
    locations = {
        "main": Location.objects.update_or_create(
            code="main",
            defaults={
                "name": "ファインドスポーツクラブ",
                "short_name": "本館",
                "timezone": "Asia/Tokyo",
                "display_order": 10,
            },
        )[0],
        "findfits": Location.objects.update_or_create(
            code="findfits",
            defaults={
                "name": "FindFits",
                "short_name": "FITS",
                "timezone": "Asia/Tokyo",
                "display_order": 20,
            },
        )[0],
        "findpilates": Location.objects.update_or_create(
            code="findpilates",
            defaults={
                "name": "Find Pilates",
                "short_name": "ピラティス",
                "timezone": "Asia/Tokyo",
                "display_order": 30,
            },
        )[0],
    }

    work_areas = {}
    for location_code, items in {
        "main": [
            ("gym", "ジム"),
            ("front", "フロント"),
            ("pool", "プール"),
            ("studio", "スタジオ"),
            ("office", "事務局"),
            ("all", "全部門共通"),
        ],
        "findfits": [
            ("training", "トレーニングエリア"),
            ("cleaning", "清掃"),
            ("tour", "見学対応"),
        ],
        "findpilates": [
            ("pilates_studio", "ピラティススタジオ"),
            ("self_esthe", "セルフエステ"),
            ("front", "フロント"),
        ],
    }.items():
        for index, (code, name) in enumerate(items, start=1):
            work_areas[(location_code, code)] = WorkArea.objects.update_or_create(
                location=locations[location_code],
                code=code,
                defaults={"name": name, "display_order": index * 10},
            )[0]

    categories = {}
    for index, (code, name) in enumerate(
        [
            ("general", "General"),
            ("reception", "受付"),
            ("cleaning", "清掃"),
            ("instruction", "指導"),
            ("booking", "予約・案内"),
            ("meeting", "会議・研修"),
            ("break", "休憩"),
            ("other", "その他"),
        ],
        start=1,
    ):
        categories[code] = WorkCategory.objects.update_or_create(
            code=code,
            defaults={"name": name, "display_order": index * 10},
        )[0]

    work_types = {}
    work_type_seed = [
        ("gym_duty", "ジムメニュー", "general", 60, "blue", False, False, False, False),
        ("front_duty", "受付対応", "reception", 60, "green", False, False, False, False),
        ("office_work", "バックオフィス", "general", 60, "slate", False, False, False, False),
        ("open_tasks", "オープン業務", "general", 30, "amber", False, False, False, False),
        ("close_tasks", "クローズ業務", "general", 30, "amber", False, False, False, False),
        ("gym_cleaning", "ジム清掃", "cleaning", 30, "cyan", False, False, False, False),
        ("findfits_cleaning", "FindFits清掃", "cleaning", 30, "cyan", False, False, False, False),
        ("facility_cleaning", "館内清掃", "cleaning", 45, "cyan", False, False, False, False),
        ("personal_training", "パーソナルトレーニング", "instruction", 60, "violet", True, False, False, True),
        ("semi_personal", "セミパーソナル", "instruction", 60, "violet", True, False, False, True),
        ("exercise_guidance", "運動指導", "instruction", 45, "violet", True, False, False, True),
        ("first_guidance", "初回ガイダンス", "booking", 60, "pink", True, False, True, True),
        ("repeat_guidance", "継続ガイダンス", "booking", 45, "pink", True, False, True, True),
        ("findfits_tour", "FindFits見学", "booking", 30, "pink", True, False, True, True),
        ("trial", "体験", "booking", 60, "pink", True, False, True, True),
        ("membership", "入会案内", "booking", 45, "pink", False, False, True, True),
        ("meeting", "会議", "meeting", 60, "slate", False, True, False, False),
        ("training", "トレーニング", "meeting", 60, "slate", True, True, False, False),
        ("break", "休憩", "break", 60, "green", False, True, False, False, True),
        ("other", "その他", "other", 60, "red", False, True, False, False),
    ]
    for index, seed in enumerate(work_type_seed, start=1):
        if len(seed) == 10:
            (
                code,
                name,
                category_code,
                duration,
                color_key,
                requires_capability,
                can_overlap,
                is_bookable,
                requires_customer,
                is_break,
            ) = seed
        else:
            (
                code,
                name,
                category_code,
                duration,
                color_key,
                requires_capability,
                can_overlap,
                is_bookable,
                requires_customer,
            ) = seed
            is_break = False
        work_types[code] = WorkType.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "short_name": name,
                "category": categories[category_code],
                "default_duration_minutes": duration,
                "minimum_staff_count": 1,
                "maximum_staff_count": None,
                "color_key": color_key,
                "requires_capability": requires_capability,
                "can_overlap": can_overlap,
                "is_break": is_break,
                "is_bookable": is_bookable,
                "requires_customer": requires_customer,
                "display_order": index * 10,
            },
        )[0]

    availability_seed = [
        ("gym_duty", "main", "gym"),
        ("front_duty", "main", "front"),
        ("gym_cleaning", "main", "gym"),
        ("findfits_cleaning", "findfits", "cleaning"),
        ("facility_cleaning", "main", "all"),
        ("first_guidance", "main", "gym"),
        ("repeat_guidance", "main", "gym"),
        ("findfits_tour", "findfits", "tour"),
        ("trial", "main", "gym"),
        ("membership", "main", "front"),
        ("personal_training", "main", "gym"),
        ("semi_personal", "main", "gym"),
        ("exercise_guidance", "main", "gym"),
    ]
    for work_type_code, location_code, area_code in availability_seed:
        WorkTypeAvailability.objects.update_or_create(
            work_type=work_types[work_type_code],
            location=locations[location_code],
            work_area=work_areas[(location_code, area_code)],
            defaults={"is_active": True},
        )

    today = timezone.localdate()
    for role, user in dev_users.items():
        primary_location = locations["main"] if role != "viewer" else locations["findfits"]
        StaffLocation.objects.update_or_create(
            staff=user,
            location=primary_location,
            valid_from=today,
            valid_until=None,
            defaults={"is_primary": True, "is_active": True, "display_order": 10},
        )

    capability_map = {
        "system_admin": [
            ("gym_duty", "main", "independent"),
            ("front_duty", "main", "trainer"),
            ("first_guidance", "main", "trainer"),
        ],
        "shift_manager": [
            ("gym_duty", "main", "independent"),
            ("front_duty", "main", "independent"),
            ("findfits_tour", "findfits", "assisted"),
        ],
        "supervisor": [("gym_duty", "main", "assisted")],
        "staff": [("gym_duty", "main", "independent"), ("trial", "main", "assisted")],
        "viewer": [("findfits_tour", "findfits", "trainee")],
    }
    for role, capability_items in capability_map.items():
        user = dev_users[role]
        for work_type_code, location_code, level in capability_items:
            StaffCapability.objects.update_or_create(
                staff=user,
                work_type=work_types[work_type_code],
                location=locations[location_code],
                valid_from=today,
                valid_until=None,
                defaults={
                    "level": level,
                    "approved_by": dev_users["system_admin"],
                    "approved_at": timezone.now(),
                    "notes": "",
                    "is_active": True,
                    "display_order": 10,
                },
            )
