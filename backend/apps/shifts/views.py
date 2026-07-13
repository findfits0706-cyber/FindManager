from datetime import date
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.models import User
from apps.operations.models import StaffLocation

from .models import (
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftPublication,
    MonthlyShiftPublicationAssignment,
    MonthlyShiftPublicationSegment,
    MonthlyShiftSegment,
    ShiftPattern,
    ShiftRequestItem,
    ShiftRequestPeriod,
    ShiftRequestSubmission,
    WeeklyShiftTemplate,
)
from .serializers import (
    MonthlyShiftAssignmentListSerializer,
    MonthlyShiftAssignmentSerializer,
    MonthlyShiftPlanListSerializer,
    MonthlyShiftPlanSerializer,
    MonthlyShiftPublicationListSerializer,
    MonthlyShiftPublicationSerializer,
    MyPublishedShiftSerializer,
    PublicationAcknowledgeSerializer,
    PublicationReopenSerializer,
    PublicationWithdrawSerializer,
    ShiftPatternDuplicateSerializer,
    ShiftPatternListSerializer,
    ShiftPatternSerializer,
    ShiftRequestPeriodSerializer,
    ShiftRequestReturnSerializer,
    ShiftRequestSubmissionSaveSerializer,
    ShiftRequestSubmissionSerializer,
    TemplateGenerationSerializer,
    WeeklyShiftTemplateDuplicateSerializer,
    WeeklyShiftTemplateListSerializer,
    WeeklyShiftTemplateSerializer,
)
from .services import (
    apply_template_generation,
    build_capability_lookup,
    build_publication_preview,
    can_manage_shifts,
    can_view_shifts,
    confirm_monthly_shift_plan,
    deactivate_instance,
    deactivate_monthly_instance,
    duplicate_shift_pattern,
    duplicate_weekly_template,
    ensure_monthly_plan_editable,
    get_or_create_shift_request_submission,
    get_shift_request_info_lookup,
    get_shift_request_lookup,
    get_shift_request_target_staff_counts,
    lock_shift_request_submission,
    month_dates,
    monthly_assignment_metadata,
    monthly_assignment_warning_count,
    monthly_plan_metadata,
    preview_template_generation,
    publish_monthly_shift_plan,
    record_shift_event,
    reopen_monthly_shift_plan,
    return_shift_request_submission,
    save_shift_request_period,
    save_shift_request_submission,
    set_shift_request_period_active,
    set_shift_request_period_status,
    shift_pattern_metadata,
    shift_request_items_for_display,
    shift_request_period_metadata,
    shift_request_submission_metadata,
    submit_shift_request_submission,
    unlock_shift_request_submission,
    unsubmit_shift_request_submission,
    validate_and_reactivate_monthly_assignment,
    validate_and_reactivate_monthly_plan,
    validate_and_reactivate_pattern,
    validate_and_reactivate_template,
    validate_assignment_against_shift_requests,
    weekly_template_metadata,
    withdraw_monthly_shift_publication,
)
from .timeline_services import build_timeline_response


def publication_base_queryset():
    return MonthlyShiftPublication.objects.select_related(
        "monthly_shift_plan",
        "location",
        "published_by",
        "withdrawn_by",
    ).annotate(
        assignment_total=Count("assignments", distinct=True),
        staff_total=Count("assignments__staff", distinct=True),
        segment_total=Count("assignments__segments", distinct=True),
    )


def publication_detail_queryset():
    return publication_base_queryset().prefetch_related(
        Prefetch(
            "assignments",
            queryset=MonthlyShiftPublicationAssignment.objects.select_related("staff").prefetch_related(
                Prefetch(
                    "segments",
                    queryset=MonthlyShiftPublicationSegment.objects.select_related("work_type", "work_area"),
                    to_attr="prefetched_segments",
                )
            ),
        )
    )


class ShiftSettingsPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(view, "action", None) == "publication_preview":
            return can_view_shifts(request.user)
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
        MonthlyShiftPlan.objects.select_related(
            "location",
            "source_weekly_template",
            "last_generated_by",
            "confirmed_by",
        )
        .annotate(
            active_assignment_count=Count("assignments", filter=Q(assignments__is_active=True), distinct=True),
            active_staff_count=Count("assignments__staff", filter=Q(assignments__is_active=True), distinct=True),
            publication_total=Count("publications", distinct=True),
        )
        .prefetch_related(
            Prefetch(
                "publications",
                queryset=MonthlyShiftPublication.objects.filter(is_active=True)
                .select_related("published_by")
                .order_by("-version"),
                to_attr="active_publications",
            )
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
        if params.get("workflow_status"):
            queryset = queryset.filter(workflow_status=params["workflow_status"])
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
        request_lookup = get_shift_request_lookup(plan.location, plan.year, plan.month, staff_ids)
        request_info_lookup = get_shift_request_info_lookup(plan.location, plan.year, plan.month, staff_ids)
        request_period = (
            ShiftRequestPeriod.objects.select_related("location")
            .annotate(
                submission_count=Count("submissions", distinct=True),
                draft_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.DRAFT),
                    distinct=True,
                ),
                submitted_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.SUBMITTED),
                    distinct=True,
                ),
                returned_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.RETURNED),
                    distinct=True,
                ),
                locked_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.LOCKED),
                    distinct=True,
                ),
                item_count=Count("submissions__items", filter=Q(submissions__items__is_active=True), distinct=True),
            )
            .filter(location=plan.location, year=plan.year, month=plan.month, is_active=True)
            .first()
        )
        request_period_data = None
        if request_period is not None:
            request_period.target_staff_count = get_shift_request_target_staff_counts([request_period]).get(
                str(request_period.id), 0
            )
            request_period_data = ShiftRequestPeriodSerializer(request_period).data

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
                request_items = request_info_lookup.get((str(staff.id), work_date.isoformat()), [])
                if assignment is not None:
                    active_segments = list(assignment.segments.all())
                    request_issues = validate_assignment_against_shift_requests(
                        assignment, active_segments, request_lookup
                    )
                    capability_warning_count = monthly_assignment_warning_count(assignment, capability_lookup)
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
                        "warning_count": capability_warning_count
                        + sum(1 for issue in request_issues if issue["severity"] == "warning"),
                        "issues": request_issues,
                        "shift_requests": shift_request_items_for_display(request_items),
                    }
                    continue
                prefer_issues = [
                    {
                        "severity": "info",
                        "code": "preferred_work_day",
                        "message": "勤務希望日です。",
                    }
                    for item in request_items
                    if item.request_type == ShiftRequestItem.RequestType.PREFER_WORK
                ]
                inactive = inactive_by_staff_date.get((str(staff.id), work_date.isoformat()))
                if inactive is not None:
                    inactive_assignments[work_date.isoformat()] = {
                        "id": str(inactive.id),
                        "pattern_short_name": inactive.pattern_short_name_snapshot,
                    }
                if request_items or prefer_issues:
                    assignments.setdefault(
                        work_date.isoformat(),
                        {
                            "id": None,
                            "pattern_short_name": "",
                            "start_offset_minutes": None,
                            "end_offset_minutes": None,
                            "source_type": "",
                            "is_customized": False,
                            "warning_count": 0,
                            "issues": prefer_issues,
                            "shift_requests": shift_request_items_for_display(request_items),
                        },
                    )
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
                "shift_request_period": request_period_data,
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
        ensure_monthly_plan_editable(plan)
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
        ensure_monthly_plan_editable(plan)
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

    @action(detail=True, methods=["post"], url_path="publication-preview")
    def publication_preview(self, request, pk=None):
        plan = self.get_object()
        return Response(build_publication_preview(plan))

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        self._require_manage()
        serializer = PublicationAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            plan = self.get_object()
            preview = confirm_monthly_shift_plan(
                plan=plan,
                actor=request.user,
                acknowledge_warnings=serializer.validated_data["acknowledge_warnings"],
            )
            plan.refresh_from_db()
            record_shift_event(
                entity="monthly_shift_plan",
                action="confirm",
                actor=request.user,
                request=request,
                metadata={
                    "plan_id": str(plan.id),
                    "location_id": str(plan.location_id),
                    "year": plan.year,
                    "month": plan.month,
                    "content_hash": preview["content_hash"],
                    "staff_count": preview["summary"]["staff_count"],
                    "assignment_count": preview["summary"]["assignment_count"],
                    "segment_count": preview["summary"]["segment_count"],
                    "warning_count": preview["summary"]["warning_count"],
                },
            )
            response_data = {"plan": self.get_serializer(plan).data, "preview": preview}
        return Response(response_data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        self._require_manage()
        serializer = PublicationReopenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")
        with transaction.atomic():
            source_plan = self.get_object()
            previous_content_hash = source_plan.confirmed_content_hash
            plan = reopen_monthly_shift_plan(plan=source_plan, actor=request.user)
            record_shift_event(
                entity="monthly_shift_plan",
                action="reopen",
                actor=request.user,
                request=request,
                metadata={
                    "plan_id": str(plan.id),
                    "previous_content_hash": previous_content_hash,
                    "reason": reason,
                },
            )
            response_data = self.get_serializer(plan).data
        return Response(response_data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        self._require_manage()
        serializer = PublicationAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            plan = self.get_object()
            publication, preview = publish_monthly_shift_plan(
                plan=plan,
                actor=request.user,
                acknowledge_warnings=serializer.validated_data["acknowledge_warnings"],
            )
            plan.refresh_from_db()
            publication = publication_base_queryset().get(pk=publication.pk)
            record_shift_event(
                entity="monthly_shift_plan",
                action="publish",
                actor=request.user,
                request=request,
                metadata={
                    "plan_id": str(plan.id),
                    "publication_id": str(publication.id),
                    "version": publication.version,
                    "content_hash": preview["content_hash"],
                    "staff_count": preview["summary"]["staff_count"],
                    "assignment_count": preview["summary"]["assignment_count"],
                    "segment_count": preview["summary"]["segment_count"],
                    "warning_count": preview["summary"]["warning_count"],
                },
            )
            response_data = {
                "plan": self.get_serializer(plan).data,
                "publication": MonthlyShiftPublicationListSerializer(publication).data,
                "preview": preview,
            }
        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="withdraw-publication")
    def withdraw_publication(self, request, pk=None):
        self._require_manage()
        serializer = PublicationWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]
        with transaction.atomic():
            plan = self.get_object()
            publication = withdraw_monthly_shift_publication(
                plan=plan,
                actor=request.user,
                reason=reason,
            )
            plan.refresh_from_db()
            publication = publication_base_queryset().get(pk=publication.pk)
            record_shift_event(
                entity="monthly_shift_plan",
                action="withdraw",
                actor=request.user,
                request=request,
                metadata={
                    "plan_id": str(plan.id),
                    "publication_id": str(publication.id),
                    "version": publication.version,
                    "reason": reason,
                },
            )
            response_data = {
                "plan": self.get_serializer(plan).data,
                "publication": MonthlyShiftPublicationListSerializer(publication).data,
            }
        return Response(response_data)

    @action(detail=True, methods=["get"])
    def publications(self, request, pk=None):
        plan = self.get_object()
        queryset = (
            MonthlyShiftPublication.objects.filter(monthly_shift_plan=plan)
            .select_related("published_by", "withdrawn_by")
            .annotate(
                assignment_total=Count("assignments", distinct=True),
                staff_total=Count("assignments__staff", distinct=True),
                segment_total=Count("assignments__segments", distinct=True),
            )
            .order_by("-version")
        )
        return Response(MonthlyShiftPublicationListSerializer(queryset, many=True).data)


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


