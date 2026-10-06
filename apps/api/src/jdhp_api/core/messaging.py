"""Text messages behind an adapter (ADR-0001 D7, ACC-1).

The platform sends one kind of SMS today: the phone verification code. The mock keeps what it
sent so tests can read the code back; it is refused outside local and test environments by the
settings validation, like every other mock provider.
"""

from __future__ import annotations

import asyncio
import dataclasses
import smtplib
from email.message import EmailMessage
from typing import Protocol

from jdhp_api.core.config import EMAIL_SMS_PROVIDER, MOCK_PROVIDER, ConfigurationError, Settings
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


class EmailSmsSender:
    """Delivers each message as an email to one inbox: a testing rig's mail catcher (ADR-0010).

    The subject names the destination number so a tester finds their code; nothing leaves the
    stack because the SMTP host is the catcher itself. Refused where real content lives.
    """

    def __init__(self, host: str, port: int, sender: str, inbox: str) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._inbox = inbox

    def _deliver(self, to: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = self._inbox
        message["Subject"] = f"SMS to {to}"
        message.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            smtp.send_message(message)

    async def send(self, to: str, body: str) -> None:
        await asyncio.to_thread(self._deliver, to, body)
        log.info("sms_emailed", to=mask_phone(to), inbox=self._inbox)


def make_sms_sender(settings: Settings) -> SmsSender:
    if settings.sms_provider == MOCK_PROVIDER:
        return MockSmsSender()
    if settings.sms_provider == EMAIL_SMS_PROVIDER:
        if not settings.smtp_host:  # pragma: no cover - the settings validator refuses this
            raise ConfigurationError("sms_provider 'email' needs smtp_host")
        return EmailSmsSender(
            settings.smtp_host, settings.smtp_port, settings.smtp_from, settings.sms_inbox
        )
    raise ConfigurationError(
        f"sms_provider '{settings.sms_provider}' has no adapter yet; the SMS gateway adapter "
        "arrives with the Phase 2 messaging work (ADR-0009)"
    )
