"""Catalog: works, agents, items, collections and controlled vocabularies."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.orm import (
    AccessClass,
    AgentKind,
    AgentRole,
    Base,
    CollectionKind,
    DigitizationStatus,
    PrimaryKeyMixin,
    PublishState,
    SoftDeleteMixin,
    TermFacet,
    TermScheme,
    TimestampMixin,
    pg_enum,
)

DEFAULT_RIGHTS_STATEMENT = "http://rightsstatements.org/vocab/InC/1.0/"


class Work(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """The intellectual book, independent of copies."""

    __tablename__ = "work"

    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title_ar: Mapped[str] = mapped_column(Text)
    title_translit: Mapped[str | None] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    uniform_title: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(3), default="ara")
    script: Mapped[str] = mapped_column(String(4), default="Arab")
    date_edtf: Mapped[str | None] = mapped_column(String(64))
    date_hijri: Mapped[str | None] = mapped_column(String(64))
    date_earliest: Mapped[dt.date | None] = mapped_column(Date)
    date_latest: Mapped[dt.date | None] = mapped_column(Date)
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    extent: Mapped[str | None] = mapped_column(Text)
    rights_statement: Mapped[str] = mapped_column(Text, default=DEFAULT_RIGHTS_STATEMENT)
    rights_basis: Mapped[str | None] = mapped_column(Text)
    access_class: Mapped[AccessClass] = mapped_column(
        pg_enum(AccessClass, "access_class"), default=AccessClass.REGISTERED, index=True
    )
    pricing: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    publish_state: Mapped[PublishState] = mapped_column(
        pg_enum(PublishState, "publish_state"), default=PublishState.DRAFT, index=True
    )
    published_at: Mapped[dt.datetime | None]
    sample_page_override: Mapped[int | None] = mapped_column(Integer)
    frozen: Mapped[bool] = mapped_column(default=False)
    owner_institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institution.id"))
    extra_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Agent(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A person, organization or family in any role."""

    __tablename__ = "agent"

    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[AgentKind] = mapped_column(pg_enum(AgentKind, "agent_kind"))
    name_ar: Mapped[str] = mapped_column(Text)
    name_latin: Mapped[str | None] = mapped_column(Text)
    dates_edtf: Mapped[str | None] = mapped_column(String(64))
    authority_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text)


class WorkAgent(Base):
    __tablename__ = "work_agent"

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), primary_key=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[AgentRole] = mapped_column(pg_enum(AgentRole, "agent_role"), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)


class Item(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A physical copy held by the library."""

    __tablename__ = "item"

    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    shelfmark: Mapped[str | None] = mapped_column(Text)
    condition: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[str | None] = mapped_column(Text)
    donor_agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent.id"))
    digitization_status: Mapped[DigitizationStatus] = mapped_column(
        pg_enum(DigitizationStatus, "digitization_status"), default=DigitizationStatus.NOT_STARTED
    )


class Collection(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "collection"

    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[CollectionKind] = mapped_column(pg_enum(CollectionKind, "collection_kind"))
    title_ar: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    cover_work_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work.id"))
    publish_state: Mapped[PublishState] = mapped_column(
        pg_enum(PublishState, "publish_state"), default=PublishState.DRAFT
    )


class CollectionWork(Base):
    __tablename__ = "collection_work"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), primary_key=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0)


class VocabularyTerm(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A controlled subject, place, period, theme or material, with its curated landing page."""

    __tablename__ = "vocabulary_term"
    __table_args__ = (UniqueConstraint("scheme", "code", name="scheme_code"),)

    scheme: Mapped[TermScheme] = mapped_column(pg_enum(TermScheme, "term_scheme"))
    facet: Mapped[TermFacet] = mapped_column(pg_enum(TermFacet, "term_facet"), index=True)
    code: Mapped[str] = mapped_column(String(128))
    pref_label_ar: Mapped[str] = mapped_column(Text)
    pref_label_en: Mapped[str | None] = mapped_column(Text)
    alt_labels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    broader_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vocabulary_term.id"))
    external_uri: Mapped[str | None] = mapped_column(Text)
    geonames_id: Mapped[str | None] = mapped_column(String(32))
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    period_edtf: Mapped[str | None] = mapped_column(String(64))
    landing_ar: Mapped[str | None] = mapped_column(Text)
    landing_en: Mapped[str | None] = mapped_column(Text)


class WorkTerm(Base):
    __tablename__ = "work_term"
    __table_args__ = (Index("ix_work_term_term_id", "term_id"),)

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), primary_key=True
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vocabulary_term.id", ondelete="CASCADE"), primary_key=True
    )
    facet: Mapped[TermFacet] = mapped_column(pg_enum(TermFacet, "term_facet"), primary_key=True)
