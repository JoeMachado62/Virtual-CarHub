"""Pydantic request/response schemas for /v1/agent-actions/* endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class ActionContext(BaseModel):
    intent_thread_id: str | None = None
    deal_id: str | None = None
    from_skill: str
    mode: str | None = None  # buyer | admin | wholesale


class RejectedResponse(BaseModel):
    status: str = "rejected"
    reason: str
    detail: str | None = None
    audit_log_id: str
    retry_after_seconds: int | None = None


# ---------------------------------------------------------------------------
# Batch 1 — Foundational
# ---------------------------------------------------------------------------

# Intent threads
class IntentThreadCreate(BaseModel):
    contact_id: str
    intent_code: str
    context_payload: dict[str, Any] | None = None
    deal_id: str | None = None
    context: ActionContext


class IntentThreadUpdate(BaseModel):
    status: str | None = None
    context_payload: dict[str, Any] | None = None
    resolution_summary: str | None = None
    context: ActionContext


class IntentThreadResponse(BaseModel):
    intent_thread_id: str
    status: str
    audit_log_id: str


# Log interaction
class LogInteractionRequest(BaseModel):
    interaction_type: str  # inbound_message | call_summary | meeting_note
    contact_id: str
    channel: str
    content_summary: str
    sentiment: str | None = None  # positive | neutral | negative | mixed
    key_entities: list[str] = Field(default_factory=list)
    context: ActionContext


class LogInteractionResponse(BaseModel):
    status: str = "logged"
    audit_log_id: str


# HITL
class HitlEscalateRequest(BaseModel):
    trigger_code: str
    summary: str
    context_payload: dict[str, Any]
    suggested_action: str | None = None
    blocking: bool = True
    urgency: str = "medium"  # low | medium | high | urgent
    from_skill: str
    contact_id: str | None = None
    deal_id: str | None = None
    intent_thread_id: str | None = None


class HitlEscalateResponse(BaseModel):
    status: str = "escalated"
    hitl_task_id: str
    audit_log_id: str


class HitlResolveRequest(BaseModel):
    hitl_task_id: str
    resolution_action: str
    resolution_notes: str | None = None
    resolved_by: str


class HitlResolveResponse(BaseModel):
    status: str = "resolved"
    hitl_task_id: str
    audit_log_id: str


# Rate limit check
class RateLimitCheckResponse(BaseModel):
    allowed: bool
    reason: str | None = None
    next_allowed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Batch 2 — Buyer-side (Danny)
# ---------------------------------------------------------------------------

class SendMessageRequest(BaseModel):
    contact_id: str
    channel: str  # sms | email | mms
    body: str
    subject: str | None = None  # email only
    media_urls: list[str] = Field(default_factory=list)
    context: ActionContext


class SendMessageResponse(BaseModel):
    status: str  # sent | rejected
    external_id: str | None = None
    audit_log_id: str
    sent_at: datetime | None = None
    # Rejection fields (populated only when status == "rejected")
    reason: str | None = None
    detail: str | None = None
    retry_after_seconds: int | None = None


class AddContactNoteRequest(BaseModel):
    contact_id: str
    note_body: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    context: ActionContext


class AddContactNoteResponse(BaseModel):
    status: str = "noted"
    audit_log_id: str


class UpdateContactFieldRequest(BaseModel):
    contact_id: str
    field_name: str
    value: str | int | float | bool
    context: ActionContext


class UpdateContactFieldResponse(BaseModel):
    status: str = "updated"
    audit_log_id: str


class ScheduleFollowupRequest(BaseModel):
    contact_id: str
    due_at: datetime
    title: str
    body: str
    assigned_to: str | None = None
    context: ActionContext


class ScheduleFollowupResponse(BaseModel):
    status: str = "scheduled"
    audit_log_id: str


# ---------------------------------------------------------------------------
# Batch 3 — Wholesale-side (Negotiator)
# ---------------------------------------------------------------------------

class VehicleTarget(BaseModel):
    year: int
    make: str
    model: str
    trim: str | None = None


class PricingEnvelope(BaseModel):
    target_otd: float
    max_otd: float
    walk_away_otd: float


class OutreachTarget(BaseModel):
    dealer_id: str
    priority: int
    rationale: str


class StrategyReportRequest(BaseModel):
    contact_id: str
    vehicle_target: VehicleTarget
    report_content: str
    key_data_points: dict[str, Any] | None = None
    outreach_targets: list[OutreachTarget] = Field(default_factory=list)
    pricing_envelope: PricingEnvelope
    deal_id: str | None = None
    context: ActionContext


class StrategyReportResponse(BaseModel):
    status: str = "created"
    report_id: str
    audit_log_id: str


class DealerOutreachRequest(BaseModel):
    strategy_report_id: str
    dealer_id: str
    dealer_contact_id: str | None = None
    channel: str  # email | sms | chat_widget
    subject: str | None = None  # email only
    body: str
    context: ActionContext


class DealerOutreachResponse(BaseModel):
    status: str  # sent | rejected
    external_id: str | None = None
    audit_log_id: str
    sent_at: datetime | None = None
    reason: str | None = None
    detail: str | None = None
    retry_after_seconds: int | None = None
