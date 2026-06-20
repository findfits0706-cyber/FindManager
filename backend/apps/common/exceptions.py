from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    return Response({"detail": "サーバーエラーが発生しました。"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
