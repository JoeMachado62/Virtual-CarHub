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
    create_reset_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.integrations import GHLClient
from app.models.entities import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    EmailLoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
)

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
    if ghl_contact_id and user.ghl_contact_id != ghl_contact_id:
        user.ghl_contact_id = ghl_contact_id
        db.commit()
        db.refresh(user)

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


@router.post("/email-login")
def email_login(payload: EmailLoginRequest, db: Session = Depends(get_db)) -> dict:
    token_data = decode_token(payload.token, expected_type=TokenType.EMAIL_LOGIN)
    user_id = token_data.get("sub")
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return ok(
        {
            "user_id": user.id,
            "email": user.email,
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }
    )


def _send_reset_email(to_email: str, reset_url: str, first_name: str | None) -> None:
    """Send a password-reset email via SendGrid. Fails silently with a log warning."""
    if not settings.has_sendgrid:
        logger.warning("sendgrid_not_configured — password reset email not sent to %s", to_email)
        return

    greeting = f"Hi {first_name}" if first_name else "Hi"
    html_body = f"""\
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
  <h2 style="color:#1a1a2e;">Reset Your Password</h2>
  <p>{greeting},</p>
  <p>We received a request to reset the password for your Virtual CarHub account.</p>
  <p>Click the button below to set a new password. This link expires in {settings.password_reset_expire_minutes} minutes.</p>
  <p style="text-align:center;margin:28px 0;">
    <a href="{reset_url}" style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:600;">
      Reset Password
    </a>
  </p>
  <p style="font-size:13px;color:#666;">If you didn&rsquo;t request this, you can safely ignore this email.</p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="font-size:12px;color:#999;">Virtual CarHub &mdash; Your personal vehicle marketplace</p>
</div>"""

    text_body = (
        f"{greeting},\n\n"
        "We received a request to reset your Virtual CarHub password.\n\n"
        f"Reset your password here (expires in {settings.password_reset_expire_minutes} minutes):\n"
        f"{reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email.\n\n"
        "— Virtual CarHub"
    )

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Content, Email, Mail, To

        sg = SendGridAPIClient(settings.sendgrid_api_key)
        from_email = Email(settings.sendgrid_from_email, settings.sendgrid_from_name)
        to = To(to_email)
        mail = Mail(from_email=from_email, to_emails=to, subject="Reset your Virtual CarHub password")
        mail.add_content(Content("text/plain", text_body))
        mail.add_content(Content("text/html", html_body))
        response = sg.send(mail)
        logger.info("password_reset_email_sent to=%s status=%s", to_email, response.status_code)
    except Exception as exc:
        logger.warning("password_reset_email_failed to=%s error=%s", to_email, str(exc))


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    # Always return success to avoid email enumeration
    user = db.scalar(select(User).where(User.email == payload.email))
    if user:
        token = create_reset_token(user.id)
        reset_url = f"{settings.public_web_base_url}/reset-password?token={token}"
        _send_reset_email(user.email, reset_url, user.first_name)

    return ok({"message": "If an account with that email exists, a password reset link has been sent."})


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    token_data = decode_token(payload.token, expected_type=TokenType.RESET)
    user_id = token_data.get("sub")
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    return ok({"message": "Your password has been reset successfully. You can now sign in with your new password."})
