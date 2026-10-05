"""Reader: sessions bound to a grant and a device, and print jobs."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.orm import Base, PrimaryKeyMixin, ReaderSessionState, TimestampMixin, pg_enum


class ReaderSession(PrimaryKeyMixin, TimestampMixin, Base):
    """One open reader. The forensic key is stored encrypted so a leak can be traced (SEC-11)."""

    __tablename__ = "reader_session"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), index=True)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    grant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant.id"), index=True)
    device_hash: Mapped[str] = mapped_column(String(64))
    forensic_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    state: Mapped[ReaderSessionState] = mapped_column(
        pg_enum(ReaderSessionState, "reader_session_state"), default=ReaderSessionState.ACTIVE
    )
    last_seen_at: Mapped[dt.datetime]
    idle_expires_at: Mapped[dt.datetime]
    hard_expires_at: Mapped[dt.datetime]
    ended_at: Mapped[dt.datetime | None]
    suspended_reason: Mapped[str | None] = mapped_column(Text)


class PrintJob(PrimaryKeyMixin, TimestampMixin, Base):
    """A server-rendered, watermarked, low-resolution print (RDR-4). Logged with its pages."""

    __tablename__ = "print_job"

    reader_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reader_session.id"))
    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    pages: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    rendered_at: Mapped[dt.datetime | None]
    export_key: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[str | None] = mapped_column(String(64))
    downloaded_at: Mapped[dt.datetime | None]
