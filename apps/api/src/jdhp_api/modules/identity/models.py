"""Identity: platform users, partner institutions, licenses and researcher verification."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.orm import (
    Base,
    PrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UserRole,
    UserVerification,
    VerificationCaseState,
    pg_enum,
)


class Institution(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "institution"

    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name_ar: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    license_terms: Mapped[str | None] = mapped_column(Text)
    seat_limit: Mapped[int | None] = mapped_column(Integer)
    sso_idp_alias: Mapped[str | None] = mapped_column(String(64), unique=True)
    ip_ranges: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    contact_email: Mapped[str | None] = mapped_column(Text)


class User(PrimaryKeyMixin, TimestampMixin, Base):
    """A platform principal. Deletion pseudonymizes; the row stays for the audit trail."""

    __tablename__ = "user"

    keycloak_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), default=UserRole.MEMBER)
    verification_level: Mapped[UserVerification] = mapped_column(
        pg_enum(UserVerification, "user_verification"), default=UserVerification.NONE
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institution.id"), index=True
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_seen_at: Mapped[dt.datetime | None]
    pseudonymized_at: Mapped[dt.datetime | None]
    phone_number: Mapped[str | None] = mapped_column(Text)
    phone_verified_at: Mapped[dt.datetime | None]


class InstitutionLicense(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institution_license"

    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institution.id"), index=True)
    access_classes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    seat_limit: Mapped[int] = mapped_column(Integer, default=1)
    starts_at: Mapped[dt.datetime]
    ends_at: Mapped[dt.datetime]


class VerificationCase(PrimaryKeyMixin, TimestampMixin, Base):
    """Researcher verification. Documents are deleted 30 days after the decision (ACC-3)."""

    __tablename__ = "verification_case"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(32))
    document_keys: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    affiliation: Mapped[str | None] = mapped_column(Text)
    state: Mapped[VerificationCaseState] = mapped_column(
        pg_enum(VerificationCaseState, "verification_case_state"),
        default=VerificationCaseState.SUBMITTED,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    decided_at: Mapped[dt.datetime | None]
    reason: Mapped[str | None] = mapped_column(Text)
    delete_documents_after: Mapped[dt.datetime | None]
    documents_deleted_at: Mapped[dt.datetime | None]


class PhoneVerification(PrimaryKeyMixin, TimestampMixin, Base):
    """The one pending phone code of a user: hashed, short-lived, attempt-limited (ACC-1)."""

    __tablename__ = "phone_verification"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), unique=True
    )
    phone_number: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[dt.datetime]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sends_in_window: Mapped[int] = mapped_column(Integer, default=1)
    window_started_at: Mapped[dt.datetime]
    last_sent_at: Mapped[dt.datetime]
