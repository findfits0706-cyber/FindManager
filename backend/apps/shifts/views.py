from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.serializers import ValidationError as DRFValidationError

from .models import ShiftPattern, WeeklyShiftTemplate
from .serializers import (
    ShiftPatternDuplicateSerializer,
    ShiftPatternSerializer,
    WeeklyShiftTemplateDuplicateSerializer,
    WeeklyShiftTemplateSerializer,
)
from .services import (
    can_manage_shifts,
    can_view_shifts,
    deactivate_instance,
    duplicate_shift_pattern,
    duplicate_weekly_template,
    record_shift_event,
    shift_pattern_metadata,
    validate_and_reactivate_pattern,
    validate_and_reactivate_template,
    weekly_template_metadata,
)


class ShiftManagementBaseViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [permissions.IsAuthenticated]

    def _require_manage(self):
        if not can_manage_shifts(self.request.user):
            raise PermissionDenied("You do not have permission to manage shift settings.")


class ShiftPatternViewSet(ShiftManagementBaseViewSet):
    serializer_class = ShiftPatternSerializer
    queryset = (
        ShiftPattern.objects.select_related("location")
        .prefetch_related("segments__work_type", "segments__work_area")
        .order_by("location__display_order", "display_order", "code")
    )

    def get_queryset(self):
        if not can_view_shifts(self.request.user):
            return self.queryset.none()
        queryset = self.queryset
        params = self.request.query_params
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        if params.get("search"):
            term = params["search"]
            queryset = queryset.filter(
                Q(code__icontains=term)
                | Q(name__icontains=term)
                | Q(short_name__icontains=term)
                | Q(description__icontains=term)
            )
        return queryset

    def perform_create(self, serializer):
        self._require_manage()
        instance = serializer.save()
        record_shift_event(
            entity="shift_pattern",
            action="create",
            actor=self.request.user,
            request=self.request,
            metadata=shift_pattern_metadata(instance),
        )

    def perform_update(self, serializer):
        self._require_manage()
        instance = serializer.save()
        record_shift_event(
            entity="shift_pattern",
            action="update",
            actor=self.request.user,
            request=self.request,
            metadata=shift_pattern_metadata(instance),
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        deactivate_instance(instance)
        record_shift_event(
            entity="shift_pattern",
            action="deactivate",
            actor=request.user,
            request=request,
            metadata=shift_pattern_metadata(instance),
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        try:
            validate_and_reactivate_pattern(instance)
        except DRFValidationError:
            raise
        record_shift_event(
            entity="shift_pattern",
            action="reactivate",
            actor=request.user,
            request=request,
            metadata=shift_pattern_metadata(instance),
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        self._require_manage()
        source = self.get_object()
        serializer = ShiftPatternDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = duplicate_shift_pattern(source, **serializer.validated_data)
        record_shift_event(
            entity="shift_pattern",
            action="duplicate",
            actor=request.user,
            request=request,
            metadata=shift_pattern_metadata(instance, source_id=source.id),
        )
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)


class WeeklyShiftTemplateViewSet(ShiftManagementBaseViewSet):
    serializer_class = WeeklyShiftTemplateSerializer
    queryset = (
        WeeklyShiftTemplate.objects.select_related("location")
        .prefetch_related("entries__staff", "entries__shift_pattern")
        .order_by("location__display_order", "display_order", "code")
    )

    def get_queryset(self):
        if not can_view_shifts(self.request.user):
            return self.queryset.none()
        queryset = self.queryset
        params = self.request.query_params
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        if params.get("staff"):
            queryset = queryset.filter(entries__staff_id=params["staff"], entries__is_active=True)
        if params.get("search"):
            term = params["search"]
            queryset = queryset.filter(
                Q(code__icontains=term) | Q(name__icontains=term) | Q(description__icontains=term)
            )
        return queryset.distinct()

    def perform_create(self, serializer):
        self._require_manage()
        instance = serializer.save()
        record_shift_event(
            entity="weekly_shift_template",
            action="create",
            actor=self.request.user,
            request=self.request,
            metadata=weekly_template_metadata(instance),
        )

    def perform_update(self, serializer):
        self._require_manage()
        instance = serializer.save()
        record_shift_event(
            entity="weekly_shift_template",
            action="update",
            actor=self.request.user,
            request=self.request,
            metadata=weekly_template_metadata(instance),
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        deactivate_instance(instance)
        record_shift_event(
            entity="weekly_shift_template",
            action="deactivate",
            actor=request.user,
            request=request,
            metadata=weekly_template_metadata(instance),
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        validate_and_reactivate_template(instance)
        record_shift_event(
            entity="weekly_shift_template",
            action="reactivate",
            actor=request.user,
            request=request,
            metadata=weekly_template_metadata(instance),
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        self._require_manage()
        source = self.get_object()
        serializer = WeeklyShiftTemplateDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = duplicate_weekly_template(source, **serializer.validated_data)
        record_shift_event(
            entity="weekly_shift_template",
            action="duplicate",
            actor=request.user,
            request=request,
            metadata=weekly_template_metadata(instance, source_id=source.id),
        )
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)
