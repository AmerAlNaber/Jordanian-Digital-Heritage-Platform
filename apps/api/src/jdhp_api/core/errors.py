"""Error model: RFC 9457 problem details with stable codes and localized text.

Responses never carry internal identifiers, stack traces or database text (SEC-17). Every
problem carries the request identifier so an operator can find the full record in the logs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status as http

from jdhp_api.core.i18n import negotiate_locale, translate

PROBLEM_MEDIA_TYPE = "application/problem+json"
ERROR_TYPE_PREFIX = "urn:jdhp:error:"


class JdhpError(Exception):
    """Base class for errors the API raises on purpose."""

    status: int = http.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal"
    headers: Mapping[str, str] | None = None

    def __init__(
        self, *, detail: str | None = None, extra: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(detail or self.code)
        self.detail_override = detail
        self.extra = dict(extra or {})


class NotFoundError(JdhpError):
    status = http.HTTP_404_NOT_FOUND
    code = "not_found"


class InvalidIdentifierError(JdhpError):
    status = http.HTTP_404_NOT_FOUND
    code = "invalid_identifier"


class ForbiddenError(JdhpError):
    status = http.HTTP_403_FORBIDDEN
    code = "forbidden"


class UnauthorizedError(JdhpError):
    status = http.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    headers = {"WWW-Authenticate": "Bearer"}


class ConflictError(JdhpError):
    status = http.HTTP_409_CONFLICT
    code = "conflict"


class ReviewTransitionError(ConflictError):
    code = "review_transition"


class PolicyEngineUnavailableError(JdhpError):
    """A policy engine failure is a denial, never an allowance (SEC-6)."""

    status = http.HTTP_503_SERVICE_UNAVAILABLE
    code = "policy_engine_unavailable"
    headers = {"Retry-After": "5"}


class RateLimitedError(JdhpError):
    status = http.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


def problem(
    request: Request, *, status: int, code: str, extra: Mapping[str, Any] | None = None
) -> JSONResponse:
    locale = negotiate_locale(request.headers.get("accept-language"))
    body: dict[str, Any] = {
        "type": f"{ERROR_TYPE_PREFIX}{code}",
        "title": translate(locale, f"errors.{code}.title"),
        "status": status,
        "detail": translate(locale, f"errors.{code}.detail"),
        "instance": request.url.path,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(JdhpError)
    async def _jdhp_error(request: Request, exc: JdhpError) -> JSONResponse:
        response = problem(request, status=exc.status, code=exc.code, extra=exc.extra)
        for key, value in (exc.headers or {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations only; never echo submitted values back (SEC-17).
        fields = [
            {"loc": [str(part) for part in err.get("loc", ())], "type": str(err.get("type", ""))}
            for err in exc.errors()
        ]
        return problem(
            request,
            status=http.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation",
            extra={"errors": fields},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        return problem(request, status=http.HTTP_500_INTERNAL_SERVER_ERROR, code="internal")
