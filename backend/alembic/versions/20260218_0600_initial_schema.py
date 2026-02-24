"""Initial schema

Revision ID: 20260218_0600
Revises:
Create Date: 2026-02-18 06:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.models import *  # noqa: F401,F403

# revision identifiers, used by Alembic.
revision: str = "20260218_0600"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
