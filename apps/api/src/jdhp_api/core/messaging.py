"""Text messages behind an adapter (ADR-0001 D7, ACC-1).

The platform sends one kind of SMS today: the phone verification code. The mock keeps what it
sent so tests can read the code back; it is refused outside local and test environments by the
settings validation, like every other mock provider.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from jdhp_api.core.config import MOCK_PROVIDER, ConfigurationError, Settings
from jdhp_api.core.observability import get_logger

log = get_logger(__name__)


class SmsSender(Protocol):
    async def send(self, to: str, body: str) -> None: ...


def mask_phone(number: str) -> str:
    """``+962790001234`` becomes ``+962•••••••34``: enough to recognise, never to dial."""
    if len(number) <= 6:
        return "•" * len(number)
    return number[:4] + "•" * (len(number) - 6) + number[-2:]


@dataclasses.dataclass(frozen=True)
class SentSms:
    to: str
    body: str


class MockSmsSender:
    """Records messages instead of sending them; the local stack reads them from the log."""

    def __init__(self) -> None:
        self.sent: list[SentSms] = []

    async def send(self, to: str, body: str) -> None:
        self.sent.append(SentSms(to=to, body=body))
        log.info("sms_mock_sent", to=mask_phone(to), body=body)


def make_sms_sender(settings: Settings) -> SmsSender:
    if settings.sms_provider == MOCK_PROVIDER:
        return MockSmsSender()
    raise ConfigurationError(
        f"sms_provider '{settings.sms_provider}' has no adapter yet; the SMS gateway adapter "
        "arrives with the Phase 2 messaging work (ADR-0009)"
    )
