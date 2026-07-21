import logging
import re
import time
import uuid

from .request_context import reset_request_id, set_request_id

logger = logging.getLogger("findmanager.request")
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _request_id(request) -> str:
    candidate = request.headers.get("X-Request-ID", "")
    return candidate if SAFE_REQUEST_ID.fullmatch(candidate) else str(uuid.uuid4())


def _user_metadata(request) -> tuple[str | None, str | None]:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None, None
    roles = user.role_keys
    return str(user.pk), ",".join(roles) or None


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = _request_id(request)
        request.request_id = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception as exc:
            user_id, role = _user_metadata(request)
            logger.error(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "status": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "user_id": user_id,
                    "role": role,
                    "exception_type": type(exc).__name__,
                },
            )
            raise
        else:
            response["X-Request-ID"] = request_id
            user_id, role = _user_metadata(request)
            logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "user_id": user_id,
                    "role": role,
                },
            )
            return response
        finally:
            reset_request_id(token)
