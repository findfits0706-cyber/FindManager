from datetime import date
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.models import User
from apps.operations.models import StaffLocation

from .models import (
    AttendanceClosingPeriod,
    AttendanceClosingRecordSnapshot,
    AttendanceClosingStaffSummary,
    AttendanceCorrectionRequest,
    AttendanceEvent,
    AttendanceRecord,
    LaborCostEstimateAllowanceSnapshot,
    LaborCostEstimatePeriod,
    LaborCostEstimateRecordSnapshot,
    LaborCostEstimateStaffSummary,
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftPublication,
    MonthlyShiftPublicationAssignment,
    MonthlyShiftPublicationSegment,
    MonthlyShiftSegment,
    ShiftChangeRequest,
    ShiftPattern,
    ShiftRequestItem,
    ShiftRequestPeriod,
    ShiftRequestSubmission,
    StaffAllowanceAssignment,
    StaffCompensationProfile,
    WeeklyShiftTemplate,
)
from .serializers import (
    AttendanceClockEventSerializer,
    AttendanceClockInSerializer,
    AttendanceClosingCloseSerializer,
    AttendanceClosingManagerNoteSerializer,
    AttendanceClosingPeriodSerializer,
    AttendanceClosingRecordSnapshotSerializer,
    AttendanceClosingStaffSummarySerializer,
    AttendanceCorrectionRequestSerializer,
    AttendanceCorrectionSaveSerializer,
    AttendanceManagerNoteSerializer,
    AttendanceManualAdjustSerializer,
    AttendanceRecordSerializer,
    LaborCostEstimateAllowanceSnapshotSerializer,
    LaborCostEstimateFinalizeSerializer,
    LaborCostEstimateManagerNoteSerializer,
    LaborCostEstimatePeriodSerializer,
    LaborCostEstimateRecordSnapshotSerializer,
    LaborCostEstimateStaffSummarySerializer,
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
    ShiftChangeRequestActionSerializer,
    ShiftChangeRequestManagerNoteSerializer,
    ShiftChangeRequestSaveSerializer,
    ShiftChangeRequestSerializer,
    ShiftPatternDuplicateSerializer,
    ShiftPatternListSerializer,
    ShiftPatternSerializer,
    ShiftRequestPeriodSerializer,
    ShiftRequestReturnSerializer,
    ShiftRequestSubmissionSaveSerializer,
    ShiftRequestSubmissionSerializer,
    StaffAllowanceAssignmentSerializer,
    StaffCompensationProfileSerializer,
    TemplateGenerationSerializer,
    WeeklyShiftTemplateDuplicateSerializer,
    WeeklyShiftTemplateListSerializer,
    WeeklyShiftTemplateSerializer,
)
from .services import (
    add_self_attendance_event,
    apply_attendance_correction_request,
    apply_shift_change_request,
    apply_template_generation,
    approve_attendance_correction_request,
    approve_shift_change_request,
    archive_attendance_period,
    archive_labor_cost_estimate,
    attendance_closing_period_metadata,
    attendance_correction_metadata,
    attendance_record_metadata,
    attendance_record_summary,
    build_attendance_closing_preview,
    build_capability_lookup,
    build_labor_cost_preview,
    build_publication_preview,
    can_manage_labor_costs,
    can_manage_shifts,
    can_view_shifts,
    cancel_attendance_correction_request,
    cancel_shift_change_request,
    clock_in_attendance,
    close_attendance_period,
    close_shift_change_request,
    confirm_attendance_record,
    confirm_monthly_shift_plan,
    deactivate_instance,
    deactivate_monthly_instance,
    duplicate_shift_pattern,
    duplicate_weekly_template,
    ensure_monthly_plan_editable,
    export_attendance_closing_csv,
    export_labor_cost_estimate_csv,
    finalize_labor_cost_estimate,
    get_attendance_closed_period_lookup,
    get_attendance_lookup,
    get_or_create_shift_request_submission,
    get_shift_change_request_assignment_lookup,
    get_shift_change_request_lookup,
    get_shift_request_info_lookup,
    get_shift_request_lookup,
    get_shift_request_target_staff_counts,
    labor_cost_estimate_period_metadata,
    lock_shift_request_submission,
    manual_adjust_attendance_record,
    month_dates,
    monthly_assignment_metadata,
    monthly_assignment_warning_count,
    monthly_plan_metadata,
    preview_template_generation,
    publish_monthly_shift_plan,
    record_shift_event,
    reject_attendance_correction_request,
    reject_shift_change_request,
    reopen_attendance_period,
    reopen_labor_cost_estimate,
    reopen_monthly_shift_plan,
    return_shift_request_submission,
    save_attendance_correction_request,
    save_shift_change_request,
    save_shift_request_period,
    save_shift_request_submission,
    set_shift_request_period_active,
    set_shift_request_period_status,
    shift_change_request_metadata,
    shift_change_request_summary,
    shift_change_requests_for_display,
    shift_pattern_metadata,
    shift_request_items_for_display,
    shift_request_period_metadata,
    shift_request_submission_metadata,
    submit_attendance_correction_request,
    submit_shift_change_request,
    submit_shift_request_submission,
    unconfirm_attendance_record,
    unlock_shift_request_submission,
    unsubmit_shift_request_submission,
    validate_and_reactivate_monthly_assignment,
    validate_and_reactivate_monthly_plan,
    validate_and_reactivate_pattern,
    validate_and_reactivate_template,
    validate_assignment_against_shift_requests,
    void_attendance_record,
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


def shift_change_request_queryset():
    return ShiftChangeRequest.objects.select_related(
        "location",
        "monthly_shift_plan",
        "publication",
        "publication_assignment",
        "requester",
        "target_staff",
        "requested_staff",
        "requested_shift_pattern",
        "submitted_by",
        "approved_by",
        "rejected_by",
        "cancelled_by",
        "applied_by",
    )


def get_shift_change_request_for_update(pk):
    return (
        ShiftChangeRequest.objects.select_for_update(of=("self",))
        .select_related(
            "location",
            "monthly_shift_plan",
            "publication",
            "publication_assignment",
            "requester",
            "target_staff",
            "requested_staff",
            "requested_shift_pattern",
        )
        .get(pk=pk)
    )


def attendance_record_queryset():
    return AttendanceRecord.objects.select_related(
        "location",
        "staff",
        "monthly_shift_plan",
        "monthly_shift_assignment",
        "publication",
        "publication_assignment",
        "confirmed_by",
    ).prefetch_related(
        Prefetch(
            "events",
            queryset=AttendanceEvent.objects.select_related("actor").order_by("occurred_at", "created_at"),
        ),
        Prefetch(
            "correction_requests",
            queryset=AttendanceCorrectionRequest.objects.select_related(
                "requester",
                "approved_by",
                "rejected_by",
                "cancelled_by",
                "applied_by",
                "attendance_record",
                "attendance_record__location",
                "attendance_record__staff",
            ).order_by("-created_at"),
        ),
    )


def attendance_correction_queryset():
    return AttendanceCorrectionRequest.objects.select_related(
        "attendance_record",
        "attendance_record__location",
        "attendance_record__staff",
        "requester",
        "approved_by",
        "rejected_by",
        "cancelled_by",
        "applied_by",
    )


def attendance_closing_period_queryset():
    return (
        AttendanceClosingPeriod.objects.select_related(
            "location",
            "closed_by",
            "reopened_by",
            "created_by",
            "updated_by",
        )
        .prefetch_related(
            Prefetch(
                "labor_cost_estimate_periods",
                queryset=LaborCostEstimatePeriod.objects.filter(is_active=True).order_by("created_at"),
                to_attr="prefetched_labor_cost_periods",
            )
        )
        .annotate(
            snapshot_total=Count("record_snapshots", distinct=True),
            staff_summary_total=Count("staff_summaries", distinct=True),
        )
    )


def attendance_closing_snapshot_queryset():
    return AttendanceClosingRecordSnapshot.objects.select_related(
        "closing_period",
        "location",
        "staff",
        "confirmed_by",
    )


def attendance_closing_staff_summary_queryset():
    return AttendanceClosingStaffSummary.objects.select_related("closing_period", "staff")


def staff_compensation_profile_queryset():
    return StaffCompensationProfile.objects.select_related(
        "location",
        "staff",
        "created_by",
        "updated_by",
    )


def staff_allowance_assignment_queryset():
    return StaffAllowanceAssignment.objects.select_related(
        "location",
        "staff",
        "created_by",
        "updated_by",
    )


def labor_cost_estimate_period_queryset():
    return LaborCostEstimatePeriod.objects.select_related(
        "location",
        "attendance_closing_period",
        "finalized_by",
        "reopened_by",
        "created_by",
        "updated_by",
    ).annotate(
        record_snapshot_total=Count("record_snapshots", distinct=True),
        staff_summary_total=Count("staff_summaries", distinct=True),
        allowance_snapshot_total=Count("allowance_snapshots", distinct=True),
    )


def labor_cost_record_snapshot_queryset():
    return LaborCostEstimateRecordSnapshot.objects.select_related(
        "estimate_period",
        "attendance_closing_snapshot",
        "attendance_record",
        "location",
        "staff",
    )


def labor_cost_staff_summary_queryset():
    return LaborCostEstimateStaffSummary.objects.select_related("estimate_period", "staff")


def labor_cost_allowance_snapshot_queryset():
    return LaborCostEstimateAllowanceSnapshot.objects.select_related(
        "estimate_period",
        "staff",
        "allowance_assignment",
    )


def staff_compensation_profile_metadata(profile: StaffCompensationProfile) -> dict:
    return {
        "staff_compensation_profile_id": str(profile.id),
        "location_id": str(profile.location_id),
        "staff_id": str(profile.staff_id),
        "employment_type": profile.employment_type,
        "valid_from": profile.valid_from.isoformat(),
        "valid_to": profile.valid_to.isoformat() if profile.valid_to else None,
        "is_active": profile.is_active,
    }


def staff_allowance_assignment_metadata(assignment: StaffAllowanceAssignment) -> dict:
    return {
        "staff_allowance_assignment_id": str(assignment.id),
        "location_id": str(assignment.location_id),
        "staff_id": str(assignment.staff_id),
        "code": assignment.code,
        "allowance_type": assignment.allowance_type,
        "valid_from": assignment.valid_from.isoformat(),
        "valid_to": assignment.valid_to.isoformat() if assignment.valid_to else None,
        "is_active": assignment.is_active,
    }


def drf_validation_from_django(exc):
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            return ValidationError(exc.message_dict)
        return ValidationError({"non_field_errors": exc.messages})
    return ValidationError({"non_field_errors": ["重複または不正なデータです。"]})


def validate_change_request_date_range(params, *, max_days=92):
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    try:
        parsed_from = date.fromisoformat(date_from) if date_from else None
        parsed_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise ValidationError({"date": "YYYY-MM-DD形式で指定してください。"}) from exc
    if parsed_from and parsed_to:
        if parsed_from > parsed_to:
            raise ValidationError({"date_to": "date_from以降の日付を指定してください。"})
        if (parsed_to - parsed_from).days > max_days:
            raise ValidationError({"date_to": f"検索範囲は最大{max_days + 1}日です。"})
    return parsed_from, parsed_to


def validate_attendance_date_range(params):
    return validate_change_request_date_range(params, max_days=91)


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
        shift_change_lookup = get_shift_change_request_lookup(plan, staff_ids)
        shift_change_summary = shift_change_request_summary(plan)
        attendance_lookup = get_attendance_lookup(
            staff_ids=staff_ids,
            date_from=start_date,
            date_to=end_date,
            location=plan.location,
            monthly_shift_plan=plan,
        )
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
                change_requests = shift_change_lookup.get((str(staff.id), work_date.isoformat()), [])
                attendance_record = attendance_lookup["by_staff_date"].get((str(staff.id), work_date.isoformat()))
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
                        "shift_change_requests": shift_change_requests_for_display(change_requests),
                        "attendance": attendance_record_summary(
                            attendance_lookup["by_monthly_assignment"].get(str(assignment.id), attendance_record)
                        ),
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
                if request_items or prefer_issues or change_requests or attendance_record:
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
                            "shift_change_requests": shift_change_requests_for_display(change_requests),
                            "attendance": attendance_record_summary(attendance_record),
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
                "shift_change_request_summary": shift_change_summary,
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


class MyShiftChangeRequestPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return obj.requester_id == request.user.id


class ShiftChangeRequestManagementPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return can_view_shifts(request.user)
        return can_manage_shifts(request.user)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class MyAttendancePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "staff_id"):
            return obj.staff_id == request.user.id
        if hasattr(obj, "requester_id"):
            return obj.requester_id == request.user.id
        return False


class AttendanceManagementPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return can_view_shifts(request.user)
        return can_manage_shifts(request.user)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class AttendanceClosingPermission(permissions.BasePermission):
    readonly_actions = {"list", "retrieve", "preview", "snapshots", "staff_summaries", "export_csv"}

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(view, "action", None) in self.readonly_actions or request.method in permissions.SAFE_METHODS:
            return can_view_shifts(request.user)
        return can_manage_shifts(request.user)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class MyAttendanceMonthlyPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class AttendanceClosingPeriodViewSet(viewsets.ModelViewSet):
    permission_classes = [AttendanceClosingPermission]
    serializer_class = AttendanceClosingPeriodSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        queryset = attendance_closing_period_queryset()
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("year"):
            queryset = queryset.filter(year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(month=params["month"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("-year", "-month", "location__display_order", "created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="attendance_closing_period",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=attendance_closing_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(self.get_serializer(attendance_closing_period_queryset().get(pk=period.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="attendance_closing_period",
                    action="update",
                    actor=request.user,
                    request=request,
                    metadata=attendance_closing_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(self.get_serializer(attendance_closing_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["get", "post"])
    def preview(self, request, pk=None):
        period = self.get_object()
        preview = build_attendance_closing_preview(period)
        with transaction.atomic():
            record_shift_event(
                entity="attendance_closing_period",
                action="preview",
                actor=request.user,
                request=request,
                metadata=attendance_closing_period_metadata(period, preview),
            )
        return Response(preview)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        serializer = AttendanceClosingCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period, preview = close_attendance_period(
                period=self.get_object(),
                actor=request.user,
                acknowledge_warnings=serializer.validated_data["acknowledge_warnings"],
                validation_fingerprint=serializer.validated_data["validation_fingerprint"],
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_closing_period",
                action="close",
                actor=request.user,
                request=request,
                metadata=attendance_closing_period_metadata(period, preview),
            )
        return Response(self.get_serializer(attendance_closing_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        serializer = AttendanceClosingManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period = reopen_attendance_period(
                period=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_closing_period",
                action="reopen",
                actor=request.user,
                request=request,
                metadata=attendance_closing_period_metadata(period),
            )
        return Response(self.get_serializer(attendance_closing_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        serializer = AttendanceClosingManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period = archive_attendance_period(
                period=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_closing_period",
                action="archive",
                actor=request.user,
                request=request,
                metadata=attendance_closing_period_metadata(period),
            )
        return Response(self.get_serializer(attendance_closing_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["get"], url_path="snapshots")
    def snapshots(self, request, pk=None):
        period = self.get_object()
        queryset = (
            attendance_closing_snapshot_queryset()
            .filter(closing_period=period)
            .order_by(
                "work_date",
                "employee_code_snapshot",
            )
        )
        serializer = AttendanceClosingRecordSnapshotSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="staff-summaries")
    def staff_summaries(self, request, pk=None):
        period = self.get_object()
        queryset = (
            attendance_closing_staff_summary_queryset()
            .filter(closing_period=period)
            .order_by(
                "employee_code_snapshot",
                "staff_display_name_snapshot",
            )
        )
        serializer = AttendanceClosingStaffSummarySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="export-csv")
    def export_csv(self, request, pk=None):
        period = self.get_object()
        with transaction.atomic():
            data, filename, summary = export_attendance_closing_csv(period)
            record_shift_event(
                entity="attendance_closing_period",
                action="export",
                actor=request.user,
                request=request,
                metadata=attendance_closing_period_metadata(period)
                | {
                    "snapshot_count": summary.get("snapshot_count", 0),
                    "warning_count": summary.get("warning_count", 0),
                    "error_count": summary.get("error_count", 0),
                },
            )
        response = HttpResponse(data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class LaborCostManagementPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and can_manage_labor_costs(request.user))

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class StaffCompensationProfileViewSet(viewsets.ModelViewSet):
    permission_classes = [LaborCostManagementPermission]
    serializer_class = StaffCompensationProfileSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        queryset = staff_compensation_profile_queryset()
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("staff"):
            queryset = queryset.filter(staff_id=params["staff"])
        if params.get("employment_type"):
            queryset = queryset.filter(employment_type=params["employment_type"])
        if params.get("valid_on"):
            valid_on = date.fromisoformat(params["valid_on"])
            queryset = queryset.filter(valid_from__lte=valid_on).filter(
                Q(valid_to__isnull=True) | Q(valid_to__gte=valid_on)
            )
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("location__display_order", "staff__employee_code", "-valid_from", "created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                profile = serializer.save()
                record_shift_event(
                    entity="staff_compensation_profile",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=staff_compensation_profile_metadata(profile),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(self.get_serializer(staff_compensation_profile_queryset().get(pk=profile.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        was_active = instance.is_active
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                profile = serializer.save()
                action_name = "deactivate" if was_active and not profile.is_active else "update"
                record_shift_event(
                    entity="staff_compensation_profile",
                    action=action_name,
                    actor=request.user,
                    request=request,
                    metadata=staff_compensation_profile_metadata(profile),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(self.get_serializer(staff_compensation_profile_queryset().get(pk=profile.pk)).data)


class StaffAllowanceAssignmentViewSet(viewsets.ModelViewSet):
    permission_classes = [LaborCostManagementPermission]
    serializer_class = StaffAllowanceAssignmentSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        queryset = staff_allowance_assignment_queryset()
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("staff"):
            queryset = queryset.filter(staff_id=params["staff"])
        if params.get("code"):
            queryset = queryset.filter(code=params["code"])
        if params.get("allowance_type"):
            queryset = queryset.filter(allowance_type=params["allowance_type"])
        if params.get("valid_on"):
            valid_on = date.fromisoformat(params["valid_on"])
            queryset = queryset.filter(valid_from__lte=valid_on).filter(
                Q(valid_to__isnull=True) | Q(valid_to__gte=valid_on)
            )
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("location__display_order", "staff__employee_code", "code", "-valid_from", "created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                assignment = serializer.save()
                record_shift_event(
                    entity="staff_allowance_assignment",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=staff_allowance_assignment_metadata(assignment),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(
            self.get_serializer(staff_allowance_assignment_queryset().get(pk=assignment.pk)).data,
            status=201,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        was_active = instance.is_active
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                assignment = serializer.save()
                action_name = "deactivate" if was_active and not assignment.is_active else "update"
                record_shift_event(
                    entity="staff_allowance_assignment",
                    action=action_name,
                    actor=request.user,
                    request=request,
                    metadata=staff_allowance_assignment_metadata(assignment),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(self.get_serializer(staff_allowance_assignment_queryset().get(pk=assignment.pk)).data)


class LaborCostEstimatePeriodViewSet(viewsets.ModelViewSet):
    permission_classes = [LaborCostManagementPermission]
    serializer_class = LaborCostEstimatePeriodSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        queryset = labor_cost_estimate_period_queryset()
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("year"):
            queryset = queryset.filter(year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(month=params["month"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("-year", "-month", "location__display_order", "created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="labor_cost_estimate_period",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=labor_cost_estimate_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(self.get_serializer(labor_cost_estimate_period_queryset().get(pk=period.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="labor_cost_estimate_period",
                    action="update",
                    actor=request.user,
                    request=request,
                    metadata=labor_cost_estimate_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise drf_validation_from_django(exc) from exc
        return Response(self.get_serializer(labor_cost_estimate_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        with transaction.atomic():
            period = (
                LaborCostEstimatePeriod.objects.select_for_update(of=("self",))
                .select_related("location", "attendance_closing_period")
                .get(pk=self.get_object().pk)
            )
            if period.status == LaborCostEstimatePeriod.Status.ARCHIVED or not period.is_active:
                raise ValidationError({"status": "アーカイブ済みの概算人件費periodは操作できません。"})
            if period.status in {LaborCostEstimatePeriod.Status.DRAFT, LaborCostEstimatePeriod.Status.REOPENED}:
                period.status = LaborCostEstimatePeriod.Status.REVIEW
                period.updated_by = request.user
                period.full_clean()
                period.save(update_fields=["status", "updated_by", "updated_at"])
            preview = build_labor_cost_preview(period)
            record_shift_event(
                entity="labor_cost_estimate_period",
                action="preview",
                actor=request.user,
                request=request,
                metadata=labor_cost_estimate_period_metadata(period, preview),
            )
        return Response(preview)

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        serializer = LaborCostEstimateFinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period, preview = finalize_labor_cost_estimate(
                period=self.get_object(),
                actor=request.user,
                acknowledge_warnings=serializer.validated_data["acknowledge_warnings"],
                validation_fingerprint=serializer.validated_data["validation_fingerprint"],
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="labor_cost_estimate_period",
                action="finalize",
                actor=request.user,
                request=request,
                metadata=labor_cost_estimate_period_metadata(period, preview),
            )
        return Response(self.get_serializer(labor_cost_estimate_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        serializer = LaborCostEstimateManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period = reopen_labor_cost_estimate(
                period=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="labor_cost_estimate_period",
                action="reopen",
                actor=request.user,
                request=request,
                metadata=labor_cost_estimate_period_metadata(period),
            )
        return Response(self.get_serializer(labor_cost_estimate_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        serializer = LaborCostEstimateManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period = archive_labor_cost_estimate(
                period=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="labor_cost_estimate_period",
                action="archive",
                actor=request.user,
                request=request,
                metadata=labor_cost_estimate_period_metadata(period),
            )
        return Response(self.get_serializer(labor_cost_estimate_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["get"], url_path="record-snapshots")
    def record_snapshots(self, request, pk=None):
        period = self.get_object()
        queryset = (
            labor_cost_record_snapshot_queryset()
            .filter(estimate_period=period)
            .order_by("work_date", "employee_code_snapshot")
        )
        serializer = LaborCostEstimateRecordSnapshotSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="staff-summaries")
    def staff_summaries(self, request, pk=None):
        period = self.get_object()
        queryset = (
            labor_cost_staff_summary_queryset()
            .filter(estimate_period=period)
            .order_by("employee_code_snapshot", "staff_display_name_snapshot")
        )
        serializer = LaborCostEstimateStaffSummarySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="allowance-snapshots")
    def allowance_snapshots(self, request, pk=None):
        period = self.get_object()
        queryset = (
            labor_cost_allowance_snapshot_queryset()
            .filter(estimate_period=period)
            .order_by("employee_code_snapshot", "code_snapshot")
        )
        serializer = LaborCostEstimateAllowanceSnapshotSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="export-csv")
    def export_csv(self, request, pk=None):
        period = self.get_object()
        with transaction.atomic():
            data, filename, summary = export_labor_cost_estimate_csv(period)
            record_shift_event(
                entity="labor_cost_estimate_period",
                action="export",
                actor=request.user,
                request=request,
                metadata=labor_cost_estimate_period_metadata(period)
                | {
                    "record_snapshot_count": summary.get("record_snapshot_count", 0),
                    "warning_count": summary.get("warning_count", 0),
                    "error_count": summary.get("error_count", 0),
                },
            )
        response = HttpResponse(data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class MyAttendanceMonthlyViewSet(viewsets.GenericViewSet):
    permission_classes = [MyAttendanceMonthlyPermission]
    http_method_names = ["get", "head", "options"]

    def _validated_filters(self):
        params = self.request.query_params
        if "staff" in params:
            raise ValidationError({"staff": "本人APIでは指定できません。"})
        today = date.today()
        try:
            year = int(params.get("year", today.year))
            month = int(params.get("month", today.month))
        except ValueError as exc:
            raise ValidationError({"year": "year/monthは数値で指定してください。"}) from exc
        if month < 1 or month > 12:
            raise ValidationError({"month": "1から12で指定してください。"})
        return year, month, params.get("location"), params.get("status")

    def _live_period(self, *, year: int, month: int, location_id: str | None):
        if not location_id:
            location_ids = StaffLocation.objects.filter(staff=self.request.user, is_active=True).values_list(
                "location_id",
                flat=True,
            )
            location_id = next(iter(location_ids), None)
        if not location_id:
            return None
        from apps.operations.models import Location

        location = Location.objects.filter(id=location_id, is_active=True).first()
        if location is None:
            return None
        return AttendanceClosingPeriod(
            location=location,
            year=year,
            month=month,
            name=f"{location.short_name} {year}-{month:02d} 月次勤怠速報",
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def _own_live_payload(self, period: AttendanceClosingPeriod):
        preview = build_attendance_closing_preview(period)
        own_items = [item for item in preview["items"] if item["staff"] == str(self.request.user.id)]
        own_summaries = [item for item in preview["staff_summaries"] if item["staff"] == str(self.request.user.id)]
        return {
            "period": str(period.id) if period.pk else None,
            "location": str(period.location_id),
            "location_name": period.location.name,
            "year": period.year,
            "month": period.month,
            "status": period.status if period.pk else "live",
            "is_closed": False,
            "summary": own_summaries[0] if own_summaries else None,
            "daily": own_items,
            "warnings": [warning for item in own_items for warning in item["warnings"]],
        }

    def _own_closed_payload(self, period: AttendanceClosingPeriod):
        summary = period.staff_summaries.filter(staff=self.request.user).first()
        snapshots = list(period.record_snapshots.filter(staff=self.request.user).order_by("work_date"))
        return {
            "period": str(period.id),
            "location": str(period.location_id),
            "location_name": period.location.name,
            "year": period.year,
            "month": period.month,
            "status": period.status,
            "is_closed": period.status == AttendanceClosingPeriod.Status.CLOSED,
            "summary": AttendanceClosingStaffSummarySerializer(summary).data if summary else None,
            "daily": AttendanceClosingRecordSnapshotSerializer(snapshots, many=True).data,
            "warnings": [warning for snapshot in snapshots for warning in snapshot.warnings],
        }

    def list(self, request, *args, **kwargs):
        year, month, location_id, status_filter = self._validated_filters()
        periods = attendance_closing_period_queryset().filter(year=year, month=month, is_active=True)
        if location_id:
            periods = periods.filter(location_id=location_id)
        if status_filter:
            periods = periods.filter(status=status_filter)
        payload = []
        for period in periods:
            if period.status == AttendanceClosingPeriod.Status.CLOSED:
                payload.append(self._own_closed_payload(period))
            else:
                payload.append(self._own_live_payload(period))
        if not payload and (not status_filter or status_filter in {"live", "draft", "review", "reopened"}):
            live_period = self._live_period(year=year, month=month, location_id=location_id)
            if live_period is not None:
                payload.append(self._own_live_payload(live_period))
        return Response({"results": payload, "count": len(payload)})

    def retrieve(self, request, pk=None):
        if {"staff", "requester"}.intersection(request.query_params):
            raise ValidationError({"staff": "本人APIでは指定できません。"})
        period = attendance_closing_period_queryset().get(pk=pk)
        if period.status == AttendanceClosingPeriod.Status.CLOSED:
            return Response(self._own_closed_payload(period))
        return Response(self._own_live_payload(period))


class MyAttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [MyAttendancePermission]
    serializer_class = AttendanceRecordSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        if "staff" in params:
            raise ValidationError({"staff": "本人APIでは指定できません。"})
        date_from, date_to = validate_attendance_date_range(params)
        queryset = attendance_record_queryset().filter(staff=self.request.user)
        if date_from:
            queryset = queryset.filter(work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(work_date__lte=date_to)
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        return queryset.order_by("-work_date", "-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        try:
            date_from, date_to = validate_attendance_date_range(self.request.query_params)
        except ValidationError:
            return context
        if date_from and date_to:
            location_ids = (
                {self.request.query_params["location"]}
                if self.request.query_params.get("location")
                else set(
                    StaffLocation.objects.filter(staff=self.request.user, is_active=True).values_list(
                        "location_id",
                        flat=True,
                    )
                )
            )
            context["closed_period_lookup"] = get_attendance_closed_period_lookup(
                location_ids=location_ids,
                date_from=date_from,
                date_to=date_to,
            )
        return context

    @action(detail=False, methods=["post"], url_path="clock-in")
    def clock_in(self, request):
        serializer = AttendanceClockInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            record, created = clock_in_attendance(
                staff=request.user,
                location=serializer.validated_data["location"],
                work_date=serializer.validated_data["work_date"],
                actor=request.user,
                occurred_at=serializer.validated_data.get("occurred_at"),
                note=serializer.validated_data.get("note", ""),
            )
            if created:
                record_shift_event(
                    entity="attendance_record",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=attendance_record_metadata(record),
                )
            record_shift_event(
                entity="attendance_record",
                action="clock_in",
                actor=request.user,
                request=request,
                metadata=attendance_record_metadata(record),
            )
        return Response(self.get_serializer(attendance_record_queryset().get(pk=record.pk)).data, status=201)

    def _clock_action(self, request, pk, *, event_type: str, audit_action: str):
        serializer = AttendanceClockEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            record = self.get_object()
            record = add_self_attendance_event(
                record=record,
                event_type=event_type,
                actor=request.user,
                occurred_at=serializer.validated_data.get("occurred_at"),
                note=serializer.validated_data.get("note", ""),
            )
            record_shift_event(
                entity="attendance_record",
                action=audit_action,
                actor=request.user,
                request=request,
                metadata=attendance_record_metadata(record),
            )
        return Response(self.get_serializer(attendance_record_queryset().get(pk=record.pk)).data)

    @action(detail=True, methods=["post"], url_path="break-start")
    def break_start(self, request, pk=None):
        return self._clock_action(
            request,
            pk,
            event_type=AttendanceEvent.EventType.BREAK_START,
            audit_action="break_start",
        )

    @action(detail=True, methods=["post"], url_path="break-end")
    def break_end(self, request, pk=None):
        return self._clock_action(
            request,
            pk,
            event_type=AttendanceEvent.EventType.BREAK_END,
            audit_action="break_end",
        )

    @action(detail=True, methods=["post"], url_path="clock-out")
    def clock_out(self, request, pk=None):
        return self._clock_action(
            request,
            pk,
            event_type=AttendanceEvent.EventType.CLOCK_OUT,
            audit_action="clock_out",
        )


class AttendanceRecordViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AttendanceManagementPermission]
    serializer_class = AttendanceRecordSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        date_from, date_to = validate_attendance_date_range(params)
        queryset = attendance_record_queryset()
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if date_from:
            queryset = queryset.filter(work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(work_date__lte=date_to)
        if params.get("staff"):
            queryset = queryset.filter(staff_id=params["staff"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("source"):
            queryset = queryset.filter(source=params["source"])
        if params.get("has_warnings") == "true":
            queryset = queryset.filter(warning_count__gt=0)
        if params.get("has_warnings") == "false":
            queryset = queryset.filter(warning_count=0)
        if params.get("confirmed") == "true":
            queryset = queryset.filter(status=AttendanceRecord.Status.CONFIRMED)
        if params.get("confirmed") == "false":
            queryset = queryset.exclude(status=AttendanceRecord.Status.CONFIRMED)
        return queryset.order_by("-work_date", "location__display_order", "staff__employee_code")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        try:
            date_from, date_to = validate_attendance_date_range(self.request.query_params)
        except ValidationError:
            return context
        if date_from and date_to:
            if self.request.query_params.get("location"):
                location_ids = {self.request.query_params["location"]}
            else:
                location_ids = set(
                    AttendanceRecord.objects.filter(work_date__gte=date_from, work_date__lte=date_to).values_list(
                        "location_id",
                        flat=True,
                    )
                )
            context["closed_period_lookup"] = get_attendance_closed_period_lookup(
                location_ids=location_ids,
                date_from=date_from,
                date_to=date_to,
            )
        return context

    @action(detail=True, methods=["post"], url_path="manual-adjust")
    def manual_adjust(self, request, pk=None):
        serializer = AttendanceManualAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            record = manual_adjust_attendance_record(
                record=self.get_object(),
                actor=request.user,
                actual_clock_in_at=serializer.validated_data["actual_clock_in_at"],
                actual_clock_out_at=serializer.validated_data["actual_clock_out_at"],
                break_minutes=serializer.validated_data["break_minutes"],
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_record",
                action="manual_adjust",
                actor=request.user,
                request=request,
                metadata=attendance_record_metadata(record),
            )
        return Response(self.get_serializer(attendance_record_queryset().get(pk=record.pk)).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        serializer = AttendanceManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            record = confirm_attendance_record(
                record=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_record",
                action="confirm",
                actor=request.user,
                request=request,
                metadata=attendance_record_metadata(record),
            )
        return Response(self.get_serializer(attendance_record_queryset().get(pk=record.pk)).data)

    @action(detail=True, methods=["post"])
    def unconfirm(self, request, pk=None):
        serializer = AttendanceManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            record = unconfirm_attendance_record(
                record=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_record",
                action="unconfirm",
                actor=request.user,
                request=request,
                metadata=attendance_record_metadata(record),
            )
        return Response(self.get_serializer(attendance_record_queryset().get(pk=record.pk)).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        serializer = AttendanceManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            record = void_attendance_record(
                record=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_record",
                action="void",
                actor=request.user,
                request=request,
                metadata=attendance_record_metadata(record),
            )
        return Response(self.get_serializer(record).data)


class MyAttendanceCorrectionRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [MyAttendancePermission]
    serializer_class = AttendanceCorrectionRequestSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        forbidden = {"staff", "requester"}.intersection(params)
        if forbidden:
            raise ValidationError({field: "本人APIでは指定できません。" for field in forbidden})
        date_from, date_to = validate_attendance_date_range(params)
        queryset = attendance_correction_queryset().filter(requester=self.request.user, is_active=True)
        if date_from:
            queryset = queryset.filter(attendance_record__work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(attendance_record__work_date__lte=date_to)
        if params.get("location"):
            queryset = queryset.filter(attendance_record__location_id=params["location"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        return queryset.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = AttendanceCorrectionSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submit = serializer.validated_data.pop("submit", False)
        attendance_record = serializer.validated_data.pop("attendance_record", None)
        with transaction.atomic():
            correction = save_attendance_correction_request(
                instance=None,
                attendance_record=attendance_record,
                actor=request.user,
                validated_data=serializer.validated_data,
                submit=submit,
            )
            record_shift_event(
                entity="attendance_correction",
                action="create",
                actor=request.user,
                request=request,
                metadata=attendance_correction_metadata(correction),
            )
            if submit:
                record_shift_event(
                    entity="attendance_correction",
                    action="submit",
                    actor=request.user,
                    request=request,
                    metadata=attendance_correction_metadata(correction),
                )
        return Response(self.get_serializer(attendance_correction_queryset().get(pk=correction.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = AttendanceCorrectionSaveSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("attendance_record", None)
        serializer.validated_data.pop("submit", None)
        with transaction.atomic():
            correction = save_attendance_correction_request(
                instance=self.get_object(),
                attendance_record=None,
                actor=request.user,
                validated_data=serializer.validated_data,
            )
            record_shift_event(
                entity="attendance_correction",
                action="update",
                actor=request.user,
                request=request,
                metadata=attendance_correction_metadata(correction),
            )
        return Response(self.get_serializer(attendance_correction_queryset().get(pk=correction.pk)).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        with transaction.atomic():
            correction = submit_attendance_correction_request(correction=self.get_object(), actor=request.user)
            record_shift_event(
                entity="attendance_correction",
                action="submit",
                actor=request.user,
                request=request,
                metadata=attendance_correction_metadata(correction),
            )
        return Response(self.get_serializer(attendance_correction_queryset().get(pk=correction.pk)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            correction = cancel_attendance_correction_request(correction=self.get_object(), actor=request.user)
            record_shift_event(
                entity="attendance_correction",
                action="cancel",
                actor=request.user,
                request=request,
                metadata=attendance_correction_metadata(correction),
            )
        return Response(self.get_serializer(attendance_correction_queryset().get(pk=correction.pk)).data)


class AttendanceCorrectionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AttendanceManagementPermission]
    serializer_class = AttendanceCorrectionRequestSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        date_from, date_to = validate_attendance_date_range(params)
        queryset = attendance_correction_queryset().filter(is_active=True)
        if params.get("location"):
            queryset = queryset.filter(attendance_record__location_id=params["location"])
        if date_from:
            queryset = queryset.filter(attendance_record__work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(attendance_record__work_date__lte=date_to)
        if params.get("staff"):
            queryset = queryset.filter(attendance_record__staff_id=params["staff"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = AttendanceManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            correction = approve_attendance_correction_request(
                correction=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_correction",
                action="approve",
                actor=request.user,
                request=request,
                metadata=attendance_correction_metadata(correction),
            )
        return Response(self.get_serializer(attendance_correction_queryset().get(pk=correction.pk)).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = AttendanceManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            correction = reject_attendance_correction_request(
                correction=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_correction",
                action="reject",
                actor=request.user,
                request=request,
                metadata=attendance_correction_metadata(correction),
            )
        return Response(self.get_serializer(attendance_correction_queryset().get(pk=correction.pk)).data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        serializer = AttendanceManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            correction = apply_attendance_correction_request(
                correction=self.get_object(),
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="attendance_correction",
                action="apply",
                actor=request.user,
                request=request,
                metadata=attendance_correction_metadata(correction),
            )
        return Response(self.get_serializer(attendance_correction_queryset().get(pk=correction.pk)).data)


class MyShiftChangeRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [MyShiftChangeRequestPermission]
    serializer_class = ShiftChangeRequestSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _staff_queryset(self):
        return User.objects.filter(is_active=True)

    def _save_serializer_context(self):
        return {**self.get_serializer_context(), "staff_queryset": self._staff_queryset()}

    def get_queryset(self):
        params = self.request.query_params
        forbidden = {"staff", "requester", "target_staff"}.intersection(params)
        if forbidden:
            raise ValidationError({field: "本人APIでは指定できません。" for field in forbidden})
        date_from, date_to = validate_change_request_date_range(params)
        queryset = shift_change_request_queryset().filter(requester=self.request.user, is_active=True)
        if date_from:
            queryset = queryset.filter(work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(work_date__lte=date_to)
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("request_type"):
            queryset = queryset.filter(request_type=params["request_type"])
        return queryset.order_by("-work_date", "-created_at")

    def create(self, request, *args, **kwargs):
        serializer = ShiftChangeRequestSaveSerializer(data=request.data, context=self._save_serializer_context())
        serializer.is_valid(raise_exception=True)
        submit = serializer.validated_data.pop("submit", False)
        with transaction.atomic():
            change_request = save_shift_change_request(
                instance=None,
                validated_data=serializer.validated_data,
                actor=request.user,
                self_service=True,
                submit=submit,
            )
            record_shift_event(
                entity="shift_change_request",
                action="create",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
            if submit:
                record_shift_event(
                    entity="shift_change_request",
                    action="submit",
                    actor=request.user,
                    request=request,
                    metadata=shift_change_request_metadata(change_request),
                )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = ShiftChangeRequestSaveSerializer(
            data=request.data,
            partial=True,
            context=self._save_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            change_request = get_shift_change_request_for_update(kwargs["pk"])
            if change_request.requester_id != request.user.id:
                raise PermissionDenied("本人の申請のみ編集できます。")
            change_request = save_shift_change_request(
                instance=change_request,
                validated_data=serializer.validated_data,
                actor=request.user,
                self_service=True,
            )
            record_shift_event(
                entity="shift_change_request",
                action="update",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        with transaction.atomic():
            change_request = self.get_object()
            change_request = submit_shift_change_request(change_request=change_request, actor=request.user)
            record_shift_event(
                entity="shift_change_request",
                action="submit",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            change_request = self.get_object()
            change_request = cancel_shift_change_request(change_request=change_request, actor=request.user)
            record_shift_event(
                entity="shift_change_request",
                action="cancel",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)


class ShiftChangeRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [ShiftChangeRequestManagementPermission]
    serializer_class = ShiftChangeRequestSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _staff_queryset(self):
        return User.objects.filter(is_active=True)

    def _save_serializer_context(self):
        return {**self.get_serializer_context(), "staff_queryset": self._staff_queryset()}

    def get_queryset(self):
        params = self.request.query_params
        date_from, date_to = validate_change_request_date_range(params)
        queryset = shift_change_request_queryset().filter(is_active=True)
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("year"):
            queryset = queryset.filter(monthly_shift_plan__year=params["year"])
        if params.get("month"):
            queryset = queryset.filter(monthly_shift_plan__month=params["month"])
        if date_from:
            queryset = queryset.filter(work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(work_date__lte=date_to)
        for field in [
            "requester",
            "target_staff",
            "requested_staff",
            "status",
            "request_type",
            "priority",
            "publication",
            "monthly_shift_plan",
        ]:
            if params.get(field):
                lookup = (
                    f"{field}_id"
                    if field.endswith("staff") or field in {"requester", "publication", "monthly_shift_plan"}
                    else field
                )
                queryset = queryset.filter(**{lookup: params[field]})
        return queryset.order_by("-work_date", "-created_at")

    def create(self, request, *args, **kwargs):
        serializer = ShiftChangeRequestSaveSerializer(data=request.data, context=self._save_serializer_context())
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("request_type") != ShiftChangeRequest.RequestType.MANAGER_ADJUSTMENT:
            raise ValidationError({"request_type": "管理APIから作成できるのはmanager_adjustmentのみです。"})
        submit = serializer.validated_data.pop("submit", True)
        with transaction.atomic():
            change_request = save_shift_change_request(
                instance=None,
                validated_data=serializer.validated_data,
                actor=request.user,
                self_service=False,
                submit=submit,
            )
            record_shift_event(
                entity="shift_change_request",
                action="create",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = ShiftChangeRequestSaveSerializer(
            data=request.data,
            partial=True,
            context=self._save_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            change_request = get_shift_change_request_for_update(kwargs["pk"])
            change_request = save_shift_change_request(
                instance=change_request,
                validated_data=serializer.validated_data,
                actor=request.user,
                self_service=False,
            )
            record_shift_event(
                entity="shift_change_request",
                action="update",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = ShiftChangeRequestActionSerializer(data=request.data, context=self._save_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            change_request = get_shift_change_request_for_update(pk)
            change_request = approve_shift_change_request(
                change_request=change_request,
                actor=request.user,
                validated_data=serializer.validated_data,
            )
            record_shift_event(
                entity="shift_change_request",
                action="approve",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = ShiftChangeRequestManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            change_request = get_shift_change_request_for_update(pk)
            change_request = reject_shift_change_request(
                change_request=change_request,
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="shift_change_request",
                action="reject",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = ShiftChangeRequestManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            change_request = get_shift_change_request_for_update(pk)
            change_request = cancel_shift_change_request(
                change_request=change_request,
                actor=request.user,
                manager=True,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="shift_change_request",
                action="cancel",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        serializer = ShiftChangeRequestManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            change_request = get_shift_change_request_for_update(pk)
            change_request, publication = apply_shift_change_request(
                change_request=change_request,
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="shift_change_request",
                action="apply",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(
                    change_request,
                    reason=f"change_request_applied:{change_request.id}",
                )
                | {"withdrawn_publication_id": str(publication.id)},
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        serializer = ShiftChangeRequestManagerNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            change_request = get_shift_change_request_for_update(pk)
            change_request = close_shift_change_request(
                change_request=change_request,
                actor=request.user,
                manager_note=serializer.validated_data.get("manager_note", ""),
            )
            record_shift_event(
                entity="shift_change_request",
                action="close",
                actor=request.user,
                request=request,
                metadata=shift_change_request_metadata(change_request),
            )
        return Response(self.get_serializer(shift_change_request_queryset().get(pk=change_request.pk)).data)


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
        shifts = list(self.get_queryset())
        change_request_lookup = get_shift_change_request_assignment_lookup([item.id for item in shifts])
        attendance_lookup = get_attendance_lookup(
            staff_ids={item.staff_id for item in shifts},
            date_from=date_from,
            date_to=date_to,
            publication_assignment_ids=[item.id for item in shifts],
        )["by_publication_assignment"]
        closed_period_lookup = get_attendance_closed_period_lookup(
            location_ids={item.publication.location_id for item in shifts},
            date_from=date_from,
            date_to=date_to,
        )
        serializer = self.get_serializer(
            shifts,
            many=True,
            context={
                **self.get_serializer_context(),
                "shift_change_request_lookup": change_request_lookup,
                "attendance_lookup": attendance_lookup,
                "closed_period_lookup": closed_period_lookup,
            },
        )
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
