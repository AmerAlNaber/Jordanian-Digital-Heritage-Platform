"""Security controls in the schema: roles, grants, row-level security and invariants.

Revision ID: 0002
Revises: 0001

- Database roles: jdhp_app (API), jdhp_worker (pipeline) with least privilege (SEC-7, D17).
- Row-level security on every table that holds personal or grant data (SEC-7).
- Audit log is append-only (SEC-25).
- AI content objects are created pending and only the review portal approves them (REV-1).
- Hash chain columns and the helper functions the policies use.

Reverse: downgrade() drops the policies, triggers, functions and grants. Roles are kept
because other databases on the cluster may use them; drop them by hand if needed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "jdhp_app"
WORKER_ROLE = "jdhp_worker"

RLS_TABLES = (
    "user",
    "institution_license",
    "verification_case",
    "access_request",
    "grant",
    "payment",
    "reader_session",
    "print_job",
)

# Tables the pipeline writes. Everything else is read-only for the worker (ADR-0001 D17).
WORKER_WRITE_TABLES = (
    "intake_batch",
    "digital_object",
    "page",
    "premis_event",
    "incident",
    "page_embedding",
    "content_object",
    "review_task",
    "record_change",
    "work",
    "item",
)

HELPER_FUNCTIONS = ("""
CREATE OR REPLACE FUNCTION app_roles() RETURNS text[] LANGUAGE sql STABLE AS $$
  SELECT string_to_array(coalesce(nullif(current_setting('app.roles', true), ''), 'anonymous'), ',')
$$
""", """
CREATE OR REPLACE FUNCTION app_has_role(role_name text) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT role_name = ANY (app_roles())
$$
""", """
CREATE OR REPLACE FUNCTION app_has_any_role(VARIADIC role_names text[]) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT app_roles() && role_names
$$
""", """
CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.user_id', true), '')::uuid
$$
""", """
CREATE OR REPLACE FUNCTION app_institution_id() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.institution_id', true), '')::uuid
$$
""", """
CREATE OR REPLACE FUNCTION app_is_system() RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT app_has_role('system')
$$
""")

AUDIT_APPEND_ONLY = ("""
CREATE OR REPLACE FUNCTION audit_event_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_event is append-only (SEC-25)' USING ERRCODE = 'insufficient_privilege';
END
$$
""", """
CREATE TRIGGER audit_event_no_update_delete
  BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION audit_event_append_only()
""")

REVIEW_GUARD = ("""
CREATE OR REPLACE FUNCTION content_object_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.origin = 'ai' AND NEW.review_status <> 'pending' THEN
      RAISE EXCEPTION 'objects with origin ai are created pending (REV-1)'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.origin = 'ai'
     AND NEW.review_status = 'approved'
     AND OLD.review_status IS DISTINCT FROM 'approved'
     AND NOT (coalesce(current_setting('app.review_action', true), '') = 'approve'
              AND app_has_role('reviewer')) THEN
    RAISE EXCEPTION 'only the review portal action by a Reviewer approves an ai object (REV-1)'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END
$$
""", """
CREATE TRIGGER content_object_review_guard
  BEFORE INSERT OR UPDATE ON content_object
  FOR EACH ROW EXECUTE FUNCTION content_object_review_guard()
