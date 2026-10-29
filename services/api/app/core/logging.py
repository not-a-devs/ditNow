import json
import logging
from uuid import uuid4

from starlette.routing import get_route_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response
from app.schemas.common import ErrorCode

logger = logging.getLogger("ditnow.api")

# Token/personal-answer route trees. Matched on the route-relative path so an ASGI root_path
# (proxy prefix, mount) keeps them private, including 404s and trailing-slash redirects.
PRIVATE_ROUTE_PREFIXES = ("/api/v1/auth", "/api/v1/ai/ask")


def is_private_route(scope: Scope) -> bool:
    path = get_route_path(scope)
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in PRIVATE_ROUTE_PREFIXES)


def configure_logging(level: str) -> None:
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


class SafeRequestMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        status = 500
        started = False

        async def safe_send(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                headers = [
                    pair
                    for pair in message.get("headers", [])
                    if pair[0].lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                if is_private_route(scope):
                    headers = [pair for pair in headers if pair[0].lower() != b"cache-control"]
                    headers.append((b"cache-control", b"private, no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, safe_send)
        except Exception:
            # Never pass exception repr, request body, URL, headers or credentials to loggers.
            logger.error(json.dumps({"event": "request.failed", "request_id": request_id}))
            if started:
                raise RuntimeError("Response handling failed") from None
            await error_response(ErrorCode.INTERNAL, request_id)(scope, receive, safe_send)
        finally:
            method = scope.get("method", "")
            logger.info(
                json.dumps(
                    {
                        "event": "request.completed",
                        "request_id": request_id,
                        "method": method
                        if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                        else "OTHER",
                        "status": status,
                    }
                )
            )
