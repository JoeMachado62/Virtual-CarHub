"""OVE detail request lease queue

Revision ID: 20260407_1200
Revises: 20260406_1915
Create Date: 2026-04-07 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260407_1200"
down_revision: Union[str, None] = "20260406_1915"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # The status column is a Postgres native enum type. Add the two new
        # values BEFORE any code that might insert/update them runs.
        # ALTER TYPE ... ADD VALUE cannot run inside a transaction block,
        # so we use AUTOCOMMIT for these statements.
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE ovedetailrequeststatus ADD VALUE IF NOT EXISTS 'CLAIMED'"
            )
            op.execute(
                "ALTER TYPE ovedetailrequeststatus ADD VALUE IF NOT EXISTS 'TERMINAL'"
            )

    with op.batch_alter_table("ove_detail_requests") as batch_op:
        batch_op.add_column(sa.Column("leased_to", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_error_category", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("terminal_reason", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("terminal_message", sa.Text(), nullable=True))

    op.create_index(
        "ix_ove_detail_requests_leased_to",
        "ove_detail_requests",
        ["leased_to"],
    )
    op.create_index(
        "ix_ove_detail_requests_lease_expires_at",
        "ove_detail_requests",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_ove_detail_requests_next_retry_at",
        "ove_detail_requests",
        ["next_retry_at"],
    )
    # Composite index that supports the claim hot path:
    # eligible-by-status, ordered by priority desc / requested_at asc.
    op.create_index(
        "ix_ove_detail_requests_claim_lookup",
        "ove_detail_requests",
        ["status", "priority", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ove_detail_requests_claim_lookup", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_next_retry_at", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_lease_expires_at", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_leased_to", table_name="ove_detail_requests")

    with op.batch_alter_table("ove_detail_requests") as batch_op:
        batch_op.drop_column("terminal_message")
        batch_op.drop_column("terminal_reason")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("last_error_category")
        batch_op.drop_column("last_error")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("claimed_at")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("leased_to")
