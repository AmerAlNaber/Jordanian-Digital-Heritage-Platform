"""Phone verification and the sign-in behind each reader session (ACC-1, SEC-5).

Revision ID: 0005
Revises: 0004

- ``user.phone_number`` and ``user.phone_verified_at``: the verified number and when (ACC-1).
- ``phone_verification``: the one pending code of a user, hashed, with its expiry, attempt
  count and sending window. Row-level security confines rows to their owner and the system
  context; the application role is granted the table because the schema-wide grant of 0002
  predates it.
- ``reader_session.sid``: the identity provider's session id the reader was opened under, so
  ending a sign-in ends its readers within the cache window (SEC-5).

Reverse: drops the table, the columns and the index.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "jdhp_app"
OWNER_OR_SYSTEM = "app_is_system() OR user_id = app_user_id()"


def upgrade() -> None:
    op.add_column("user", sa.Column("phone_number", sa.Text(), nullable=True))
    op.add_column(
        "user", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("reader_session", sa.Column("sid", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_reader_session_sid"), "reader_session", ["sid"], unique=False)
    op.create_table(
        "phone_verification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("phone_number", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sends_in_window", sa.Integer(), server_default="1", nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_phone_verification_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phone_verification")),
        sa.UniqueConstraint("user_id", name=op.f("uq_phone_verification_user_id")),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON phone_verification TO {APP_ROLE}")
    op.execute("ALTER TABLE phone_verification ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE phone_verification FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY phone_verification_read ON phone_verification AS PERMISSIVE FOR SELECT "
        f"TO PUBLIC USING ({OWNER_OR_SYSTEM})"
    )
    op.execute(
        "CREATE POLICY phone_verification_write ON phone_verification AS PERMISSIVE FOR ALL "
        f"TO PUBLIC USING ({OWNER_OR_SYSTEM}) WITH CHECK ({OWNER_OR_SYSTEM})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS phone_verification_write ON phone_verification")
    op.execute("DROP POLICY IF EXISTS phone_verification_read ON phone_verification")
    op.drop_table("phone_verification")
    op.drop_index(op.f("ix_reader_session_sid"), table_name="reader_session")
    op.drop_column("reader_session", "sid")
    op.drop_column("user", "phone_verified_at")
    op.drop_column("user", "phone_number")
