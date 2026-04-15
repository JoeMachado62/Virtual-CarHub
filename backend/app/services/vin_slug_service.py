"""Deterministic public-facing slug derived from a VIN.

The slug replaces the VIN in public URLs and SEO metadata so that the
last six digits of a VIN (the production sequence) are never exposed to
the general public. Backend operations continue to use the raw VIN
internally; the slug is purely a surface-layer identifier.

Properties:
- Deterministic: the same VIN always produces the same slug, so URLs
  are stable across deploys and safe to index/link.
- Keyed: derived via HMAC-SHA256 using ``settings.jwt_secret_key`` so
  slugs cannot be reversed or predicted without access to the backend
  secret. (Not cryptographically critical — just enough to prevent
  casual enumeration.)
- Short + URL-safe: 12 base32 characters, lowercase, no padding.
- Collision-resistant: 12 base32 chars ≈ 60 bits of entropy, which is
  well beyond the collision risk for a single-tenant inventory.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from app.core.config import settings

SLUG_LENGTH = 12


def compute_public_slug(vin: str) -> str:
    """Return the deterministic 12-char slug for a VIN."""
    if not vin:
        raise ValueError("VIN is required to compute a public slug")
    normalized = vin.strip().upper()
    digest = hmac.new(
        key=settings.jwt_secret_key.encode("utf-8"),
        msg=normalized.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    # base32 → URL-safe, case-insensitive, no padding
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return encoded[:SLUG_LENGTH]


def looks_like_slug(identifier: str) -> bool:
    """Heuristic: treat anything that is not a 17-char VIN as a slug."""
    if not identifier:
        return False
    return len(identifier.strip()) != 17


def resolve_vehicle_identifier(db, identifier: str):
    """Look up a Vehicle by either its raw VIN or its public slug.

    Public URLs only ever expose the slug, but legacy/bookmarked URLs,
    internal admin tools, and backend service calls all still hit the
    same endpoints with a raw VIN. This resolver lets every route
    accept either form transparently.
    """
    # Local import to avoid a circular dependency at module import time.
    from sqlalchemy import select

    from app.models.entities import Vehicle

    if not identifier:
        return None
    normalized = identifier.strip()
    if len(normalized) == 17:
        vehicle = db.get(Vehicle, normalized.upper())
        if vehicle:
            return vehicle
    # Slugs are lowercase base32; normalize for a forgiving match.
    return db.scalar(select(Vehicle).where(Vehicle.public_slug == normalized.lower()))
