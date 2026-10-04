"""Digitization intake: batches, digital objects, pages, preservation events and incidents.

The page row is where the scan and the OCR text live. The OCR text column is internal: no
response schema ever includes it (CAT-4, RDR-3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.orm import (
    Base,
    CorrectionState,
    DigitalObjectState,
    FixityStatus,
    IncidentKind,
    IncidentState,
    IntakeState,
    PageType,
    PremisEventType,
    PrimaryKeyMixin,
    ReadingDirection,
    TimestampMixin,
    pg_enum,
)


class IntakeBatch(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "intake_batch"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    work_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work.id"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item.id"))
    digital_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("digital_object.id"))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    staging_prefix: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer)
    state: Mapped[IntakeState] = mapped_column(
        pg_enum(IntakeState, "intake_state"), default=IntakeState.RECEIVED, index=True
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    error_detail: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[dt.datetime | None]


class DigitalObject(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "digital_object"

    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item.id"))
    mets_key: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[DigitalObjectState] = mapped_column(
        pg_enum(DigitalObjectState, "digital_object_state"),
        default=DigitalObjectState.DRAFT,
        index=True,
    )
    fixity_status: Mapped[FixityStatus] = mapped_column(
        pg_enum(FixityStatus, "fixity_status"), default=FixityStatus.UNCHECKED
    )
    last_fixity_at: Mapped[dt.datetime | None]
    frozen_reason: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[dt.datetime | None]


class Page(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "page"
    __table_args__ = (UniqueConstraint("digital_object_id", "seq", name="digital_object_seq"),)

    digital_object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("digital_object.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(64))
    folio: Mapped[str | None] = mapped_column(String(64))
    page_type: Mapped[PageType] = mapped_column(
        pg_enum(PageType, "page_type"), default=PageType.TEXT
    )
    language: Mapped[str | None] = mapped_column(String(3))
    script: Mapped[str | None] = mapped_column(String(4))
    reading_direction: Mapped[ReadingDirection] = mapped_column(
        pg_enum(ReadingDirection, "reading_direction"), default=ReadingDirection.RTL
    )
    # Scan
    master_key: Mapped[str | None] = mapped_column(Text)
    derivative_key: Mapped[str | None] = mapped_column(Text)
    thumb_key: Mapped[str | None] = mapped_column(Text)
    sample_key: Mapped[str | None] = mapped_column(Text)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    capture_date: Mapped[dt.date | None]
    capture_device: Mapped[str | None] = mapped_column(Text)
    color_target_ref: Mapped[str | None] = mapped_column(Text)
    condition_notes: Mapped[str | None] = mapped_column(Text)
    # Text (internal)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    alto_key: Mapped[str | None] = mapped_column(Text)
    offsets_key: Mapped[str | None] = mapped_column(Text)
    ocr_avg_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    ocr_min_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    ocr_engine: Mapped[str | None] = mapped_column(String(64))
    ocr_engine_version: Mapped[str | None] = mapped_column(String(64))
    ocr_at: Mapped[dt.datetime | None]
    ocr_flagged: Mapped[bool] = mapped_column(default=False)
    correction_state: Mapped[CorrectionState] = mapped_column(
        pg_enum(CorrectionState, "correction_state"), default=CorrectionState.RAW
    )
    # Structure
    section_title: Mapped[str | None] = mapped_column(Text)
    toc_entry: Mapped[str | None] = mapped_column(Text)
    running_head: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # Preservation
    master_sha256: Mapped[str | None] = mapped_column(String(64))
    derivative_sha256: Mapped[str | None] = mapped_column(String(64))
    last_fixity_at: Mapped[dt.datetime | None]


class PremisEvent(PrimaryKeyMixin, Base):
    __tablename__ = "premis_event"

    digital_object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("digital_object.id"), index=True
    )
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("page.id"))
    event_type: Mapped[PremisEventType] = mapped_column(
        pg_enum(PremisEventType, "premis_event_type")
    )
    outcome: Mapped[str] = mapped_column(String(16))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    agent: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[dt.datetime]


class Incident(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incident"

    kind: Mapped[IncidentKind] = mapped_column(pg_enum(IncidentKind, "incident_kind"))
    severity: Mapped[str] = mapped_column(String(16), default="high")
    digital_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("digital_object.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    state: Mapped[IncidentState] = mapped_column(
        pg_enum(IncidentState, "incident_state"), default=IncidentState.OPEN
    )
    resolved_at: Mapped[dt.datetime | None]
