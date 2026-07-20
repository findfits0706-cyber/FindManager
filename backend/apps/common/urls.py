from django.urls import path

from .views import AuditEventListView, HealthCheckView, ReadinessCheckView, SystemStatusView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("readiness/", ReadinessCheckView.as_view(), name="readiness"),
    path("audit-events/", AuditEventListView.as_view(), name="audit-events"),
    path("system/status/", SystemStatusView.as_view(), name="system-status"),
]
