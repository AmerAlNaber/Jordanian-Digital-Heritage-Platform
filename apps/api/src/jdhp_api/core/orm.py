"""Declarative base, mixins and enumerations shared by every model.

All primary keys are UUIDv7. Every table carries created_at, updated_at and created_by; the
soft-delete column exists only where deletion is ever allowed. Enumerations are native
PostgreSQL enums so the database rejects an unknown state as firmly as the code does.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from jdhp_api.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        uuid.UUID: PG_UUID(as_uuid=True),
        dt.datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
    }


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
        native_enum=True,
        create_constraint=False,
    )


class PrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class SoftDeleteMixin:
    deleted_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)


# --- Enumerations -------------------------------------------------------------------------


class AccessClass(enum.StrEnum):
    OPEN = "open"
    REGISTERED = "registered"
    PAID = "paid"
    RESTRICTED = "restricted"
    EMBARGOED = "embargoed"


def sample_page_limit(access_class: AccessClass) -> int | None:
    """Pages visible without a grant, per the access class table. None means every page."""
    return {
        AccessClass.OPEN: None,
        AccessClass.REGISTERED: 10,
        AccessClass.PAID: 10,
        AccessClass.RESTRICTED: 3,
        AccessClass.EMBARGOED: 1,
    }[access_class]


class PublishState(enum.StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class ProvenanceType(enum.StrEnum):
    SCAN = "scan"
    OCR = "ocr"
    TRANSCRIPTION = "transcription"
    TRANSLATION = "translation"
    EDITORIAL = "editorial"
    VISUALIZATION = "visualization"


class Origin(enum.StrEnum):
    HUMAN = "human"
    AI = "ai"


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PageType(enum.StrEnum):
    COVER = "cover"
    TITLE = "title"
    BLANK = "blank"
    TEXT = "text"
    ILLUSTRATION = "illustration"
    MAP = "map"
    TABLE = "table"
    COLOPHON = "colophon"
    ENDPAPER = "endpaper"


class CorrectionState(enum.StrEnum):
    RAW = "raw"
    CORRECTED = "corrected"
    VERIFIED = "verified"


class ReadingDirection(enum.StrEnum):
    RTL = "rtl"
    LTR = "ltr"


class DigitizationStatus(enum.StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class DigitalObjectState(enum.StrEnum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    FROZEN = "frozen"


class FixityStatus(enum.StrEnum):
    UNCHECKED = "unchecked"
    OK = "ok"
    MISMATCH = "mismatch"


class IntakeState(enum.StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    FAILED = "failed"
    INGESTED = "ingested"


class AgentKind(enum.StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    FAMILY = "family"


class AgentRole(enum.StrEnum):
    AUTHOR = "author"
    EDITOR = "editor"
    TRANSLATOR = "translator"
    SCRIBE = "scribe"
    COMMENTATOR = "commentator"
    PRINTER = "printer"
    PUBLISHER = "publisher"
    DONOR = "donor"


class CollectionKind(enum.StrEnum):
    DONOR = "donor"
    SERIES = "series"
    PROJECT = "project"
    THEMATIC = "thematic"


class TermScheme(enum.StrEnum):
    LCSH = "lcsh"
    LOCAL_AR = "local_ar"
    GAZETTEER_JO = "gazetteer_jo"
    PERIOD_JO = "period_jo"
    MATERIAL = "material"
    THEME = "theme"


class TermFacet(enum.StrEnum):
    SUBJECT = "subject"
    PLACE = "place"
    PERIOD = "period"
    THEME = "theme"
    MATERIAL = "material"


class UserRole(enum.StrEnum):
    MEMBER = "member"
    VERIFIED_RESEARCHER = "verified_researcher"
    INSTITUTIONAL_USER = "institutional_user"
    INSTITUTION_ADMIN = "institution_admin"
    CURATOR = "curator"
    REVIEWER = "reviewer"
    RIGHTS_OFFICER = "rights_officer"
    PLATFORM_ADMIN = "platform_admin"


class UserVerification(enum.StrEnum):
    NONE = "none"
    EMAIL = "email"
    PHONE = "phone"
    RESEARCHER = "researcher"
    INSTITUTIONAL = "institutional"


class RequestState(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"


class GrantSource(enum.StrEnum):
    REQUEST = "request"
    PAYMENT = "payment"
    LICENSE = "license"
    STAFF = "staff"
    ACCESS_CLASS = "access_class"  # implied by the work's class: Open and Registered (Phase 1)


class PaymentStatus(enum.StrEnum):
    INITIATED = "initiated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class AuditOutcome(enum.StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    SUCCESS = "success"
    FAILURE = "failure"


class AuditSeverity(enum.StrEnum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    HIGH = "high"


class ReaderSessionState(enum.StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class ApprovalKind(enum.StrEnum):
    PUBLISH = "publish"
    ACCESS_CLASS_CHANGE = "access_class_change"
    PRICING_CHANGE = "pricing_change"
    GRANT_EXTENSION = "grant_extension"


class ApprovalState(enum.StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class BreakGlassState(enum.StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class PremisEventType(enum.StrEnum):
    INGEST = "ingest"
    FIXITY_CHECK = "fixity_check"
    DERIVATIVE_GENERATION = "derivative_generation"
    ACCESS_CLASS_CHANGE = "access_class_change"
    WITHDRAWAL = "withdrawal"


class VerificationCaseState(enum.StrEnum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class IncidentKind(enum.StrEnum):
    FIXITY_MISMATCH = "fixity_mismatch"
    RATE_LIMIT_ABUSE = "rate_limit_abuse"
    POLICY_ENGINE_ERROR = "policy_engine_error"


class IncidentState(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
