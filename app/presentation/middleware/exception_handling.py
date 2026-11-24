import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.application.errors import AppError
from app.core.logging import request_id_context

logger = logging.getLogger("app.error")


class ExceptionHandlingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def track_response_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_response_start)
        except AppError as exc:
            if response_started:
                raise

            logger.log(
                logging.ERROR if exc.status_code >= 500 else logging.INFO,
                "Application error while processing request",
                extra={
                    "event": "http.request.application_error",
                    "error_code": exc.code,
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": exc.status_code,
                },
            )
            headers: dict[str, str] = {}
            request_id = request_id_context.get()
            if request_id != "-":
                headers["X-Request-ID"] = request_id
            response = JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.code, "message": exc.message},
                headers=headers,
            )
            await response(scope, receive, send)
        except Exception:
            if response_started:
                raise

            logger.exception(
                "Unhandled exception while processing request",
                extra={
                    "event": "http.request.unhandled_exception",
                    "error_code": "internal_server_error",
                    "method": scope["method"],
                    "path": scope["path"],
                },
            )
            headers: dict[str, str] = {}
            request_id = request_id_context.get()
            if request_id != "-":
                headers["X-Request-ID"] = request_id
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers=headers,
            )
            await response(scope, receive, send)
