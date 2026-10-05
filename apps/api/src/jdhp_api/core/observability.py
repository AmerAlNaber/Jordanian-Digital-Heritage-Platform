"""Structured logging with redaction (SEC-27). Tracing and metrics attach here later.

Logs never contain tokens, passwords, secrets or identity documents. The redaction processor
runs on every event, so a careless log call cannot leak a credential.
"""

from __future__ import annotations

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

SENSITIVE_KEY_PARTS = ("token", "password", "secret", "authorization", "cookie", "document", "key")
REDACTED = "[redacted]"
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        value = _BEARER.sub(f"Bearer {REDACTED}", value)
        return _JWT.sub(REDACTED, value)
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_sensitive_key(str(k)) else redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_value(v) for v in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in {"request_id", "key_id", "kid", "public_key"}:
        return False
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if _is_sensitive_key(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = redact_value(event_dict[key])
    return event_dict


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level.upper(), format="%(message)s")


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
