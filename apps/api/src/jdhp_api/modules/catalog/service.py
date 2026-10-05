"""Catalog service: the only code that reads and writes works, pages, collections and terms."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.ids import format_ark, format_page_ark, mint_name
from jdhp_api.core.orm import (
    AccessClass,
    AuditOutcome,
    AuditSeverity,
    PublishState,
    TermScheme,
    sample_page_limit,
)
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.access.service import grant_covers_page
from jdhp_api.modules.admin.models import RecordChange
from jdhp_api.modules.catalog.models import (
    Agent,
    Collection,
    CollectionWork,
    Item,
    VocabularyTerm,
    Work,
    WorkAgent,
    WorkTerm,
)
from jdhp_api.modules.catalog.schemas import (
    AgentRef,
    Citation,
    CollectionDetail,
    CollectionRef,
    CollectionSummary,
    PageSummary,
    TermRef,
    TermSummary,
    WorkCreate,
    WorkDetail,
    WorkSummary,
    WorkUpdate,
)
from jdhp_api.modules.ingest.models import Page


def visible_works(stmt: Select[Any], principal: Principal) -> Select[Any]:
    """Public visibility: published, not embargoed, not frozen. Staff see everything (CAT-5)."""
    if principal.is_staff:
        return stmt.where(Work.deleted_at.is_(None))
    return stmt.where(
        Work.deleted_at.is_(None),
        Work.publish_state == PublishState.PUBLISHED,
        Work.access_class != AccessClass.EMBARGOED,
        Work.frozen.is_(False),
    )


def effective_sample_limit(work: Work) -> int | None:
    if work.sample_page_override is not None:
        return work.sample_page_override
    return sample_page_limit(work.access_class)


def in_sample_range(work: Work, seq: int) -> bool:
    limit = effective_sample_limit(work)
    return limit is None or seq <= limit


def work_attributes(work: Work, grant: Grant | None) -> dict[str, Any]:
    """The attributes the work policy reads."""
    return {
        "access_class": str(work.access_class),
        "publish_state": str(work.publish_state),
        "frozen": work.frozen,
        "has_grant": grant is not None,
        "grant_page_from": grant.page_from if grant else None,
        "grant_page_to": grant.page_to if grant else None,
        "owner_institution_id": str(work.owner_institution_id or ""),
        "break_glass_active": False,
    }


def page_attributes(work: Work, seq: int, grant: Grant | None) -> dict[str, Any]:
    return {
        "access_class": str(work.access_class),
        "publish_state": str(work.publish_state),
        "frozen": work.frozen,
        "seq": seq,
        "in_sample_range": in_sample_range(work, seq),
        "has_grant": grant is not None,
        "in_grant_range": grant_covers_page(grant, seq),
        "break_glass_active": False,
    }


async def get_work_by_name(session: AsyncSession, name: str) -> Work | None:
    return (
        await session.scalars(select(Work).where(Work.public_id == name, Work.deleted_at.is_(None)))
    ).first()


async def get_collection_by_name(session: AsyncSession, name: str) -> Collection | None:
    return (
        await session.scalars(
            select(Collection).where(Collection.public_id == name, Collection.deleted_at.is_(None))
        )
    ).first()


async def page_counts(session: AsyncSession, work_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not work_ids:
        return {}
    rows = await session.execute(
        select(Page.work_id, func.count()).where(Page.work_id.in_(work_ids)).group_by(Page.work_id)
    )
    return {work_id: int(count) for work_id, count in rows.all()}


async def thumbnail_flags(session: AsyncSession, work_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    if not work_ids:
        return set()
    rows = await session.execute(
        select(Page.work_id)
        .where(Page.work_id.in_(work_ids), Page.seq == 1, Page.thumb_key.is_not(None))
        .distinct()
    )
    return {row[0] for row in rows.all()}


def summarize(
    work: Work, settings: Settings, *, page_count: int, has_thumbnail: bool
) -> WorkSummary:
    return WorkSummary(
        public_id=work.public_id,
        ark=format_ark(settings.ark_naan, work.public_id),
        title_ar=work.title_ar,
        title_translit=work.title_translit,
        title_en=work.title_en,
        language=work.language,
        script=work.script,
        date_edtf=work.date_edtf,
        date_hijri=work.date_hijri,
        access_class=work.access_class,
        publish_state=work.publish_state,
        page_count=page_count,
        sample_page_limit=effective_sample_limit(work),
        thumbnail_available=has_thumbnail,
    )


async def summarize_many(
    session: AsyncSession, works: Sequence[Work], settings: Settings
) -> list[WorkSummary]:
    ids = [w.id for w in works]
    counts = await page_counts(session, ids)
    thumbs = await thumbnail_flags(session, ids)
    return [
        summarize(w, settings, page_count=counts.get(w.id, 0), has_thumbnail=w.id in thumbs)
        for w in works
    ]


async def list_works(
    session: AsyncSession,
    principal: Principal,
    settings: Settings,
    *,
    query: str | None,
    access_class: AccessClass | None,
    limit: int,
    offset: int,
) -> tuple[list[WorkSummary], int]:
    stmt = visible_works(select(Work), principal)
    if access_class is not None:
        stmt = stmt.where(Work.access_class == access_class)
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            Work.title_ar.ilike(pattern)
            | Work.title_en.ilike(pattern)
            | Work.title_translit.ilike(pattern)
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(Work.title_ar.asc(), Work.id.asc()).limit(limit).offset(offset)
    )
    works = list(rows.all())
    return await summarize_many(session, works, settings), int(total)


async def agents_for(session: AsyncSession, work: Work, settings: Settings) -> list[AgentRef]:
    rows = await session.execute(
        select(Agent, WorkAgent.role)
        .join(WorkAgent, WorkAgent.agent_id == Agent.id)
        .where(WorkAgent.work_id == work.id)
        .order_by(WorkAgent.ordinal.asc())
    )
    return [
        AgentRef(
            public_id=agent.public_id,
            ark=format_ark(settings.ark_naan, agent.public_id),
            name_ar=agent.name_ar,
            name_latin=agent.name_latin,
            role=role,
        )
        for agent, role in rows.all()
    ]


async def terms_for(session: AsyncSession, work: Work) -> list[TermRef]:
    rows = await session.execute(
        select(VocabularyTerm, WorkTerm.facet)
        .join(WorkTerm, WorkTerm.term_id == VocabularyTerm.id)
        .where(WorkTerm.work_id == work.id)
        .order_by(WorkTerm.facet.asc(), VocabularyTerm.pref_label_ar.asc())
    )
    return [
        TermRef(
            scheme=str(term.scheme),
            facet=facet,
            code=term.code,
            label_ar=term.pref_label_ar,
            label_en=term.pref_label_en,
        )
        for term, facet in rows.all()
    ]


async def collections_for(
    session: AsyncSession, work: Work, settings: Settings
) -> list[CollectionRef]:
    rows = await session.scalars(
        select(Collection)
        .join(CollectionWork, CollectionWork.collection_id == Collection.id)
        .where(
            CollectionWork.work_id == work.id, Collection.publish_state == PublishState.PUBLISHED
        )
        .order_by(Collection.title_ar.asc())
    )
    return [
        CollectionRef(
            public_id=c.public_id,
            ark=format_ark(settings.ark_naan, c.public_id),
            title_ar=c.title_ar,
            title_en=c.title_en,
        )
        for c in rows.all()
    ]


def citation_for(work: Work, agents: list[AgentRef], ark: str) -> Citation:
    authors_ar = "، ".join(a.name_ar for a in agents if a.role.value == "author") or "مؤلف مجهول"
    authors_en = (
        ", ".join((a.name_latin or a.name_ar) for a in agents if a.role.value == "author")
        or "Unknown author"
    )
    date = work.date_edtf or ""
    title_en = work.title_en or work.title_translit or work.title_ar
    return Citation(
        ark=ark,
        ar=f"{authors_ar}. {work.title_ar}. {date}. {ark}".replace(". .", "."),
        en=f"{authors_en}. {title_en}. {date}. {ark}".replace(". .", "."),
    )


async def work_detail(
    session: AsyncSession, work: Work, principal: Principal, settings: Settings, *, can_read: bool
) -> WorkDetail:
    summary = (await summarize_many(session, [work], settings))[0]
    agents = await agents_for(session, work, settings)
    item = await session.scalar(select(Item).where(Item.work_id == work.id).limit(1))
    return WorkDetail(
        **summary.model_dump(),
        uniform_title=work.uniform_title,
        description_ar=work.description_ar,
        description_en=work.description_en,
        extent=work.extent,
        rights_statement=work.rights_statement,
        rights_basis=work.rights_basis if principal.is_staff else None,
        pricing=work.pricing if work.access_class == AccessClass.PAID else None,
        published_at=work.published_at,
        agents=agents,
        terms=await terms_for(session, work),
        collections=await collections_for(session, work, settings),
        provenance=item.provenance if item else None,
        citation=citation_for(work, agents, summary.ark),
        can_read=can_read,
        can_request_access=(
            principal.authenticated and work.access_class == AccessClass.RESTRICTED and not can_read
        ),
    )


async def list_pages(session: AsyncSession, work: Work, settings: Settings) -> list[PageSummary]:
    rows = await session.scalars(
        select(Page).where(Page.work_id == work.id).order_by(Page.seq.asc())
    )
    return [
        PageSummary(
            seq=p.seq,
            ark=format_page_ark(settings.ark_naan, work.public_id, p.seq),
            label=p.label,
            page_type=p.page_type,
            width_px=p.width_px,
            height_px=p.height_px,
            in_sample_range=in_sample_range(work, p.seq),
            thumbnail_available=p.thumb_key is not None,
            section_title=p.section_title,
            description=p.description,
        )
        for p in rows.all()
    ]


async def create_work(
    session: AsyncSession,
    data: WorkCreate,
    principal: Principal,
    settings: Settings,
    *,
    request_id: str | None,
) -> Work:
    work = Work(
        public_id=mint_name(settings.ark_shoulder_work),
        created_by=principal.user_id,
        **{k: v for k, v in data.model_dump().items() if v is not None},
    )
    session.add(work)
    await session.flush()
    await audit.write(
        session,
        actor_id=principal.id,
        actor_type="user",
        actor_roles=principal.roles,
        action="work.create",
        resource_kind="work",
        resource_id=work.public_id,
        outcome=AuditOutcome.SUCCESS,
        request_id=request_id,
    )
    return work


async def update_work(
    session: AsyncSession,
    work: Work,
    data: WorkUpdate,
    principal: Principal,
    *,
    request_id: str | None,
) -> Work:
    changes = data.model_dump(exclude_unset=True, exclude={"reason"})
    now = dt.datetime.now(dt.UTC)
    changed_fields: list[str] = []
    for field, new_value in changes.items():
        old_value = getattr(work, field)
        if old_value == new_value:
            continue
        setattr(work, field, new_value)
        session.add(
            RecordChange(
                entity_kind="work",
                entity_id=work.id,
                field=field,
                old_value={"value": old_value},
                new_value={"value": new_value},
                changed_by=principal.user_id,
                changed_at=now,
                reason=data.reason,
            )
        )
        changed_fields.append(field)
    await session.flush()
    if changed_fields:
        await audit.write(
            session,
            actor_id=principal.id,
            actor_type="user",
            actor_roles=principal.roles,
            action="work.edit",
            resource_kind="work",
            resource_id=work.public_id,
            outcome=AuditOutcome.SUCCESS,
            severity=AuditSeverity.INFO,
            details={"fields": changed_fields},
            request_id=request_id,
        )
    return work


async def list_collections(
    session: AsyncSession, principal: Principal, settings: Settings, *, limit: int, offset: int
) -> tuple[list[CollectionSummary], int]:
    stmt = select(Collection).where(Collection.deleted_at.is_(None))
    if not principal.is_staff:
        stmt = stmt.where(Collection.publish_state == PublishState.PUBLISHED)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(Collection.title_ar.asc()).limit(limit).offset(offset)
    )
    collections = list(rows.all())
    count_rows = await session.execute(
        select(CollectionWork.collection_id, func.count())
        .where(CollectionWork.collection_id.in_([c.id for c in collections] or [uuid.uuid4()]))
        .group_by(CollectionWork.collection_id)
    )
    counts: dict[uuid.UUID, int] = {key: int(n) for key, n in count_rows.all()}
    return [
        CollectionSummary(
            public_id=c.public_id,
            ark=format_ark(settings.ark_naan, c.public_id),
            kind=c.kind,
            title_ar=c.title_ar,
            title_en=c.title_en,
            description_ar=c.description_ar,
            description_en=c.description_en,
            work_count=int(counts.get(c.id, 0)),
        )
        for c in collections
    ], int(total)


async def collection_detail(
    session: AsyncSession, collection: Collection, principal: Principal, settings: Settings
) -> CollectionDetail:
    stmt = (
        visible_works(select(Work), principal)
        .join(CollectionWork, CollectionWork.work_id == Work.id)
        .where(CollectionWork.collection_id == collection.id)
        .order_by(CollectionWork.ordinal.asc())
    )
    works = list((await session.scalars(stmt)).all())
    return CollectionDetail(
        public_id=collection.public_id,
        ark=format_ark(settings.ark_naan, collection.public_id),
        kind=collection.kind,
        title_ar=collection.title_ar,
        title_en=collection.title_en,
        description_ar=collection.description_ar,
        description_en=collection.description_en,
        work_count=len(works),
        works=await summarize_many(session, works, settings),
    )


async def list_terms(
    session: AsyncSession, principal: Principal, *, scheme: TermScheme, limit: int, offset: int
) -> tuple[list[TermSummary], int]:
    stmt = select(VocabularyTerm).where(
        VocabularyTerm.scheme == scheme, VocabularyTerm.deleted_at.is_(None)
    )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(VocabularyTerm.pref_label_ar.asc()).limit(limit).offset(offset)
    )
    terms = list(rows.all())
    visible = visible_works(select(Work.id), principal).subquery()
    count_rows = await session.execute(
        select(WorkTerm.term_id, func.count())
        .where(WorkTerm.term_id.in_([t.id for t in terms] or [uuid.uuid4()]))
        .where(WorkTerm.work_id.in_(select(visible.c.id)))
        .group_by(WorkTerm.term_id)
    )
    counts: dict[uuid.UUID, int] = {key: int(n) for key, n in count_rows.all()}
    return [
        TermSummary(
            scheme=str(t.scheme),
            facet=t.facet,
            code=t.code,
            label_ar=t.pref_label_ar,
            label_en=t.pref_label_en,
            landing_ar=t.landing_ar,
            landing_en=t.landing_en,
            latitude=float(t.latitude) if t.latitude is not None else None,
            longitude=float(t.longitude) if t.longitude is not None else None,
            work_count=int(counts.get(t.id, 0)),
        )
        for t in terms
    ], int(total)


# --- Seeding and curation helpers used by the worker and the seed command ------------------


async def create_agent(
    session: AsyncSession,
    settings: Settings,
    *,
    kind: str,
    name_ar: str,
    name_latin: str | None,
    dates_edtf: str | None,
) -> Agent:
    from jdhp_api.core.orm import AgentKind

    agent = Agent(
        public_id=mint_name(settings.ark_shoulder_agent),
        kind=AgentKind(kind),
        name_ar=name_ar,
        name_latin=name_latin,
        dates_edtf=dates_edtf,
    )
    session.add(agent)
    await session.flush()
    return agent


async def link_agent(
    session: AsyncSession, work: Work, agent: Agent, role: str, ordinal: int = 0
) -> None:
    from jdhp_api.core.orm import AgentRole

    session.add(
        WorkAgent(work_id=work.id, agent_id=agent.id, role=AgentRole(role), ordinal=ordinal)
    )
    await session.flush()


async def upsert_term(
    session: AsyncSession,
    *,
    scheme: str,
    facet: str,
    code: str,
    label_ar: str,
    label_en: str | None,
) -> VocabularyTerm:
    from jdhp_api.core.orm import TermFacet

    term = (
        await session.scalars(
            select(VocabularyTerm).where(
                VocabularyTerm.scheme == TermScheme(scheme), VocabularyTerm.code == code
            )
        )
    ).first()
    if term is None:
        term = VocabularyTerm(
            scheme=TermScheme(scheme),
            facet=TermFacet(facet),
            code=code,
            pref_label_ar=label_ar,
            pref_label_en=label_en,
        )
        session.add(term)
        await session.flush()
    return term


async def link_term(session: AsyncSession, work: Work, term: VocabularyTerm) -> None:
    existing = (
        await session.scalars(
            select(WorkTerm).where(WorkTerm.work_id == work.id, WorkTerm.term_id == term.id)
        )
    ).first()
    if existing is None:
        session.add(WorkTerm(work_id=work.id, term_id=term.id, facet=term.facet))
        await session.flush()


async def create_collection(
    session: AsyncSession,
    settings: Settings,
    *,
    kind: str,
    title_ar: str,
    title_en: str | None,
    description_ar: str | None,
    description_en: str | None,
    publish: bool,
) -> Collection:
    from jdhp_api.core.orm import CollectionKind

    collection = Collection(
        public_id=mint_name(settings.ark_shoulder_collection),
        kind=CollectionKind(kind),
        title_ar=title_ar,
        title_en=title_en,
        description_ar=description_ar,
        description_en=description_en,
        publish_state=PublishState.PUBLISHED if publish else PublishState.DRAFT,
    )
    session.add(collection)
    await session.flush()
    return collection


async def add_to_collection(
    session: AsyncSession, collection: Collection, work: Work, ordinal: int = 0
) -> None:
    session.add(CollectionWork(collection_id=collection.id, work_id=work.id, ordinal=ordinal))
    await session.flush()


async def set_publish_state(
    session: AsyncSession,
    work: Work,
    state: PublishState,
    *,
    actor_id: str,
    actor_roles: tuple[str, ...] | frozenset[str],
    request_id: str | None = None,
) -> Work:
    """Direct state change for seeding and withdrawal. Staff publishing goes through four-eyes."""
    previous = work.publish_state
    work.publish_state = state
    if state == PublishState.PUBLISHED and work.published_at is None:
        work.published_at = dt.datetime.now(dt.UTC)
    await session.flush()
    await audit.write(
        session,
        actor_id=actor_id,
        actor_type="system" if actor_id == "system" else "user",
        actor_roles=actor_roles,
        action="work.publish_state",
        resource_kind="work",
        resource_id=work.public_id,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        details={"from": str(previous), "to": str(state)},
        request_id=request_id,
    )
    return work
