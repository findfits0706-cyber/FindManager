from django.db import transaction
from django.db.models import Count, Prefetch, Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.models import User
from apps.operations.models import StaffLocation

from .models import MonthlyShiftAssignment, MonthlyShiftPlan, MonthlyShiftSegment, ShiftPattern, WeeklyShiftTemplate
from .serializers import (
    MonthlyShiftAssignmentListSerializer,
    MonthlyShiftAssignmentSerializer,
    MonthlyShiftPlanListSerializer,
    MonthlyShiftPlanSerializer,
    ShiftPatternDuplicateSerializer,
    ShiftPatternListSerializer,
    ShiftPatternSerializer,
    TemplateGenerationSerializer,
    WeeklyShiftTemplateDuplicateSerializer,
    WeeklyShiftTemplateListSerializer,
    WeeklyShiftTemplateSerializer,
)
from .services import (
    apply_template_generation,
    build_capability_lookup,
    can_manage_shifts,
    can_view_shifts,
    deactivate_instance,
    deactivate_monthly_instance,
    duplicate_shift_pattern,
    duplicate_weekly_template,
    ensure_active_monthly_plan,
    month_dates,
    monthly_assignment_metadata,
    monthly_assignment_warning_count,
    monthly_plan_metadata,
    preview_template_generation,
    record_shift_event,
    shift_pattern_metadata,
    validate_and_reactivate_monthly_assignment,
    validate_and_reactivate_monthly_plan,
    validate_and_reactivate_pattern,
    validate_and_reactivate_template,
    weekly_template_metadata,
)
from .timeline_services import build_timeline_response


class ShiftSettingsPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return can_view_shifts(request.user)
        return can_manage_shifts(request.user)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class ShiftManagementBaseViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [ShiftSettingsPermission]

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

    def get_serializer_class(self):
        if self.action == "list":
            return ShiftPatternListSerializer
        return ShiftPatternSerializer

    def get_queryset(self):
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
        with transaction.atomic():
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
        with transaction.atomic():
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
        with transaction.atomic():
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
        with transaction.atomic():
            validate_and_reactivate_pattern(instance)
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
        with transaction.atomic():
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

    def get_serializer_class(self):
        if self.action == "list":
            return WeeklyShiftTemplateListSerializer
        return WeeklyShiftTemplateSerializer

    def get_queryset(self):
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
        with transaction.atomic():
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
        with transaction.atomic():
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
        with transaction.atomic():
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
        with transaction.atomic():
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
        with transaction.atomic():
            instance = duplicate_weekly_template(source, **serializer.validated_data)
            record_shift_event(
                entity="weekly_shift_template",
                action="duplicate",
                actor=request.user,
                request=request,
                metadata=weekly_template_metadata(instance, source_id=source.id),
            )
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)


