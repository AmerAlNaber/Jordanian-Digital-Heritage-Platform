"""Content objects, glossary and page embeddings.

Every content object carries provenance_type and origin (SRC-1). Objects with origin ``ai``
are created at ``pending`` and only the review portal can approve them (REV-1); the database
enforces both with triggers defined in the initial migration.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.orm import (
    Base,
    Origin,
    PrimaryKeyMixin,
    ProvenanceType,
    ReviewStatus,
    SoftDeleteMixin,
    TimestampMixin,
    pg_enum,
)


class ContentObject(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "content_object"
    __table_args__ = (
        CheckConstraint(
            "origin <> 'ai' OR (model IS NOT NULL AND model_version IS NOT NULL)",
            name="ai_objects_record_model",
        ),
        CheckConstraint("provenance_type <> 'ocr'", name="ocr_is_page_text_not_content"),
    )

    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("page.id"), index=True)
    provenance_type: Mapped[ProvenanceType] = mapped_column(
        pg_enum(ProvenanceType, "provenance_type"), index=True
    )
    origin: Mapped[Origin] = mapped_column(pg_enum(Origin, "origin"), index=True)
    language: Mapped[str] = mapped_column(String(3))
    script: Mapped[str] = mapped_column(String(4))
    body: Mapped[str | None] = mapped_column(Text)
    reference_key: Mapped[str | None] = mapped_column(Text)
    segments: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    prompt_template_version: Mapped[str | None] = mapped_column(String(64))
    glossary_version: Mapped[str | None] = mapped_column(String(64))
    self_assessment: Mapped[float | None] = mapped_column(Numeric(4, 3))
    review_status: Mapped[ReviewStatus] = mapped_column(
        pg_enum(ReviewStatus, "review_status"), default=ReviewStatus.PENDING, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    reviewer_subject: Mapped[str | None] = mapped_column(String(64))
    reviewer_name: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[dt.datetime | None]
    generated_at: Mapped[dt.datetime | None]


class GlossaryTerm(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "glossary_term"

    source_form: Mapped[str] = mapped_column(Text, index=True)
    source_language: Mapped[str] = mapped_column(String(3), default="ara")
    target_forms: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    context_note: Mapped[str | None] = mapped_column(Text)
    vocabulary_term_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vocabulary_term.id"))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))


class PageEmbedding(PrimaryKeyMixin, TimestampMixin, Base):
    """A vector per page chunk, with the model and version that produced it (SRCH-6)."""

    __tablename__ = "page_embedding"
    __table_args__ = (
        UniqueConstraint("page_id", "chunk_index", "model", "model_version", name="chunk"),
    )

    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("page.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[Any] = mapped_column(Vector())
    dimensions: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(64))
    chunk_hash: Mapped[str] = mapped_column(String(64))
