"""Canary endpoint: authenticated healthcheck for v7 agent service tokens."""

from fastapi import APIRouter, Depends

from app.auth.service_token import AgentContext, get_agent_context

router = APIRouter()


@router.get("/healthcheck-authenticated")
def healthcheck_authenticated(
    agent: AgentContext = Depends(get_agent_context),
):
    """Returns 200 if the caller presents a valid, non-revoked service token.

    No scope requirement — any valid agent token works. This is the canary
    endpoint for verifying the X-Service-Token auth layer is operational.
    """
    return {
        "status": "ok",
        "agent_id": agent.agent_id,
        "scopes": agent.scopes,
    }
