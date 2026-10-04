"""Test harness: a real PostgreSQL database per test, a real Cerbos, signed test tokens.

Infrastructure comes from the environment when CI provides it (JDHP_TEST_ADMIN_DATABASE_URL,
JDHP_CERBOS_URL, JDHP_TEST_REDIS_URL) and is started locally otherwise. Every test gets a
fresh database cloned from a template that the migrations built once per session, and the
application connects as the unprivileged ``jdhp_app`` role so row-level security is real.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from psycopg import sql
from sqlalchemy import create_engine

from jdhp_api.core.auth import TokenVerifier
from jdhp_api.core.config import Settings, load_settings
from jdhp_api.core.db import Database
from jdhp_api.core.tasks import RecordingDispatcher
from jdhp_api.main import create_app

API_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = API_DIR.parents[1]
POLICIES_DIR = REPO_DIR / "policies"

ADMIN_URL = os.environ.get(
    "JDHP_TEST_ADMIN_DATABASE_URL", "postgresql://postgres@localhost:54329/postgres"
)
APP_ROLE = "jdhp_app"
WORKER_ROLE = "jdhp_worker"
APP_PASSWORD = "jdhp_app_test_password"
STRONG = "test-" + "k" * 40
TEST_ISSUER = "http://keycloak.test/realms/jdhp"
TEST_AUDIENCE = "jdhp-api"
KID = "test-key-1"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _admin_conn(dbname: str | None = None) -> psycopg.Connection[Any]:
    url = ADMIN_URL if dbname is None else ADMIN_URL.rsplit("/", 1)[0] + f"/{dbname}"
    return psycopg.connect(url, autocommit=True)


def _admin_host_port() -> tuple[str, str]:
    rest = ADMIN_URL.split("@")[-1].split("/")[0]
    host, _, port = rest.partition(":")
    return host, port or "5432"


# --- Cerbos -------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cerbos_url() -> Iterator[str]:
    provided = os.environ.get("JDHP_CERBOS_URL")
    if provided:
        yield provided.rstrip("/")
        return
    binary = os.environ.get("CERBOS_BIN") or shutil.which("cerbos")
    if binary is None:
        pytest.skip("no cerbos binary (set CERBOS_BIN) and no JDHP_CERBOS_URL")
    http_port, grpc_port = _free_port(), _free_port()
    config_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"jdhp-cerbos-{uuid.uuid4().hex}"  # noqa: S108
    config_dir.mkdir(parents=True)
    config = config_dir / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "server:",
                f'  httpListenAddr: "127.0.0.1:{http_port}"',
                f'  grpcListenAddr: "127.0.0.1:{grpc_port}"',
                "storage:",
                '  driver: "disk"',
                "  disk:",
                f'    directory: "{POLICIES_DIR}"',
                "schema:",
                "  enforcement: reject",
                "telemetry:",
                "  disabled: true",
                "",
            ]
        )
    )
    process = subprocess.Popen(  # noqa: S603 - fixed binary and arguments
        [binary, "server", f"--config={config}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{http_port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/_cerbos/health", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        process.terminate()
        pytest.fail("cerbos did not become healthy")
    try:
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)
        shutil.rmtree(config_dir, ignore_errors=True)


# --- Redis -------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    provided = os.environ.get("JDHP_TEST_REDIS_URL")
    if provided:
        yield provided
        return
    binary = shutil.which("redis-server")
    if binary is None:
        pytest.skip("no redis-server and no JDHP_TEST_REDIS_URL")
    port = _free_port()
    process = subprocess.Popen(  # noqa: S603
        [binary, "--port", str(port), "--save", "", "--appendonly", "no", "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.3)
    try:
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        process.terminate()
        process.wait(timeout=10)


# --- Database ----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def template_database() -> Iterator[str]:
    name = f"jdhp_tmpl_{uuid.uuid4().hex[:10]}"
    with _admin_conn() as conn:
        for role in (APP_ROLE, WORKER_ROLE):
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            verb = "ALTER" if exists else "CREATE"
            conn.execute(
                sql.SQL("{verb} ROLE {role} LOGIN PASSWORD {password} NOBYPASSRLS").format(
                    verb=sql.SQL(verb),
                    role=sql.Identifier(role),
                    password=sql.Literal(APP_PASSWORD),
                )
            )
        conn.execute(f'CREATE DATABASE "{name}"')
    with _admin_conn(name) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    sync_url = (
        ADMIN_URL.replace("postgresql://", "postgresql+psycopg://").rsplit("/", 1)[0] + f"/{name}"
    )
    engine = create_engine(sync_url)
    config = Config(str(API_DIR / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()
    try:
        yield name
    finally:
        with _admin_conn() as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def database_name(template_database: str) -> Iterator[str]:
    name = f"jdhp_test_{uuid.uuid4().hex[:10]}"
    with _admin_conn() as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template_database}"')
    try:
        yield name
    finally:
        with _admin_conn() as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def app_database_url(database_name: str) -> str:
    host, port = _admin_host_port()
    return f"postgresql+asyncpg://{APP_ROLE}:{APP_PASSWORD}@{host}:{port}/{database_name}"


@pytest.fixture
def admin_database_url(database_name: str) -> str:
    """Superuser access for test setup that bypasses row-level security on purpose."""
    return (
        ADMIN_URL.replace("postgresql://", "postgresql+asyncpg://").rsplit("/", 1)[0]
        + f"/{database_name}"
    )


# --- Keys and tokens ---------------------------------------------------------------------


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def jwks_json(signing_key: rsa.RSAPrivateKey) -> str:
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public_jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    return json.dumps({"keys": [public_jwk]})


TokenFactory = Callable[..., str]


@pytest.fixture(scope="session")
def make_token(signing_key: rsa.RSAPrivateKey) -> TokenFactory:
    pem = signing_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    def _make(
        subject: str = "user-1",
        roles: list[str] | None = None,
        *,
        mfa: bool = False,
        email_verified: bool = True,
        phone_verified: bool = False,
        lifetime: int = 300,
        issued_at: int | None = None,
        audience: str = TEST_AUDIENCE,
        issuer: str = TEST_ISSUER,
        kid: str = KID,
        extra: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time()) if issued_at is None else issued_at
        claims: dict[str, Any] = {
            "iss": issuer,
            "aud": audience,
            "sub": subject,
            "iat": now,
            "auth_time": now,
            "exp": now + lifetime,
            "jti": uuid.uuid4().hex,
            "email": f"{subject}@example.test",
            "email_verified": email_verified,
            "phone_number_verified": phone_verified,
            "name": subject.replace("-", " ").title(),
            "realm_access": {"roles": roles or ["member"]},
        }
        if mfa:
            claims["amr"] = ["pwd", "otp"]
            claims["acr"] = "2"
        claims.update(extra or {})
        return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid})

    return _make


# --- Settings and application -----------------------------------------------------------


@pytest.fixture
def settings(app_database_url: str, cerbos_url: str, redis_url: str, jwks_json: str) -> Settings:
    return load_settings(
        {
            "env": "test",
            "database_url": app_database_url,
            "redis_url": redis_url,
            "opensearch_url": "http://opensearch.test:9200",
            "cerbos_url": cerbos_url,
            "oidc_issuer": TEST_ISSUER,
            "oidc_audience": TEST_AUDIENCE,
            "oidc_jwks_json": jwks_json,
            "public_base_url": "http://localhost:8080",
            "api_base_url": "http://localhost:8080/api",
            "s3_access_key": "test",
            "s3_secret_key": STRONG,
            "token_signing_key": STRONG,
            "forensic_master_key": STRONG,
            "field_encryption_key": STRONG,
            "log_json": False,
        }
    )


@pytest_asyncio.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    db = Database(settings.sqlalchemy_url, pooled=False)
    try:
        yield db
    finally:
        await db.dispose()


@pytest_asyncio.fixture
async def admin_database(admin_database_url: str) -> AsyncIterator[Database]:
    db = Database(admin_database_url, pooled=False)
    try:
        yield db
    finally:
        await db.dispose()


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest_asyncio.fixture
async def app(
    settings: Settings, database: Database, dispatcher: RecordingDispatcher
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, database=database, token_verifier=TokenVerifier(settings))
    application.state.dispatcher = dispatcher
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def auth(make_token: TokenFactory) -> Callable[..., dict[str, str]]:
    def _headers(
        subject: str = "user-1", roles: list[str] | None = None, **kwargs: Any
    ) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(subject, roles, **kwargs)}"}

    return _headers


@pytest.fixture
def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