""")


def _policy(table: str, name: str, command: str, using: str, check: str | None = None) -> str:
    """INSERT policies take only WITH CHECK; every other command takes USING and optionally WITH CHECK."""
    clauses = "" if command == "INSERT" else f" USING ({using})"
    if check:
        clauses += f" WITH CHECK ({check})"
    return f'CREATE POLICY {name} ON "{table}" AS PERMISSIVE FOR {command} TO PUBLIC{clauses}'


RLS_POLICIES: dict[str, list[tuple[str, str, str, str | None]]] = {
    "user": [
        ("user_read", "SELECT", "app_is_system() OR app_has_any_role('platform_admin', 'rights_officer') OR id = app_user_id() OR (app_has_role('institution_admin') AND institution_id IS NOT NULL AND institution_id = app_institution_id())", None),
        ("user_write", "INSERT", "true", "app_is_system() OR app_has_role('platform_admin')"),
        ("user_update", "UPDATE", "app_is_system() OR app_has_role('platform_admin') OR id = app_user_id()", "app_is_system() OR app_has_role('platform_admin') OR id = app_user_id()"),
    ],
    "institution_license": [
        ("license_read", "SELECT", "app_is_system() OR app_has_any_role('platform_admin', 'rights_officer') OR (app_has_any_role('institution_admin', 'institutional_user') AND institution_id = app_institution_id())", None),
        ("license_write", "ALL", "app_is_system() OR app_has_any_role('platform_admin', 'rights_officer')", "app_is_system() OR app_has_any_role('platform_admin', 'rights_officer')"),
    ],
    "verification_case": [
        ("verification_read", "SELECT", "app_is_system() OR app_has_role('rights_officer') OR user_id = app_user_id()", None),
        ("verification_insert", "INSERT", "true", "app_is_system() OR user_id = app_user_id()"),
        ("verification_update", "UPDATE", "app_is_system() OR app_has_role('rights_officer')", "app_is_system() OR app_has_role('rights_officer')"),
    ],
    "access_request": [
        ("request_read", "SELECT", "app_is_system() OR app_has_any_role('rights_officer', 'platform_admin') OR requester_id = app_user_id()", None),
        ("request_insert", "INSERT", "true", "app_is_system() OR requester_id = app_user_id()"),
        ("request_update", "UPDATE", "app_is_system() OR app_has_role('rights_officer') OR requester_id = app_user_id()", "app_is_system() OR app_has_role('rights_officer') OR requester_id = app_user_id()"),
    ],
    "grant": [
        ("grant_read", "SELECT", "app_is_system() OR app_has_any_role('rights_officer', 'platform_admin') OR user_id = app_user_id() OR (app_has_role('institution_admin') AND institution_id IS NOT NULL AND institution_id = app_institution_id())", None),
        ("grant_write", "ALL", "app_is_system() OR app_has_role('rights_officer')", "app_is_system() OR app_has_role('rights_officer')"),
    ],
    "payment": [
        ("payment_read", "SELECT", "app_is_system() OR app_has_any_role('rights_officer', 'platform_admin') OR user_id = app_user_id()", None),
        ("payment_write", "ALL", "app_is_system()", "app_is_system()"),
    ],
    "reader_session": [
        ("session_read", "SELECT", "app_is_system() OR app_has_any_role('rights_officer', 'platform_admin') OR user_id = app_user_id()", None),
        ("session_write", "ALL", "app_is_system() OR user_id = app_user_id()", "app_is_system() OR user_id = app_user_id()"),
    ],
    "print_job": [
        ("print_read", "SELECT", "app_is_system() OR app_has_any_role('rights_officer', 'platform_admin') OR user_id = app_user_id()", None),
        ("print_write", "ALL", "app_is_system() OR user_id = app_user_id()", "app_is_system() OR user_id = app_user_id()"),
    ],
}


def upgrade() -> None:
    for statement in (*HELPER_FUNCTIONS, *AUDIT_APPEND_ONLY, *REVIEW_GUARD):
        op.execute(statement)

    # Roles exist cluster-wide; create them if the deployment's init script has not.
    for role in (APP_ROLE, WORKER_ROLE):
        op.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "  # nosec B608  # role names are constants
            f"CREATE ROLE {role} NOLOGIN NOBYPASSRLS; END IF; END $$;"
        )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}, {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}, {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {WORKER_ROLE}")
    for table in WORKER_WRITE_TABLES:
        op.execute(f'GRANT INSERT, UPDATE ON "{table}" TO {WORKER_ROLE}')
    op.execute(f"GRANT INSERT ON audit_event TO {WORKER_ROLE}")
    op.execute(f"GRANT DELETE ON page_embedding TO {WORKER_ROLE}")
    # The audit log is append-only for everyone, by privilege and by trigger.
    op.execute(f"REVOKE UPDATE, DELETE ON audit_event FROM {APP_ROLE}, {WORKER_ROLE}")
    op.execute(f"REVOKE DELETE ON content_object, page, work, digital_object FROM {WORKER_ROLE}")

    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        for name, command, using, check in RLS_POLICIES[table]:
            op.execute(_policy(table, name, command, using, check))


def downgrade() -> None:
    for table in RLS_TABLES:
        for name, _command, _using, _check in RLS_POLICIES[table]:
            op.execute(f'DROP POLICY IF EXISTS {name} ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}, {WORKER_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}, {WORKER_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}, {WORKER_ROLE}")
    op.execute("DROP TRIGGER IF EXISTS content_object_review_guard ON content_object")
    op.execute("DROP FUNCTION IF EXISTS content_object_review_guard()")
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_update_delete ON audit_event")
    op.execute("DROP FUNCTION IF EXISTS audit_event_append_only()")
    for fn in (
        "app_is_system()",
        "app_institution_id()",
        "app_user_id()",
        "app_has_any_role(text[])",
        "app_has_role(text)",
        "app_roles()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
