from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


def csrf_failure(request, reason=""):
    return JsonResponse(
        {
            "detail": "CSRF検証に失敗しました。ページを再読み込みして再度お試しください。",
            "code": "csrf_failed",
            "reason": reason,
        },
        status=403,
    )
