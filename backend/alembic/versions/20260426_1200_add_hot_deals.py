"""add hot deals

Revision ID: 20260426_1200
Revises: 20260424_1200
Create Date: 2026-04-26 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_1200"
down_revision = "20260424_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hot_deals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vin", sa.String(length=17), nullable=False),
        sa.Column("source_platform", sa.String(length=40), nullable=False),
        sa.Column("source_list_name", sa.String(length=120), nullable=False),
        sa.Column("batch_id", sa.String(length=160), nullable=False),
        sa.Column("snapshot_mode", sa.String(length=30), nullable=False),
        sa.Column("listing_id", sa.String(length=120), nullable=True),
        sa.Column("listing_url", sa.String(length=1200), nullable=True),
        sa.Column("auction_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auction_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mmr_value", sa.Float(), nullable=False),
        sa.Column("asking_price", sa.Float(), nullable=False),
        sa.Column("deal_delta", sa.Float(), nullable=False),
        sa.Column("deal_delta_pct", sa.Float(), nullable=True),
        sa.Column("deal_label", sa.String(length=40), nullable=False),
        sa.Column("deal_rank", sa.Integer(), nullable=False),
        sa.Column("cr_screen_status", sa.String(length=40), nullable=False),
        sa.Column("cr_screen_reasons", sa.JSON(), nullable=True),
        sa.Column("marketing_title", sa.String(length=255), nullable=True),
        sa.Column("marketing_summary", sa.Text(), nullable=True),
        sa.Column("hero_image_url", sa.String(length=1200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("featured_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vin"], ["vehicles.vin"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hot_deals_vin", "hot_deals", ["vin"])
    op.create_index("ix_hot_deals_batch_id", "hot_deals", ["batch_id"])
    op.create_index("ix_hot_deals_source_list_name", "hot_deals", ["source_list_name"])
    op.create_index("ix_hot_deals_source_platform", "hot_deals", ["source_platform"])
    op.create_index("ix_hot_deals_listing_id", "hot_deals", ["listing_id"])
    op.create_index("ix_hot_deals_auction_start_at", "hot_deals", ["auction_start_at"])
    op.create_index("ix_hot_deals_auction_end_at", "hot_deals", ["auction_end_at"])
    op.create_index("ix_hot_deals_deal_delta", "hot_deals", ["deal_delta"])
    op.create_index("ix_hot_deals_deal_label", "hot_deals", ["deal_label"])
    op.create_index("ix_hot_deals_deal_rank", "hot_deals", ["deal_rank"])
    op.create_index("ix_hot_deals_cr_screen_status", "hot_deals", ["cr_screen_status"])
    op.create_index("ix_hot_deals_is_active", "hot_deals", ["is_active"])
    op.create_index("ix_hot_deals_featured_until", "hot_deals", ["featured_until"])
    op.create_index("ix_hot_deals_expires_at", "hot_deals", ["expires_at"])
    op.create_index("ix_hot_deals_active_expires", "hot_deals", ["is_active", "expires_at"])
    op.create_index("ix_hot_deals_active_rank_delta", "hot_deals", ["is_active", "deal_rank", "deal_delta"])
    op.create_index(
        "uq_hot_deals_active_vin",
        "hot_deals",
        ["vin"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_hot_deals_active_vin", table_name="hot_deals")
    op.drop_index("ix_hot_deals_active_rank_delta", table_name="hot_deals")
    op.drop_index("ix_hot_deals_active_expires", table_name="hot_deals")
    op.drop_index("ix_hot_deals_expires_at", table_name="hot_deals")
    op.drop_index("ix_hot_deals_featured_until", table_name="hot_deals")
    op.drop_index("ix_hot_deals_is_active", table_name="hot_deals")
    op.drop_index("ix_hot_deals_cr_screen_status", table_name="hot_deals")
    op.drop_index("ix_hot_deals_deal_rank", table_name="hot_deals")
    op.drop_index("ix_hot_deals_deal_label", table_name="hot_deals")
    op.drop_index("ix_hot_deals_deal_delta", table_name="hot_deals")
    op.drop_index("ix_hot_deals_auction_end_at", table_name="hot_deals")
    op.drop_index("ix_hot_deals_auction_start_at", table_name="hot_deals")
    op.drop_index("ix_hot_deals_listing_id", table_name="hot_deals")
    op.drop_index("ix_hot_deals_source_platform", table_name="hot_deals")
    op.drop_index("ix_hot_deals_source_list_name", table_name="hot_deals")
    op.drop_index("ix_hot_deals_batch_id", table_name="hot_deals")
    op.drop_index("ix_hot_deals_vin", table_name="hot_deals")
    op.drop_table("hot_deals")
