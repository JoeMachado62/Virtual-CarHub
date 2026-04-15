from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class TokenType:
    ACCESS = "access"
    REFRESH = "refresh"
    RESET = "reset"
    EMAIL_LOGIN = "email_login"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.jwt_access_expire_minutes),
    )


def create_refresh_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.jwt_refresh_expire_days),
    )


def create_reset_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type=TokenType.RESET,
        expires_delta=timedelta(minutes=settings.password_reset_expire_minutes),
    )


def create_email_login_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_type=TokenType.EMAIL_LOGIN,
        expires_delta=timedelta(minutes=settings.email_login_expire_minutes),
    )


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc

    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unexpected token type",
        )
    return payload
