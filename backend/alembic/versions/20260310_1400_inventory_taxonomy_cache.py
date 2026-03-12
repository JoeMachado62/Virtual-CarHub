"""inventory taxonomy cache

Revision ID: 20260310_1400
Revises: 20260308_1200
Create Date: 2026-03-10 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260310_1400"
down_revision: Union[str, None] = "20260308_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicle_taxonomy_cache",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("make", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("trim", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("year", "make", "model", "trim", name="uq_vehicle_taxonomy_cache_ymmt"),
    )
    op.create_index("ix_vehicle_taxonomy_cache_source", "vehicle_taxonomy_cache", ["source"])
    op.create_index("ix_vehicle_taxonomy_cache_year", "vehicle_taxonomy_cache", ["year"])
    op.create_index("ix_vehicle_taxonomy_cache_make", "vehicle_taxonomy_cache", ["make"])
    op.create_index("ix_vehicle_taxonomy_cache_model", "vehicle_taxonomy_cache", ["model"])
    op.create_index("ix_vehicle_taxonomy_cache_trim", "vehicle_taxonomy_cache", ["trim"])
    op.create_index("ix_vehicle_taxonomy_cache_active", "vehicle_taxonomy_cache", ["active"])
    op.create_index("ix_vehicle_taxonomy_cache_last_synced_at", "vehicle_taxonomy_cache", ["last_synced_at"])


def downgrade() -> None:
    op.drop_index("ix_vehicle_taxonomy_cache_last_synced_at", table_name="vehicle_taxonomy_cache")
    op.drop_index("ix_vehicle_taxonomy_cache_active", table_name="vehicle_taxonomy_cache")
    op.drop_index("ix_vehicle_taxonomy_cache_trim", table_name="vehicle_taxonomy_cache")
    op.drop_index("ix_vehicle_taxonomy_cache_model", table_name="vehicle_taxonomy_cache")
    op.drop_index("ix_vehicle_taxonomy_cache_make", table_name="vehicle_taxonomy_cache")
    op.drop_index("ix_vehicle_taxonomy_cache_year", table_name="vehicle_taxonomy_cache")
    op.drop_index("ix_vehicle_taxonomy_cache_source", table_name="vehicle_taxonomy_cache")
    op.drop_table("vehicle_taxonomy_cache")
