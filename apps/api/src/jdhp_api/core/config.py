"""Application configuration, validated at startup (SEC-19).

Every setting comes from an environment variable prefixed ``JDHP_`` or from a file in the
secrets directory named after the setting (``/run/secrets/jdhp_token_signing_key``). The
process refuses to start when a required setting is missing or insecure for its environment.
``.env.example`` at the repository root documents every variable.
"""

from __future__ import annotations

import enum
import os
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Self

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(enum.StrEnum):
    """Where the process runs. Drives which settings are mandatory."""

    LOCAL = "local"
    TEST = "test"
    CI = "ci"
    STAGING = "staging"
    PILOT = "pilot"
    PRODUCTION = "production"

    @property
    def is_deployed(self) -> bool:
        """Staging, pilot and production run on shared infrastructure."""
        return self in {Environment.STAGING, Environment.PILOT, Environment.PRODUCTION}

    @property
    def holds_real_content(self) -> bool:
        """Pilot and production hold real heritage material and real users."""
        return self in {Environment.PILOT, Environment.PRODUCTION}


MIN_SECRET_LENGTH = 32
INSECURE_SECRET_VALUES = frozenset(
    {"", "change-me", "changeme", "secret", "password", "dev", "test", "example", "insecure"}
)
MOCK_PROVIDER = "mock"
SUPPORTED_LOCALES = ("ar", "en")


class ConfigurationError(RuntimeError):
    """Raised when the configuration is missing or insecure. The process must not start."""


