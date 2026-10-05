"""Print jobs: public names, state, error detail and the download token expiry (RDR-4, SEC-15).

Revision ID: 0004
Revises: 0003

- ``public_id``: an opaque name so the API never exposes a row id (INT-7).
- ``state``: queued, ready, downloaded or failed; the quota counts every job but the failed.
- ``token_expires_at``: the single-use download link lives fifteen minutes (SEC-15).
- The worker role may update print jobs: it renders them.

Reverse: drops the columns, the index and the enum; revokes the worker's update privilege.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from jdhp_api.core.ids import mint_name

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRINT_STATES = ("queued", "ready", "downloaded", "failed")
WORKER_ROLE = "jdhp_worker"


def upgrade() -> None:
    postgresql.ENUM(*PRINT_STATES, name="print_job_state").create(op.get_bind(), checkfirst=True)
    connection = op.get_bind()
    op.add_column("print_job", sa.Column("public_id", sa.String(length=32), nullable=True))
    rows = connection.execute(sa.text("SELECT id FROM print_job WHERE public_id IS NULL")).fetchall()
    for (row_id,) in rows:
        connection.execute(
            sa.text("UPDATE print_job SET public_id = :name WHERE id = :id"),
            {"name": mint_name("p8"), "id": row_id},
        )
    op.alter_column("print_job", "public_id", nullable=False)
    op.create_index(op.f("ix_print_job_public_id"), "print_job", ["public_id"], unique=True)
    op.add_column(
        "print_job",
        sa.Column(
            "state",
            postgresql.ENUM(*PRINT_STATES, name="print_job_state", create_type=False),
            nullable=False,
            server_default="queued",
        ),
    )
    op.add_column("print_job", sa.Column("error_detail", sa.Text(), nullable=True))
    op.add_column(
        "print_job", sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(op.f("ix_print_job_state"), "print_job", ["state"], unique=False)
    op.execute(f"GRANT UPDATE ON print_job TO {WORKER_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE ON print_job FROM {WORKER_ROLE}")
    op.drop_index(op.f("ix_print_job_state"), table_name="print_job")
    op.drop_column("print_job", "token_expires_at")
    op.drop_column("print_job", "error_detail")
    op.drop_column("print_job", "state")
    op.drop_index(op.f("ix_print_job_public_id"), table_name="print_job")
    op.drop_column("print_job", "public_id")
    postgresql.ENUM(name="print_job_state").drop(op.get_bind(), checkfirst=True)
