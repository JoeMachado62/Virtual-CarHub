"""v7 X-Service-Token authentication layer.

Per Doc 2 §2.2: every /v1/agent-actions/* and /v1/admin-actions/* request
requires an X-Service-Token header. Tokens are per-agent, scoped, stored as
argon2 hashes in agent_service_tokens table.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

_ph = PasswordHasher()


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def hash_token(raw_token: str) -> str:
    """Hash a plaintext service token with argon2."""
    return _ph.hash(raw_token)


def verify_token(token_hash: str, raw_token: str) -> bool:
    """Verify a plaintext token against an argon2 hash."""
    try:
        return _ph.verify(token_hash, raw_token)
    except VerifyMismatchError:
        return False


def generate_raw_token() -> str:
    """Generate a cryptographically random 32-byte URL-safe token."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Agent context (attached to request after auth)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AgentContext:
    """Resolved identity of the authenticated agent."""
    agent_id: str
    token_id: str  # UUID from agent_service_tokens.id
    scopes: list[str]

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


# ---------------------------------------------------------------------------
# Token lookup (DB query)
# ---------------------------------------------------------------------------

def _lookup_token(db: Session, raw_token: str) -> AgentContext | None:
    """Look up a raw token against all non-revoked rows in agent_service_tokens.

    We fetch all non-revoked hashes and verify against each. This is safe
    because the expected row count is small (5 agents at launch). If the
    table grows, add a token-prefix index.
    """
    rows = db.execute(
        text(
            "SELECT id, agent_id, token_hash, scopes "
            "FROM agent_service_tokens "
            "WHERE revoked_at IS NULL"
        )
    ).fetchall()

    for row in rows:
        if verify_token(row.token_hash, raw_token):
            return AgentContext(
                agent_id=row.agent_id,
                token_id=str(row.id),
                scopes=list(row.scopes),
            )
    return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_agent_context(
    x_service_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AgentContext:
    """FastAPI dependency: extracts X-Service-Token, validates, returns AgentContext.

    Use as: agent = Depends(get_agent_context)
    Returns 401 for missing/invalid token.
    """
    if not x_service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Service-Token header",
        )

    ctx = _lookup_token(db, x_service_token)
    if ctx is None:
        logger.warning("service_token_auth_failed token_prefix=%s", x_service_token[:8])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )

    logger.debug("service_token_auth_ok agent_id=%s", ctx.agent_id)
    return ctx


def require_scope(required_scope: str):
    """Factory: returns a FastAPI dependency that enforces a specific scope.

    Usage:
        @router.post("/v1/agent-actions/send-message",
                      dependencies=[Depends(require_scope("agent_actions.send_message"))])
        async def send_message(agent: AgentContext = Depends(get_agent_context), ...):
            ...

    Or as a standalone dependency:
        agent = Depends(require_scope("agent_actions.send_message"))
    """
    def _check(agent: AgentContext = Depends(get_agent_context)) -> AgentContext:
        if not agent.has_scope(required_scope):
            logger.warning(
                "scope_denied agent_id=%s required=%s available=%s",
                agent.agent_id,
                required_scope,
                agent.scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scope: requires '{required_scope}'",
            )
        return agent
    return _check
