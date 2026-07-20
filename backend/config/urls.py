from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include("apps.common.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.operations.urls")),
    path("api/v1/", include("apps.shifts.urls")),
]

handler404 = "apps.common.views.json_not_found"
handler500 = "apps.common.views.json_server_error"
