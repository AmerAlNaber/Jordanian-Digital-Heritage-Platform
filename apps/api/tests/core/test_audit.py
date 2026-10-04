"""SEC-25, SEC-27: append-only, hash-chained, redacted audit log."""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from jdhp_api.core import audit
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import AuditOutcome
from jdhp_api.modules.audit.models import GENESIS_HASH, AuditEvent


async def _write(db: Database, n: int) -> None:
    async with db.session(RlsContext.system()) as session:
        for i in range(n):
            await audit.write(
                session,
                actor_id="system",
                actor_type="system",
                actor_roles=("system",),
                action=f"test.event.{i}",
                resource_kind="work",
                resource_id=f"w{i}",
                outcome=AuditOutcome.SUCCESS,
                details={
                    "i": i,
                    "token": "secret-token-value",
                    "nested": {"password": "pw", "ok": "fine"},
                },
            )


async def test_sec_25_hash_chain_verifies(database: Database) -> None:
    await _write(database, 5)
    async with database.session(RlsContext.system()) as session:
        intact, checked = await audit.verify_chain(session)
        events = (await session.scalars(select(AuditEvent).order_by(AuditEvent.seq))).all()
    assert intact
    assert checked == 5
    assert events[0].prev_hash == GENESIS_HASH
    for previous, current in itertools.pairwise(events):
        assert current.prev_hash == previous.hash


async def test_sec_25_tampering_breaks_the_chain(
    database: Database, admin_database: Database
) -> None:
    await _write(database, 3)
    # The owner bypasses revoked privileges but not the trigger; disable it to simulate tampering.
    async with admin_database.session(RlsContext.system()) as session:
        await session.execute(
            text("ALTER TABLE audit_event DISABLE TRIGGER audit_event_no_update_delete")
        )
        await session.execute(
            update(AuditEvent).where(AuditEvent.seq == 2).values(action="tampered")
        )
        await session.execute(
            text("ALTER TABLE audit_event ENABLE TRIGGER audit_event_no_update_delete")
        )
    async with database.session(RlsContext.system()) as session:
        intact, checked = await audit.verify_chain(session)
    assert not intact
    assert checked == 1


async def test_sec_25_audit_rows_cannot_be_updated_or_deleted(database: Database) -> None:
    await _write(database, 1)
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with database.session(RlsContext.system()) as session:
            await session.execute(update(AuditEvent).values(action="x"))
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with database.session(RlsContext.system()) as session:
            await session.execute(text("DELETE FROM audit_event"))


async def test_sec_27_details_are_redacted_before_hashing(database: Database) -> None:
    await _write(database, 1)
    async with database.session(RlsContext.system()) as session:
        event = (await session.scalars(select(AuditEvent))).one()
    assert event.details["token"] == "[redacted]"
    assert event.details["nested"]["password"] == "[redacted]"
    assert event.details["nested"]["ok"] == "fine"
    assert "secret-token-value" not in audit.canonical_json(audit.hashed_payload(event))
