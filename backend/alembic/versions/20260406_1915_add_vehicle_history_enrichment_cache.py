"""Add vehicle_history_enrichments cache table

Revision ID: 20260406_1915
Revises: 20260327_1200
Create Date: 2026-04-06 19:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_1915"
down_revision: Union[str, None] = "20260327_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicle_history_enrichments",
        sa.Column("vin", sa.String(17), sa.ForeignKey("vehicles.vin", ondelete="CASCADE"), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False, server_default="marketcheck_history"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("source_listing_id", sa.String(120), nullable=True),
        sa.Column("source_url", sa.String(1200), nullable=True),
        sa.Column("seller_comments", sa.Text(), nullable=True),
        sa.Column("listing_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("history_entry_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("listing_payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vehicle_history_enrichments_provider", "vehicle_history_enrichments", ["provider"])
    op.create_index("ix_vehicle_history_enrichments_status", "vehicle_history_enrichments", ["status"])
    op.create_index("ix_vehicle_history_enrichments_source_listing_id", "vehicle_history_enrichments", ["source_listing_id"])
    op.create_index("ix_vehicle_history_enrichments_last_attempted_at", "vehicle_history_enrichments", ["last_attempted_at"])
    op.create_index("ix_vehicle_history_enrichments_last_enriched_at", "vehicle_history_enrichments", ["last_enriched_at"])


def downgrade() -> None:
    op.drop_index("ix_vehicle_history_enrichments_last_enriched_at", table_name="vehicle_history_enrichments")
    op.drop_index("ix_vehicle_history_enrichments_last_attempted_at", table_name="vehicle_history_enrichments")
    op.drop_index("ix_vehicle_history_enrichments_source_listing_id", table_name="vehicle_history_enrichments")
    op.drop_index("ix_vehicle_history_enrichments_status", table_name="vehicle_history_enrichments")
    op.drop_index("ix_vehicle_history_enrichments_provider", table_name="vehicle_history_enrichments")
    op.drop_table("vehicle_history_enrichments")
