"""Add ghl_contact_id to users.

Revision ID: 20260410_1500
Revises: 20260409_1400
Create Date: 2026-04-10 15:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260410_1500"
down_revision: Union[str, None] = "20260409_1400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ghl_contact_id", sa.String(length=80), nullable=True))
    op.create_index("ix_users_ghl_contact_id", "users", ["ghl_contact_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_ghl_contact_id", table_name="users")
    op.drop_column("users", "ghl_contact_id")
