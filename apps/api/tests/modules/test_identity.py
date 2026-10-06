"""Accounts: just-in-time users, profile, phone verification, sessions (ACC-1, ACC-5, SEC-5)."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.messaging import MockSmsSender
from jdhp_api.core.orm import AccessClass, ReaderSessionState
from jdhp_api.modules.identity import service
from jdhp_api.modules.identity.models import PhoneVerification, User
from jdhp_api.modules.reader.models import ReaderSession
from tests.factories import make_work

Headers = Callable[..., dict[str, str]]


async def test_me_creates_the_user_on_first_sight_with_the_token_role(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    response = await client.get(
        "/me", headers=auth("newcomer", ["reviewer"], mfa=True, phone_verified=True)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "newcomer"
    assert body["role"] == "reviewer"
    assert body["verification_level"] == "phone"
    assert body["mfa"] is True
    async with admin_database.session(RlsContext.system()) as session:
        users = (await session.scalars(select(User))).all()
    assert [u.keycloak_sub for u in users] == ["newcomer"]


async def test_anonymous_has_no_profile(client: httpx.AsyncClient) -> None:
    assert (await client.get("/me")).status_code == 403


async def test_preferences_are_validated_and_merged(
    client: httpx.AsyncClient, auth: Headers
) -> None:
    headers = auth("pref", ["member"])
    first = await client.patch("/me/preferences", json={"locale": "en"}, headers=headers)
    assert first.status_code == 200
    second = await client.patch("/me/preferences", json={"numerals": "eastern"}, headers=headers)
    assert second.json()["preferences"] == {"locale": "en", "numerals": "eastern"}
    invalid = await client.patch("/me/preferences", json={"locale": "fr"}, headers=headers)
    assert invalid.status_code == 422
    unknown = await client.patch(
        "/me/preferences", json={"role": "platform_admin"}, headers=headers
    )
    assert unknown.status_code == 422


async def test_role_follows_the_token_on_later_requests(
    client: httpx.AsyncClient, auth: Headers
) -> None:
    assert (await client.get("/me", headers=auth("flux", ["member"]))).json()["role"] == "member"
    assert (await client.get("/me", headers=auth("flux", ["curator"], mfa=True))).json()[
        "role"
    ] == "curator"
    assert (await client.get("/me", headers=auth("flux", ["member"]))).json()["role"] == "member"


# --- Phone verification (ACC-1, SEC-4, T-B7) ---------------------------------------------------

PHONE = "+962790001234"


def _sms(app: FastAPI) -> MockSmsSender:
    sender = app.state.sms_sender
    assert isinstance(sender, MockSmsSender)
    return sender


def _code(sms: MockSmsSender) -> str:
    match = re.search(r"\b(\d{6})\b", sms.sent[-1].body)
    assert match, sms.sent[-1].body
    return match.group(1)


async def test_sec_2_first_requests_of_one_sign_in_that_race_share_the_user_row(
    admin_database: Database,
) -> None:
    """A page's first requests arrive together; two of them insert the same subject at once."""
    claims = {
        "sub": str(uuid.uuid4()),
        "email": "race@example.test",
        "name": "Racing Member",
        "realm_access": {"roles": ["member"]},
    }
    async with admin_database.session(RlsContext.system()) as first:
        winner = await service.upsert_from_claims(first, claims)

        async def second_request() -> User:
            async with admin_database.session(RlsContext.system()) as second:
                return await service.upsert_from_claims(second, claims)

        # The second insert waits on the first transaction's index entry, then finds the row taken.
        task = asyncio.create_task(second_request())
        await asyncio.sleep(0.3)
        assert not task.done()
        await first.commit()
    loser = await task
    assert loser.id == winner.id
    async with admin_database.session(RlsContext.system()) as session:
        rows = (await session.scalars(select(User).where(User.keycloak_sub == claims["sub"]))).all()
    assert len(rows) == 1


