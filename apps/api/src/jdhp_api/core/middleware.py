"""Request context and response hygiene.

Every response carries a request identifier for the audit trail and the logs. API responses
are private and uncacheable unless a handler says otherwise (PRF-4); public catalog handlers
set their own cache headers. The remaining security headers come from the reverse proxy
(SEC-16), but the ones that matter for API bodies are set here too.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


def _request_id(request: Request) -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    try:
        return str(uuid.UUID(incoming))
    except ValueError:
        return str(uuid.uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _request_id(request)
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=request.method, path=request.url.path
        )
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers.setdefault("Cache-Control", "private, no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response
