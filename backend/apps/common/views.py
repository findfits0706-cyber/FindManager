from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import ROLE_SYSTEM_ADMIN
from apps.accounts.models import User
from apps.operations.models import Location
from apps.shifts.models import (
    AttendanceClosingPeriod,
    AttendanceCorrectionRequest,
    LaborCostBudgetPeriod,
    LaborCostEstimatePeriod,
    RevenueActualPeriod,
    ShiftChangeRequest,
    ShiftRequestSubmission,
)

from .exceptions import error_payload
from .models import AuditEvent
from .readiness import check_readiness
from .serializers import AuditEventSerializer


class IsSystemAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.has_role(ROLE_SYSTEM_ADMIN))


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class ReadinessCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        result = check_readiness()
        return Response(
            {"status": "ready" if result.ready else "not_ready"},
            status=status.HTTP_200_OK if result.ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class AuditEventListView(generics.ListAPIView):
    permission_classes = [IsSystemAdmin]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        queryset = AuditEvent.objects.select_related("actor", "target_user").order_by("-occurred_at")
        event_type = self.request.query_params.get("event_type")
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        return queryset


class SystemStatusView(APIView):
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        readiness = check_readiness()
        last_audit_at = AuditEvent.objects.order_by("-occurred_at").values_list("occurred_at", flat=True).first()
        pending_requests = (
            ShiftRequestSubmission.objects.filter(status=ShiftRequestSubmission.Status.SUBMITTED).count()
            + ShiftChangeRequest.objects.filter(
                status__in=[ShiftChangeRequest.Status.SUBMITTED, ShiftChangeRequest.Status.APPROVED]
            ).count()
            + AttendanceCorrectionRequest.objects.filter(
                status__in=[AttendanceCorrectionRequest.Status.SUBMITTED, AttendanceCorrectionRequest.Status.APPROVED]
            ).count()
        )
        payload = {
            "backend_version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "api_health": "ok",
            "api_readiness": "ready" if readiness.ready else "not_ready",
            "migration_status": "up_to_date" if readiness.migrations else "pending",
            "database_status": "connected" if readiness.database else "unavailable",
            "last_audit_event_at": timezone.localtime(last_audit_at).isoformat() if last_audit_at else None,
            "active_location_count": Location.objects.filter(is_active=True).count(),
            "active_staff_count": User.objects.filter(is_active=True).count(),
            "pending_request_count": pending_requests,
            "unclosed_attendance_period_count": AttendanceClosingPeriod.objects.filter(is_active=True)
            .exclude(status__in=[AttendanceClosingPeriod.Status.CLOSED, AttendanceClosingPeriod.Status.ARCHIVED])
            .count(),
            "unfinalized_labor_estimate_period_count": LaborCostEstimatePeriod.objects.filter(is_active=True)
            .exclude(status__in=[LaborCostEstimatePeriod.Status.FINALIZED, LaborCostEstimatePeriod.Status.ARCHIVED])
            .count(),
            "unapproved_labor_budget_period_count": LaborCostBudgetPeriod.objects.filter(is_active=True)
            .exclude(status__in=[LaborCostBudgetPeriod.Status.APPROVED, LaborCostBudgetPeriod.Status.ARCHIVED])
            .count(),
            "unfinalized_revenue_actual_period_count": RevenueActualPeriod.objects.filter(is_active=True)
            .exclude(status__in=[RevenueActualPeriod.Status.FINALIZED, RevenueActualPeriod.Status.ARCHIVED])
            .count(),
        }
        return Response(payload)


def csrf_failure(request, reason=""):
    request_id = getattr(request, "request_id", None)
    payload = error_payload(
        status_code=403,
        data={"detail": "CSRF検証に失敗しました。ページを再読み込みして再度お試しください。"},
        request_id=request_id,
    )
    payload["code"] = "csrf_failed"
    if settings.DEBUG and reason:
        payload["reason"] = reason
    return JsonResponse(payload, status=403)


def json_not_found(request, exception=None):
    if request.path.startswith("/api/"):
        return JsonResponse(
            error_payload(status_code=404, request_id=getattr(request, "request_id", None)),
            status=404,
        )
    return JsonResponse({"detail": "Not found."}, status=404)


def json_server_error(request):
    if request.path.startswith("/api/"):
        return JsonResponse(
            error_payload(status_code=500, request_id=getattr(request, "request_id", None)),
            status=500,
        )
    return JsonResponse({"detail": "Server error."}, status=500)