class MonthlyShiftPlanViewSet(ShiftManagementBaseViewSet):
    serializer_class = MonthlyShiftPlanSerializer
    queryset = (
        MonthlyShiftPlan.objects.select_related("location", "source_weekly_template", "last_generated_by")
        .annotate(
            active_assignment_count=Count("assignments", filter=Q(assignments__is_active=True), distinct=True),
            active_staff_count=Count("assignments__staff", filter=Q(assignments__is_active=True), distinct=True),
        )
        .order_by("-year", "-month", "location__display_order")
    )

    def get_serializer_class(self):
        if self.action == "list":
            return MonthlyShiftPlanListSerializer
        return MonthlyShiftPlanSerializer

    def get_queryset(self):
        queryset = self.queryset
        params = self.request.query_params
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("year"):
            queryset = queryset.filter(year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(month=params["month"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        if params.get("search"):
            term = params["search"]
            queryset = queryset.filter(Q(name__icontains=term) | Q(notes__icontains=term))
        return queryset

    def perform_create(self, serializer):
        self._require_manage()
        with transaction.atomic():
            instance = serializer.save()
            record_shift_event(
                entity="monthly_shift_plan",
                action="create",
                actor=self.request.user,
                request=self.request,
                metadata=monthly_plan_metadata(instance),
            )

    def perform_update(self, serializer):
        self._require_manage()
        with transaction.atomic():
            instance = serializer.save()
            record_shift_event(
                entity="monthly_shift_plan",
                action="update",
                actor=self.request.user,
                request=self.request,
                metadata=monthly_plan_metadata(instance),
            )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        with transaction.atomic():
            deactivate_monthly_instance(instance)
            record_shift_event(
                entity="monthly_shift_plan",
                action="deactivate",
                actor=request.user,
                request=request,
                metadata=monthly_plan_metadata(instance),
            )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        with transaction.atomic():
            validate_and_reactivate_monthly_plan(instance)
            record_shift_event(
                entity="monthly_shift_plan",
                action="reactivate",
                actor=request.user,
                request=request,
                metadata=monthly_plan_metadata(instance),
            )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["get"])
    def matrix(self, request, pk=None):
        plan = self.get_object()
        dates = month_dates(plan.year, plan.month)
        start_date, end_date = dates[0], dates[-1]
        assigned_only = request.query_params.get("assigned_only") == "true"
        staff_search = request.query_params.get("staff_search", "")
        assignment_queryset = (
            MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, is_active=True)
            .select_related("staff")
            .prefetch_related(
                Prefetch(
                    "segments",
                    queryset=MonthlyShiftSegment.objects.filter(is_active=True).select_related("work_type"),
                )
            )
        )
        assignment_list = list(assignment_queryset)
        assignment_staff_ids = {item.staff_id for item in assignment_list}
        inactive_assignment_staff_ids = set(
            MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, is_active=False).values_list(
                "staff_id", flat=True
            )
        )
        staff_location_ids = set(
            StaffLocation.objects.filter(location=plan.location, is_active=True, valid_from__lte=end_date)
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start_date))
            .values_list("staff_id", flat=True)
        )
        staff_ids = (
            assignment_staff_ids
            if assigned_only
            else assignment_staff_ids | staff_location_ids | inactive_assignment_staff_ids
        )
        capability_lookup = build_capability_lookup(
            assignments=assignment_list,
            location=plan.location,
            start_date=start_date,
            end_date=end_date,
        )

        staff_queryset = User.objects.filter(id__in=staff_ids)
        if staff_search:
            staff_queryset = staff_queryset.filter(
                Q(display_name__icontains=staff_search)
                | Q(username__icontains=staff_search)
                | Q(employee_code__icontains=staff_search)
            )
        staff_list = list(staff_queryset.order_by("employee_code", "display_name"))
        assignments_by_staff_date = {
            (str(item.staff_id), item.work_date.isoformat()): item
            for item in assignment_list
            if item.staff_id in staff_ids
        }
        inactive_queryset = (
            MonthlyShiftAssignment.objects.filter(monthly_shift_plan=plan, is_active=False, staff_id__in=staff_ids)
            .select_related("staff")
            .order_by("staff_id", "work_date", "-updated_at", "-created_at")
        )
        inactive_by_staff_date = {}
        for item in inactive_queryset:
            key = (str(item.staff_id), item.work_date.isoformat())
            if key in assignments_by_staff_date or key in inactive_by_staff_date:
                continue
            inactive_by_staff_date[key] = item
        rows = []
        for staff in staff_list:
            assignments = {}
            inactive_assignments = {}
            for work_date in dates:
                assignment = assignments_by_staff_date.get((str(staff.id), work_date.isoformat()))
                if assignment is not None:
                    active_segments = list(assignment.segments.all())
                    assignments[work_date.isoformat()] = {
                        "id": str(assignment.id),
                        "pattern_short_name": assignment.pattern_short_name_snapshot,
                        "start_offset_minutes": min(
                            (segment.start_offset_minutes for segment in active_segments), default=None
                        ),
                        "end_offset_minutes": max(
                            (segment.end_offset_minutes for segment in active_segments), default=None
                        ),
                        "source_type": assignment.source_type,
                        "is_customized": assignment.is_customized,
                        "warning_count": monthly_assignment_warning_count(assignment, capability_lookup),
                    }
                    continue
                inactive = inactive_by_staff_date.get((str(staff.id), work_date.isoformat()))
                if inactive is not None:
                    inactive_assignments[work_date.isoformat()] = {
                        "id": str(inactive.id),
                        "pattern_short_name": inactive.pattern_short_name_snapshot,
                    }
            rows.append(
                {
                    "staff": str(staff.id),
                    "staff_display_name": staff.display_name,
                    "employee_code": staff.employee_code,
                    "assignments": assignments,
                    "inactive_assignments": inactive_assignments,
                }
            )
        weekday_labels = ["月", "火", "水", "木", "金", "土", "日"]
        return Response(
            {
                "plan": {
                    "id": str(plan.id),
                    "location": str(plan.location_id),
                    "location_name": plan.location.name,
                    "year": plan.year,
                    "month": plan.month,
                    "name": plan.name,
                },
                "dates": [
                    {
                        "date": item.isoformat(),
                        "day": item.day,
                        "weekday": item.weekday(),
                        "weekday_label": weekday_labels[item.weekday()],
                        "is_saturday": item.weekday() == 5,
                        "is_sunday": item.weekday() == 6,
                    }
                    for item in dates
                ],
                "rows": rows,
            }
        )

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        plan = self.get_object()
        return Response(build_timeline_response(plan, request.query_params))

    @action(detail=True, methods=["post"], url_path="preview-template-generation")
    def preview_template_generation(self, request, pk=None):
        self._require_manage()
        plan = self.get_object()
        ensure_active_monthly_plan(plan)
        serializer = TemplateGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = preview_template_generation(
            plan=plan,
            weekly_template=serializer.validated_data["weekly_shift_template"],
            existing_mode=serializer.validated_data["existing_mode"],
            invalid_mode=serializer.validated_data["invalid_mode"],
        )
        return Response(result)

    @action(detail=True, methods=["post"], url_path="apply-template")
    def apply_template(self, request, pk=None):
        self._require_manage()
        plan = self.get_object()
        ensure_active_monthly_plan(plan)
        serializer = TemplateGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            result = apply_template_generation(
                plan=plan,
                weekly_template=serializer.validated_data["weekly_shift_template"],
                existing_mode=serializer.validated_data["existing_mode"],
                invalid_mode=serializer.validated_data["invalid_mode"],
                actor=request.user,
            )
            record_shift_event(
                entity="monthly_shift_template",
                action="apply",
                actor=request.user,
                request=request,
                metadata={
                    "plan_id": str(plan.id),
                    "location_id": str(plan.location_id),
                    "year": plan.year,
                    "month": plan.month,
                    "weekly_shift_template_id": str(serializer.validated_data["weekly_shift_template"].id),
                    "existing_mode": serializer.validated_data["existing_mode"],
                    "invalid_mode": serializer.validated_data["invalid_mode"],
                    "candidate_count": result["summary"]["candidate_count"],
                    "created_count": result["summary"].get("created_count", result["summary"]["create_count"]),
                    "replaced_count": result["summary"].get("replaced_count", result["summary"]["replace_count"]),
                    "skipped_count": result["summary"].get("skipped_count", 0),
                    "skip_existing_count": result["summary"]["skip_existing_count"],
                    "skip_manual_count": result["summary"]["skip_manual_count"],
                    "skip_invalid_count": result["summary"]["skip_invalid_count"],
                    "error_count": result["summary"]["error_count"],
                    "warning_count": result["summary"]["warning_count"],
                },
            )
        return Response(result)


