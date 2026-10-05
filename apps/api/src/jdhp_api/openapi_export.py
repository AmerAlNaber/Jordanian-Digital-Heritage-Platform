"""Write the OpenAPI document to a file: ``python -m jdhp_api.openapi_export out.json``.

Every public API change bumps the version and regenerates ``packages/schemas`` from this file.
The document depends on the routes and schemas only, so the exporter builds the application with
placeholder settings and never reads the environment or connects to anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jdhp_api.core.config import Settings, load_settings
from jdhp_api.main import openapi_document

_PLACEHOLDER_KEY = "openapi-export-placeholder-not-a-secret-0000"


def export_settings() -> Settings:
    """Settings that satisfy validation without configuring any real service."""
    return load_settings(
        {
            "env": "test",
            "database_url": "postgresql+asyncpg://jdhp_app:placeholder@localhost:5432/jdhp",
            "redis_url": "redis://localhost:6379/0",
            "opensearch_url": "http://localhost:9200",
            "cerbos_url": "http://localhost:3592",
            "oidc_issuer": "http://localhost:8080/auth/realms/jdhp",
            "oidc_audience": "jdhp-api",
            "oidc_jwks_json": json.dumps({"keys": []}),
            "public_base_url": "http://localhost:8080",
            "api_base_url": "http://localhost:8080/api",
            "s3_access_key": "placeholder",
            "s3_secret_key": _PLACEHOLDER_KEY,
            "token_signing_key": _PLACEHOLDER_KEY,
            "forensic_master_key": _PLACEHOLDER_KEY,
            "field_encryption_key": _PLACEHOLDER_KEY,
            "log_json": False,
        }
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python -m jdhp_api.openapi_export <output.json>\n")
        return 2
    output = Path(argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    document = openapi_document(export_settings())
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", "utf-8")
    sys.stdout.write(f"wrote {output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
