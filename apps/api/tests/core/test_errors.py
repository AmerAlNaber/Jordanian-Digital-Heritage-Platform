"""Problem details are localized, Arabic by default, and never leak internals (SEC-17)."""

from __future__ import annotations

import httpx


async def test_not_found_is_problem_json_in_arabic_by_default(client: httpx.AsyncClient) -> None:
    response = await client.get("/works/w8zzzzzzzzzzz")
    assert response.status_code == 404
    body = response.json()
    assert response.headers["content-type"].startswith("application/problem+json")
    assert body["code"] == "invalid_identifier"
    assert body["title"] == "معرّف غير صالح"
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]


async def test_english_when_requested(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/works/w8zzzzzzzzzzz", headers={"Accept-Language": "en-GB,en;q=0.9"}
    )
    assert response.json()["title"] == "Invalid identifier"


async def test_validation_errors_never_echo_values(client: httpx.AsyncClient) -> None:
    response = await client.get("/works?limit=999999")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation"
    assert "999999" not in response.text
    assert body["errors"][0]["loc"] == ["query", "limit"]


async def test_private_no_store_by_default_and_security_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/me")
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


async def test_incoming_request_id_is_honoured_when_valid(client: httpx.AsyncClient) -> None:
    rid = "0f0e5d5e-7f4a-4a6e-9e38-3a2bd4f1c123"
    response = await client.get("/works", headers={"X-Request-ID": rid})
    assert response.headers["X-Request-ID"] == rid
    response = await client.get("/works", headers={"X-Request-ID": "not-a-uuid"})
    assert response.headers["X-Request-ID"] != "not-a-uuid"
