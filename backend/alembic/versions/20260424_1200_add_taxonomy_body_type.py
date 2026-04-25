"""add body type to inventory taxonomy cache

Revision ID: 20260424_1200
Revises: 20260410_1500
Create Date: 2026-04-24 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_1200"
down_revision = "20260410_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicle_taxonomy_cache", sa.Column("body_type", sa.String(length=40), nullable=True))
    op.create_index("ix_vehicle_taxonomy_cache_body_type", "vehicle_taxonomy_cache", ["body_type"])


def downgrade() -> None:
    op.drop_index("ix_vehicle_taxonomy_cache_body_type", table_name="vehicle_taxonomy_cache")
    op.drop_column("vehicle_taxonomy_cache", "body_type")
