"""add market comparison cache

Revision ID: 20260502_1200
Revises: 20260426_1200
Create Date: 2026-05-02 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260502_1200"
down_revision = "20260426_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicle_market_comparison_cache",
        sa.Column("vin", sa.String(length=17), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vin"], ["vehicles.vin"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("vin"),
    )
    op.create_index(
        "ix_vehicle_market_comparison_cache_generated_at",
        "vehicle_market_comparison_cache",
        ["generated_at"],
    )
    op.create_index(
        "ix_vehicle_market_comparison_cache_expires_at",
        "vehicle_market_comparison_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_market_comparison_cache_expires_at",
        table_name="vehicle_market_comparison_cache",
    )
    op.drop_index(
        "ix_vehicle_market_comparison_cache_generated_at",
        table_name="vehicle_market_comparison_cache",
    )
    op.drop_table("vehicle_market_comparison_cache")
