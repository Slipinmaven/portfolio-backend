import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_context

logger = logging.getLogger("app.http")
_REQUEST_ID_PATTERN = re.compile(rb"^[A-Za-z0-9._:-]{1,128}$")


def _request_id(headers: list[tuple[bytes, bytes]]) -> str:
    supplied = next(
        (value for name, value in headers if name.lower() == b"x-request-id"),
        b"",
    )
    if _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied.decode("ascii")
    return str(uuid4())


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope.get("headers", []))
        token = request_id_context.set(request_id)
        started_at = perf_counter()
        method = scope["method"]
        path = scope["path"]
        status_code = 500
        response_logged = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_logged
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}

            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                duration_ms = round((perf_counter() - started_at) * 1000, 2)
                logger.info(
                    "HTTP request completed",
                    extra={
                        "event": "http.request.completed",
                        "method": method,
                        "path": path,
                        "status": status_code,
                        "duration_ms": duration_ms,
                    },
                )
                response_logged = True

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            if not response_logged:
                logger.exception(
                    "HTTP request failed",
                    extra={
                        "event": "http.request.failed",
                        "method": method,
                        "path": path,
                        "status": status_code,
                        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                    },
                )
            raise
        finally:
            request_id_context.reset(token)
