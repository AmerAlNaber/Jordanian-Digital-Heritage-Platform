"""CAT-4, RDR-3: no public schema carries OCR text; no schema exposes internal identifiers."""

from __future__ import annotations

from typing import Any

import httpx

TEXT_FIELDS = {"ocr_text", "alto", "alto_xml", "text", "plain_text", "offsets"}
PORTAL_SCHEMAS = {"ReviewTaskOut"}  # reviewers see OCR text side by side with the scan (ADM-8)


def properties(schema: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = schema.get("properties", {})
    return found


async def test_cat_4_public_schemas_have_no_text_fields(client: httpx.AsyncClient) -> None:
    document = (await client.get("/openapi.json")).json()
    offenders: list[str] = []
    for name, schema in document["components"]["schemas"].items():
        if name in PORTAL_SCHEMAS:
            continue
        offenders.extend(f"{name}.{field}" for field in properties(schema) if field in TEXT_FIELDS)
    assert offenders == []


async def test_no_schema_exposes_uuid_identifiers(client: httpx.AsyncClient) -> None:
    document = (await client.get("/openapi.json")).json()
    offenders = [
        f"{name}.{field}"
        for name, schema in document["components"]["schemas"].items()
        for field, spec in properties(schema).items()
        if spec.get("format") == "uuid"
        or any(s.get("format") == "uuid" for s in spec.get("anyOf", []))
    ]
    assert offenders == []


async def test_openapi_document_is_served_with_the_platform_title(
    client: httpx.AsyncClient,
) -> None:
    document = (await client.get("/openapi.json")).json()
    assert document["info"]["title"] == "Jordanian Digital Heritage Platform API"
    assert "/works/{name}" in document["paths"]
