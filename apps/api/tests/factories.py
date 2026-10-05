"""Factories that write test data through the system context (bypassing nothing but auth)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.ids import mint_name
from jdhp_api.core.orm import (
    AccessClass,
    AgentKind,
    AgentRole,
    DigitalObjectState,
    GrantSource,
    Origin,
    PageType,
    ProvenanceType,
    PublishState,
    ReviewStatus,
    UserRole,
)
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.catalog.models import Agent, Work, WorkAgent
from jdhp_api.modules.content.models import ContentObject
from jdhp_api.modules.identity.models import User
from jdhp_api.modules.ingest.models import DigitalObject, Page
from jdhp_api.modules.review.models import ReviewTask


async def make_user(
    session: AsyncSession, subject: str = "user-1", role: UserRole = UserRole.MEMBER
) -> User:
    user = User(
        keycloak_sub=subject, email=f"{subject}@example.test", display_name=subject, role=role
    )
    session.add(user)
    await session.flush()
    return user


async def make_work(
    session: AsyncSession,
    *,
    access_class: AccessClass = AccessClass.REGISTERED,
    publish_state: PublishState = PublishState.PUBLISHED,
    title_ar: str = "أخبار بلدة سُميرة",
    title_en: str | None = "Chronicle of Sumayra",
    pages: int = 0,
    frozen: bool = False,
    **overrides: Any,
) -> Work:
    work = Work(
        public_id=mint_name("w8"),
        title_ar=title_ar,
        title_en=title_en,
        access_class=access_class,
        publish_state=publish_state,
        frozen=frozen,
        published_at=dt.datetime.now(dt.UTC) if publish_state == PublishState.PUBLISHED else None,
        **overrides,
    )
    session.add(work)
    await session.flush()
    if pages:
        digital_object = DigitalObject(
            work_id=work.id, page_count=pages, state=DigitalObjectState.READY
        )
        session.add(digital_object)
        await session.flush()
        for seq in range(1, pages + 1):
            session.add(
                Page(
                    digital_object_id=digital_object.id,
                    work_id=work.id,
                    seq=seq,
                    label=str(seq),
                    page_type=PageType.TEXT if seq > 1 else PageType.COVER,
                    ocr_text=f"نص الصفحة {seq} سري داخلي",
                    thumb_key=f"access/{work.id}/{digital_object.id}/thumb/{seq}.webp",
                    width_px=945,
                    height_px=1418,
                )
            )
        await session.flush()
    return work


async def make_author(
    session: AsyncSession, work: Work, name_ar: str = "يعقوب بن سالم الطحّان"
) -> Agent:
    agent = Agent(
        public_id=mint_name("a8"),
        kind=AgentKind.PERSON,
        name_ar=name_ar,
        name_latin="Yaqub ibn Salim al-Tahhan",
    )
    session.add(agent)
    await session.flush()
    session.add(WorkAgent(work_id=work.id, agent_id=agent.id, role=AgentRole.AUTHOR))
    await session.flush()
    return agent


async def make_grant(
    session: AsyncSession,
    *,
    user: User,
    work: Work,
    hours: int = 24,
    page_from: int | None = None,
    page_to: int | None = None,
) -> Grant:
    now = dt.datetime.now(dt.UTC)
    grant = Grant(
        user_id=user.id,
        work_id=work.id,
        starts_at=now - dt.timedelta(minutes=1),
        ends_at=now + dt.timedelta(hours=hours),
        device_limit=2,
        page_from=page_from,
        page_to=page_to,
        source=GrantSource.STAFF,
    )
    session.add(grant)
    await session.flush()
    return grant


async def make_content(
    session: AsyncSession,
    work: Work,
    *,
    origin: Origin = Origin.AI,
    review_status: ReviewStatus = ReviewStatus.PENDING,
    provenance_type: ProvenanceType = ProvenanceType.TRANSLATION,
    body: str = "A translation produced by a model.",
    page_id: uuid.UUID | None = None,
    with_task: bool = True,
) -> ContentObject:
    obj = ContentObject(
        public_id=mint_name("t8"),
        work_id=work.id,
        page_id=page_id,
        provenance_type=provenance_type,
        origin=origin,
        language="eng",
        script="Latn",
        body=body,
        model="mock-translator" if origin == Origin.AI else None,
        model_version="1" if origin == Origin.AI else None,
        review_status=review_status,
        generated_at=dt.datetime.now(dt.UTC),
    )
    session.add(obj)
    await session.flush()
    if with_task and origin == Origin.AI:
        session.add(ReviewTask(content_object_id=obj.id, work_id=work.id, state=review_status))
        await session.flush()
    return obj
