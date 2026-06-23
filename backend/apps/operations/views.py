from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import (
    Location,
    StaffCapability,
    StaffLocation,
    WorkArea,
    WorkCategory,
    WorkType,
    WorkTypeAvailability,
)
from .serializers import (
    LocationSerializer,
    MyStaffCapabilitySerializer,
    MyStaffLocationSerializer,
    StaffCapabilitySerializer,
    StaffLocationSerializer,
    WorkAreaSerializer,
    WorkCategorySerializer,
    WorkTypeAvailabilitySerializer,
    WorkTypeSerializer,
)
from .services import (
    can_manage_masters,
    can_manage_staff_relationships,
    deactivate_instance,
    filter_queryset_for_user,
    record_operations_event,
    validate_and_reactivate,
    visible_master_queryset,
)


class OperationsBaseViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return self.queryset


class MasterViewSet(OperationsBaseViewSet):
    reactivate_enabled = True
    entity_name = ""

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return visible_master_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        if not can_manage_masters(self.request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = serializer.save(is_active=True)
        record_operations_event(
            entity=self.entity_name,
            action="create",
            actor=self.request.user,
            request=self.request,
            metadata={
                "id": str(instance.id),
                "code": getattr(instance, "code", ""),
                "name": getattr(instance, "name", ""),
            },
        )

    def perform_update(self, serializer):
        if not can_manage_masters(self.request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = serializer.save()
        record_operations_event(
            entity=self.entity_name,
            action="update",
            actor=self.request.user,
            request=self.request,
            metadata={
                "id": str(instance.id),
                "code": getattr(instance, "code", ""),
                "name": getattr(instance, "name", ""),
            },
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        if not can_manage_masters(request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = self.get_object()
        deactivate_instance(instance)
        record_operations_event(
            entity=self.entity_name,
            action="deactivate",
            actor=request.user,
            request=request,
            metadata={"id": str(instance.id), "code": getattr(instance, "code", "")},
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        if not self.reactivate_enabled:
            raise PermissionDenied("This resource does not support reactivation.")
        if not can_manage_masters(request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = self.get_object()
        validate_and_reactivate(instance)
        record_operations_event(
            entity=self.entity_name,
            action="reactivate",
            actor=request.user,
            request=request,
            metadata={"id": str(instance.id), "code": getattr(instance, "code", "")},
        )
        return Response(self.get_serializer(instance).data)


class LocationViewSet(MasterViewSet):
    queryset = Location.objects.all().order_by("display_order", "code")
    serializer_class = LocationSerializer
    entity_name = "location"

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("name"):
            queryset = queryset.filter(name__icontains=params["name"])
        if params.get("code"):
            queryset = queryset.filter(code__icontains=params["code"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        return queryset


class WorkAreaViewSet(MasterViewSet):
    queryset = (
        WorkArea.objects.select_related("location").all().order_by("location__display_order", "display_order", "code")
    )
    serializer_class = WorkAreaSerializer
    entity_name = "work_area"

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("name"):
            queryset = queryset.filter(name__icontains=params["name"])
        if params.get("code"):
            queryset = queryset.filter(code__icontains=params["code"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        return queryset


class WorkCategoryViewSet(MasterViewSet):
    queryset = WorkCategory.objects.all().order_by("display_order", "code")
    serializer_class = WorkCategorySerializer
    entity_name = "work_category"

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("name"):
            queryset = queryset.filter(name__icontains=params["name"])
        if params.get("code"):
            queryset = queryset.filter(code__icontains=params["code"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        return queryset


class WorkTypeViewSet(MasterViewSet):
    queryset = (
        WorkType.objects.select_related("category")
        .prefetch_related("availabilities")
        .all()
        .order_by("display_order", "code")
    )
    serializer_class = WorkTypeSerializer
    entity_name = "work_type"

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("category"):
            queryset = queryset.filter(category_id=params["category"])
        if params.get("location"):
            queryset = queryset.filter(availabilities__location_id=params["location"])
        if params.get("work_area"):
            queryset = queryset.filter(availabilities__work_area_id=params["work_area"])
        for field in ["is_bookable", "requires_capability", "is_break", "is_active"]:
            if params.get(field) in {"true", "false"}:
                queryset = queryset.filter(**{field: params[field] == "true"})
        if params.get("search"):
            queryset = queryset.filter(Q(name__icontains=params["search"]) | Q(code__icontains=params["search"]))
        return queryset.distinct()


class WorkTypeAvailabilityViewSet(OperationsBaseViewSet):
    queryset = (
        WorkTypeAvailability.objects.select_related("work_type", "location", "work_area")
        .all()
        .order_by(
            "location__display_order",
            "work_type__display_order",
            "created_at",
        )
    )
    serializer_class = WorkTypeAvailabilitySerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = visible_master_queryset(self.queryset, self.request.user)
        params = self.request.query_params
        if params.get("work_type"):
            queryset = queryset.filter(work_type_id=params["work_type"])
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("work_area"):
            queryset = queryset.filter(work_area_id=params["work_area"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        return queryset

    def perform_create(self, serializer):
        if not can_manage_masters(self.request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = serializer.save(is_active=True)
        record_operations_event(
            entity="work_type_availability",
            action="create",
            actor=self.request.user,
            request=self.request,
            metadata={
                "id": str(instance.id),
                "work_type_id": str(instance.work_type_id),
                "location_id": str(instance.location_id),
            },
        )

    def perform_update(self, serializer):
        if not can_manage_masters(self.request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = serializer.save()
        record_operations_event(
            entity="work_type_availability",
            action="update",
            actor=self.request.user,
            request=self.request,
            metadata={
                "id": str(instance.id),
                "work_type_id": str(instance.work_type_id),
                "location_id": str(instance.location_id),
            },
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        if not can_manage_masters(request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = self.get_object()
        deactivate_instance(instance)
        record_operations_event(
            entity="work_type_availability",
            action="deactivate",
            actor=request.user,
            request=request,
            metadata={
                "id": str(instance.id),
                "work_type_id": str(instance.work_type_id),
                "location_id": str(instance.location_id),
            },
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        if not can_manage_masters(request.user):
            raise PermissionDenied("Only system admins can perform this action.")
        instance = self.get_object()
        validate_and_reactivate(instance)
        record_operations_event(
            entity="work_type_availability",
            action="reactivate",
            actor=request.user,
            request=request,
            metadata={
                "id": str(instance.id),
                "work_type_id": str(instance.work_type_id),
                "location_id": str(instance.location_id),
            },
        )
        return Response(self.get_serializer(instance).data)


class StaffLocationViewSet(OperationsBaseViewSet):
    queryset = (
        StaffLocation.objects.select_related("staff", "location").all().order_by("staff__display_name", "-valid_from")
    )
    serializer_class = StaffLocationSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = filter_queryset_for_user(self.queryset, self.request.user)
        params = self.request.query_params
        if params.get("staff"):
            queryset = queryset.filter(staff_id=params["staff"])
        if params.get("staff_search"):
            queryset = queryset.filter(
                Q(staff__display_name__icontains=params["staff_search"])
                | Q(staff__username__icontains=params["staff_search"])
                | Q(staff__employee_code__icontains=params["staff_search"])
            )
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("is_primary") in {"true", "false"}:
            queryset = queryset.filter(is_primary=params["is_primary"] == "true")
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        if params.get("reference_date"):
            queryset = queryset.filter(valid_from__lte=params["reference_date"]).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=params["reference_date"])
            )
        return queryset

    def perform_create(self, serializer):
        if not can_manage_staff_relationships(self.request.user):
            raise PermissionDenied("You do not have permission to manage staff assignments.")
        instance = serializer.save(is_active=True)
        record_operations_event(
            entity="staff_location",
            action="create",
            actor=self.request.user,
            request=self.request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "location_id": str(instance.location_id),
            },
        )

    def perform_update(self, serializer):
        if not can_manage_staff_relationships(self.request.user):
            raise PermissionDenied("You do not have permission to manage staff assignments.")
        instance = serializer.save()
        record_operations_event(
            entity="staff_location",
            action="update",
            actor=self.request.user,
            request=self.request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "location_id": str(instance.location_id),
            },
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        if not can_manage_staff_relationships(request.user):
            raise PermissionDenied("You do not have permission to manage staff assignments.")
        instance = self.get_object()
        deactivate_instance(instance)
        record_operations_event(
            entity="staff_location",
            action="deactivate",
            actor=request.user,
            request=request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "location_id": str(instance.location_id),
            },
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        if not can_manage_staff_relationships(request.user):
            raise PermissionDenied("You do not have permission to manage staff assignments.")
        instance = self.get_object()
        validate_and_reactivate(instance)
        record_operations_event(
            entity="staff_location",
            action="reactivate",
            actor=request.user,
            request=request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "location_id": str(instance.location_id),
            },
        )
        return Response(self.get_serializer(instance).data)


class StaffCapabilityViewSet(OperationsBaseViewSet):
    queryset = (
        StaffCapability.objects.select_related("staff", "work_type", "location", "approved_by")
        .all()
        .order_by(
            "staff__display_name",
            "-valid_from",
        )
    )
    serializer_class = StaffCapabilitySerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = filter_queryset_for_user(self.queryset, self.request.user)
        params = self.request.query_params
        if params.get("staff"):
            queryset = queryset.filter(staff_id=params["staff"])
        if params.get("work_type"):
            queryset = queryset.filter(work_type_id=params["work_type"])
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("level"):
            queryset = queryset.filter(level=params["level"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        if params.get("reference_date"):
            queryset = queryset.filter(valid_from__lte=params["reference_date"]).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=params["reference_date"])
            )
        return queryset

    def perform_create(self, serializer):
        if not can_manage_staff_relationships(self.request.user):
            raise PermissionDenied("You do not have permission to manage staff capabilities.")
        instance = serializer.save(
            is_active=True,
            approved_by=self.request.user,
            approved_at=timezone.now(),
        )
        record_operations_event(
            entity="staff_capability",
            action="create",
            actor=self.request.user,
            request=self.request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "work_type_id": str(instance.work_type_id),
            },
        )

    def perform_update(self, serializer):
        if not can_manage_staff_relationships(self.request.user):
            raise PermissionDenied("You do not have permission to manage staff capabilities.")
        instance = serializer.save(approved_by=self.request.user, approved_at=timezone.now())
        record_operations_event(
            entity="staff_capability",
            action="update",
            actor=self.request.user,
            request=self.request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "work_type_id": str(instance.work_type_id),
            },
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        if not can_manage_staff_relationships(request.user):
            raise PermissionDenied("You do not have permission to manage staff capabilities.")
        instance = self.get_object()
        deactivate_instance(instance)
        record_operations_event(
            entity="staff_capability",
            action="deactivate",
            actor=request.user,
            request=request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "work_type_id": str(instance.work_type_id),
            },
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        if not can_manage_staff_relationships(request.user):
            raise PermissionDenied("You do not have permission to manage staff capabilities.")
        instance = self.get_object()
        validate_and_reactivate(
            instance,
            extra_updates={
                "approved_by": request.user,
                "approved_at": timezone.now(),
            },
        )
        record_operations_event(
            entity="staff_capability",
            action="reactivate",
            actor=request.user,
            request=request,
            target_user=instance.staff,
            metadata={
                "id": str(instance.id),
                "staff_id": str(instance.staff_id),
                "work_type_id": str(instance.work_type_id),
            },
        )
        return Response(self.get_serializer(instance).data)


class MyStaffLocationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MyStaffLocationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return StaffLocation.objects.select_related("location").filter(staff=self.request.user).order_by("-valid_from")


class MyStaffCapabilityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MyStaffCapabilitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            StaffCapability.objects.select_related("work_type", "location", "approved_by")
            .filter(staff=self.request.user)
            .order_by("-valid_from")
        )
