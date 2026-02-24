import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import TokenType, decode_token
from app.db.session import get_db
from app.models.entities import Deal, User
from app.services.deal_service import get_or_create_active_deal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = db.scalar(select(User).where(User.id == subject))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
    return user


def get_current_deal(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Deal:
    return get_or_create_active_deal(db, current_user.id)


def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
    if x_service_token != settings.service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )


def _verify_hmac_signature(secret: str, payload: bytes, signature: str) -> bool:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    provided = signature.replace("sha256=", "").strip()
    return hmac.compare_digest(digest, provided)


async def require_ghl_webhook_auth(
    request: Request,
    x_service_token: str | None = Header(default=None),
    x_ghl_signature: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
) -> None:
    secret = settings.ghl_webhook_secret
    if secret:
        signature = x_ghl_signature or x_webhook_signature
        if not signature:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature")
        body = await request.body()
        if not _verify_hmac_signature(secret=secret, payload=body, signature=signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
        return

    require_service_token(x_service_token=x_service_token)


async def require_docusign_webhook_auth(
    x_service_token: str | None = Header(default=None),
    x_docusign_signature_1: str | None = Header(default=None),
) -> None:
    if settings.docusign_secret_key and not x_docusign_signature_1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing DocuSign signature")
    if settings.docusign_secret_key:
        return
    require_service_token(x_service_token=x_service_token)


async def require_telnyx_webhook_auth(
    x_service_token: str | None = Header(default=None),
    telnyx_signature_ed25519: str | None = Header(default=None),
) -> None:
    if settings.telnyx_api_key and not telnyx_signature_ed25519:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telnyx signature")
    if settings.telnyx_api_key:
        return
    require_service_token(x_service_token=x_service_token)
