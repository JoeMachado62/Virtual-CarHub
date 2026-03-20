import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.responses import ok
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.integrations import GHLClient
from app.models.entities import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest

logger = logging.getLogger("vch.auth")

router = APIRouter()


def _create_ghl_contact(user: User) -> str | None:
    """Create a GoHighLevel contact for a newly registered user.

    Returns the GHL contact ID or None if creation fails / GHL is disabled.
    """
    if not settings.has_ghl:
        return None

    ghl = GHLClient(
        api_key=settings.ghl_api_key,
        api_base_url=settings.ghl_api_base_url,
        api_version=settings.ghl_api_version,
        live=settings.has_ghl,
    )
    payload = {
        "firstName": user.first_name or "Buyer",
        "lastName": user.last_name or "Contact",
        "email": user.email,
        "phone": user.phone,
        "locationId": settings.ghl_location_id,
        "tags": ["virtual_carhub", "buyer_portal", "self_registered"],
        "source": "Virtual-CarHub Garage Registration",
    }
    try:
        response = ghl.create_contact(payload)
        contact = response.get("contact", response)
        return contact.get("id")
    except Exception as exc:
        logger.warning("ghl_registration_contact_failed", extra={"email": user.email, "error": str(exc)})
        try:
            search = ghl.search_contacts(location_id=settings.ghl_location_id, query=user.email)
            contacts = search.get("contacts", [])
            if contacts:
                return contacts[0].get("id")
        except Exception:
            pass
    return None


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Fire-and-forget GHL contact creation (non-blocking for the user)
    ghl_contact_id = _create_ghl_contact(user)

    return ok(
        {
            "user_id": user.id,
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
            "ghl_contact_id": ghl_contact_id,
            "is_new_user": True,
        }
    )


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return ok(
        {
            "user_id": user.id,
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }
    )


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    token_data = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
    user_id = token_data.get("sub")
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return ok(
        {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }
    )