class MonthlyShiftAssignmentViewSet(ShiftManagementBaseViewSet):
    serializer_class = MonthlyShiftAssignmentSerializer
    queryset = (
        MonthlyShiftAssignment.objects.select_related(
            "monthly_shift_plan",
            "monthly_shift_plan__location",
            "staff",
            "source_shift_pattern",
        )
        .prefetch_related(Prefetch("segments"))
        .order_by("work_date", "staff__employee_code")
    )

    def get_serializer_class(self):
        if self.action == "list":
            return MonthlyShiftAssignmentListSerializer
        return MonthlyShiftAssignmentSerializer

    def get_queryset(self):
        queryset = self.queryset
        params = self.request.query_params
        if params.get("monthly_shift_plan"):
            queryset = queryset.filter(monthly_shift_plan_id=params["monthly_shift_plan"])
        if params.get("work_date"):
            queryset = queryset.filter(work_date=params["work_date"])
        if params.get("date_from"):
            queryset = queryset.filter(work_date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(work_date__lte=params["date_to"])
        if params.get("staff"):
            queryset = queryset.filter(staff_id=params["staff"])
        if params.get("source_type"):
            queryset = queryset.filter(source_type=params["source_type"])
        if params.get("is_customized") in {"true", "false"}:
            queryset = queryset.filter(is_customized=params["is_customized"] == "true")
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        return queryset

    def perform_create(self, serializer):
        self._require_manage()
        with transaction.atomic():
            instance = serializer.save()
            record_shift_event(
                entity="monthly_shift_assignment",
                action="create",
                actor=self.request.user,
                request=self.request,
                metadata=monthly_assignment_metadata(instance),
            )

    def perform_update(self, serializer):
        self._require_manage()
        with transaction.atomic():
            instance = serializer.save()
            record_shift_event(
                entity="monthly_shift_assignment",
                action="update",
                actor=self.request.user,
                request=self.request,
                metadata=monthly_assignment_metadata(instance),
            )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        with transaction.atomic():
            deactivate_monthly_instance(instance)
            record_shift_event(
                entity="monthly_shift_assignment",
                action="deactivate",
                actor=request.user,
                request=request,
                metadata=monthly_assignment_metadata(instance),
            )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        self._require_manage()
        instance = self.get_object()
        with transaction.atomic():
            validate_and_reactivate_monthly_assignment(instance)
            record_shift_event(
                entity="monthly_shift_assignment",
                action="reactivate",
                actor=request.user,
                request=request,
                metadata=monthly_assignment_metadata(instance),
            )
        return Response(self.get_serializer(instance).data)
