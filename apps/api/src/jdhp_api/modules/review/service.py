"""Review service: the only code path from pending to approved (REV-1, REV-2, REV-4).

Approval runs inside one transaction that first tells the database it is the portal action
(``app.review_action``), so the trigger on content_object lets the transition through, and
writes the audit event with the reviewer's identity before committing.
"""

from __future__ import annotations

import datetime as dt
import difflib

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.errors import NotFoundError, ReviewTransitionError
from jdhp_api.core.orm import AuditOutcome, AuditSeverity, ReviewStatus
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.content.models import ContentObject
from jdhp_api.modules.content.service import to_out
from jdhp_api.modules.identity.models import User
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.review.models import ReviewTask
from jdhp_api.modules.review.schemas import ReviewTaskOut

OPEN_STATES = {ReviewStatus.PENDING, ReviewStatus.IN_REVIEW}


async def get_task_for_content(
    session: AsyncSession, public_id: str
) -> tuple[ReviewTask, ContentObject] | None:
    row = (
        await session.execute(
            select(ReviewTask, ContentObject)
            .join(ContentObject, ContentObject.id == ReviewTask.content_object_id)
            .where(ContentObject.public_id == public_id)
            .order_by(ReviewTask.attempt.desc())
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def list_tasks(
    session: AsyncSession,
    *,
    state: ReviewStatus | None,
    work_public_id: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[ReviewTask, ContentObject, Work]], int]:
    stmt = (
        select(ReviewTask, ContentObject, Work)
        .join(ContentObject, ContentObject.id == ReviewTask.content_object_id)
        .join(Work, Work.id == ReviewTask.work_id)
    )
    if state is not None:
        stmt = stmt.where(ReviewTask.state == state)
    if work_public_id is not None:
        stmt = stmt.where(Work.public_id == work_public_id)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.execute(
        stmt.order_by(ReviewTask.priority.desc(), ReviewTask.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return [(t, c, w) for t, c, w in rows.all()], int(total)


async def task_out(
    session: AsyncSession, task: ReviewTask, obj: ContentObject, work: Work, settings: Settings
) -> ReviewTaskOut:
    content = (await to_out(session, [obj], work, settings))[0]
    page = await session.get(Page, obj.page_id) if obj.page_id else None
    assignee = await session.get(User, task.assignee_id) if task.assignee_id else None
    return ReviewTaskOut(
        content_public_id=obj.public_id,
        work_public_id=work.public_id,
        state=task.state,
        assignee_subject=assignee.keycloak_sub if assignee else None,
        due_at=task.due_at,
        priority=task.priority,
        attempt=task.attempt,
        reviewer_note=task.reviewer_note,
        decided_at=task.decided_at,
        created_at=task.created_at,
        content=content,
        page_seq=page.seq if page else None,
        ocr_text=page.ocr_text if page else None,
    )


def edit_diff(original: str, edited: str) -> dict[str, object]:
    diff = list(
        difflib.unified_diff(
            original.splitlines(),
            edited.splitlines(),
            fromfile="generated",
            tofile="reviewed",
            lineterm="",
        )
    )
    return {"unified": diff, "changed": original != edited}


async def approve(
    session: AsyncSession,
    task: ReviewTask,
    obj: ContentObject,
    principal: Principal,
    *,
    edited_body: str | None,
    note: str | None,
    request_id: str | None,
) -> ReviewTask:
    if task.state not in OPEN_STATES:
        raise ReviewTransitionError
    reviewer = await session.scalar(select(User).where(User.keycloak_sub == principal.id))
    if reviewer is None:
        raise NotFoundError
    now = dt.datetime.now(dt.UTC)
    original = obj.body or ""
    if edited_body is not None and edited_body != original:
        task.edit_diff = edit_diff(original, edited_body)
        obj.body = edited_body
    # Tell the database this is the portal action, for this transaction only.
    await session.execute(text("SELECT set_config('app.review_action', 'approve', true)"))
    obj.review_status = ReviewStatus.APPROVED
    obj.reviewer_id = reviewer.id
    obj.reviewer_subject = reviewer.keycloak_sub
    obj.reviewer_name = reviewer.display_name
    obj.reviewed_at = now
    task.state = ReviewStatus.APPROVED
    task.decided_by = reviewer.id
    task.decided_at = now
    task.reviewer_note = note
    await session.flush()
    await session.execute(text("SELECT set_config('app.review_action', '', true)"))
    await audit.write(
        session,
        actor_id=principal.id,
        actor_type="user",
        actor_roles=principal.roles,
        action="review.approve",
        resource_kind="content_object",
        resource_id=obj.public_id,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        details={"edited": task.edit_diff is not None, "attempt": task.attempt},
        request_id=request_id,
    )
    return task


async def reject(
    session: AsyncSession,
    task: ReviewTask,
    obj: ContentObject,
    principal: Principal,
    *,
    reason: str,
    request_id: str | None,
) -> ReviewTask:
    if task.state not in OPEN_STATES:
        raise ReviewTransitionError
    reviewer = await session.scalar(select(User).where(User.keycloak_sub == principal.id))
    if reviewer is None:
        raise NotFoundError
    now = dt.datetime.now(dt.UTC)
    obj.review_status = ReviewStatus.REJECTED
    obj.reviewer_id = reviewer.id
    obj.reviewer_subject = reviewer.keycloak_sub
    obj.reviewer_name = reviewer.display_name
    obj.reviewed_at = now
    task.state = ReviewStatus.REJECTED
    task.decided_by = reviewer.id
    task.decided_at = now
    task.reviewer_note = reason
    await session.flush()
    await audit.write(
        session,
        actor_id=principal.id,
        actor_type="user",
        actor_roles=principal.roles,
        action="review.reject",
        resource_kind="content_object",
        resource_id=obj.public_id,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        details={"attempt": task.attempt},
        request_id=request_id,
    )
    return task
