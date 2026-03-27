"""Add evox_vif_cache and evox_color_cache tables

Revision ID: 20260327_1200
Revises: 20260316_1200
Create Date: 2026-03-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260327_1200'
down_revision: Union[str, None] = '20260316_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'evox_vif_cache',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('vifnum', sa.Integer(), nullable=False),
        sa.Column('orgnum', sa.Integer(), nullable=True),
        sa.Column('sendnum', sa.Integer(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('make', sa.String(80), nullable=False),
        sa.Column('model', sa.String(120), nullable=False),
        sa.Column('trim', sa.String(120), nullable=False, server_default=''),
        sa.Column('doors', sa.Integer(), nullable=True),
        sa.Column('body', sa.String(40), nullable=True),
        sa.Column('cab', sa.String(40), nullable=True),
        sa.Column('wheels', sa.String(20), nullable=True),
        sa.Column('vin_photographed', sa.String(17), nullable=True),
        sa.Column('date_delivered', sa.String(20), nullable=True),
        sa.Column('has_btl', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_colors', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_stills', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_exterior', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_interior', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_hdspin', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_ext_color', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('vifnum', name='uq_evox_vif_cache_vifnum'),
    )
    op.create_index('ix_evox_vif_cache_vifnum', 'evox_vif_cache', ['vifnum'])
    op.create_index('ix_evox_vif_cache_year', 'evox_vif_cache', ['year'])
    op.create_index('ix_evox_vif_cache_make', 'evox_vif_cache', ['make'])
    op.create_index('ix_evox_vif_cache_model', 'evox_vif_cache', ['model'])
    op.create_index('ix_evox_vif_cache_trim', 'evox_vif_cache', ['trim'])
    op.create_index('ix_evox_vif_cache_body', 'evox_vif_cache', ['body'])
    op.create_index('ix_evox_vif_cache_active', 'evox_vif_cache', ['active'])
    op.create_index('ix_evox_vif_cache_ymmt', 'evox_vif_cache', ['year', 'make', 'model', 'trim'])

    op.create_table(
        'evox_color_cache',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('vifnum', sa.Integer(), nullable=False),
        sa.Column('color_code', sa.String(40), nullable=False),
        sa.Column('color_title', sa.String(120), nullable=False),
        sa.Column('color_simpletitle', sa.String(60), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('vifnum', 'color_code', name='uq_evox_color_cache_vif_code'),
    )
    op.create_index('ix_evox_color_cache_vifnum', 'evox_color_cache', ['vifnum'])
    op.create_index('ix_evox_color_cache_color_simpletitle', 'evox_color_cache', ['color_simpletitle'])
    op.create_index('ix_evox_color_cache_vif_simple', 'evox_color_cache', ['vifnum', 'color_simpletitle'])


def downgrade() -> None:
    op.drop_table('evox_color_cache')
    op.drop_table('evox_vif_cache')
