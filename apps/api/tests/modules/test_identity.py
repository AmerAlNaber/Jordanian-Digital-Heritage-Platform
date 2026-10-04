"""Accounts: just-in-time user creation from verified tokens, own profile only (ACC-5)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from sqlalchemy import select

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.modules.identity.models import User

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
