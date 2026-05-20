"""v7 agent_actions router — /v1/agent-actions/*

The policy enforcement boundary. Every agent state-changing operation routes
through these endpoints. Per Doc 2 §2.3.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.service_token import AgentContext, get_agent_context, require_scope
from app.db.session import get_db
from app.schemas.agent_actions import (
    AddContactNoteRequest,
    AddContactNoteResponse,
    CreateOpportunityRequest,
    CreateOpportunityResponse,
    DealerOutreachRequest,
    DealerOutreachResponse,
    HitlEscalateRequest,
    HitlEscalateResponse,
    HitlResolveRequest,
    HitlResolveResponse,
    IntentThreadCreate,
    IntentThreadResponse,
    IntentThreadUpdate,
    LogInteractionRequest,
    LogInteractionResponse,
    RateLimitCheckResponse,
    ScheduleFollowupRequest,
    ScheduleFollowupResponse,
    SendMessageRequest,
    SendMessageResponse,
    StrategyReportRequest,
    StrategyReportResponse,
    UpdateContactFieldRequest,
    UpdateContactFieldResponse,
    UpdateOpportunityStageRequest,
    UpdateOpportunityStageResponse,
)
import httpx

from app.core.config import settings
from app.integrations import GHLClient, TelnyxClient
from app.services import rate_limit_service

GRAPHITI_URL = settings.graphiti_url

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Integration clients (reuse existing wrappers)
# ---------------------------------------------------------------------------

_ghl: GHLClient | None = None
_telnyx: TelnyxClient | None = None


def _get_ghl() -> GHLClient:
    global _ghl
    if _ghl is None:
        _ghl = GHLClient(
            api_key=settings.ghl_api_key,
            api_base_url=settings.ghl_api_base_url,
            api_version=settings.ghl_api_version,
            live=settings.has_ghl,
        )
    return _ghl


def _get_telnyx() -> TelnyxClient:
    global _telnyx
    if _telnyx is None:
        _telnyx = TelnyxClient(
            api_key=settings.telnyx_api_key,
            live=settings.has_telnyx,
        )
    return _telnyx


# ---------------------------------------------------------------------------
# Graphiti forwarding (fire-and-forget)
# ---------------------------------------------------------------------------

def _forward_to_graphiti(
    *,
    contact_id: str,
    content: str,
    agent_id: str,
    interaction_type: str,
    channel: str,
    trace_id: str,
) -> None:
    """Forward interaction to Graphiti on MC for knowledge graph enrichment.

    Fire-and-forget: failures are logged but never block the audit_log path.
    Graphiti returns 202 (async processing); entity extraction happens in
    background on MC via OpenAI.

    group_id convention per MC integration contract:
    - vch-buyer-{contact_id} for buyer interactions
    - vch-dealer-{dealer_id} for dealer interactions
    - vch-shared for fleet-wide observations
    """
    try:
        # Determine role_type: agent replies are "assistant", buyer/dealer
        # inbound is "user", system events are "system".
        if interaction_type == "inbound_message":
            role_type = "user"
            role = f"buyer-{contact_id}"
        elif interaction_type in ("call_summary", "meeting_note"):
            role_type = "system"
            role = "audit"
        else:
            role_type = "assistant"
            role = agent_id

        group_id = f"vch-buyer-{contact_id}"
        body = {
            "group_id": group_id,
            "messages": [{
                "content": content,
                "role_type": role_type,
                "role": role,
                "source_description": f"{channel} via {agent_id}",
                "name": trace_id,
            }],
        }

        with httpx.Client(timeout=5.0) as client:
            r = client.post(f"{GRAPHITI_URL}/messages", json=body)
            r.raise_for_status()
            logger.debug("graphiti_forward_ok contact=%s group=%s", contact_id, group_id)
    except Exception as exc:
        logger.warning("graphiti_forward_failed contact=%s error=%s", contact_id, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fields agents are allowed to update on contacts (Doc 2 §2.3.3).
ALLOWED_AGENT_UPDATABLE_FIELDS = {
    "buyer_intent_strength",
    "last_match_presented_at",
    "preferred_contact_method",
    "vehicle_preference_summary",
    "deal_stall_reason",
    "agent_disposition",
}

# Patterns that must NOT appear in outbound message bodies.
_SECRET_PATTERNS = [
    re.compile(r"(?i)x-service-token"),
    re.compile(r"10\.50\.0\.\d+"),          # WG internal IPs
    re.compile(r"(?i)token_hash"),
    re.compile(r"(?i)service_token\s*[:=]"),
]


def _resolve_trace_id(header_value: str | None) -> str:
    """Use caller-provided trace_id or generate one."""
    if header_value:
        return header_value
    return f"gen-{uuid.uuid4().hex[:16]}"


def _write_audit(
    db: Session,
    *,
    trace_id: str,
    agent_id: str,
    action_type: str,
    target_type: str | None = None,
    target_id: str | None = None,
    payload_redacted: dict | None = None,
    outcome: str,
    outcome_detail: str | None = None,
) -> str:
    """Insert into v7 audit_log table. Returns the audit_log row id."""
    row_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO audit_log "
            "(id, trace_id, agent_id, action_type, target_type, target_id, "
            " payload_redacted, outcome, outcome_detail) "
            "VALUES (:id, :trace_id, :agent_id, :action_type, :target_type, "
            " :target_id, :payload, :outcome, :outcome_detail)"
        ),
        {
            "id": row_id,
            "trace_id": trace_id,
            "agent_id": agent_id,
            "action_type": action_type,
            "target_type": target_type,
            "target_id": target_id,
            "payload": json.dumps(_redact_payload(payload_redacted or {})),
            "outcome": outcome,
            "outcome_detail": outcome_detail,
        },
    )
    return row_id


def _redact_payload(payload: dict) -> dict:
    """Strip secrets/PII patterns from audit payload."""
    s = json.dumps(payload)
    for pat in _SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    try:
        return json.loads(s)
    except Exception:
        return {"_redaction_error": True}


def _check_body_policy(body: str, channel: str) -> str | None:
    """Return rejection reason if body violates content policy, else None."""
    for pat in _SECRET_PATTERNS:
        if pat.search(body):
            return "policy_violation: body contains restricted content"
    if channel == "sms" and len(body) > 1600:
        return "body_too_long: SMS max 1600 chars"
    if channel == "email" and len(body) > 102400:
        return "body_too_long: email max 100KB"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# BATCH 1 — Foundational endpoints
# ═══════════════════════════════════════════════════════════════════════════

# --- Intent threads ---

@router.post("/intent-thread", response_model=IntentThreadResponse)
def create_intent_thread(
    payload: IntentThreadCreate,
    agent: AgentContext = Depends(require_scope("agent_actions.intent_thread.create")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)
    thread_id = str(uuid.uuid4())
    initial_status = "open"

    db.execute(
        text(
            "INSERT INTO intent_threads "
            "(id, contact_id, intent_code, status, context_payload, deal_id) "
            "VALUES (:id, :contact_id, :intent_code, :status, :ctx, :deal_id)"
        ),
        {
            "id": thread_id,
            "contact_id": payload.contact_id,
            "intent_code": payload.intent_code,
            "status": initial_status,
            "ctx": json.dumps(payload.context_payload) if payload.context_payload else None,
            "deal_id": payload.deal_id,
        },
    )

    audit_id = _write_audit(
        db,
        trace_id=trace_id,
        agent_id=agent.agent_id,
        action_type="intent_thread.create",
        target_type="intent_thread",
        target_id=thread_id,
        payload_redacted={"contact_id": payload.contact_id, "intent_code": payload.intent_code},
        outcome="success",
    )
    db.commit()

    return IntentThreadResponse(
        intent_thread_id=thread_id,
        status=initial_status,
        audit_log_id=audit_id,
    )


@router.patch("/intent-thread/{thread_id}", response_model=IntentThreadResponse)
def update_intent_thread(
    thread_id: str,
    payload: IntentThreadUpdate,
    agent: AgentContext = Depends(require_scope("agent_actions.intent_thread.update")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    row = db.execute(
        text("SELECT id, status FROM intent_threads WHERE id = :id"),
        {"id": thread_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Intent thread not found")

    updates = []
    params: dict = {"id": thread_id}

    if payload.status is not None:
        updates.append("status = :status")
        params["status"] = payload.status
        if payload.status in ("closed", "resolved", "abandoned"):
            updates.append("closed_at = NOW()")

    if payload.context_payload is not None:
        updates.append("context_payload = :ctx")
        params["ctx"] = json.dumps(payload.context_payload)

    if payload.resolution_summary is not None:
        updates.append("resolution_summary = :res")
        params["res"] = payload.resolution_summary

    updates.append("last_activity_at = NOW()")

    if updates:
        db.execute(
            text(f"UPDATE intent_threads SET {', '.join(updates)} WHERE id = :id"),
            params,
        )

    new_status = payload.status or row.status
    audit_id = _write_audit(
        db,
        trace_id=trace_id,
        agent_id=agent.agent_id,
        action_type="intent_thread.update",
        target_type="intent_thread",
        target_id=thread_id,
        payload_redacted={"new_status": new_status},
        outcome="success",
    )
    db.commit()

    return IntentThreadResponse(
        intent_thread_id=thread_id,
        status=new_status,
        audit_log_id=audit_id,
    )


# --- Log interaction ---

@router.post("/log-interaction", response_model=LogInteractionResponse)
def log_interaction(
    payload: LogInteractionRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.log_interaction")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    audit_id = _write_audit(
        db,
        trace_id=trace_id,
        agent_id=agent.agent_id,
        action_type="log_interaction",
        target_type="contact",
        target_id=payload.contact_id,
        payload_redacted={
            "interaction_type": payload.interaction_type,
            "channel": payload.channel,
            "sentiment": payload.sentiment,
            "key_entities": payload.key_entities[:5],  # cap for audit size
        },
        outcome="success",
    )
    db.commit()

    # Forward to Graphiti for knowledge graph enrichment (fire-and-forget).
    _forward_to_graphiti(
        contact_id=payload.contact_id,
        content=payload.content_summary,
        agent_id=agent.agent_id,
        interaction_type=payload.interaction_type,
        channel=payload.channel,
        trace_id=trace_id,
    )

    return LogInteractionResponse(audit_log_id=audit_id)


# --- HITL escalate ---

@router.post("/hitl-escalate", response_model=HitlEscalateResponse)
def hitl_escalate(
    payload: HitlEscalateRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.hitl_escalate")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)
    task_id = str(uuid.uuid4())

    db.execute(
        text(
            "INSERT INTO hitl_tasks "
            "(id, trace_id, agent_id, trigger_code, summary, context_payload, "
            " suggested_action, urgency, status, contact_id, deal_id, intent_thread_id) "
            "VALUES (:id, :trace_id, :agent_id, :trigger_code, :summary, :ctx, "
            " :suggested, :urgency, 'open', :contact_id, :deal_id, :thread_id)"
        ),
        {
            "id": task_id,
            "trace_id": trace_id,
            "agent_id": agent.agent_id,
            "trigger_code": payload.trigger_code,
            "summary": payload.summary,
            "ctx": json.dumps(payload.context_payload),
            "suggested": payload.suggested_action,
            "urgency": payload.urgency,
            "contact_id": payload.contact_id,
            "deal_id": payload.deal_id,
            "thread_id": payload.intent_thread_id,
        },
    )

    audit_id = _write_audit(
        db,
        trace_id=trace_id,
        agent_id=agent.agent_id,
        action_type="hitl_escalate",
        target_type="hitl_task",
        target_id=task_id,
        payload_redacted={
            "trigger_code": payload.trigger_code,
            "urgency": payload.urgency,
            "blocking": payload.blocking,
        },
        outcome="success",
    )
    db.commit()

    logger.info(
        "hitl_escalated task_id=%s trigger=%s urgency=%s agent=%s",
        task_id, payload.trigger_code, payload.urgency, agent.agent_id,
    )

    return HitlEscalateResponse(
        hitl_task_id=task_id,
        audit_log_id=audit_id,
    )


# --- HITL resolve ---

@router.post("/hitl-resolve", response_model=HitlResolveResponse)
def hitl_resolve(
    payload: HitlResolveRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.hitl_resolve")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    row = db.execute(
        text("SELECT id, status FROM hitl_tasks WHERE id = :id"),
        {"id": payload.hitl_task_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="HITL task not found")
    if row.status == "resolved":
        raise HTTPException(status_code=409, detail="HITL task already resolved")

    db.execute(
        text(
            "UPDATE hitl_tasks SET "
            "  status = 'resolved', "
            "  resolution_action = :action, "
            "  resolution_notes = :notes, "
            "  resolved_at = NOW(), "
            "  claimed_by = :resolved_by "
            "WHERE id = :id"
        ),
        {
            "id": payload.hitl_task_id,
            "action": payload.resolution_action,
            "notes": payload.resolution_notes,
            "resolved_by": payload.resolved_by,
        },
    )

    audit_id = _write_audit(
        db,
        trace_id=trace_id,
        agent_id=agent.agent_id,
        action_type="hitl_resolve",
        target_type="hitl_task",
        target_id=payload.hitl_task_id,
        payload_redacted={
            "resolution_action": payload.resolution_action,
            "resolved_by": payload.resolved_by,
        },
        outcome="success",
    )
    db.commit()

    return HitlResolveResponse(
        hitl_task_id=payload.hitl_task_id,
        audit_log_id=audit_id,
    )


# --- Rate limit check ---

@router.get("/rate-limit-check", response_model=RateLimitCheckResponse)
def rate_limit_check(
    contact_id: str = Query(...),
    channel: str = Query(...),
    action_type: str = Query(default="buyer"),
    agent: AgentContext = Depends(require_scope("agent_actions.rate_limit_check")),
):
    result = rate_limit_service.check(
        target_id=contact_id,
        channel=channel,
        context_type=action_type,
    )
    return RateLimitCheckResponse(
        allowed=result.allowed,
        reason=result.reason,
        next_allowed_at=result.next_allowed_at,
    )


# --- GHL Opportunity management (Doc 2 §2.3.4-2.3.5) ---

@router.post("/create-opportunity", response_model=CreateOpportunityResponse)
def create_opportunity(
    payload: CreateOpportunityRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.create_opportunity")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    # Dispatch to GHL via existing client.
    ghl = _get_ghl()
    ghl_payload: dict = {
        "pipelineId": payload.pipeline_id,
        "pipelineStageId": payload.stage_id,
        "contactId": payload.contact_id,
        "name": payload.name,
        "locationId": settings.ghl_location_id,
        "status": "open",
    }
    if payload.monetary_value is not None:
        ghl_payload["monetaryValue"] = payload.monetary_value

    try:
        result = ghl.create_opportunity(ghl_payload)
        opportunity_id = result.get("id", "") or f"ghl-{uuid.uuid4().hex[:8]}"
    except Exception as exc:
        logger.warning("create_opportunity_dispatch_error contact=%s error=%s", payload.contact_id, exc)
        opportunity_id = f"dispatch-error-{uuid.uuid4().hex[:8]}"

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="create_opportunity", target_type="opportunity",
        target_id=opportunity_id,
        payload_redacted={
            "contact_id": payload.contact_id,
            "pipeline_id": payload.pipeline_id,
            "stage_id": payload.stage_id,
            "name": payload.name,
        },
        outcome="success",
    )
    db.commit()

    return CreateOpportunityResponse(
        opportunity_id=opportunity_id,
        audit_log_id=audit_id,
    )


@router.post("/update-opportunity-stage", response_model=UpdateOpportunityStageResponse)
def update_opportunity_stage(
    payload: UpdateOpportunityStageRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.update_opportunity_stage")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    # Dispatch to GHL via existing client.
    try:
        ghl = _get_ghl()
        ghl.update_opportunity_stage(payload.opportunity_id, payload.new_stage_id)
    except Exception as exc:
        logger.warning("update_opportunity_stage_dispatch_error opp=%s error=%s",
                        payload.opportunity_id, exc)

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="update_opportunity_stage", target_type="opportunity",
        target_id=payload.opportunity_id,
        payload_redacted={
            "new_stage_id": payload.new_stage_id,
            "reason": payload.transition_reason,
        },
        outcome="success",
    )
    db.commit()

    return UpdateOpportunityStageResponse(
        opportunity_id=payload.opportunity_id,
        audit_log_id=audit_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# BATCH 2 — Buyer-side actions (Danny)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/send-message", response_model=SendMessageResponse)
def send_message(
    payload: SendMessageRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.send_message")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    # --- Content policy ---
    violation = _check_body_policy(payload.body, payload.channel)
    if violation:
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="send_message", target_type="contact",
            target_id=payload.contact_id,
            payload_redacted={"channel": payload.channel, "violation": violation},
            outcome="policy_rejected", outcome_detail=violation,
        )
        db.commit()
        return SendMessageResponse(
            status="rejected", audit_log_id=audit_id,
            reason="policy_violation", detail=violation,
        )

    # --- Rate limit ---
    context_type = payload.context.mode or "buyer"
    rl = rate_limit_service.check(
        target_id=payload.contact_id,
        channel=payload.channel,
        context_type=context_type,
    )
    if not rl.allowed:
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="send_message", target_type="contact",
            target_id=payload.contact_id,
            payload_redacted={"channel": payload.channel, "reason": rl.reason},
            outcome="rate_limited", outcome_detail=rl.reason,
        )
        db.commit()
        retry_seconds = None
        if rl.next_allowed_at:
            retry_seconds = max(0, int((rl.next_allowed_at - datetime.now(UTC)).total_seconds()))
        return SendMessageResponse(
            status="rejected", audit_log_id=audit_id,
            reason="rate_limit_exceeded", detail=rl.reason,
            retry_after_seconds=retry_seconds,
        )

    # --- Resolve GHL contact_id → phone/email ---
    ghl = _get_ghl()
    contact_phone = None
    contact_email = None
    try:
        contact_data = ghl.get_contact(payload.contact_id)
        contact = contact_data.get("contact", contact_data)
        contact_phone = contact.get("phone")
        contact_email = contact.get("email")
    except Exception as exc:
        logger.warning("send_message_contact_resolve_error contact=%s error=%s",
                        payload.contact_id, exc)

    if payload.channel in ("sms", "mms") and not contact_phone:
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="send_message", target_type="contact",
            target_id=payload.contact_id,
            payload_redacted={"channel": payload.channel, "reason": "no phone on contact"},
            outcome="policy_rejected", outcome_detail="contact has no phone number",
        )
        db.commit()
        return SendMessageResponse(
            status="rejected", audit_log_id=audit_id,
            reason="invalid_contact", detail="Contact has no phone number for SMS",
        )

    if payload.channel == "email" and not contact_email:
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="send_message", target_type="contact",
            target_id=payload.contact_id,
            payload_redacted={"channel": payload.channel, "reason": "no email on contact"},
            outcome="policy_rejected", outcome_detail="contact has no email",
        )
        db.commit()
        return SendMessageResponse(
            status="rejected", audit_log_id=audit_id,
            reason="invalid_contact", detail="Contact has no email address",
        )

    # --- Dispatch via existing integration clients ---
    sent_at = datetime.now(UTC)
    external_id = ""

    try:
        if payload.channel in ("sms", "mms"):
            telnyx = _get_telnyx()
            result = telnyx.send_sms(
                from_number=settings.telnyx_phone_number,
                to_number=contact_phone,
                text=payload.body,
            )
            external_id = result.get("data", {}).get("id", "") or f"telnyx-{uuid.uuid4().hex[:8]}"
        elif payload.channel == "email":
            from app.services.email_service import _send_email
            _send_email(
                to_email=contact_email,
                subject=payload.subject or "Message from VirtualCarHub",
                html_body=payload.body,
                text_body=payload.body,
            )
            external_id = f"sendgrid-{uuid.uuid4().hex[:8]}"
        else:
            external_id = f"unknown-channel-{uuid.uuid4().hex[:8]}"
    except Exception as exc:
        logger.warning("send_message_dispatch_error channel=%s error=%s", payload.channel, exc)
        external_id = f"dispatch-error-{uuid.uuid4().hex[:8]}"

    db.execute(
        text(
            "INSERT INTO outbound_log "
            "(id, trace_id, agent_id, contact_id, channel, body_redacted, "
            " external_id, rate_limit_check_passed, deal_id) "
            "VALUES (:id, :trace_id, :agent_id, :contact_id, :channel, "
            " :body, :ext_id, TRUE, :deal_id)"
        ),
        {
            "id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "agent_id": agent.agent_id,
            "contact_id": payload.contact_id,
            "channel": payload.channel,
            "body": payload.body[:500],  # redacted for audit
            "ext_id": external_id,
            "deal_id": payload.context.deal_id,
        },
    )

    # Record for rate limiting.
    rate_limit_service.record(
        target_id=payload.contact_id,
        channel=payload.channel,
        context_type=context_type,
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="send_message", target_type="contact",
        target_id=payload.contact_id,
        payload_redacted={"channel": payload.channel, "external_id": external_id},
        outcome="success",
    )
    db.commit()

    return SendMessageResponse(
        status="sent",
        external_id=external_id,
        audit_log_id=audit_id,
        sent_at=sent_at,
    )


@router.post("/add-contact-note", response_model=AddContactNoteResponse)
def add_contact_note(
    payload: AddContactNoteRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.add_contact_note")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    if len(payload.tags) > 10:
        raise HTTPException(status_code=422, detail="Max 10 tags allowed")

    # Policy: no secrets in note body.
    for pat in _SECRET_PATTERNS:
        if pat.search(payload.note_body):
            audit_id = _write_audit(
                db, trace_id=trace_id, agent_id=agent.agent_id,
                action_type="add_contact_note", target_type="contact",
                target_id=payload.contact_id,
                payload_redacted={"violation": "restricted content in note"},
                outcome="policy_rejected",
            )
            db.commit()
            raise HTTPException(status_code=422, detail="Note body contains restricted content")

    # Dispatch to GHL via existing client.
    note_body = payload.note_body
    if payload.tags:
        note_body += f"\n\nTags: {', '.join(payload.tags)}"
    note_body += f"\n[trace: {trace_id}, agent: {agent.agent_id}]"

    try:
        ghl = _get_ghl()
        ghl.add_contact_note(contact_id=payload.contact_id, body=note_body)
    except Exception as exc:
        logger.warning("add_contact_note_dispatch_error contact=%s error=%s", payload.contact_id, exc)

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="add_contact_note", target_type="contact",
        target_id=payload.contact_id,
        payload_redacted={"tags": payload.tags, "body_length": len(payload.note_body)},
        outcome="success",
    )
    db.commit()

    return AddContactNoteResponse(audit_log_id=audit_id)


@router.post("/update-contact-field", response_model=UpdateContactFieldResponse)
def update_contact_field(
    payload: UpdateContactFieldRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.update_contact_field")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    if payload.field_name not in ALLOWED_AGENT_UPDATABLE_FIELDS:
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="update_contact_field", target_type="contact",
            target_id=payload.contact_id,
            payload_redacted={"field_name": payload.field_name, "violation": "field not in allowlist"},
            outcome="policy_rejected",
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail=f"Field '{payload.field_name}' is not in the agent-updatable allowlist",
        )

    # Dispatch to GHL via existing client.
    try:
        ghl = _get_ghl()
        ghl.update_contact(payload.contact_id, {"customFields": [{
            "key": payload.field_name,
            "field_value": payload.value,
        }]})
    except Exception as exc:
        logger.warning("update_contact_field_dispatch_error contact=%s field=%s error=%s",
                        payload.contact_id, payload.field_name, exc)

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="update_contact_field", target_type="contact",
        target_id=payload.contact_id,
        payload_redacted={"field_name": payload.field_name},
        outcome="success",
    )
    db.commit()

    return UpdateContactFieldResponse(audit_log_id=audit_id)


@router.post("/schedule-followup", response_model=ScheduleFollowupResponse)
def schedule_followup(
    payload: ScheduleFollowupRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.schedule_followup")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    # Policy: due_at must be in the future, max 30 days out.
    now = datetime.now(UTC)
    if payload.due_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="due_at must include timezone")
    if payload.due_at <= now:
        raise HTTPException(status_code=422, detail="due_at must be in the future")
    if payload.due_at > now + timedelta(days=30):
        raise HTTPException(status_code=422, detail="due_at must be within 30 days")

    # Dispatch to GHL via existing client.
    try:
        ghl = _get_ghl()
        ghl.create_task({
            "title": payload.title,
            "body": payload.body,
            "dueDate": payload.due_at.isoformat(),
            "contactId": payload.contact_id,
            "assignedTo": payload.assigned_to or "",
        })
    except Exception as exc:
        logger.warning("schedule_followup_dispatch_error contact=%s error=%s", payload.contact_id, exc)

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="schedule_followup", target_type="contact",
        target_id=payload.contact_id,
        payload_redacted={"title": payload.title, "due_at": payload.due_at.isoformat()},
        outcome="success",
    )
    db.commit()

    return ScheduleFollowupResponse(audit_log_id=audit_id)


# ═══════════════════════════════════════════════════════════════════════════
# BATCH 3 — Wholesale-side actions (Negotiator)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/strategy-report", response_model=StrategyReportResponse)
def create_strategy_report(
    payload: StrategyReportRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.strategy_report")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)
    report_id = str(uuid.uuid4())

    db.execute(
        text(
            "INSERT INTO strategy_reports "
            "(id, trace_id, contact_id, vehicle_target, report_content, "
            " key_data_points, outreach_targets, pricing_envelope, status, deal_id) "
            "VALUES (:id, :trace_id, :contact_id, :vt, :content, "
            " :kdp, :ot, :pe, 'draft', :deal_id)"
        ),
        {
            "id": report_id,
            "trace_id": trace_id,
            "contact_id": payload.contact_id,
            "vt": payload.vehicle_target.model_dump_json(),
            "content": payload.report_content,
            "kdp": json.dumps(payload.key_data_points) if payload.key_data_points else None,
            "ot": json.dumps([t.model_dump() for t in payload.outreach_targets]) if payload.outreach_targets else None,
            "pe": payload.pricing_envelope.model_dump_json(),
            "deal_id": payload.deal_id,
        },
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="strategy_report.create", target_type="strategy_report",
        target_id=report_id,
        payload_redacted={
            "contact_id": payload.contact_id,
            "vehicle": f"{payload.vehicle_target.year} {payload.vehicle_target.make} {payload.vehicle_target.model}",
            "target_otd": payload.pricing_envelope.target_otd,
        },
        outcome="success",
    )
    db.commit()

    return StrategyReportResponse(
        report_id=report_id,
        audit_log_id=audit_id,
    )


@router.post("/dealer-outreach", response_model=DealerOutreachResponse)
def dealer_outreach(
    payload: DealerOutreachRequest,
    agent: AgentContext = Depends(require_scope("agent_actions.dealer_outreach")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    # Verify strategy report exists and is approved.
    report = db.execute(
        text("SELECT id, status FROM strategy_reports WHERE id = :id"),
        {"id": payload.strategy_report_id},
    ).fetchone()
    if not report:
        raise HTTPException(status_code=404, detail="Strategy report not found")
    if report.status not in ("approved", "executing"):
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="dealer_outreach", target_type="dealer",
            target_id=payload.dealer_id,
            payload_redacted={"report_status": report.status, "violation": "report not approved"},
            outcome="policy_rejected",
        )
        db.commit()
        return DealerOutreachResponse(
            status="rejected", audit_log_id=audit_id,
            reason="report_not_approved",
            detail=f"Strategy report status is '{report.status}', must be 'approved' or 'executing'",
        )

    # Content policy.
    violation = _check_body_policy(payload.body, payload.channel)
    if violation:
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="dealer_outreach", target_type="dealer",
            target_id=payload.dealer_id,
            payload_redacted={"channel": payload.channel, "violation": violation},
            outcome="policy_rejected", outcome_detail=violation,
        )
        db.commit()
        return DealerOutreachResponse(
            status="rejected", audit_log_id=audit_id,
            reason="policy_violation", detail=violation,
        )

    # Rate limit (dealer-side).
    target_id = payload.dealer_contact_id or payload.dealer_id
    rl = rate_limit_service.check(
        target_id=target_id,
        channel=payload.channel,
        context_type="dealer",
    )
    if not rl.allowed:
        audit_id = _write_audit(
            db, trace_id=trace_id, agent_id=agent.agent_id,
            action_type="dealer_outreach", target_type="dealer",
            target_id=payload.dealer_id,
            payload_redacted={"channel": payload.channel, "reason": rl.reason},
            outcome="rate_limited", outcome_detail=rl.reason,
        )
        db.commit()
        retry_seconds = None
        if rl.next_allowed_at:
            retry_seconds = max(0, int((rl.next_allowed_at - datetime.now(UTC)).total_seconds()))
        return DealerOutreachResponse(
            status="rejected", audit_log_id=audit_id,
            reason="rate_limit_exceeded", detail=rl.reason,
            retry_after_seconds=retry_seconds,
        )

    # Ensure/create dealer_thread.
    thread_row = db.execute(
        text(
            "SELECT id FROM dealer_threads "
            "WHERE strategy_report_id = :sr AND dealer_id = :did AND channel = :ch "
            "LIMIT 1"
        ),
        {"sr": payload.strategy_report_id, "did": payload.dealer_id, "ch": payload.channel},
    ).fetchone()

    if thread_row:
        thread_id = str(thread_row.id)
        db.execute(
            text(
                "UPDATE dealer_threads SET last_outbound_at = NOW(), updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"id": thread_id},
        )
    else:
        thread_id = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO dealer_threads "
                "(id, strategy_report_id, dealer_id, dealer_contact_id, channel, status, last_outbound_at) "
                "VALUES (:id, :sr, :did, :dcid, :ch, 'outreach_sent', NOW())"
            ),
            {
                "id": thread_id,
                "sr": payload.strategy_report_id,
                "did": payload.dealer_id,
                "dcid": payload.dealer_contact_id,
                "ch": payload.channel,
            },
        )

    # Log outbound.
    external_id = f"pending-{uuid.uuid4().hex[:12]}"
    sent_at = datetime.now(UTC)

    db.execute(
        text(
            "INSERT INTO outbound_log "
            "(id, trace_id, agent_id, dealer_thread_id, channel, body_redacted, "
            " external_id, rate_limit_check_passed) "
            "VALUES (:id, :trace_id, :agent_id, :dt_id, :channel, :body, :ext_id, TRUE)"
        ),
        {
            "id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "agent_id": agent.agent_id,
            "dt_id": thread_id,
            "channel": payload.channel,
            "body": payload.body[:500],
            "ext_id": external_id,
        },
    )

    rate_limit_service.record(
        target_id=target_id,
        channel=payload.channel,
        context_type="dealer",
    )

    # Update strategy report status to executing if still draft/approved.
    if report.status == "approved":
        db.execute(
            text("UPDATE strategy_reports SET status = 'executing' WHERE id = :id"),
            {"id": payload.strategy_report_id},
        )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="dealer_outreach", target_type="dealer",
        target_id=payload.dealer_id,
        payload_redacted={
            "channel": payload.channel,
            "dealer_thread_id": thread_id,
            "external_id": external_id,
        },
        outcome="success",
    )
    db.commit()

    return DealerOutreachResponse(
        status="sent",
        external_id=external_id,
        audit_log_id=audit_id,
        sent_at=sent_at,
    )