class MonthlyShiftPublicationViewSet(viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "head", "options"]
    permission_classes = [ShiftSettingsPermission]
    queryset = publication_base_queryset().order_by("-published_at", "-version")

    def get_serializer_class(self):
        if self.action == "list":
            return MonthlyShiftPublicationListSerializer
        return MonthlyShiftPublicationSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.action == "retrieve":
            queryset = publication_detail_queryset().order_by("-published_at", "-version")
        params = self.request.query_params
        if params.get("monthly_shift_plan"):
            queryset = queryset.filter(monthly_shift_plan_id=params["monthly_shift_plan"])
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("year"):
            queryset = queryset.filter(year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(month=params["month"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        return queryset


class ShiftRequestPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(view, "basename", "") in {"my-shift-request-period"}:
            return True
        if request.method in permissions.SAFE_METHODS or getattr(view, "action", None) in {"submissions"}:
            return can_view_shifts(request.user)
        return can_manage_shifts(request.user)


def shift_request_submission_queryset():
    return (
        ShiftRequestSubmission.objects.select_related(
            "request_period",
            "request_period__location",
            "staff",
            "submitted_by",
            "returned_by",
        )
        .annotate(
            item_count=Count("items", filter=Q(items__is_active=True), distinct=True),
            day_off_count=Count(
                "items",
                filter=Q(items__is_active=True, items__request_type=ShiftRequestItem.RequestType.DAY_OFF),
                distinct=True,
            ),
            unavailable_count=Count(
                "items",
                filter=Q(items__is_active=True, items__request_type=ShiftRequestItem.RequestType.UNAVAILABLE),
                distinct=True,
            ),
            prefer_count=Count(
                "items",
                filter=Q(
                    items__is_active=True,
                    items__request_type__in=[
                        ShiftRequestItem.RequestType.PREFER_WORK,
                        ShiftRequestItem.RequestType.PREFER_TIME,
                    ],
                ),
                distinct=True,
            ),
            has_note=Count(
                "items",
                filter=Q(items__is_active=True, items__request_type=ShiftRequestItem.RequestType.NOTE),
                distinct=True,
            ),
        )
        .prefetch_related(
            Prefetch(
                "items",
                queryset=ShiftRequestItem.objects.filter(is_active=True).select_related("work_type", "work_area"),
            )
        )
    )


def get_shift_request_period_for_update(pk):
    return ShiftRequestPeriod.objects.select_for_update(of=("self",)).select_related("location").get(pk=pk)


def get_shift_request_submission_for_update(pk):
    return (
        ShiftRequestSubmission.objects.select_for_update(of=("self",))
        .select_related("request_period", "request_period__location", "staff")
        .get(pk=pk)
    )


class ShiftRequestPeriodViewSet(viewsets.ModelViewSet):
    permission_classes = [ShiftRequestPermission]
    serializer_class = ShiftRequestPeriodSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        queryset = (
            ShiftRequestPeriod.objects.select_related("location")
            .annotate(
                submission_count=Count("submissions", distinct=True),
                draft_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.DRAFT),
                    distinct=True,
                ),
                submitted_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.SUBMITTED),
                    distinct=True,
                ),
                returned_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.RETURNED),
                    distinct=True,
                ),
                locked_count=Count(
                    "submissions",
                    filter=Q(submissions__status=ShiftRequestSubmission.Status.LOCKED),
                    distinct=True,
                ),
                item_count=Count("submissions__items", filter=Q(submissions__items__is_active=True), distinct=True),
            )
            .order_by("-year", "-month", "location__display_order", "created_at")
        )
        params = self.request.query_params
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("year"):
            queryset = queryset.filter(year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(month=params["month"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        return queryset

    def _attach_target_staff_counts(self, periods):
        counts = get_shift_request_target_staff_counts(list(periods))
        for period in periods:
            period.target_staff_count = counts.get(str(period.id), 0)
        return periods

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            periods = self._attach_target_staff_counts(list(page))
            serializer = self.get_serializer(periods, many=True)
            return self.get_paginated_response(serializer.data)
        periods = self._attach_target_staff_counts(list(queryset))
        serializer = self.get_serializer(periods, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        period = self.get_object()
        self._attach_target_staff_counts([period])
        return Response(self.get_serializer(period).data)

    def update(self, request, *args, **kwargs):
        if "status" in request.data:
            raise ValidationError({"status": "statusはaction endpointで変更してください。"})
        if self.get_object().status == ShiftRequestPeriod.Status.ARCHIVED:
            raise ValidationError({"status": "Archived periods cannot be edited."})
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if "status" in request.data:
            raise ValidationError({"status": "statusはaction endpointで変更してください。"})
        if self.get_object().status == ShiftRequestPeriod.Status.ARCHIVED:
            raise ValidationError({"status": "Archived periods cannot be edited."})
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        with transaction.atomic():
            period = save_shift_request_period(
                instance=None, validated_data=serializer.validated_data, actor=self.request.user
            )
            record_shift_event(
                entity="shift_request_period",
                action="create",
                actor=self.request.user,
                request=self.request,
                metadata=shift_request_period_metadata(period),
            )
            serializer.instance = period

    def perform_update(self, serializer):
        with transaction.atomic():
            period = save_shift_request_period(
                instance=self.get_object(),
                validated_data=serializer.validated_data,
                actor=self.request.user,
            )
            record_shift_event(
                entity="shift_request_period",
                action="update",
                actor=self.request.user,
                request=self.request,
                metadata=shift_request_period_metadata(period),
            )
            serializer.instance = period

    def _status_action(self, request, status_value: str, action_name: str, pk=None):
        self._require_manage()
        with transaction.atomic():
            period = set_shift_request_period_status(
                get_shift_request_period_for_update(pk), status_value, actor=request.user
            )
            record_shift_event(
                entity="shift_request_period",
                action=action_name,
                actor=request.user,
                request=request,
                metadata=shift_request_period_metadata(period),
            )
        return Response(self.get_serializer(period).data)

    def _require_manage(self):
        if not can_manage_shifts(self.request.user):
            raise PermissionDenied("権限がありません。")

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        return self._status_action(request, ShiftRequestPeriod.Status.OPEN, "open", pk)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._status_action(request, ShiftRequestPeriod.Status.CLOSED, "close", pk)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._status_action(request, ShiftRequestPeriod.Status.OPEN, "reopen", pk)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return self._status_action(request, ShiftRequestPeriod.Status.ARCHIVED, "archive", pk)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        self._require_manage()
        with transaction.atomic():
            period = set_shift_request_period_active(
                get_shift_request_period_for_update(pk), is_active=False, actor=request.user
            )
            record_shift_event(
                entity="shift_request_period",
                action="update",
                actor=request.user,
                request=request,
                metadata=shift_request_period_metadata(period),
            )
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        self._require_manage()
        with transaction.atomic():
            period = set_shift_request_period_active(
                get_shift_request_period_for_update(pk), is_active=True, actor=request.user
            )
            record_shift_event(
                entity="shift_request_period",
                action="update",
                actor=request.user,
                request=request,
                metadata=shift_request_period_metadata(period),
            )
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["get"])
    def submissions(self, request, pk=None):
        period = self.get_object()
        serializer = ShiftRequestSubmissionSerializer(
            shift_request_submission_queryset().filter(request_period=period),
            many=True,
        )
        return Response(serializer.data)


class ShiftRequestSubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ShiftRequestPermission]
    serializer_class = ShiftRequestSubmissionSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = shift_request_submission_queryset().order_by(
            "-request_period__year",
            "-request_period__month",
            "staff__employee_code",
        )
        params = self.request.query_params
        if params.get("request_period"):
            queryset = queryset.filter(request_period_id=params["request_period"])
        if params.get("location"):
            queryset = queryset.filter(request_period__location_id=params["location"])
        if params.get("year"):
            queryset = queryset.filter(request_period__year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(request_period__month=params["month"])
        if params.get("staff"):
            queryset = queryset.filter(staff_id=params["staff"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("submitted") in {"true", "false"}:
            queryset = queryset.filter(
                status=ShiftRequestSubmission.Status.SUBMITTED
                if params["submitted"] == "true"
                else ShiftRequestSubmission.Status.DRAFT
            )
        return queryset

    def _require_manage(self):
        if not can_manage_shifts(self.request.user):
            raise PermissionDenied("権限がありません。")

    def _submission_action(self, request, action_name: str, pk=None):
        self._require_manage()
        serializer = ShiftRequestReturnSerializer(data=request.data) if action_name == "return" else None
        reason = ""
        if serializer is not None:
            serializer.is_valid(raise_exception=True)
            reason = serializer.validated_data["reason"]
        with transaction.atomic():
            submission = get_shift_request_submission_for_update(pk)
            if action_name == "return":
                submission = return_shift_request_submission(submission=submission, actor=request.user, reason=reason)
            elif action_name == "lock":
                submission = lock_shift_request_submission(submission=submission, actor=request.user)
            else:
                submission = unlock_shift_request_submission(submission=submission, actor=request.user)
            record_shift_event(
                entity="shift_request_submission",
                action=action_name,
                actor=request.user,
                request=request,
                metadata=shift_request_submission_metadata(submission),
            )
        submission = shift_request_submission_queryset().get(pk=submission.pk)
        return Response(self.get_serializer(submission).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_submission(self, request, pk=None):
        return self._submission_action(request, "return", pk)

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        return self._submission_action(request, "lock", pk)

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        return self._submission_action(request, "unlock", pk)


class MyShiftRequestPeriodViewSet(viewsets.GenericViewSet):
    permission_classes = [ShiftRequestPermission]
    serializer_class = ShiftRequestPeriodSerializer
    http_method_names = ["get", "put", "patch", "post", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        if "staff" in params:
            raise ValidationError({"staff": "staffクエリパラメータは指定できません。"})
        staff_locations = StaffLocation.objects.filter(staff=self.request.user, is_active=True).values_list(
            "location_id", flat=True
        )
        queryset = ShiftRequestPeriod.objects.select_related("location").filter(
            location_id__in=staff_locations, is_active=True
        )
        if params.get("year"):
            queryset = queryset.filter(year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(month=params["month"])
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        return queryset.order_by("-year", "-month", "location__display_order")

    def _period_serializer_context(self, periods):
        period_ids = [period.id for period in periods]
        submission_map = {
            str(submission.request_period_id): submission
            for submission in ShiftRequestSubmission.objects.filter(
                request_period_id__in=period_ids,
                staff=self.request.user,
            ).annotate(item_count=Count("items", filter=Q(items__is_active=True), distinct=True))
        }
        return {
            **self.get_serializer_context(),
            "target_staff_counts": get_shift_request_target_staff_counts(periods),
            "my_submission_map": submission_map,
        }

    def list(self, request, *args, **kwargs):
        periods = list(self.get_queryset())
        serializer = self.get_serializer(periods, many=True, context=self._period_serializer_context(periods))
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        period = self.get_object()
        return Response(self.get_serializer(period, context=self._period_serializer_context([period])).data)

    def _submission(self):
        return get_or_create_shift_request_submission(period=self.get_object(), staff=self.request.user)

    @action(detail=True, methods=["get", "put", "patch"])
    def submission(self, request, pk=None):
        submission = self._submission()
        if request.method == "GET":
            return Response(ShiftRequestSubmissionSerializer(submission).data)
        serializer = ShiftRequestSubmissionSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            submission = save_shift_request_submission(
                submission=submission,
                notes=serializer.validated_data.get("notes", ""),
                items_data=serializer.validated_data.get("items", []),
                actor=request.user,
            )
            record_shift_event(
                entity="shift_request_submission",
                action="save",
                actor=request.user,
                request=request,
                metadata=shift_request_submission_metadata(submission),
            )
        return Response(ShiftRequestSubmissionSerializer(submission).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        with transaction.atomic():
            submission = submit_shift_request_submission(submission=self._submission(), actor=request.user)
            record_shift_event(
                entity="shift_request_submission",
                action="submit",
                actor=request.user,
                request=request,
                metadata=shift_request_submission_metadata(submission),
            )
        return Response(ShiftRequestSubmissionSerializer(submission).data)

    @action(detail=True, methods=["post"])
    def unsubmit(self, request, pk=None):
        with transaction.atomic():
            submission = unsubmit_shift_request_submission(submission=self._submission(), actor=request.user)
            record_shift_event(
                entity="shift_request_submission",
                action="unsubmit",
                actor=request.user,
                request=request,
                metadata=shift_request_submission_metadata(submission),
            )
        return Response(ShiftRequestSubmissionSerializer(submission).data)


class MyPublishedShiftsPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class MyPublishedShiftViewSet(viewsets.GenericViewSet):
    http_method_names = ["get", "head", "options"]
    permission_classes = [MyPublishedShiftsPermission]
    serializer_class = MyPublishedShiftSerializer

    def _parse_date(self, value: str | None, field: str) -> date:
        if not value:
            raise ValidationError({field: "必須です。"})
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError({field: "YYYY-MM-DD形式で指定してください。"}) from exc

    def _location_id(self) -> str | None:
        location_id = self.request.query_params.get("location")
        if not location_id:
            return None
        try:
            UUID(location_id)
        except ValueError as exc:
            raise ValidationError({"location": "有効なUUIDを指定してください。"}) from exc
        return location_id

    def _validated_params(self):
        params = self.request.query_params
        if "staff" in params:
            raise ValidationError({"staff": "staffクエリパラメータは指定できません。"})
        date_from = self._parse_date(params.get("date_from"), "date_from")
        date_to = self._parse_date(params.get("date_to"), "date_to")
        if date_from > date_to:
            raise ValidationError({"date_to": "date_from以降の日付を指定してください。"})
        if (date_to - date_from).days > 61:
            raise ValidationError({"date_to": "検索範囲は最大62日です。"})
        return date_from, date_to, self._location_id()

    def get_queryset(self):
        date_from, date_to, location_id = self._validated_params()
        queryset = (
            MonthlyShiftPublicationAssignment.objects.select_related(
                "publication",
                "publication__monthly_shift_plan",
            )
            .filter(
                staff=self.request.user,
                work_date__gte=date_from,
                work_date__lte=date_to,
                publication__is_active=True,
                publication__withdrawn_at__isnull=True,
            )
            .prefetch_related(
                Prefetch(
                    "segments",
                    queryset=MonthlyShiftPublicationSegment.objects.select_related("work_type", "work_area"),
                    to_attr="prefetched_segments",
                )
            )
            .order_by("work_date", "display_order", "created_at")
        )
        if location_id:
            queryset = queryset.filter(publication__location_id=location_id)
        return queryset

    def list(self, request, *args, **kwargs):
        date_from, date_to, _location_id = self._validated_params()
        weekday_labels = ["月", "火", "水", "木", "金", "土", "日"]
        dates = []
        current = date_from
        while current <= date_to:
            dates.append(
                {
                    "date": current.isoformat(),
                    "weekday": current.weekday(),
                    "weekday_label": weekday_labels[current.weekday()],
                    "is_saturday": current.weekday() == 5,
                    "is_sunday": current.weekday() == 6,
                }
            )
            current = date.fromordinal(current.toordinal() + 1)
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "range": {
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                },
                "dates": dates,
                "shifts": serializer.data,
            }
        )
