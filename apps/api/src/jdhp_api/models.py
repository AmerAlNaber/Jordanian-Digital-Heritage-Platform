"""Imports every model so metadata is complete for Alembic and tests."""

from jdhp_api.core.orm import Base
from jdhp_api.modules.access.models import AccessRequest, Grant, Payment
from jdhp_api.modules.admin.models import Approval, BreakGlassRequest, RecordChange
from jdhp_api.modules.audit.models import AuditEvent
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
from jdhp_api.modules.content.models import ContentObject, GlossaryTerm, PageEmbedding
from jdhp_api.modules.identity.models import Institution, InstitutionLicense, User, VerificationCase
from jdhp_api.modules.ingest.models import DigitalObject, Incident, IntakeBatch, Page, PremisEvent
from jdhp_api.modules.reader.models import PrintJob, ReaderSession
from jdhp_api.modules.review.models import ReviewTask

__all__ = [
    "AccessRequest",
    "Agent",
    "Approval",
    "AuditEvent",
    "Base",
    "BreakGlassRequest",
    "Collection",
    "CollectionWork",
    "ContentObject",
    "DigitalObject",
    "GlossaryTerm",
    "Grant",
    "Incident",
    "Institution",
    "InstitutionLicense",
    "IntakeBatch",
    "Item",
    "Page",
    "PageEmbedding",
    "Payment",
    "PremisEvent",
    "PrintJob",
    "ReaderSession",
    "RecordChange",
    "ReviewTask",
    "User",
    "VerificationCase",
    "VocabularyTerm",
    "Work",
    "WorkAgent",
    "WorkTerm",
]
