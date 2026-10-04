"""Initial schema: every core entity of SPEC.md plus the additions in ARCHITECTURE.md 9.1.

Revision ID: 0001
Revises: 
Create Date: 2026-10-04 21:46:57.864256+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    'agent_kind': ('person', 'organization', 'family',),
    'audit_outcome': ('allow', 'deny', 'success', 'failure',),
    'audit_severity': ('info', 'notice', 'warning', 'high',),
    'term_scheme': ('lcsh', 'local_ar', 'gazetteer_jo', 'period_jo', 'material', 'theme',),
    'term_facet': ('subject', 'place', 'period', 'theme', 'material',),
    'user_role': ('member', 'verified_researcher', 'institutional_user', 'institution_admin', 'curator', 'reviewer', 'rights_officer', 'platform_admin',),
    'user_verification': ('none', 'email', 'phone', 'researcher', 'institutional',),
    'access_class': ('open', 'registered', 'paid', 'restricted', 'embargoed',),
    'publish_state': ('draft', 'review', 'published', 'withdrawn',),
    'request_state': ('pending', 'approved', 'denied', 'withdrawn',),
    'approval_kind': ('publish', 'access_class_change', 'pricing_change', 'grant_extension',),
    'approval_state': ('proposed', 'approved', 'rejected', 'expired',),
    'break_glass_state': ('requested', 'approved', 'denied', 'expired',),
    'collection_kind': ('donor', 'series', 'project', 'thematic',),
    'digitization_status': ('not_started', 'in_progress', 'done',),
    'payment_status': ('initiated', 'succeeded', 'failed', 'refunded',),
    'verification_case_state': ('submitted', 'in_review', 'approved', 'rejected',),
    'agent_role': ('author', 'editor', 'translator', 'scribe', 'commentator', 'printer', 'publisher', 'donor',),
    'digital_object_state': ('draft', 'processing', 'ready', 'frozen',),
    'fixity_status': ('unchecked', 'ok', 'mismatch',),
    'grant_source': ('request', 'payment', 'license', 'staff',),
    'incident_kind': ('fixity_mismatch', 'rate_limit_abuse', 'policy_engine_error',),
    'incident_state': ('open', 'resolved',),
    'intake_state': ('received', 'validating', 'failed', 'ingested',),
    'page_type': ('cover', 'title', 'blank', 'text', 'illustration', 'map', 'table', 'colophon', 'endpaper',),
    'reading_direction': ('rtl', 'ltr',),
    'correction_state': ('raw', 'corrected', 'verified',),
    'reader_session_state': ('active', 'expired', 'revoked', 'suspended',),
    'provenance_type': ('scan', 'ocr', 'transcription', 'translation', 'editorial', 'visualization',),
    'origin': ('human', 'ai',),
    'review_status': ('pending', 'in_review', 'approved', 'rejected',),
    'premis_event_type': ('ingest', 'fixity_check', 'derivative_generation', 'access_class_change', 'withdrawal',),
}


def upgrade() -> None:
    # Extensions and enumerated types. Shared types are created once, here.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)

    op.create_table('agent',
    sa.Column('public_id', sa.String(length=32), nullable=False),
    sa.Column('kind', postgresql.ENUM('person', 'organization', 'family', name='agent_kind', create_type=False), nullable=False),
    sa.Column('name_ar', sa.Text(), nullable=False),
    sa.Column('name_latin', sa.Text(), nullable=True),
    sa.Column('dates_edtf', sa.String(length=64), nullable=True),
    sa.Column('authority_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent'))
    )
    op.create_index(op.f('ix_agent_public_id'), 'agent', ['public_id'], unique=True)
    op.create_table('audit_event',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('seq', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_id', sa.String(length=64), nullable=False),
    sa.Column('actor_type', sa.String(length=16), nullable=False),
    sa.Column('actor_roles', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('resource_kind', sa.String(length=32), nullable=False),
    sa.Column('resource_id', sa.String(length=128), nullable=False),
    sa.Column('outcome', postgresql.ENUM('allow', 'deny', 'success', 'failure', name='audit_outcome', create_type=False), nullable=False),
    sa.Column('severity', postgresql.ENUM('info', 'notice', 'warning', 'high', name='audit_severity', create_type=False), nullable=False),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=36), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('prev_hash', sa.String(length=64), nullable=False),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_event')),
    sa.UniqueConstraint('hash', name=op.f('uq_audit_event_hash')),
    sa.UniqueConstraint('seq', name=op.f('uq_audit_event_seq'))
    )
    op.create_index(op.f('ix_audit_event_action'), 'audit_event', ['action'], unique=False)
    op.create_index(op.f('ix_audit_event_actor_id'), 'audit_event', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_event_occurred_at'), 'audit_event', ['occurred_at'], unique=False)
    op.create_index(op.f('ix_audit_event_request_id'), 'audit_event', ['request_id'], unique=False)
    op.create_index(op.f('ix_audit_event_resource_id'), 'audit_event', ['resource_id'], unique=False)
    op.create_index(op.f('ix_audit_event_resource_kind'), 'audit_event', ['resource_kind'], unique=False)
    op.create_table('institution',
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name_ar', sa.Text(), nullable=False),
    sa.Column('name_en', sa.Text(), nullable=True),
    sa.Column('license_terms', sa.Text(), nullable=True),
    sa.Column('seat_limit', sa.Integer(), nullable=True),
    sa.Column('sso_idp_alias', sa.String(length=64), nullable=True),
    sa.Column('ip_ranges', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('contact_email', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_institution')),
    sa.UniqueConstraint('slug', name=op.f('uq_institution_slug')),
    sa.UniqueConstraint('sso_idp_alias', name=op.f('uq_institution_sso_idp_alias'))
    )
    op.create_table('vocabulary_term',
    sa.Column('scheme', postgresql.ENUM('lcsh', 'local_ar', 'gazetteer_jo', 'period_jo', 'material', 'theme', name='term_scheme', create_type=False), nullable=False),
    sa.Column('facet', postgresql.ENUM('subject', 'place', 'period', 'theme', 'material', name='term_facet', create_type=False), nullable=False),
    sa.Column('code', sa.String(length=128), nullable=False),
    sa.Column('pref_label_ar', sa.Text(), nullable=False),
    sa.Column('pref_label_en', sa.Text(), nullable=True),
    sa.Column('alt_labels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('broader_id', sa.UUID(), nullable=True),
    sa.Column('external_uri', sa.Text(), nullable=True),
    sa.Column('geonames_id', sa.String(length=32), nullable=True),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('period_edtf', sa.String(length=64), nullable=True),
    sa.Column('landing_ar', sa.Text(), nullable=True),
    sa.Column('landing_en', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['broader_id'], ['vocabulary_term.id'], name=op.f('fk_vocabulary_term_broader_id_vocabulary_term')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vocabulary_term')),
    sa.UniqueConstraint('scheme', 'code', name='scheme_code')
    )
    op.create_index(op.f('ix_vocabulary_term_facet'), 'vocabulary_term', ['facet'], unique=False)
    op.create_table('institution_license',
    sa.Column('institution_id', sa.UUID(), nullable=False),
    sa.Column('access_classes', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('seat_limit', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['institution_id'], ['institution.id'], name=op.f('fk_institution_license_institution_id_institution')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_institution_license'))
    )
    op.create_index(op.f('ix_institution_license_institution_id'), 'institution_license', ['institution_id'], unique=False)
    op.create_table('user',
    sa.Column('keycloak_sub', sa.String(length=64), nullable=False),
    sa.Column('email', sa.Text(), nullable=True),
    sa.Column('display_name', sa.Text(), nullable=True),
    sa.Column('role', postgresql.ENUM('member', 'verified_researcher', 'institutional_user', 'institution_admin', 'curator', 'reviewer', 'rights_officer', 'platform_admin', name='user_role', create_type=False), nullable=False),
    sa.Column('verification_level', postgresql.ENUM('none', 'email', 'phone', 'researcher', 'institutional', name='user_verification', create_type=False), nullable=False),
    sa.Column('institution_id', sa.UUID(), nullable=True),
    sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pseudonymized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['institution_id'], ['institution.id'], name=op.f('fk_user_institution_id_institution')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user'))
    )
    op.create_index(op.f('ix_user_institution_id'), 'user', ['institution_id'], unique=False)
    op.create_index(op.f('ix_user_keycloak_sub'), 'user', ['keycloak_sub'], unique=True)
    op.create_table('work',
    sa.Column('public_id', sa.String(length=32), nullable=False),
    sa.Column('title_ar', sa.Text(), nullable=False),
    sa.Column('title_translit', sa.Text(), nullable=True),
    sa.Column('title_en', sa.Text(), nullable=True),
    sa.Column('uniform_title', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=3), nullable=False),
    sa.Column('script', sa.String(length=4), nullable=False),
    sa.Column('date_edtf', sa.String(length=64), nullable=True),
    sa.Column('date_hijri', sa.String(length=64), nullable=True),
    sa.Column('date_earliest', sa.Date(), nullable=True),
    sa.Column('date_latest', sa.Date(), nullable=True),
    sa.Column('description_ar', sa.Text(), nullable=True),
    sa.Column('description_en', sa.Text(), nullable=True),
    sa.Column('extent', sa.Text(), nullable=True),
    sa.Column('rights_statement', sa.Text(), nullable=False),
    sa.Column('rights_basis', sa.Text(), nullable=True),
    sa.Column('access_class', postgresql.ENUM('open', 'registered', 'paid', 'restricted', 'embargoed', name='access_class', create_type=False), nullable=False),
    sa.Column('pricing', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('publish_state', postgresql.ENUM('draft', 'review', 'published', 'withdrawn', name='publish_state', create_type=False), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sample_page_override', sa.Integer(), nullable=True),
    sa.Column('frozen', sa.Boolean(), nullable=False),
    sa.Column('owner_institution_id', sa.UUID(), nullable=True),
    sa.Column('extra_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_institution_id'], ['institution.id'], name=op.f('fk_work_owner_institution_id_institution')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_work'))
    )
    op.create_index(op.f('ix_work_access_class'), 'work', ['access_class'], unique=False)
    op.create_index(op.f('ix_work_public_id'), 'work', ['public_id'], unique=True)
    op.create_index(op.f('ix_work_publish_state'), 'work', ['publish_state'], unique=False)
    op.create_table('access_request',
    sa.Column('requester_id', sa.UUID(), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('state', postgresql.ENUM('pending', 'approved', 'denied', 'withdrawn', name='request_state', create_type=False), nullable=False),
    sa.Column('decided_by', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['decided_by'], ['user.id'], name=op.f('fk_access_request_decided_by_user')),
    sa.ForeignKeyConstraint(['requester_id'], ['user.id'], name=op.f('fk_access_request_requester_id_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_access_request_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_access_request'))
    )
    op.create_index(op.f('ix_access_request_requester_id'), 'access_request', ['requester_id'], unique=False)
    op.create_index(op.f('ix_access_request_state'), 'access_request', ['state'], unique=False)
    op.create_index(op.f('ix_access_request_work_id'), 'access_request', ['work_id'], unique=False)
    op.create_table('approval',
    sa.Column('kind', postgresql.ENUM('publish', 'access_class_change', 'pricing_change', 'grant_extension', name='approval_kind', create_type=False), nullable=False),
    sa.Column('target_kind', sa.String(length=32), nullable=False),
    sa.Column('target_id', sa.UUID(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('proposed_by', sa.UUID(), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('state', postgresql.ENUM('proposed', 'approved', 'rejected', 'expired', name='approval_state', create_type=False), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('approved_by IS NULL OR approved_by <> proposed_by', name=op.f('ck_approval_two_people')),
    sa.ForeignKeyConstraint(['approved_by'], ['user.id'], name=op.f('fk_approval_approved_by_user')),
    sa.ForeignKeyConstraint(['proposed_by'], ['user.id'], name=op.f('fk_approval_proposed_by_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approval'))
    )
    op.create_index(op.f('ix_approval_state'), 'approval', ['state'], unique=False)
    op.create_table('break_glass_request',
    sa.Column('requester_id', sa.UUID(), nullable=False),
    sa.Column('approver_id', sa.UUID(), nullable=True),
    sa.Column('scope', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('state', postgresql.ENUM('requested', 'approved', 'denied', 'expired', name='break_glass_state', create_type=False), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('approver_id IS NULL OR approver_id <> requester_id', name=op.f('ck_break_glass_request_two_admins')),
    sa.ForeignKeyConstraint(['approver_id'], ['user.id'], name=op.f('fk_break_glass_request_approver_id_user')),
    sa.ForeignKeyConstraint(['requester_id'], ['user.id'], name=op.f('fk_break_glass_request_requester_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_break_glass_request'))
    )
    op.create_table('collection',
    sa.Column('public_id', sa.String(length=32), nullable=False),
    sa.Column('kind', postgresql.ENUM('donor', 'series', 'project', 'thematic', name='collection_kind', create_type=False), nullable=False),
    sa.Column('title_ar', sa.Text(), nullable=False),
    sa.Column('title_en', sa.Text(), nullable=True),
    sa.Column('description_ar', sa.Text(), nullable=True),
    sa.Column('description_en', sa.Text(), nullable=True),
    sa.Column('cover_work_id', sa.UUID(), nullable=True),
    sa.Column('publish_state', postgresql.ENUM('draft', 'review', 'published', 'withdrawn', name='publish_state', create_type=False), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['cover_work_id'], ['work.id'], name=op.f('fk_collection_cover_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_collection'))
    )
    op.create_index(op.f('ix_collection_public_id'), 'collection', ['public_id'], unique=True)
    op.create_table('glossary_term',
    sa.Column('source_form', sa.Text(), nullable=False),
    sa.Column('source_language', sa.String(length=3), nullable=False),
    sa.Column('target_forms', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('context_note', sa.Text(), nullable=True),
    sa.Column('vocabulary_term_id', sa.UUID(), nullable=True),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], name=op.f('fk_glossary_term_agent_id_agent')),
    sa.ForeignKeyConstraint(['approved_by'], ['user.id'], name=op.f('fk_glossary_term_approved_by_user')),
    sa.ForeignKeyConstraint(['vocabulary_term_id'], ['vocabulary_term.id'], name=op.f('fk_glossary_term_vocabulary_term_id_vocabulary_term')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_glossary_term'))
    )
    op.create_index(op.f('ix_glossary_term_source_form'), 'glossary_term', ['source_form'], unique=False)
    op.create_table('item',
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('shelfmark', sa.Text(), nullable=True),
    sa.Column('condition', sa.Text(), nullable=True),
    sa.Column('provenance', sa.Text(), nullable=True),
    sa.Column('donor_agent_id', sa.UUID(), nullable=True),
    sa.Column('digitization_status', postgresql.ENUM('not_started', 'in_progress', 'done', name='digitization_status', create_type=False), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['donor_agent_id'], ['agent.id'], name=op.f('fk_item_donor_agent_id_agent')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_item_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_item'))
    )
    op.create_index(op.f('ix_item_work_id'), 'item', ['work_id'], unique=False)
    op.create_table('payment',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('gateway', sa.String(length=32), nullable=False),
    sa.Column('gateway_reference', sa.String(length=128), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=3), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('duration', sa.String(length=8), nullable=False),
    sa.Column('status', postgresql.ENUM('initiated', 'succeeded', 'failed', 'refunded', name='payment_status', create_type=False), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_payment_user_id_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_payment_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment')),
    sa.UniqueConstraint('gateway_reference', name=op.f('uq_payment_gateway_reference'))
    )
    op.create_index(op.f('ix_payment_user_id'), 'payment', ['user_id'], unique=False)
    op.create_index(op.f('ix_payment_work_id'), 'payment', ['work_id'], unique=False)
    op.create_table('record_change',
    sa.Column('entity_kind', sa.String(length=32), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('field', sa.String(length=64), nullable=False),
    sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('changed_by', sa.UUID(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['user.id'], name=op.f('fk_record_change_changed_by_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_record_change'))
    )
    op.create_index(op.f('ix_record_change_entity_id'), 'record_change', ['entity_id'], unique=False)
    op.create_index(op.f('ix_record_change_entity_kind'), 'record_change', ['entity_kind'], unique=False)
    op.create_table('verification_case',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('document_type', sa.String(length=32), nullable=False),
    sa.Column('document_keys', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('affiliation', sa.Text(), nullable=True),
    sa.Column('state', postgresql.ENUM('submitted', 'in_review', 'approved', 'rejected', name='verification_case_state', create_type=False), nullable=False),
    sa.Column('decided_by', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('delete_documents_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('documents_deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['decided_by'], ['user.id'], name=op.f('fk_verification_case_decided_by_user')),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_verification_case_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_verification_case'))
    )
    op.create_index(op.f('ix_verification_case_user_id'), 'verification_case', ['user_id'], unique=False)
    op.create_table('work_agent',
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('role', postgresql.ENUM('author', 'editor', 'translator', 'scribe', 'commentator', 'printer', 'publisher', 'donor', name='agent_role', create_type=False), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], name=op.f('fk_work_agent_agent_id_agent'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_work_agent_work_id_work'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('work_id', 'agent_id', 'role', name=op.f('pk_work_agent'))
    )
    op.create_table('work_term',
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('term_id', sa.UUID(), nullable=False),
    sa.Column('facet', postgresql.ENUM('subject', 'place', 'period', 'theme', 'material', name='term_facet', create_type=False), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['vocabulary_term.id'], name=op.f('fk_work_term_term_id_vocabulary_term'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_work_term_work_id_work'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('work_id', 'term_id', 'facet', name=op.f('pk_work_term'))
    )
    op.create_index('ix_work_term_term_id', 'work_term', ['term_id'], unique=False)
    op.create_table('collection_work',
    sa.Column('collection_id', sa.UUID(), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['collection_id'], ['collection.id'], name=op.f('fk_collection_work_collection_id_collection'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_collection_work_work_id_work'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('collection_id', 'work_id', name=op.f('pk_collection_work'))
    )
    op.create_table('digital_object',
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=True),
    sa.Column('mets_key', sa.Text(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=False),
    sa.Column('state', postgresql.ENUM('draft', 'processing', 'ready', 'frozen', name='digital_object_state', create_type=False), nullable=False),
    sa.Column('fixity_status', postgresql.ENUM('unchecked', 'ok', 'mismatch', name='fixity_status', create_type=False), nullable=False),
    sa.Column('last_fixity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('frozen_reason', sa.Text(), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['item_id'], ['item.id'], name=op.f('fk_digital_object_item_id_item')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_digital_object_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_digital_object'))
    )
    op.create_index(op.f('ix_digital_object_state'), 'digital_object', ['state'], unique=False)
    op.create_index(op.f('ix_digital_object_work_id'), 'digital_object', ['work_id'], unique=False)
    op.create_table('grant',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('institution_id', sa.UUID(), nullable=True),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('device_limit', sa.Integer(), nullable=False),
    sa.Column('page_from', sa.Integer(), nullable=True),
    sa.Column('page_to', sa.Integer(), nullable=True),
    sa.Column('source', postgresql.ENUM('request', 'payment', 'license', 'staff', name='grant_source', create_type=False), nullable=False),
    sa.Column('print_quota', sa.Integer(), nullable=False),
    sa.Column('print_used', sa.Integer(), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by', sa.UUID(), nullable=True),
    sa.Column('revoke_reason', sa.Text(), nullable=True),
    sa.Column('access_request_id', sa.UUID(), nullable=True),
    sa.Column('payment_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('(page_from IS NULL AND page_to IS NULL) OR (page_from >= 1 AND page_to >= page_from)', name=op.f('ck_grant_page_range_valid')),
    sa.CheckConstraint('device_limit >= 1', name=op.f('ck_grant_device_limit_positive')),
    sa.CheckConstraint('ends_at > starts_at', name=op.f('ck_grant_ends_after_starts')),
    sa.CheckConstraint('user_id IS NOT NULL OR institution_id IS NOT NULL', name=op.f('ck_grant_has_holder')),
    sa.ForeignKeyConstraint(['access_request_id'], ['access_request.id'], name=op.f('fk_grant_access_request_id_access_request')),
    sa.ForeignKeyConstraint(['institution_id'], ['institution.id'], name=op.f('fk_grant_institution_id_institution')),
    sa.ForeignKeyConstraint(['payment_id'], ['payment.id'], name=op.f('fk_grant_payment_id_payment')),
    sa.ForeignKeyConstraint(['revoked_by'], ['user.id'], name=op.f('fk_grant_revoked_by_user')),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_grant_user_id_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_grant_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_grant'))
    )
    op.create_index(op.f('ix_grant_institution_id'), 'grant', ['institution_id'], unique=False)
    op.create_index(op.f('ix_grant_revoked'), 'grant', ['revoked'], unique=False)
    op.create_index(op.f('ix_grant_user_id'), 'grant', ['user_id'], unique=False)
    op.create_index(op.f('ix_grant_work_id'), 'grant', ['work_id'], unique=False)
    op.create_table('incident',
    sa.Column('kind', postgresql.ENUM('fixity_mismatch', 'rate_limit_abuse', 'policy_engine_error', name='incident_kind', create_type=False), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('digital_object_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('state', postgresql.ENUM('open', 'resolved', name='incident_state', create_type=False), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['digital_object_id'], ['digital_object.id'], name=op.f('fk_incident_digital_object_id_digital_object')),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_incident_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_incident'))
    )
    op.create_table('intake_batch',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=True),
    sa.Column('item_id', sa.UUID(), nullable=True),
    sa.Column('digital_object_id', sa.UUID(), nullable=True),
    sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('staging_prefix', sa.Text(), nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=False),
    sa.Column('state', postgresql.ENUM('received', 'validating', 'failed', 'ingested', name='intake_state', create_type=False), nullable=False),
    sa.Column('submitted_by', sa.UUID(), nullable=True),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['digital_object_id'], ['digital_object.id'], name=op.f('fk_intake_batch_digital_object_id_digital_object')),
    sa.ForeignKeyConstraint(['item_id'], ['item.id'], name=op.f('fk_intake_batch_item_id_item')),
    sa.ForeignKeyConstraint(['submitted_by'], ['user.id'], name=op.f('fk_intake_batch_submitted_by_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_intake_batch_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intake_batch'))
    )
    op.create_index(op.f('ix_intake_batch_state'), 'intake_batch', ['state'], unique=False)
    op.create_index(op.f('ix_intake_batch_code'), 'intake_batch', ['code'], unique=True)
    op.create_index(op.f('ix_intake_batch_work_id'), 'intake_batch', ['work_id'], unique=False)
    op.create_table('page',
    sa.Column('digital_object_id', sa.UUID(), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=64), nullable=True),
    sa.Column('folio', sa.String(length=64), nullable=True),
    sa.Column('page_type', postgresql.ENUM('cover', 'title', 'blank', 'text', 'illustration', 'map', 'table', 'colophon', 'endpaper', name='page_type', create_type=False), nullable=False),
    sa.Column('language', sa.String(length=3), nullable=True),
    sa.Column('script', sa.String(length=4), nullable=True),
    sa.Column('reading_direction', postgresql.ENUM('rtl', 'ltr', name='reading_direction', create_type=False), nullable=False),
    sa.Column('master_key', sa.Text(), nullable=True),
    sa.Column('derivative_key', sa.Text(), nullable=True),
    sa.Column('thumb_key', sa.Text(), nullable=True),
    sa.Column('sample_key', sa.Text(), nullable=True),
    sa.Column('width_px', sa.Integer(), nullable=True),
    sa.Column('height_px', sa.Integer(), nullable=True),
    sa.Column('capture_date', sa.Date(), nullable=True),
    sa.Column('capture_device', sa.Text(), nullable=True),
    sa.Column('color_target_ref', sa.Text(), nullable=True),
    sa.Column('condition_notes', sa.Text(), nullable=True),
    sa.Column('ocr_text', sa.Text(), nullable=True),
    sa.Column('alto_key', sa.Text(), nullable=True),
    sa.Column('offsets_key', sa.Text(), nullable=True),
    sa.Column('ocr_avg_confidence', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('ocr_min_confidence', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('ocr_engine', sa.String(length=64), nullable=True),
    sa.Column('ocr_engine_version', sa.String(length=64), nullable=True),
    sa.Column('ocr_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ocr_flagged', sa.Boolean(), nullable=False),
    sa.Column('correction_state', postgresql.ENUM('raw', 'corrected', 'verified', name='correction_state', create_type=False), nullable=False),
    sa.Column('section_title', sa.Text(), nullable=True),
    sa.Column('toc_entry', sa.Text(), nullable=True),
    sa.Column('running_head', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('master_sha256', sa.String(length=64), nullable=True),
    sa.Column('derivative_sha256', sa.String(length=64), nullable=True),
    sa.Column('last_fixity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['digital_object_id'], ['digital_object.id'], name=op.f('fk_page_digital_object_id_digital_object'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_page_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_page')),
    sa.UniqueConstraint('digital_object_id', 'seq', name='digital_object_seq')
    )
    op.create_index(op.f('ix_page_digital_object_id'), 'page', ['digital_object_id'], unique=False)
    op.create_index(op.f('ix_page_work_id'), 'page', ['work_id'], unique=False)
    op.create_table('reader_session',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('grant_id', sa.UUID(), nullable=True),
    sa.Column('device_hash', sa.String(length=64), nullable=False),
    sa.Column('forensic_key_encrypted', sa.LargeBinary(), nullable=False),
    sa.Column('state', postgresql.ENUM('active', 'expired', 'revoked', 'suspended', name='reader_session_state', create_type=False), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('idle_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('hard_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('suspended_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['grant_id'], ['grant.id'], name=op.f('fk_reader_session_grant_id_grant')),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_reader_session_user_id_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_reader_session_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reader_session'))
    )
    op.create_index(op.f('ix_reader_session_grant_id'), 'reader_session', ['grant_id'], unique=False)
    op.create_index(op.f('ix_reader_session_user_id'), 'reader_session', ['user_id'], unique=False)
    op.create_index(op.f('ix_reader_session_work_id'), 'reader_session', ['work_id'], unique=False)
    op.create_table('content_object',
    sa.Column('public_id', sa.String(length=32), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('page_id', sa.UUID(), nullable=True),
    sa.Column('provenance_type', postgresql.ENUM('scan', 'ocr', 'transcription', 'translation', 'editorial', 'visualization', name='provenance_type', create_type=False), nullable=False),
    sa.Column('origin', postgresql.ENUM('human', 'ai', name='origin', create_type=False), nullable=False),
    sa.Column('language', sa.String(length=3), nullable=False),
    sa.Column('script', sa.String(length=4), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('reference_key', sa.Text(), nullable=True),
    sa.Column('segments', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('model', sa.String(length=128), nullable=True),
    sa.Column('model_version', sa.String(length=64), nullable=True),
    sa.Column('prompt_template_version', sa.String(length=64), nullable=True),
    sa.Column('glossary_version', sa.String(length=64), nullable=True),
    sa.Column('self_assessment', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('review_status', postgresql.ENUM('pending', 'in_review', 'approved', 'rejected', name='review_status', create_type=False), nullable=False),
    sa.Column('reviewer_id', sa.UUID(), nullable=True),
    sa.Column('reviewer_subject', sa.String(length=64), nullable=True),
    sa.Column('reviewer_name', sa.Text(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("origin <> 'ai' OR (model IS NOT NULL AND model_version IS NOT NULL)", name=op.f('ck_content_object_ai_objects_record_model')),
    sa.CheckConstraint("provenance_type <> 'ocr'", name=op.f('ck_content_object_ocr_is_page_text_not_content')),
    sa.ForeignKeyConstraint(['page_id'], ['page.id'], name=op.f('fk_content_object_page_id_page')),
    sa.ForeignKeyConstraint(['reviewer_id'], ['user.id'], name=op.f('fk_content_object_reviewer_id_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_content_object_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_object'))
    )
    op.create_index(op.f('ix_content_object_origin'), 'content_object', ['origin'], unique=False)
    op.create_index(op.f('ix_content_object_public_id'), 'content_object', ['public_id'], unique=True)
    op.create_index(op.f('ix_content_object_page_id'), 'content_object', ['page_id'], unique=False)
    op.create_index(op.f('ix_content_object_provenance_type'), 'content_object', ['provenance_type'], unique=False)
    op.create_index(op.f('ix_content_object_review_status'), 'content_object', ['review_status'], unique=False)
    op.create_index(op.f('ix_content_object_work_id'), 'content_object', ['work_id'], unique=False)
    op.create_table('page_embedding',
    sa.Column('page_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('embedding', Vector(), nullable=False),
    sa.Column('dimensions', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=128), nullable=False),
    sa.Column('model_version', sa.String(length=64), nullable=False),
    sa.Column('chunk_hash', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['page_id'], ['page.id'], name=op.f('fk_page_embedding_page_id_page'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_page_embedding')),
    sa.UniqueConstraint('page_id', 'chunk_index', 'model', 'model_version', name='chunk')
    )
    op.create_index(op.f('ix_page_embedding_page_id'), 'page_embedding', ['page_id'], unique=False)
    op.create_table('premis_event',
    sa.Column('digital_object_id', sa.UUID(), nullable=False),
    sa.Column('page_id', sa.UUID(), nullable=True),
    sa.Column('event_type', postgresql.ENUM('ingest', 'fixity_check', 'derivative_generation', 'access_class_change', 'withdrawal', name='premis_event_type', create_type=False), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('agent', sa.Text(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['digital_object_id'], ['digital_object.id'], name=op.f('fk_premis_event_digital_object_id_digital_object')),
    sa.ForeignKeyConstraint(['page_id'], ['page.id'], name=op.f('fk_premis_event_page_id_page')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_premis_event'))
    )
    op.create_index(op.f('ix_premis_event_digital_object_id'), 'premis_event', ['digital_object_id'], unique=False)
    op.create_table('print_job',
    sa.Column('reader_session_id', sa.UUID(), nullable=True),
    sa.Column('grant_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('pages', postgresql.ARRAY(sa.Integer()), nullable=False),
    sa.Column('rendered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('export_key', sa.Text(), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=True),
    sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['grant_id'], ['grant.id'], name=op.f('fk_print_job_grant_id_grant')),
    sa.ForeignKeyConstraint(['reader_session_id'], ['reader_session.id'], name=op.f('fk_print_job_reader_session_id_reader_session')),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_print_job_user_id_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_print_job_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_print_job'))
    )
    op.create_index(op.f('ix_print_job_grant_id'), 'print_job', ['grant_id'], unique=False)
    op.create_index(op.f('ix_print_job_user_id'), 'print_job', ['user_id'], unique=False)
    op.create_index(op.f('ix_print_job_work_id'), 'print_job', ['work_id'], unique=False)
    op.create_table('review_task',
    sa.Column('content_object_id', sa.UUID(), nullable=False),
    sa.Column('work_id', sa.UUID(), nullable=False),
    sa.Column('state', postgresql.ENUM('pending', 'in_review', 'approved', 'rejected', name='review_status', create_type=False), nullable=False),
    sa.Column('assignee_id', sa.UUID(), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('reviewer_note', sa.Text(), nullable=True),
    sa.Column('edit_diff', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('decided_by', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['assignee_id'], ['user.id'], name=op.f('fk_review_task_assignee_id_user')),
    sa.ForeignKeyConstraint(['content_object_id'], ['content_object.id'], name=op.f('fk_review_task_content_object_id_content_object')),
    sa.ForeignKeyConstraint(['decided_by'], ['user.id'], name=op.f('fk_review_task_decided_by_user')),
    sa.ForeignKeyConstraint(['work_id'], ['work.id'], name=op.f('fk_review_task_work_id_work')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_review_task'))
    )
    op.create_index(op.f('ix_review_task_assignee_id'), 'review_task', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_review_task_content_object_id'), 'review_task', ['content_object_id'], unique=False)
    op.create_index(op.f('ix_review_task_state'), 'review_task', ['state'], unique=False)
    op.create_index(op.f('ix_review_task_work_id'), 'review_task', ['work_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_review_task_work_id'), table_name='review_task')
    op.drop_index(op.f('ix_review_task_state'), table_name='review_task')
    op.drop_index(op.f('ix_review_task_content_object_id'), table_name='review_task')
    op.drop_index(op.f('ix_review_task_assignee_id'), table_name='review_task')
    op.drop_table('review_task')
    op.drop_index(op.f('ix_print_job_work_id'), table_name='print_job')
    op.drop_index(op.f('ix_print_job_user_id'), table_name='print_job')
    op.drop_index(op.f('ix_print_job_grant_id'), table_name='print_job')
    op.drop_table('print_job')
    op.drop_index(op.f('ix_premis_event_digital_object_id'), table_name='premis_event')
    op.drop_table('premis_event')
    op.drop_index(op.f('ix_page_embedding_page_id'), table_name='page_embedding')
    op.drop_table('page_embedding')
    op.drop_index(op.f('ix_content_object_work_id'), table_name='content_object')
    op.drop_index(op.f('ix_content_object_review_status'), table_name='content_object')
    op.drop_index(op.f('ix_content_object_provenance_type'), table_name='content_object')
    op.drop_index(op.f('ix_content_object_page_id'), table_name='content_object')
    op.drop_index(op.f('ix_content_object_origin'), table_name='content_object')
    op.drop_index(op.f('ix_content_object_public_id'), table_name='content_object')
    op.drop_table('content_object')
    op.drop_index(op.f('ix_reader_session_work_id'), table_name='reader_session')
    op.drop_index(op.f('ix_reader_session_user_id'), table_name='reader_session')
    op.drop_index(op.f('ix_reader_session_grant_id'), table_name='reader_session')
    op.drop_table('reader_session')
    op.drop_index(op.f('ix_page_work_id'), table_name='page')
    op.drop_index(op.f('ix_page_digital_object_id'), table_name='page')
    op.drop_table('page')
    op.drop_index(op.f('ix_intake_batch_work_id'), table_name='intake_batch')
    op.drop_index(op.f('ix_intake_batch_state'), table_name='intake_batch')
    op.drop_index(op.f('ix_intake_batch_code'), table_name='intake_batch')
    op.drop_table('intake_batch')
    op.drop_table('incident')
    op.drop_index(op.f('ix_grant_work_id'), table_name='grant')
    op.drop_index(op.f('ix_grant_user_id'), table_name='grant')
    op.drop_index(op.f('ix_grant_revoked'), table_name='grant')
    op.drop_index(op.f('ix_grant_institution_id'), table_name='grant')
    op.drop_table('grant')
    op.drop_index(op.f('ix_digital_object_work_id'), table_name='digital_object')
    op.drop_index(op.f('ix_digital_object_state'), table_name='digital_object')
    op.drop_table('digital_object')
    op.drop_table('collection_work')
    op.drop_index('ix_work_term_term_id', table_name='work_term')
    op.drop_table('work_term')
    op.drop_table('work_agent')
    op.drop_index(op.f('ix_verification_case_user_id'), table_name='verification_case')
    op.drop_table('verification_case')
    op.drop_index(op.f('ix_record_change_entity_kind'), table_name='record_change')
    op.drop_index(op.f('ix_record_change_entity_id'), table_name='record_change')
    op.drop_table('record_change')
    op.drop_index(op.f('ix_payment_work_id'), table_name='payment')
    op.drop_index(op.f('ix_payment_user_id'), table_name='payment')
    op.drop_table('payment')
    op.drop_index(op.f('ix_item_work_id'), table_name='item')
    op.drop_table('item')
    op.drop_index(op.f('ix_glossary_term_source_form'), table_name='glossary_term')
    op.drop_table('glossary_term')
    op.drop_index(op.f('ix_collection_public_id'), table_name='collection')
    op.drop_table('collection')
    op.drop_table('break_glass_request')
    op.drop_index(op.f('ix_approval_state'), table_name='approval')
    op.drop_table('approval')
    op.drop_index(op.f('ix_access_request_work_id'), table_name='access_request')
    op.drop_index(op.f('ix_access_request_state'), table_name='access_request')
    op.drop_index(op.f('ix_access_request_requester_id'), table_name='access_request')
    op.drop_table('access_request')
    op.drop_index(op.f('ix_work_publish_state'), table_name='work')
    op.drop_index(op.f('ix_work_public_id'), table_name='work')
    op.drop_index(op.f('ix_work_access_class'), table_name='work')
    op.drop_table('work')
    op.drop_index(op.f('ix_user_keycloak_sub'), table_name='user')
    op.drop_index(op.f('ix_user_institution_id'), table_name='user')
    op.drop_table('user')
    op.drop_index(op.f('ix_institution_license_institution_id'), table_name='institution_license')
    op.drop_table('institution_license')
    op.drop_index(op.f('ix_vocabulary_term_facet'), table_name='vocabulary_term')
    op.drop_table('vocabulary_term')
    op.drop_table('institution')
    op.drop_index(op.f('ix_audit_event_resource_kind'), table_name='audit_event')
    op.drop_index(op.f('ix_audit_event_resource_id'), table_name='audit_event')
    op.drop_index(op.f('ix_audit_event_request_id'), table_name='audit_event')
    op.drop_index(op.f('ix_audit_event_occurred_at'), table_name='audit_event')
    op.drop_index(op.f('ix_audit_event_actor_id'), table_name='audit_event')
    op.drop_index(op.f('ix_audit_event_action'), table_name='audit_event')
    op.drop_table('audit_event')
    op.drop_index(op.f('ix_agent_public_id'), table_name='agent')
    op.drop_table('agent')
    for name in reversed(list(ENUMS)):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
