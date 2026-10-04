"""Worker settings: the API settings plus the credentials only the pipeline holds."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr

from jdhp_api.core.config import ConfigurationError, Settings


class WorkerSettings(Settings):
    """Adds the worker database role and the only credential that writes preservation."""

    worker_database_url: PostgresDsn | None = None
    s3_ingest_access_key: SecretStr | None = None
    s3_ingest_secret_key: SecretStr | None = None
    access_derivative_format: Literal["jp2", "ptif"] = "jp2"
    thumbnail_width: int = Field(default=400, ge=100, le=1000)
    sample_width: int = Field(default=1200, ge=400, le=2000)
    ocr_flag_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    embedding_chunk_chars: int = Field(default=800, ge=100, le=4000)
    max_master_bytes: int = Field(default=400 * 1024 * 1024, ge=1024)
    master_min_ppi: int = Field(default=400, ge=72)

    @property
    def worker_sqlalchemy_url(self) -> str:
        return str(self.worker_database_url or self.database_url)

    @property
    def has_ingest_credential(self) -> bool:
        return self.s3_ingest_access_key is not None and self.s3_ingest_secret_key is not None


def load_worker_settings() -> WorkerSettings:
    try:
        return WorkerSettings()  # values come from the environment and the secrets directory
    except ConfigurationError:
        raise
    except Exception as exc:
        msg = f"refusing to start: {exc}"
        raise ConfigurationError(msg) from exc


@lru_cache(maxsize=1)
def get_worker_settings() -> WorkerSettings:
    return load_worker_settings()
