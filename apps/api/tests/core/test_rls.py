"""SEC-7: row-level security isolates personal and grant data by caller and institution."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import GrantSource, UserRole
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.identity.models import Institution, User, VerificationCase
from tests.factories import make_user, make_work


async def _seed(admin: Database) -> tuple[User, User, User, Work]:
    async with admin.session(RlsContext.system()) as session:
        inst_a = Institution(slug="a", name_ar="أ")
        inst_b = Institution(slug="b", name_ar="ب")
        session.add_all([inst_a, inst_b])
        await session.flush()
        alice = await make_user(session, "alice")
        alice.institution_id = inst_a.id
        bob = await make_user(session, "bob")
        bob.institution_id = inst_b.id
        curator = await make_user(session, "carol", UserRole.CURATOR)
        work = await make_work(session)
        now = dt.datetime.now(dt.UTC)
        for user in (alice, bob):
            session.add(
                Grant(
                    user_id=user.id,
                    work_id=work.id,
                    starts_at=now,
                    ends_at=now + dt.timedelta(days=1),
                    source=GrantSource.STAFF,
                )
            )
        session.add(
            VerificationCase(
                user_id=alice.id, document_type="passport", document_keys=["uploads/x"]
            )
        )
        await session.flush()
        return alice, bob, curator, work


async def test_sec_7_runtime_role_cannot_bypass_rls(database: Database) -> None:
    async with database.session(RlsContext.system()) as session:
        row = (
            await session.execute(
                text("select rolbypassrls, rolsuper from pg_roles where rolname = current_user")
            )
        ).one()
    assert row == (False, False)


async def test_sec_7_users_see_only_their_own_grants(
    database: Database, admin_database: Database
) -> None:
    alice, _bob, _curator, _work = await _seed(admin_database)
    async with database.session(
        RlsContext(user_id=str(alice.id), roles=("member",), institution_id="")
    ) as session:
        grants = (await session.scalars(select(Grant))).all()
    assert [g.user_id for g in grants] == [alice.id]
    async with database.session(RlsContext.anonymous()) as session:
        assert (await session.scalars(select(Grant))).all() == []


async def test_sec_7_rls_blocks_cross_institution_read(
    database: Database, admin_database: Database
) -> None:
    alice, _bob, _curator, _work = await _seed(admin_database)
    ctx = RlsContext(
        user_id=str(alice.id),
        roles=("institution_admin",),
        institution_id=str(alice.institution_id),
    )
    async with database.session(ctx) as session:
        users = (await session.scalars(select(User))).all()
    assert {u.keycloak_sub for u in users} == {"alice"}


async def test_sec_7_curator_cannot_read_identity_documents(
    database: Database, admin_database: Database
) -> None:
    _alice, _bob, curator, _work = await _seed(admin_database)
    async with database.session(
        RlsContext(user_id=str(curator.id), roles=("curator",), institution_id="")
    ) as session:
        assert (await session.scalars(select(VerificationCase))).all() == []
    async with database.session(
        RlsContext(user_id=str(curator.id), roles=("rights_officer",), institution_id="")
    ) as session:
        assert len((await session.scalars(select(VerificationCase))).all()) == 1


async def test_sec_7_rights_officer_sees_every_grant(
    database: Database, admin_database: Database
) -> None:
    _alice, _bob, curator, _work = await _seed(admin_database)
    async with database.session(
        RlsContext(user_id=str(curator.id), roles=("rights_officer",), institution_id="")
    ) as session:
        assert len((await session.scalars(select(Grant))).all()) == 2
