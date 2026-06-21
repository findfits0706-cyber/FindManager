from collections.abc import Iterable

from django.utils import timezone

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
MASTER_VIEW_ROLES = {ROLE_SYSTEM_ADMIN, ROLE_SHIFT_MANAGER, ROLE_SUPERVISOR}
STAFF_SELF_ROLES = {ROLE_STAFF, ROLE_VIEWER}


def user_has_any_role(user: User, roles: Iterable[str]) -> bool:
    return any(user.has_role(role) for role in roles)


def can_manage_masters(user: User) -> bool:
    return user.is_authenticated and user_has_any_role(user, MASTER_ADMIN_ROLES)


def can_view_master_records(user: User) -> bool:
    return user.is_authenticated and (
        user_has_any_role(user, MASTER_VIEW_ROLES) or user_has_any_role(user, STAFF_SELF_ROLES)
    )


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
    if user_has_any_role(user, MASTER_VIEW_ROLES):
        return queryset
    if user_has_any_role(user, STAFF_SELF_ROLES):
        return queryset.filter(is_active=True)
    return queryset.none()


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


def seed_operations(dev_users: dict[str, User]) -> None:
    locations = {
        "main": Location.objects.update_or_create(
            code="main",
            defaults={
                "name": "ファインドスポーツクラブ",
                "short_name": "本部",
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
            ("office", "事務所"),
            ("all", "全部署共通"),
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
        ("open_tasks", "オープン作業", "general", 30, "amber", False, False, False, False),
        ("close_tasks", "クローズ作業", "general", 30, "amber", False, False, False, False),
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
