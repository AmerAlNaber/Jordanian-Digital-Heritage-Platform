"""Review portal (ADM-8, REV-2, REV-4): MFA reviewers, edits stored as diffs, audited decisions."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from sqlalchemy import select

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.modules.audit.models import AuditEvent
from jdhp_api.modules.review.models import ReviewTask
from tests.factories import make_content, make_work

Headers = Callable[..., dict[str, str]]


async def test_sec_3_reviewer_without_mfa_cannot_approve(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
        obj = await make_content(session, work)
    weak = auth("rana", ["reviewer"], mfa=False)
    assert (await client.get("/review/tasks", headers=weak)).status_code == 200
    assert (
        await client.post(f"/review/tasks/{obj.public_id}/approve", json={}, headers=weak)
    ).status_code == 403


async def test_rev_2_edit_is_stored_as_a_diff_and_rev_4_audited(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
        obj = await make_content(session, work, body="The spring ran dry.\nThe council met.")
    reviewer = auth("rana", ["reviewer"], mfa=True)
    response = await client.post(
        f"/review/tasks/{obj.public_id}/approve",
        json={
            "edited_body": "The spring ran dry.\nThe town council met beneath the carob tree.",
            "note": "named the tree",
        },
        headers=reviewer,
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "approved"
    assert response.json()["content"]["body"].endswith("carob tree.")
    async with admin_database.session(RlsContext.system()) as session:
        task = (await session.scalars(select(ReviewTask))).one()
        events = (
            await session.scalars(select(AuditEvent).where(AuditEvent.action == "review.approve"))
        ).all()
    assert task.edit_diff is not None
    assert task.edit_diff["changed"] is True
    assert any(line.startswith("+The town council") for line in task.edit_diff["unified"])
    assert len(events) == 1
    assert events[0].actor_id == "rana"
    assert events[0].details == {"edited": True, "attempt": 1}


async def test_reject_requires_a_reason_and_closes_the_task(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
        obj = await make_content(session, work)
    reviewer = auth("rana", ["reviewer"], mfa=True)
    assert (
        await client.post(f"/review/tasks/{obj.public_id}/reject", json={}, headers=reviewer)
    ).status_code == 422
    rejected = await client.post(
        f"/review/tasks/{obj.public_id}/reject", json={"reason": "wrong register"}, headers=reviewer
    )
    assert rejected.status_code == 200
    assert rejected.json()["state"] == "rejected"
    assert rejected.json()["reviewer_note"] == "wrong register"
    assert (await client.get(f"/content/{obj.public_id}")).status_code == 404
    again = await client.post(f"/review/tasks/{obj.public_id}/approve", json={}, headers=reviewer)
    assert again.status_code == 409
    assert again.json()["code"] == "review_transition"


async def test_members_and_curators_cannot_work_the_queue(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
        obj = await make_content(session, work)
    for headers in (auth("m", ["member"]), auth("carol", ["curator"], mfa=True)):
        assert (await client.get("/review/tasks", headers=headers)).status_code == 403
        assert (
            await client.post(f"/review/tasks/{obj.public_id}/approve", json={}, headers=headers)
        ).status_code == 403
