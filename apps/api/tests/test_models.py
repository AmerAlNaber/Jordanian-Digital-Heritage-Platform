"""Database invariants the schema enforces on its own (SEC-9, ACS-2)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import ApprovalKind, GrantSource
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.admin.models import Approval
from tests.factories import make_user, make_work


async def _insert(database: Database, row: object) -> None:
    async with database.session(RlsContext.system()) as session:
        session.add(row)
        await session.flush()


async def test_sec_9_approval_needs_two_different_people(admin_database: Database) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        user = await make_user(session, "solo")
        work = await make_work(session)
    approval = Approval(
        kind=ApprovalKind.PUBLISH,
        target_kind="work",
        target_id=work.id,
        proposed_by=user.id,
        approved_by=user.id,
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await _insert(admin_database, approval)


async def test_acs_2_grant_must_end_after_it_starts(admin_database: Database) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        user = await make_user(session, "holder")
        work = await make_work(session)
    now = dt.datetime.now(dt.UTC)
    zero_length = Grant(
        user_id=user.id, work_id=work.id, starts_at=now, ends_at=now, source=GrantSource.STAFF
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await _insert(admin_database, zero_length)


async def test_acs_2_grant_needs_a_holder(admin_database: Database) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
    now = dt.datetime.now(dt.UTC)
    no_holder = Grant(
        work_id=work.id, starts_at=now, ends_at=now + dt.timedelta(days=1), source=GrantSource.STAFF
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await _insert(admin_database, no_holder)
