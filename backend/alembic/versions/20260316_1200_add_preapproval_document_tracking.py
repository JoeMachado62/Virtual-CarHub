"""Add preapproval and document tracking fields

Revision ID: 20260316_1200
Revises: 20260310_1400
Create Date: 2026-03-16 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260316_1200'
down_revision: Union[str, None] = '20260310_1400'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add preapproval fields to users table
    op.add_column('users', sa.Column('is_preapproved', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('preapproved_amount', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('preapproved_until', sa.DateTime(timezone=True), nullable=True))

    # Add document tracking fields to deals table
    op.add_column('deals', sa.Column('documents_collected', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('deals', sa.Column('preapproval_letter_url', sa.String(length=500), nullable=True))
    op.add_column('deals', sa.Column('loan_documents_url', sa.String(length=500), nullable=True))
    op.add_column('deals', sa.Column('identity_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('deals', sa.Column('income_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('deals', sa.Column('external_financing_bank', sa.String(length=120), nullable=True))
    op.add_column('deals', sa.Column('external_financing_status', sa.String(length=50), nullable=True))


def downgrade() -> None:
    # Remove document tracking fields from deals table
    op.drop_column('deals', 'external_financing_status')
    op.drop_column('deals', 'external_financing_bank')
    op.drop_column('deals', 'income_verified')
    op.drop_column('deals', 'identity_verified')
    op.drop_column('deals', 'loan_documents_url')
    op.drop_column('deals', 'preapproval_letter_url')
    op.drop_column('deals', 'documents_collected')

    # Remove preapproval fields from users table
    op.drop_column('users', 'preapproved_until')
    op.drop_column('users', 'preapproved_amount')
    op.drop_column('users', 'is_preapproved')