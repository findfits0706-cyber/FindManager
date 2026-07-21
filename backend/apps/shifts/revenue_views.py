from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import (
    RevenueActualLine,
    RevenueActualPeriod,
    RevenueBudgetLine,
    RevenueBudgetPeriod,
    RevenueCategory,
    RevenuePerformanceLineSnapshot,
    RevenuePerformanceSnapshot,
)
from .revenue_services import (
    approve_revenue_budget,
    archive_revenue_actual,
    archive_revenue_budget,
    build_revenue_actual_preview,
    build_revenue_budget_preview,
    export_revenue_actual_csv,
    export_revenue_budget_csv,
    finalize_revenue_actual,
    get_financial_performance,
    get_revenue_performance,
    reopen_revenue_actual,
    reopen_revenue_budget,
    revenue_actual_period_metadata,
    revenue_budget_period_metadata,
    revenue_category_metadata,
)
from .serializers import (
    RevenueActualLineSerializer,
    RevenueActualPeriodSerializer,
    RevenueBudgetLineSerializer,
    RevenueBudgetPeriodSerializer,
    RevenueCategorySerializer,
    RevenueManagerNoteSerializer,
    RevenuePerformanceLineSnapshotSerializer,
    RevenueWorkflowSerializer,
)
from .services import _drf_validation, can_manage_financial_performance, record_shift_event


class FinancialPerformancePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and can_manage_financial_performance(request.user))


def revenue_category_queryset():
    return RevenueCategory.objects.select_related("location", "created_by", "updated_by")


def revenue_budget_period_queryset():
    return RevenueBudgetPeriod.objects.select_related(
        "location",
        "approved_by",
        "reopened_by",
        "created_by",
        "updated_by",
    ).annotate(line_total=Count("lines", filter=Q(lines__is_active=True), distinct=True))


def revenue_actual_period_queryset():
    return RevenueActualPeriod.objects.select_related(
        "location",
        "revenue_budget_period",
        "labor_cost_budget_period",
        "labor_cost_estimate_period",
        "finalized_by",
        "reopened_by",
        "created_by",
        "updated_by",
    ).annotate(line_total=Count("lines", filter=Q(lines__is_active=True), distinct=True))


class RevenueCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [FinancialPerformancePermission]
    serializer_class = RevenueCategorySerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = revenue_category_queryset()
        params = self.request.query_params
        if params.get("location"):
            queryset = queryset.filter(location_id=params["location"])
        if params.get("code"):
            queryset = queryset.filter(code=params["code"])
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("location__display_order", "display_order", "code", "id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                category = serializer.save()
                record_shift_event(
                    entity="revenue_category",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=revenue_category_metadata(category, action="create"),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="同じ拠点・コードの売上区分が既に存在します。") from exc
        return Response(self.get_serializer(revenue_category_queryset().get(pk=category.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        current = self.get_object()
        was_active = current.is_active
        serializer = self.get_serializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                category = serializer.save()
                action_name = "deactivate" if was_active and not category.is_active else "update"
                record_shift_event(
                    entity="revenue_category",
                    action=action_name,
                    actor=request.user,
                    request=request,
                    metadata=revenue_category_metadata(category, action=action_name),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="同じ拠点・コードの売上区分が既に存在します。") from exc
        return Response(self.get_serializer(revenue_category_queryset().get(pk=category.pk)).data)


class RevenueBudgetLineViewSet(viewsets.ModelViewSet):
    permission_classes = [FinancialPerformancePermission]
    serializer_class = RevenueBudgetLineSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = RevenueBudgetLine.objects.select_related("budget_period", "budget_period__location", "category")
        params = self.request.query_params
        if params.get("budget_period"):
            queryset = queryset.filter(budget_period_id=params["budget_period"])
        if params.get("category"):
            queryset = queryset.filter(category_id=params["category"])
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("display_order", "category_code_snapshot", "id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                line = serializer.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="同じ売上区分の予算明細が既に存在します。") from exc
        return Response(self.get_serializer(self.get_queryset().get(pk=line.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                line = serializer.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="売上予算明細を更新できません。") from exc
        return Response(self.get_serializer(self.get_queryset().get(pk=line.pk)).data)


class RevenueBudgetPeriodViewSet(viewsets.ModelViewSet):
    permission_classes = [FinancialPerformancePermission]
    serializer_class = RevenueBudgetPeriodSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = revenue_budget_period_queryset()
        params = self.request.query_params
        for field in ["location", "year", "month", "status"]:
            if params.get(field):
                lookup = f"{field}_id" if field == "location" else field
                queryset = queryset.filter(**{lookup: params[field]})
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("-year", "-month", "location__display_order", "id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="revenue_budget_period",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=revenue_budget_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="同じ拠点・年月の有効な売上予算が既に存在します。") from exc
        return Response(self.get_serializer(revenue_budget_period_queryset().get(pk=period.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="revenue_budget_period",
                    action="update",
                    actor=request.user,
                    request=request,
                    metadata=revenue_budget_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc) from exc
        return Response(self.get_serializer(revenue_budget_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        with transaction.atomic():
            period = (
                RevenueBudgetPeriod.objects.select_for_update(of=("self",))
                .select_related("location")
                .get(pk=self.get_object().pk)
            )
            if period.status == RevenueBudgetPeriod.Status.ARCHIVED or not period.is_active:
                raise ValidationError({"status": "アーカイブ済み売上予算は操作できません。"})
            if period.status in {RevenueBudgetPeriod.Status.DRAFT, RevenueBudgetPeriod.Status.REOPENED}:
                period.status = RevenueBudgetPeriod.Status.REVIEW
                period.updated_by = request.user
                period.save(update_fields=["status", "updated_by", "updated_at"])
            preview = build_revenue_budget_preview(period)
            record_shift_event(
                entity="revenue_budget_period",
                action="preview",
                actor=request.user,
                request=request,
                metadata=revenue_budget_period_metadata(period, preview),
            )
        return Response(preview)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = RevenueWorkflowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period, preview = approve_revenue_budget(
                period=self.get_object(),
                actor=request.user,
                acknowledge_warnings=serializer.validated_data["acknowledge_warnings"],
                validation_fingerprint=serializer.validated_data["validation_fingerprint"],
            )
            record_shift_event(
                entity="revenue_budget_period",
                action="approve",
                actor=request.user,
                request=request,
                metadata=revenue_budget_period_metadata(period, preview),
            )
        return Response(self.get_serializer(revenue_budget_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        RevenueManagerNoteSerializer(data=request.data).is_valid(raise_exception=True)
        with transaction.atomic():
            period = reopen_revenue_budget(period=self.get_object(), actor=request.user)
            record_shift_event(
                entity="revenue_budget_period",
                action="reopen",
                actor=request.user,
                request=request,
                metadata=revenue_budget_period_metadata(period),
            )
        return Response(self.get_serializer(revenue_budget_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        RevenueManagerNoteSerializer(data=request.data).is_valid(raise_exception=True)
        with transaction.atomic():
            period = archive_revenue_budget(period=self.get_object(), actor=request.user)
            record_shift_event(
                entity="revenue_budget_period",
                action="archive",
                actor=request.user,
                request=request,
                metadata=revenue_budget_period_metadata(period),
            )
        return Response(self.get_serializer(revenue_budget_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["get"])
    def lines(self, request, pk=None):
        queryset = RevenueBudgetLine.objects.select_related("category", "budget_period").filter(
            budget_period=self.get_object()
        )
        return Response(RevenueBudgetLineSerializer(queryset.order_by("display_order", "id"), many=True).data)

    @action(detail=True, methods=["get"], url_path="export-csv")
    def export_csv(self, request, pk=None):
        period = self.get_object()
        with transaction.atomic():
            data, filename, summary = export_revenue_budget_csv(period)
            record_shift_event(
                entity="revenue_budget_period",
                action="export",
                actor=request.user,
                request=request,
                metadata=revenue_budget_period_metadata(period)
                | {
                    "line_count": summary["line_count"],
                    "warning_count": summary["warning_count"],
                    "error_count": summary["error_count"],
                },
            )
        response = HttpResponse(data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class RevenueActualLineViewSet(viewsets.ModelViewSet):
    permission_classes = [FinancialPerformancePermission]
    serializer_class = RevenueActualLineSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = RevenueActualLine.objects.select_related("actual_period", "actual_period__location", "category")
        params = self.request.query_params
        if params.get("actual_period"):
            queryset = queryset.filter(actual_period_id=params["actual_period"])
        if params.get("category"):
            queryset = queryset.filter(category_id=params["category"])
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("display_order", "category_code_snapshot", "id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                line = serializer.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="同じ売上区分の実績明細が既に存在します。") from exc
        return Response(self.get_serializer(self.get_queryset().get(pk=line.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                line = serializer.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="売上実績明細を更新できません。") from exc
        return Response(self.get_serializer(self.get_queryset().get(pk=line.pk)).data)


class RevenueActualPeriodViewSet(viewsets.ModelViewSet):
    permission_classes = [FinancialPerformancePermission]
    serializer_class = RevenueActualPeriodSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = revenue_actual_period_queryset()
        params = self.request.query_params
        for field in ["location", "year", "month", "status"]:
            if params.get(field):
                lookup = f"{field}_id" if field == "location" else field
                queryset = queryset.filter(**{lookup: params[field]})
        if params.get("is_active") == "true":
            queryset = queryset.filter(is_active=True)
        if params.get("is_active") == "false":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("-year", "-month", "location__display_order", "id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="revenue_actual_period",
                    action="create",
                    actor=request.user,
                    request=request,
                    metadata=revenue_actual_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc, integrity_message="同じ拠点・年月の有効な売上実績が既に存在します。") from exc
        return Response(self.get_serializer(revenue_actual_period_queryset().get(pk=period.pk)).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = serializer.save()
                record_shift_event(
                    entity="revenue_actual_period",
                    action="update",
                    actor=request.user,
                    request=request,
                    metadata=revenue_actual_period_metadata(period),
                )
        except (DjangoValidationError, IntegrityError) as exc:
            raise _drf_validation(exc) from exc
        return Response(self.get_serializer(revenue_actual_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        with transaction.atomic():
            period = (
                RevenueActualPeriod.objects.select_for_update(of=("self",))
                .select_related(
                    "location",
                    "revenue_budget_period",
                    "labor_cost_budget_period",
                    "labor_cost_estimate_period",
                )
                .get(pk=self.get_object().pk)
            )
            if period.status == RevenueActualPeriod.Status.ARCHIVED or not period.is_active:
                raise ValidationError({"status": "アーカイブ済み売上実績は操作できません。"})
            if period.status in {RevenueActualPeriod.Status.DRAFT, RevenueActualPeriod.Status.REOPENED}:
                period.status = RevenueActualPeriod.Status.REVIEW
                period.updated_by = request.user
                period.save(update_fields=["status", "updated_by", "updated_at"])
            preview = build_revenue_actual_preview(period)
            period.revenue_budget_period_id = preview["revenue_budget_period"]
            period.labor_cost_budget_period_id = preview["labor_cost_budget_period"]
            period.labor_cost_estimate_period_id = preview["labor_cost_estimate_period"]
            period.updated_by = request.user
            period.full_clean()
            period.save(
                update_fields=[
                    "revenue_budget_period",
                    "labor_cost_budget_period",
                    "labor_cost_estimate_period",
                    "updated_by",
                    "updated_at",
                ]
            )
            record_shift_event(
                entity="revenue_actual_period",
                action="preview",
                actor=request.user,
                request=request,
                metadata=revenue_actual_period_metadata(period, preview),
            )
        return Response(preview)

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        serializer = RevenueWorkflowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            period, preview = finalize_revenue_actual(
                period=self.get_object(),
                actor=request.user,
                acknowledge_warnings=serializer.validated_data["acknowledge_warnings"],
                validation_fingerprint=serializer.validated_data["validation_fingerprint"],
            )
            record_shift_event(
                entity="revenue_actual_period",
                action="finalize",
                actor=request.user,
                request=request,
                metadata=revenue_actual_period_metadata(period, preview),
            )
        return Response(self.get_serializer(revenue_actual_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        RevenueManagerNoteSerializer(data=request.data).is_valid(raise_exception=True)
        with transaction.atomic():
            period = reopen_revenue_actual(period=self.get_object(), actor=request.user)
            record_shift_event(
                entity="revenue_actual_period",
                action="reopen",
                actor=request.user,
                request=request,
                metadata=revenue_actual_period_metadata(period),
            )
        return Response(self.get_serializer(revenue_actual_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        RevenueManagerNoteSerializer(data=request.data).is_valid(raise_exception=True)
        with transaction.atomic():
            period = archive_revenue_actual(period=self.get_object(), actor=request.user)
            record_shift_event(
                entity="revenue_actual_period",
                action="archive",
                actor=request.user,
                request=request,
                metadata=revenue_actual_period_metadata(period),
            )
        return Response(self.get_serializer(revenue_actual_period_queryset().get(pk=period.pk)).data)

    @action(detail=True, methods=["get"])
    def lines(self, request, pk=None):
        queryset = RevenueActualLine.objects.select_related("category", "actual_period").filter(
            actual_period=self.get_object()
        )
        return Response(RevenueActualLineSerializer(queryset.order_by("display_order", "id"), many=True).data)

    @action(detail=True, methods=["get"])
    def performance(self, request, pk=None):
        payload = get_revenue_performance(self.get_object())
        return Response(payload)

    @action(detail=True, methods=["get"], url_path="performance-lines")
    def performance_lines(self, request, pk=None):
        period = self.get_object()
        if period.status == RevenueActualPeriod.Status.FINALIZED:
            snapshot = RevenuePerformanceSnapshot.objects.filter(actual_period=period).first()
            if snapshot:
                queryset = RevenuePerformanceLineSnapshot.objects.select_related("category").filter(
                    performance_snapshot=snapshot
                )
                return Response(RevenuePerformanceLineSnapshotSerializer(queryset, many=True).data)
        return Response(get_revenue_performance(period)["performance_lines"])

    @action(detail=True, methods=["get"], url_path="export-csv")
    def export_csv(self, request, pk=None):
        period = self.get_object()
        with transaction.atomic():
            data, filename, summary = export_revenue_actual_csv(period)
            record_shift_event(
                entity="revenue_actual_period",
                action="export",
                actor=request.user,
                request=request,
                metadata=revenue_actual_period_metadata(period)
                | {
                    "line_count": summary["line_count"],
                    "warning_count": summary["warning_count"],
                    "error_count": summary["error_count"],
                },
            )
        response = HttpResponse(data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class FinancialPerformanceViewSet(viewsets.ViewSet):
    permission_classes = [FinancialPerformancePermission]
    http_method_names = ["get", "head", "options"]

    def list(self, request):
        missing = [field for field in ["location", "year", "month"] if not request.query_params.get(field)]
        if missing:
            raise ValidationError({field: "必須です。" for field in missing})
        try:
            year = int(request.query_params["year"])
            month = int(request.query_params["month"])
        except ValueError as exc:
            raise ValidationError({"year": "year/monthは数値で指定してください。"}) from exc
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            raise ValidationError({"month": "yearは2000-2100、monthは1-12で指定してください。"})
        return Response(
            get_financial_performance(
                location_id=request.query_params["location"],
                year=year,
                month=month,
            )
        )
