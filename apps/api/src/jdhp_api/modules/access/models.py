"""Access: requests, grants and payments. Nothing is readable without a grant."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.ids import mint_name
from jdhp_api.core.orm import (
    Base,
    GrantSource,
    PaymentStatus,
    PrimaryKeyMixin,
    RequestState,
    TimestampMixin,
    pg_enum,
)

GRANT_SHOULDER = "g8"  # opaque public names for grants; never the row id (INT-7)


class AccessRequest(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "access_request"

    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    purpose: Mapped[str] = mapped_column(Text)
    state: Mapped[RequestState] = mapped_column(
        pg_enum(RequestState, "request_state"), default=RequestState.PENDING, index=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    decided_at: Mapped[dt.datetime | None]
    reason: Mapped[str | None] = mapped_column(Text)


class Grant(PrimaryKeyMixin, TimestampMixin, Base):
    """Permission to read one work for a bounded period. Revocable at any time (ACS-2)."""

    __tablename__ = "grant"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_starts"),
        CheckConstraint("user_id IS NOT NULL OR institution_id IS NOT NULL", name="has_holder"),
        CheckConstraint("device_limit >= 1", name="device_limit_positive"),
        CheckConstraint(
            "(page_from IS NULL AND page_to IS NULL) OR (page_from >= 1 AND page_to >= page_from)",
            name="page_range_valid",
        ),
    )

    public_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, default=lambda: mint_name(GRANT_SHOULDER)
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institution.id"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    starts_at: Mapped[dt.datetime]
    ends_at: Mapped[dt.datetime]
    device_limit: Mapped[int] = mapped_column(Integer, default=2)
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[GrantSource] = mapped_column(pg_enum(GrantSource, "grant_source"))
    print_quota: Mapped[int] = mapped_column(Integer, default=0)
    print_used: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    revoked_at: Mapped[dt.datetime | None]
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    access_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("access_request.id"))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment.id"))


class Payment(PrimaryKeyMixin, TimestampMixin, Base):
    """A transaction reference from the hosted payment page. Never any card data (SEC-30)."""

    __tablename__ = "payment"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    gateway: Mapped[str] = mapped_column(String(32))
    gateway_reference: Mapped[str] = mapped_column(String(128), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    currency: Mapped[str] = mapped_column(String(3), default="JOD")
    duration: Mapped[str] = mapped_column(String(8))
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"), default=PaymentStatus.INITIATED
    )
