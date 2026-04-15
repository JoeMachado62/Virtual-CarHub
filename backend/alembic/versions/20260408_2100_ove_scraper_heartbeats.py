"""OVE scraper heartbeats table

Revision ID: 20260408_2100
Revises: 20260407_1200
Create Date: 2026-04-08 21:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260408_2100"
down_revision: Union[str, None] = "20260407_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ove_scraper_heartbeats",
        sa.Column("worker_id", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("profile", sa.String(length=120), nullable=True),
        sa.Column("scraper_version", sa.String(length=80), nullable=True),
        sa.Column("node_id", sa.String(length=120), nullable=True),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_claim_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_claims", sa.Integer(), nullable=True),
        sa.Column("status_note", sa.String(length=255), nullable=True),
        sa.Column(
            "details_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_ove_scraper_heartbeats_last_heartbeat_at",
        "ove_scraper_heartbeats",
        ["last_heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ove_scraper_heartbeats_last_heartbeat_at",
        table_name="ove_scraper_heartbeats",
    )
    op.drop_table("ove_scraper_heartbeats")
