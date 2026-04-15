"""Add public_slug to vehicles and backfill from VIN.

Adds a deterministic, HMAC-derived short slug so public URLs, SEO
metadata, and sitemap entries can reference vehicles without leaking
the full VIN (specifically the last six production-sequence digits).

Revision ID: 20260409_1400
Revises: 20260408_2100
Create Date: 2026-04-09 14:00:00.000000
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260409_1400"
down_revision: Union[str, None] = "20260408_2100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SLUG_LENGTH = 12


def _compute_slug(vin: str, secret: str) -> str:
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=vin.strip().upper().encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b32encode(digest).decode("ascii").rstrip("=").lower()[:SLUG_LENGTH]


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("public_slug", sa.String(length=16), nullable=True),
    )

    # Backfill existing rows using the same HMAC secret the runtime uses.
    # We read it directly from the environment so migrations stay
    # decoupled from the app settings module.
    secret = os.environ.get("JWT_SECRET_KEY", "dev-secret")
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT vin FROM vehicles WHERE public_slug IS NULL")).fetchall()
    for (vin,) in rows:
        if not vin:
            continue
        slug = _compute_slug(vin, secret)
        bind.execute(
            sa.text("UPDATE vehicles SET public_slug = :slug WHERE vin = :vin"),
            {"slug": slug, "vin": vin},
        )

    op.create_index(
        "ix_vehicles_public_slug",
        "vehicles",
        ["public_slug"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_vehicles_public_slug", table_name="vehicles")
    op.drop_column("vehicles", "public_slug")