async def test_acc_1_phone_verification_raises_the_level_and_outlives_the_token_claim(
    client: httpx.AsyncClient, app: FastAPI, auth: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "RESEND_GAP", dt.timedelta(0))
    headers = auth("caller", ["member"], phone_verified=False)
    before = await client.get("/me", headers=headers)
    assert before.json()["verification_level"] == "email"
    assert before.json()["phone_number"] is None

    started = await client.post("/me/phone", json={"phone_number": PHONE}, headers=headers)
    assert started.status_code == 202
    assert started.json()["pending"] is True
    assert started.json()["phone_number"] == "+962•••••••34", "masked, never the number"
    sms = _sms(app)
    assert sms.sent[-1].to == PHONE
    assert "التراث" in sms.sent[-1].body, "Arabic by default"

    wrong = await client.post("/me/phone/verify", json={"code": "000000"}, headers=headers)
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "phone_code_invalid"

    confirmed = await client.post("/me/phone/verify", json={"code": _code(sms)}, headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["verification_level"] == "phone"
    assert body["phone_number"] == "+962•••••••34"
    assert body["phone_verified_at"] is not None

    # The next token still says nothing about the phone; the platform's record wins.
    later = await client.get("/me", headers=auth("caller", ["member"], phone_verified=False))
    assert later.json()["verification_level"] == "phone"
    status = await client.get("/me/phone", headers=headers)
    assert status.json() == {
        "phone_number": "+962•••••••34",
        "verified_at": body["phone_verified_at"],
        "pending": False,
        "expires_at": None,
    }
    repeat = await client.post("/me/phone/verify", json={"code": _code(sms)}, headers=headers)
    assert repeat.status_code == 400, "a code works once"


async def test_acc_1_wrong_codes_are_limited_and_answered_alike(
    client: httpx.AsyncClient, app: FastAPI, auth: Headers
) -> None:
    headers = auth("guesser", ["member"])
    assert (
        await client.post("/me/phone", json={"phone_number": PHONE}, headers=headers)
    ).status_code == 202
    code = _code(_sms(app))
    answers = set()
    for _ in range(service.MAX_ATTEMPTS):
        response = await client.post("/me/phone/verify", json={"code": "999999"}, headers=headers)
        answers.add((response.status_code, response.json()["code"]))
    assert answers == {(400, "phone_code_invalid")}, "every refusal reads the same (T-B7)"
    exhausted = await client.post("/me/phone/verify", json={"code": code}, headers=headers)
    assert exhausted.status_code == 400, "the right code after five wrong ones is dead too"
    assert (await client.get("/me/phone", headers=headers)).json()["pending"] is False


async def test_acc_1_codes_expire(
    client: httpx.AsyncClient, app: FastAPI, auth: Headers, admin_database: Database
) -> None:
    headers = auth("slow", ["member"])
    assert (
        await client.post("/me/phone", json={"phone_number": PHONE}, headers=headers)
    ).status_code == 202
    code = _code(_sms(app))
    async with admin_database.session(RlsContext.system()) as session:
        await session.execute(
            update(PhoneVerification).values(
                expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
            )
        )
        await session.commit()
    expired = await client.post("/me/phone/verify", json={"code": code}, headers=headers)
    assert expired.status_code == 400
    assert expired.json()["code"] == "phone_code_invalid"


async def test_sec_4_code_sends_are_rate_limited(
    client: httpx.AsyncClient, app: FastAPI, auth: Headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth("eager", ["member"])
    first = await client.post("/me/phone", json={"phone_number": PHONE}, headers=headers)
    assert first.status_code == 202
    gap = await client.post("/me/phone", json={"phone_number": PHONE}, headers=headers)
    assert gap.status_code == 429, "a minute between sends"
    monkeypatch.setattr(service, "RESEND_GAP", dt.timedelta(0))
    for _ in range(service.SENDS_PER_WINDOW - 1):
        assert (
            await client.post("/me/phone", json={"phone_number": PHONE}, headers=headers)
        ).status_code == 202
    capped = await client.post("/me/phone", json={"phone_number": PHONE}, headers=headers)
    assert capped.status_code == 429
    assert capped.json()["code"] == "phone_send_limited"
    assert len(_sms(app).sent) == service.SENDS_PER_WINDOW


async def test_acc_1_phone_numbers_must_be_e164(client: httpx.AsyncClient, auth: Headers) -> None:
    headers = auth("typo", ["member"])
    for bad in ("0790001234", "+962 79 000 1234", "+0123456789", "962790001234"):
        assert (
            await client.post("/me/phone", json={"phone_number": bad}, headers=headers)
        ).status_code == 422
    assert (
        await client.post("/me/phone/verify", json={"code": "12345"}, headers=headers)
    ).status_code == 422


async def test_acc_1_phone_routes_need_a_signed_in_user(client: httpx.AsyncClient) -> None:
    assert (await client.post("/me/phone", json={"phone_number": PHONE})).status_code == 403
    assert (await client.get("/me/sessions")).status_code == 403


# --- Sessions (SEC-5) ------------------------------------------------------------------------


async def _open_reader(
    client: httpx.AsyncClient, work: str, headers: dict[str, str], fingerprint: str
) -> dict[str, Any]:
    response = await client.post(
        "/reader/sessions",
        json={"work": work, "device_fingerprint": fingerprint},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_sec_5_user_sees_their_readers_and_ending_a_sign_in_ends_them(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, access_class=AccessClass.REGISTERED, pages=3)
        await session.commit()
        work_id = work.public_id
    laptop = auth("reader", ["member"], phone_verified=True, extra={"sid": "sign-in-laptop"})
    phone = auth("reader", ["member"], phone_verified=True, extra={"sid": "sign-in-phone"})
    on_laptop = await _open_reader(client, work_id, laptop, "fingerprint-laptop-0001")
    on_phone = await _open_reader(client, work_id, phone, "fingerprint-phone-00001")

    listed = await client.get("/me/sessions", headers=laptop)
    assert listed.status_code == 200
    body = listed.json()
    assert body["sign_in"] == "sign-in-laptop"
    by_name = {r["public_id"]: r for r in body["readers"]}
    assert set(by_name) == {on_laptop["public_id"], on_phone["public_id"]}
    assert by_name[on_laptop["public_id"]]["current_sign_in"] is True
    assert by_name[on_phone["public_id"]]["current_sign_in"] is False
    assert by_name[on_phone["public_id"]]["sign_in"] == "sign-in-phone"
    assert by_name[on_phone["public_id"]]["work"] == work_id
    assert len(by_name[on_phone["public_id"]]["device"]) == 8, (
        "a device hash prefix, never the fingerprint"
    )

    # Ending the phone's sign-in from the laptop ends the phone's reader at once.
    ended = await client.delete("/me/sign-ins/sign-in-phone", headers=laptop)
    assert ended.status_code == 204
    heartbeat = await client.post(
        f"/reader/sessions/{on_phone['public_id']}/heartbeat",
        json={
            "device_fingerprint": "fingerprint-phone-00001",
            "pages_viewed": [],
            "dwell_seconds": 1,
        },
        headers={"X-Jdhp-Grant": on_phone["tokens"]["grant_token"]},
    )
    assert heartbeat.status_code == 401
    assert heartbeat.json()["code"] == "reader_session_ended"
    remaining = (await client.get("/me/sessions", headers=laptop)).json()["readers"]
    assert [r["public_id"] for r in remaining] == [on_laptop["public_id"]]
    async with admin_database.session(RlsContext.system()) as session:
        states = {
            r.public_id: r.state for r in (await session.scalars(select(ReaderSession))).all()
        }
    assert states[on_phone["public_id"]] == ReaderSessionState.REVOKED
    assert states[on_laptop["public_id"]] == ReaderSessionState.ACTIVE


async def test_sec_5_one_reader_can_be_ended_and_only_by_its_owner(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, access_class=AccessClass.REGISTERED, pages=3)
        await session.commit()
        work_id = work.public_id
    owner = auth("owner", ["member"], phone_verified=True, extra={"sid": "s-owner"})
    other = auth("other", ["member"], phone_verified=True, extra={"sid": "s-other"})
    opened = await _open_reader(client, work_id, owner, "fingerprint-owner-00001")
    assert (
        await client.delete(f"/me/sessions/{opened['public_id']}", headers=other)
    ).status_code == 404
    assert (await client.get("/me/sessions", headers=other)).json()["readers"] == []
    assert (
        await client.delete(f"/me/sessions/{opened['public_id']}", headers=owner)
    ).status_code == 204
    assert (await client.get("/me/sessions", headers=owner)).json()["readers"] == []
    assert (await client.delete("/me/sign-ins/nothing-here", headers=owner)).status_code == 204
