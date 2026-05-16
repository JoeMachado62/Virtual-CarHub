"""Pydantic request/response schemas for /v1/admin-actions/* endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Batch 1 — Read endpoints
# ---------------------------------------------------------------------------

class FleetStateEntry(BaseModel):
    vps_hostname: str
    wg_ip: str
    reported_by_agent: str
    reported_at: datetime
    runtime_status: str
    openclaw_node_uptime_seconds: int | None = None
    active_workflows: int | None = None
    queue_depth: int | None = None
    pending_approvals: int | None = None
    drift_alerts: dict | None = None
    free_disk_gb: float | None = None
    free_memory_gb: float | None = None
    recent_errors: list | None = None


class FleetStateResponse(BaseModel):
    entries: list[FleetStateEntry]


class PostgresHealthResponse(BaseModel):
    status: str  # healthy | degraded | down
    connection_count: int
    max_connections: int
    long_running_queries: list[dict] = Field(default_factory=list)
    database_size_gb: float
    largest_tables: list[dict] = Field(default_factory=list)
    replication_status: str = "not_replicated"


class MigrationStatusResponse(BaseModel):
    current_revision: str | None
    head_revisions: list[str]
    in_sync: bool
    pending_migrations: list[dict] = Field(default_factory=list)


class AuditQueryRow(BaseModel):
    id: str
    trace_id: str
    agent_id: str
    action_type: str
    target_type: str | None
    target_id: str | None
    payload_redacted: dict | None
    outcome: str
    outcome_detail: str | None
    occurred_at: datetime


class AuditQueryResponse(BaseModel):
    rows: list[AuditQueryRow]
    total_returned: int


class ServiceStatusResponse(BaseModel):
    service: str
    active: bool
    sub_state: str
    uptime_seconds: int | None = None
    memory_mb: float | None = None
    recent_log_lines: list[dict] = Field(default_factory=list)


class EnvVerifyResponse(BaseModel):
    service: str
    vars_present: list[str]
    vars_missing: list[str]
    vars_unexpected: list[str] = Field(default_factory=list)


# Pipeline report and agent stats (built from existing deal/audit data)
class PipelineStage(BaseModel):
    stage: str
    count: int


class PipelineReportResponse(BaseModel):
    stages: list[PipelineStage]
    total_active: int
    total_closed: int
    stalled_count: int


class AgentStatsResponse(BaseModel):
    agent_id: str | None  # None means aggregate
    total_actions: int
    actions_by_type: dict[str, int]
    success_count: int
    rejected_count: int
    period_start: datetime
    period_end: datetime


class StalledDealEntry(BaseModel):
    deal_id: str
    stage: str
    stalled_since: datetime
    contact_id: str | None
    assigned_agent: str | None


class StalledDealsResponse(BaseModel):
    deals: list[StalledDealEntry]
    total: int


# ---------------------------------------------------------------------------
# Batch 2 — Write/operational endpoints
# ---------------------------------------------------------------------------

class FleetStateUpdateRequest(BaseModel):
    vps_hostname: str
    wg_ip: str
    runtime_status: str
    openclaw_node_uptime_seconds: int | None = None
    active_workflows: int | None = None
    queue_depth: int | None = None
    pending_approvals: int | None = None
    drift_alerts: dict | None = None
    free_disk_gb: float | None = None
    free_memory_gb: float | None = None
    recent_errors: list | None = None


class FleetStateUpdateResponse(BaseModel):
    status: str = "updated"
    vps_hostname: str
    audit_log_id: str


class DispatchLogRequest(BaseModel):
    action_type: str
    target_vps: str | None = None
    target_resource: str | None = None
    payload_redacted: dict | None = None
    approval_required: bool = False
    approval_status: str | None = None
    approved_by: str | None = None
    outcome: str
    outcome_detail: str | None = None


class DispatchLogResponse(BaseModel):
    status: str = "logged"
    dispatch_log_id: str
    audit_log_id: str


class ApprovalRequest(BaseModel):
    resume_token: str
    workflow_name: str
    preview: dict
    notified_channels: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class ApprovalResponse(BaseModel):
    status: str = "queued"
    approval_id: str
    audit_log_id: str


class ApprovalResolveRequest(BaseModel):
    approval_id: str
    resolution: str  # approved | rejected
    resolved_by: str


class ApprovalResolveResponse(BaseModel):
    status: str = "resolved"
    approval_id: str
    resume_token: str
    audit_log_id: str


class RestartServiceRequest(BaseModel):
    service: str  # api | orchestrator
    reason: str
    approval_token: str


class RestartServiceResponse(BaseModel):
    status: str  # restarted | failed
    service: str
    audit_log_id: str
    detail: str | None = None


class RotateTokenRequest(BaseModel):
    agent_id: str
    reason: str
    approval_token: str


class RotateTokenResponse(BaseModel):
    status: str = "rotated"
    agent_id: str
    new_token: str  # plaintext — returned ONCE
    old_token_revokes_at: datetime
    audit_log_id: str
