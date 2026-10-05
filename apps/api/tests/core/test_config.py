"""SEC-19: configuration is validated at startup and insecure settings refuse to boot."""

from __future__ import annotations

import pytest
from pydantic import AnyHttpUrl

from jdhp_api.core.config import ConfigurationError, Environment, Settings, load_settings

STRONG = "k" * 40


def base_env(**overrides: str) -> dict[str, str]:
    env = {
        "env": "production",
        "database_url": "postgresql+asyncpg://jdhp_app:x@db/jdhp",
        "redis_url": "redis://redis:6379/0",
        "opensearch_url": "https://opensearch:9200",
        "cerbos_url": "https://cerbos:3592",
        "oidc_issuer": "https://id.example.jo/realms/jdhp",
        "public_base_url": "https://library.example.jo",
        "api_base_url": "https://library.example.jo/api",
        "s3_access_key": "app",
        "s3_secret_key": STRONG,
        "token_signing_key": STRONG,
        "forensic_master_key": STRONG,
        "field_encryption_key": STRONG,
        "ocr_provider": "azure",
        "llm_provider": "claude",
        "embedding_provider": "voyage",
        "payment_provider": "hyperpay",
        "email_provider": "smtp",
        "sms_provider": "jordan-sms",
    }
    env.update(overrides)
    return env


def build(**overrides: str) -> Settings:
    return load_settings(base_env(**overrides))


def test_sec_19_production_settings_accept_strong_values() -> None:
    settings = build()
    assert settings.env is Environment.PRODUCTION
    assert settings.jwks_url == "https://id.example.jo/realms/jdhp/protocol/openid-connect/certs"


@pytest.mark.parametrize(
    "key", ["token_signing_key", "forensic_master_key", "field_encryption_key"]
)
@pytest.mark.parametrize("value", ["", "change-me", "short"])
def test_sec_19_config_refuses_insecure_values(key: str, value: str) -> None:
    with pytest.raises(ConfigurationError):
        build(**{key: value})


def test_sec_19_debug_refused_in_production_config() -> None:
    with pytest.raises(ConfigurationError, match="debug"):
        build(debug="true")


def test_sec_19_http_issuer_refused_when_deployed() -> None:
    with pytest.raises(ConfigurationError, match="oidc_issuer"):
        build(oidc_issuer="http://id.example.jo/realms/jdhp")


def test_sec_19_jwks_json_is_test_only() -> None:
    with pytest.raises(ConfigurationError, match="oidc_jwks_json"):
        build(oidc_jwks_json='{"keys": []}')


@pytest.mark.parametrize(
    "provider",
    [
        "ocr_provider",
        "llm_provider",
        "embedding_provider",
        "payment_provider",
        "email_provider",
        "sms_provider",
    ],
)
def test_trn_6_mock_providers_refused_where_real_content_lives(provider: str) -> None:
    with pytest.raises(ConfigurationError, match=provider):
        build(**{provider: "mock"})


def test_mock_providers_allowed_locally() -> None:
    settings = build(
        env="local",
        oidc_issuer="http://localhost:8081/realms/jdhp",
        public_base_url="http://localhost:8080",
        api_base_url="http://localhost:8080/api",
        ocr_provider="mock",
        llm_provider="mock",
        embedding_provider="mock",
        payment_provider="mock",
        email_provider="mock",
        sms_provider="mock",
    )
    assert settings.ocr_provider == "mock"
    assert not settings.env.is_deployed


def test_ark_naan_must_be_digits() -> None:
    with pytest.raises(ConfigurationError):
        build(ark_naan="abc")


def test_ark_shoulder_shape() -> None:
    with pytest.raises(ConfigurationError):
        build(ark_shoulder_work="W")
    assert build(ark_shoulder_work="wk7").ark_shoulder_work == "wk7"


def test_default_locale_is_arabic_and_only_supported_locales_allowed() -> None:
    assert build().default_locale == "ar"
    with pytest.raises(ConfigurationError):
        build(default_locale="fr")


def test_explicit_jwks_url_is_kept() -> None:
    settings = build(oidc_jwks_url="https://id.example.jo/certs")
    assert settings.oidc_jwks_url == AnyHttpUrl("https://id.example.jo/certs")
