"""OVE backend support

Revision ID: 20260308_1200
Revises: 20260227_1500
Create Date: 2026-03-08 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260308_1200"
down_revision: Union[str, None] = "20260227_1500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ove_vehicle_details",
        sa.Column("vin", sa.String(length=17), sa.ForeignKey("vehicles.vin", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_platform", sa.String(length=18), nullable=False),
        sa.Column("seller_comments", sa.Text(), nullable=True),
        sa.Column("images_json", sa.JSON(), nullable=False),
        sa.Column("condition_report_json", sa.JSON(), nullable=False),
        sa.Column("listing_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("sync_metadata_json", sa.JSON(), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("page_url", sa.String(length=1200), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ove_vehicle_details_last_synced_at", "ove_vehicle_details", ["last_synced_at"])
    op.create_index("ix_ove_vehicle_details_source_platform", "ove_vehicle_details", ["source_platform"])

    op.create_table(
        "ove_detail_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("vin", sa.String(length=17), nullable=False),
        sa.Column("source_platform", sa.String(length=18), nullable=False),
        sa.Column("status", sa.String(length=11), nullable=False),
        sa.Column("requested_by", sa.String(length=80), nullable=False),
        sa.Column("request_source", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ove_detail_requests_vin", "ove_detail_requests", ["vin"])
    op.create_index("ix_ove_detail_requests_status", "ove_detail_requests", ["status"])
    op.create_index("ix_ove_detail_requests_source_platform", "ove_detail_requests", ["source_platform"])
    op.create_index("ix_ove_detail_requests_priority", "ove_detail_requests", ["priority"])
    op.create_index("ix_ove_detail_requests_requested_at", "ove_detail_requests", ["requested_at"])
    op.create_index("ix_ove_detail_requests_last_polled_at", "ove_detail_requests", ["last_polled_at"])
    op.create_index("ix_ove_detail_requests_fulfilled_at", "ove_detail_requests", ["fulfilled_at"])
    op.create_index("ix_ove_detail_requests_detail_received_at", "ove_detail_requests", ["detail_received_at"])


def downgrade() -> None:
    op.drop_index("ix_ove_detail_requests_detail_received_at", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_fulfilled_at", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_last_polled_at", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_requested_at", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_priority", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_source_platform", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_status", table_name="ove_detail_requests")
    op.drop_index("ix_ove_detail_requests_vin", table_name="ove_detail_requests")
    op.drop_table("ove_detail_requests")

    op.drop_index("ix_ove_vehicle_details_source_platform", table_name="ove_vehicle_details")
    op.drop_index("ix_ove_vehicle_details_last_synced_at", table_name="ove_vehicle_details")
    op.drop_table("ove_vehicle_details")
