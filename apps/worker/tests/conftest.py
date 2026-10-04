"""Worker tests: real PostgreSQL as the worker role, moto for object storage, mock providers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from moto import mock_aws

from jdhp_adapters.mock.embeddings import MockEmbeddings
from jdhp_adapters.mock.ocr import MockOcr
from jdhp_api.core.db import Database
from jdhp_api.core.storage import ObjectStore
from jdhp_api.modules.search.indexer import RecordingIndexer
from jdhp_api.seed.generate import generate
from jdhp_api.testing import db as testing_db
from jdhp_worker.runtime import Runtime, ground_truth_from_store
from jdhp_worker.settings import WorkerSettings

STRONG = "test-" + "k" * 40
SEED_SCALE = float(os.environ.get("JDHP_TEST_SEED_SCALE", "0.12"))


@pytest.fixture(scope="session")
def template_database() -> Iterator[str]:
    yield from testing_db.create_template()


@pytest.fixture
def database_name(template_database: str) -> Iterator[str]:
    yield from testing_db.clone_database(template_database)


@pytest.fixture
def settings(database_name: str) -> WorkerSettings:
    return WorkerSettings.model_validate(
        {
            "env": "test",
            "database_url": testing_db.role_url(database_name, testing_db.APP_ROLE),
            "worker_database_url": testing_db.role_url(database_name, testing_db.WORKER_ROLE),
            "redis_url": "redis://localhost:6379/0",
            "opensearch_url": "http://opensearch.test:9200",
            "cerbos_url": "http://cerbos.test:3592",
            "oidc_issuer": "http://keycloak.test/realms/jdhp",
            "s3_access_key": "testing",
            "s3_secret_key": STRONG,
            "token_signing_key": STRONG,
            "forensic_master_key": STRONG,
            "field_encryption_key": STRONG,
            "embedding_dimensions": 16,
            "log_json": False,
        }
    )


@pytest.fixture
def aws() -> Iterator[None]:
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield


@pytest.fixture
def store(aws: None, settings: WorkerSettings) -> ObjectStore:
    store = ObjectStore(
        endpoint_url=None,
        region=settings.s3_region,
        access_key="testing",
        secret_key="testing",
    )
    store.ensure_bucket(settings.bucket_preservation, object_lock=True)
    for bucket in (
        settings.bucket_access,
        settings.bucket_uploads,
        settings.bucket_exports,
        settings.bucket_audit_archive,
    ):
        store.ensure_bucket(bucket)
    return store


@pytest.fixture
def worker_database(settings: WorkerSettings) -> Database:
    return Database(settings.worker_sqlalchemy_url, pooled=False)


@pytest.fixture
def app_database(settings: WorkerSettings) -> Database:
    return Database(settings.sqlalchemy_url, pooled=False)


@pytest.fixture
def admin_database(database_name: str) -> Database:
    return Database(testing_db.admin_async_url(database_name), pooled=False)


@pytest.fixture
def indexer() -> RecordingIndexer:
    return RecordingIndexer()


@pytest.fixture
def runtime(
    settings: WorkerSettings,
    store: ObjectStore,
    worker_database: Database,
    indexer: RecordingIndexer,
) -> Runtime:
    return Runtime(
        settings=settings,
        database=worker_database,
        store=store,
        ingest_store=store,
        ocr=MockOcr(),
        embeddings=MockEmbeddings(settings.embedding_dimensions),
        indexer=indexer,
        ground_truth_factory=ground_truth_from_store(store, settings.bucket_uploads),
        loop=None,
    )


@pytest.fixture(scope="session")
def seed_output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("seed")
    generate(out, scale=SEED_SCALE)
    return out
