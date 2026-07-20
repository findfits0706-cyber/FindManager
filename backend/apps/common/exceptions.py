import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .request_context import get_request_id

logger = logging.getLogger("findmanager.request")

STATUS_CODES = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    409: "conflict",
    429: "throttled",
    500: "server_error",
}

STATUS_MESSAGES = {
    400: "入力内容を確認してください。",
    401: "認証が必要です。",
    403: "この操作を行う権限がありません。",
    404: "対象が見つかりません。",
    409: "現在の状態では処理できません。",
    429: "リクエストが多すぎます。しばらく待ってから再度お試しください。",
    500: "サーバーエラーが発生しました。",
}


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)


def error_payload(*, status_code: int, data=None, request_id: str | None = None) -> dict:
    plain = _plain(data) if data is not None else {}
    original = plain if isinstance(plain, dict) else {"detail": plain}
    detail = original.get("detail")
    message = detail if isinstance(detail, str) else STATUS_MESSAGES.get(status_code, "リクエストに失敗しました。")
    detail_code = getattr(data.get("detail"), "code", None) if isinstance(data, dict) else None
    code = detail_code or STATUS_CODES.get(status_code, "request_error")
    field_errors = {key: value for key, value in original.items() if key not in {"detail", "code", "message"}}
    return {
        **original,
        "detail": message,
        "code": code,
        "message": message,
        "errors": field_errors,
        "request_id": request_id or get_request_id(),
    }


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    request = context.get("request")
    request_id = getattr(request, "request_id", None) or get_request_id()
    if response is not None:
        response.data = error_payload(status_code=response.status_code, data=response.data, request_id=request_id)
        return response
    logger.error(
        "unhandled_api_exception",
        extra={"request_id": request_id, "exception_type": type(exc).__name__, "status": 500},
    )
    return Response(
        error_payload(status_code=500, request_id=request_id),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
