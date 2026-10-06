"""SMS adapters (ADR-0001 D7, ADR-0010): the mock records, the email adapter posts to one inbox."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

import pytest

from jdhp_api.core.messaging import EmailSmsSender, MockSmsSender, make_sms_sender, mask_phone
from tests.core.test_config import build


class FakeSmtp:
    sent: list[tuple[tuple[str, int], EmailMessage]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.address = (host, port)
        assert timeout > 0

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def send_message(self, message: EmailMessage) -> None:
        FakeSmtp.sent.append((self.address, message))


async def test_mock_sender_records_and_logs_a_masked_number() -> None:
    sender = MockSmsSender()
    await sender.send("+962790001234", "123456 is your code")
    assert sender.sent[-1].to == "+962790001234"
    assert mask_phone("+962790001234") == "+962•••••••34"


async def test_email_sender_posts_the_code_to_the_shared_inbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    FakeSmtp.sent.clear()
    sender = EmailSmsSender("mailpit", 1025, "noreply@rig.test", "sms-codes@rig.test")
    await sender.send("+962790001234", "654321 هو رمز التحقق")
    ((address, message),) = FakeSmtp.sent
    assert address == ("mailpit", 1025)
    assert message["To"] == "sms-codes@rig.test"
    assert message["From"] == "noreply@rig.test"
    assert message["Subject"] == "SMS to +962790001234"
    assert "654321" in message.get_content()


def test_factory_picks_the_adapter_from_the_settings() -> None:
    assert isinstance(
        make_sms_sender(
            build(
                env="local",
                sms_provider="mock",
                oidc_issuer="http://x/realms/j",
                public_base_url="http://x",
                api_base_url="http://x/api",
            )
        ),
        MockSmsSender,
    )
    rig = build(
        env="testrig",
        sms_provider="email",
        smtp_host="mailpit",
        smtp_from="noreply@rig.test",
        oidc_issuer="http://x/realms/j",
        public_base_url="http://x",
        api_base_url="http://x/api",
    )
    assert isinstance(make_sms_sender(rig), EmailSmsSender)
