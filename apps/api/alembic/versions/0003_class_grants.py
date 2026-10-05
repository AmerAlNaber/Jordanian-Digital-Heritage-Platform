"""Class grants and public names for grants and reader sessions (Phase 1, ACS-2, INT-7).

Revision ID: 0003
Revises: 0002

- Adds the ``access_class`` grant source: the grant a signed-in member receives on opening a
  Registered (or Open) work, which carries the device limit and the print quota that the
  reader and the print service enforce.
- Gives grants and reader sessions an opaque public name, so the API never exposes a row id.

Reverse: drops the two columns. PostgreSQL cannot drop an enum value; it stays, unused.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from jdhp_api.core.ids import mint_name

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMED_TABLES = (("grant", "g8"), ("reader_session", "s8"))


def upgrade() -> None:
    op.execute("ALTER TYPE grant_source ADD VALUE IF NOT EXISTS 'access_class'")
    connection = op.get_bind()
    for table, shoulder in NAMED_TABLES:
        op.add_column(table, sa.Column("public_id", sa.String(length=32), nullable=True))
        rows = connection.execute(
            sa.text(f'SELECT id FROM "{table}" WHERE public_id IS NULL')  # noqa: S608  # nosec B608  # constant table names
        ).fetchall()
        for (row_id,) in rows:
            connection.execute(
                sa.text(f'UPDATE "{table}" SET public_id = :name WHERE id = :id'),  # noqa: S608  # nosec B608
                {"name": mint_name(shoulder), "id": row_id},
            )
        op.alter_column(table, "public_id", nullable=False)
        op.create_index(op.f(f"ix_{table}_public_id"), table, ["public_id"], unique=True)


def downgrade() -> None:
    for table, _shoulder in NAMED_TABLES:
        op.drop_index(op.f(f"ix_{table}_public_id"), table_name=table)
        op.drop_column(table, "public_id")