class Settings(BaseSettings):
    """All runtime configuration. Field names map to ``JDHP_<UPPER_NAME>``."""

    model_config = SettingsConfigDict(
        env_prefix="JDHP_",
        case_sensitive=False,
        secrets_dir=os.environ.get("JDHP_SECRETS_DIR") or None,
        extra="ignore",
    )

    # Environment
    env: Environment = Environment.LOCAL
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    public_base_url: AnyHttpUrl = Field(default=AnyHttpUrl("http://localhost:8080"))
    api_base_url: AnyHttpUrl = Field(default=AnyHttpUrl("http://localhost:8080/api"))
    default_locale: str = "ar"

    # Data stores
    database_url: PostgresDsn
    migration_database_url: PostgresDsn | None = None
    database_echo: bool = False
    redis_url: RedisDsn
    opensearch_url: AnyHttpUrl
    opensearch_user: str | None = None
    opensearch_password: SecretStr | None = None
    opensearch_index_prefix: str = "jdhp"

    # Policy engine
    cerbos_url: AnyHttpUrl

    # Identity (SEC-1, SEC-2)
    oidc_issuer: AnyHttpUrl
    oidc_audience: str = "jdhp-api"
    oidc_jwks_url: AnyHttpUrl | None = None
    oidc_jwks_json: SecretStr | None = None
    access_token_max_age_seconds: int = Field(default=600, ge=60, le=900)

    # Object storage. The API credential never has write access to preservation.
    s3_endpoint_url: AnyHttpUrl | None = None
    s3_region: str = "us-east-1"
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_force_path_style: bool = True
    bucket_preservation: str = "jdhp-preservation"
    bucket_access: str = "jdhp-access"
    bucket_uploads: str = "jdhp-uploads"
    bucket_exports: str = "jdhp-exports"
    bucket_audit_archive: str = "jdhp-audit-archive"

    # Keys (SEC-10, SEC-11, SEC-19, SEC-23)
    token_signing_key: SecretStr
    forensic_master_key: SecretStr
    field_encryption_key: SecretStr

    # Persistent identifiers (ADR-0001 D10)
    ark_naan: str = "99999"
    ark_shoulder_work: str = "w8"
    ark_shoulder_collection: str = "c8"
    ark_shoulder_agent: str = "a8"

    # Providers behind adapters (TRN-6, ADR-0001 D4 to D7)
    ocr_provider: str = MOCK_PROVIDER
    llm_provider: str = MOCK_PROVIDER
    embedding_provider: str = MOCK_PROVIDER
    embedding_dimensions: int = Field(default=1024, ge=8, le=4096)
    payment_provider: str = MOCK_PROVIDER
    email_provider: str = MOCK_PROVIDER
    sms_provider: str = MOCK_PROVIDER

    # Retention (ADR-0001 D16)
    retention_audit_years: int = Field(default=7, ge=1)
    retention_identity_document_days: int = Field(default=30, ge=1)
    retention_inactive_account_years: int = Field(default=2, ge=1)

    # Reader and content protection (RDR-5, SEC-10, SEC-12, SEC-15)
    reader_idle_timeout_seconds: int = Field(default=1800, ge=60)
    grant_cache_ttl_seconds: int = Field(default=60, ge=1, le=60)
    tile_token_ttl_seconds: int = Field(default=300, ge=30, le=300)
    download_url_ttl_seconds: int = Field(default=900, ge=60, le=900)
    tile_rate_burst_pages_per_second: int = Field(default=3, ge=1)
    tile_rate_sustained_per_minute: int = Field(default=600, ge=1)
    tiles_per_page_estimate: int = Field(default=12, ge=1)
    heartbeat_interval_seconds: int = Field(default=60, ge=10, le=60)

    # Observability
    sentry_dsn: SecretStr | None = None
    otel_exporter_otlp_endpoint: AnyHttpUrl | None = None

    # Web origins allowed to call the API directly (the web app calls server-side; empty is fine)
    cors_origins: list[AnyHttpUrl] = Field(default_factory=list)

    @field_validator("ark_naan")
    @classmethod
    def _naan_is_digits(cls, value: str) -> str:
        if not value.isdigit() or len(value) < 5:
            msg = "ark_naan must be a Name Assigning Authority Number of at least five digits"
            raise ValueError(msg)
        return value

    @field_validator("ark_shoulder_work", "ark_shoulder_collection", "ark_shoulder_agent")
    @classmethod
    def _shoulder_shape(cls, value: str) -> str:
        letters, digit = value[:-1], value[-1:]
        if not (letters.isalpha() and letters.islower() and digit.isdigit()):
            msg = "an ARK shoulder is one or more lowercase letters followed by one digit"
            raise ValueError(msg)
        return value

    @field_validator("default_locale")
    @classmethod
    def _locale_supported(cls, value: str) -> str:
        if value not in SUPPORTED_LOCALES:
            msg = f"default_locale must be one of {SUPPORTED_LOCALES}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _derive_and_refuse_insecure(self) -> Self:
        if self.oidc_jwks_url is None and self.oidc_jwks_json is None:
            # Keycloak's JWKS location, derived from the issuer.
            derived = f"{str(self.oidc_issuer).rstrip('/')}/protocol/openid-connect/certs"
            object.__setattr__(self, "oidc_jwks_url", AnyHttpUrl(derived))
        problems = [
            *self._secret_problems(),
            *self._deployment_problems(),
            *self._provider_problems(),
        ]
        if problems:
            raise ConfigurationError("refusing to start: " + "; ".join(problems))
        return self

    def _secret_problems(self) -> list[str]:
        problems: list[str] = []
        keys = ("token_signing_key", "forensic_master_key", "field_encryption_key", "s3_secret_key")
        for name in keys:
            value = getattr(self, name).get_secret_value()
            if value.strip().lower() in INSECURE_SECRET_VALUES:
                problems.append(f"{name} is empty or a known placeholder")
            elif len(value) < MIN_SECRET_LENGTH and name != "s3_secret_key":
                problems.append(f"{name} must be at least {MIN_SECRET_LENGTH} characters")
        return problems

    def _deployment_problems(self) -> list[str]:
        if not self.env.is_deployed:
            return []
        checks = (
            (self.debug, "debug must be false outside local and test environments"),
            (
                self.oidc_issuer.scheme != "https",
                "oidc_issuer must use https in deployed environments",
            ),
            (self.oidc_jwks_json is not None, "oidc_jwks_json is a test-only setting"),
            (
                self.s3_endpoint_url is not None and self.s3_endpoint_url.scheme != "https",
                "s3_endpoint_url must use https in deployed environments",
            ),
            (
                self.public_base_url.scheme != "https",
                "public_base_url must use https in deployed environments",
            ),
        )
        return [message for failed, message in checks if failed]

    def _provider_problems(self) -> list[str]:
        if not self.env.holds_real_content:
            return []
        names = (
            "ocr_provider",
            "llm_provider",
            "embedding_provider",
            "payment_provider",
            "email_provider",
            "sms_provider",
        )
        return [
            f"{name} may not be '{MOCK_PROVIDER}' where real content lives"
            for name in names
            if getattr(self, name) == MOCK_PROVIDER
        ]

    @property
    def jwks_url(self) -> str:
        """The JWKS endpoint, derived from the issuer unless set explicitly."""
        if self.oidc_jwks_url is None:  # pragma: no cover - the validator always derives it
            msg = "oidc_jwks_url is not set"
            raise ConfigurationError(msg)
        return str(self.oidc_jwks_url)

    @property
    def sqlalchemy_url(self) -> str:
        return str(self.database_url)

    @property
    def migration_sqlalchemy_url(self) -> str:
        return str(self.migration_database_url or self.database_url)


def load_settings(values: Mapping[str, Any] | None = None) -> Settings:
    """Build settings from the environment, or from an explicit mapping in tests.

    Every validation failure, field-level or cross-field, surfaces as ConfigurationError so
    the process entry point has one error to refuse on.
    """
    try:
        if values is None:
            return Settings()  # values come from the environment and the secrets directory
        return Settings.model_validate(dict(values))
    except ConfigurationError:
        raise
    except ValidationError as exc:
        msg = f"refusing to start: {exc}"
        raise ConfigurationError(msg) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached; tests reset the cache after changing the environment."""
    return load_settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
