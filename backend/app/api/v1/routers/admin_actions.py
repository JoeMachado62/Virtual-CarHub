"""v7 admin_actions router — /v1/admin-actions/*

Called by admin-mc-hub on Mission Control for backend administration.
Per Doc 2 §2.4.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.service_token import (
    AgentContext,
    generate_raw_token,
    get_agent_context,
    hash_token,
    require_scope,
)
from app.db.session import get_db
from app.schemas.admin_actions import (
    AgentStatsResponse,
    ApprovalRequest,
    ApprovalResolveRequest,
    ApprovalResolveResponse,
    ApprovalResponse,
    AuditQueryResponse,
    AuditQueryRow,
    DispatchLogRequest,
    DispatchLogResponse,
    EnvVerifyResponse,
    FleetStateEntry,
    FleetStateResponse,
    FleetStateUpdateRequest,
    FleetStateUpdateResponse,
    MigrationStatusResponse,
    PipelineReportResponse,
    PipelineStage,
    PostgresHealthResponse,
    RestartServiceRequest,
    RestartServiceResponse,
    RotateTokenRequest,
    RotateTokenResponse,
    ServiceStatusResponse,
    StalledDealEntry,
    StalledDealsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Reuse audit/trace helpers from agent_actions.
# Import the shared helpers.
from app.api.v1.routers.agent_actions import _redact_payload, _resolve_trace_id, _write_audit

# Secret patterns for log-line redaction.
_SECRET_RE = re.compile(
    r"(DATABASE_URL|SERVICE_TOKEN|JWT_SECRET|API_KEY|SECRET|PASSWORD|TOKEN)"
    r"\s*[=:]\s*\S+",
    re.IGNORECASE,
)


def _redact_log_line(line: str) -> str:
    return _SECRET_RE.sub(r"\1=[REDACTED]", line)


def _require_admin_mc_hub(agent: AgentContext) -> None:
    """Verify caller is specifically admin-mc-hub (not just any admin token)."""
    if agent.agent_id != "admin-mc-hub":
        raise HTTPException(
            status_code=403,
            detail=f"This endpoint requires admin-mc-hub, got '{agent.agent_id}'",
        )


def _write_dispatch_log(
    db: Session,
    *,
    trace_id: str,
    admin_agent_id: str,
    action_type: str,
    target_vps: str | None = None,
    target_resource: str | None = None,
    payload_redacted: dict | None = None,
    approval_required: bool = False,
    approval_status: str | None = None,
    approved_by: str | None = None,
    outcome: str,
    outcome_detail: str | None = None,
) -> str:
    row_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO openclaw_dispatch_log "
            "(id, trace_id, admin_agent_id, action_type, target_vps, target_resource, "
            " payload_redacted, approval_required, approval_status, approved_by, "
            " outcome, outcome_detail) "
            "VALUES (:id, :trace_id, :admin, :action, :vps, :resource, "
            " :payload, :approval_req, :approval_status, :approved_by, "
            " :outcome, :detail)"
        ),
        {
            "id": row_id,
            "trace_id": trace_id,
            "admin": admin_agent_id,
            "action": action_type,
            "vps": target_vps,
            "resource": target_resource,
            "payload": json.dumps(_redact_payload(payload_redacted or {})),
            "approval_req": approval_required,
            "approval_status": approval_status,
            "approved_by": approved_by,
            "outcome": outcome,
            "detail": outcome_detail,
        },
    )
    return row_id


# ═══════════════════════════════════════════════════════════════════════════
# BATCH 1 — Read endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/fleet-state", response_model=FleetStateResponse)
def get_fleet_state(
    agent: AgentContext = Depends(require_scope("admin_actions.fleet_state.read")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("SELECT * FROM fleet_state ORDER BY reported_at DESC")
    ).fetchall()

    entries = []
    for r in rows:
        entries.append(FleetStateEntry(
            vps_hostname=r.vps_hostname,
            wg_ip=str(r.wg_ip),
            reported_by_agent=r.reported_by_agent,
            reported_at=r.reported_at,
            runtime_status=r.runtime_status,
            openclaw_node_uptime_seconds=r.openclaw_node_uptime_seconds,
            active_workflows=r.active_workflows,
            queue_depth=r.queue_depth,
            pending_approvals=r.pending_approvals,
            drift_alerts=r.drift_alerts,
            free_disk_gb=float(r.free_disk_gb) if r.free_disk_gb else None,
            free_memory_gb=float(r.free_memory_gb) if r.free_memory_gb else None,
            recent_errors=r.recent_errors,
        ))

    return FleetStateResponse(entries=entries)


@router.get("/health/postgres", response_model=PostgresHealthResponse)
def health_postgres(
    agent: AgentContext = Depends(require_scope("admin_actions.health.read")),
    db: Session = Depends(get_db),
):
    try:
        # Connection count.
        conn_row = db.execute(text(
            "SELECT count(*) AS cnt FROM pg_stat_activity WHERE datname = current_database()"
        )).fetchone()
        connection_count = conn_row.cnt if conn_row else 0

        max_conn_row = db.execute(text("SHOW max_connections")).fetchone()
        max_connections = int(max_conn_row[0]) if max_conn_row else 100

        # Long-running queries (> 30s).
        long_queries = db.execute(text(
            "SELECT pid, EXTRACT(EPOCH FROM (NOW() - query_start))::int AS duration_seconds, "
            "  state, left(query, 80) AS query_fingerprint "
            "FROM pg_stat_activity "
            "WHERE state = 'active' AND query_start < NOW() - INTERVAL '30 seconds' "
            "  AND datname = current_database() "
            "ORDER BY query_start LIMIT 10"
        )).fetchall()

        # Database size.
        size_row = db.execute(text(
            "SELECT pg_database_size(current_database()) / (1024.0*1024*1024) AS size_gb"
        )).fetchone()
        database_size_gb = round(float(size_row.size_gb), 2) if size_row else 0

        # Largest tables.
        table_rows = db.execute(text(
            "SELECT relname AS table_name, "
            "  pg_total_relation_size(c.oid) / (1024.0*1024*1024) AS size_gb "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 10"
        )).fetchall()

        status = "healthy"
        if connection_count > max_connections * 0.8:
            status = "degraded"
        if long_queries:
            status = "degraded"

        return PostgresHealthResponse(
            status=status,
            connection_count=connection_count,
            max_connections=max_connections,
            long_running_queries=[
                {
                    "pid": q.pid,
                    "duration_seconds": q.duration_seconds,
                    "state": q.state,
                    "query_fingerprint": q.query_fingerprint,
                }
                for q in long_queries
            ],
            database_size_gb=database_size_gb,
            largest_tables=[
                {"table": t.table_name, "size_gb": round(float(t.size_gb), 3)}
                for t in table_rows
            ],
        )

    except Exception as exc:
        logger.error("postgres_health_check_failed", exc_info=True)
        return PostgresHealthResponse(
            status="down",
            connection_count=0,
            max_connections=0,
            database_size_gb=0,
        )


@router.get("/health/api")
def health_api(
    agent: AgentContext = Depends(require_scope("admin_actions.health.read")),
):
    """If this endpoint responds, the API is up."""
    return {"status": "healthy", "service": "api.service"}


@router.get("/migration-status", response_model=MigrationStatusResponse)
def migration_status(
    agent: AgentContext = Depends(require_scope("admin_actions.migration.read")),
    db: Session = Depends(get_db),
):
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()

        from app.db.session import engine
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            db_rev = ctx.get_current_revision()

        in_sync = db_rev == head_rev
        pending = []
        if not in_sync and head_rev and db_rev:
            for rev in script.iterate_revisions(head_rev, db_rev):
                if str(rev.revision) != db_rev:
                    pending.append({
                        "revision": str(rev.revision),
                        "description": rev.doc or "",
                    })

        return MigrationStatusResponse(
            current_revision=db_rev,
            head_revisions=[head_rev] if head_rev else [],
            in_sync=in_sync,
            pending_migrations=pending,
        )
    except Exception as exc:
        logger.error("migration_status_check_failed", exc_info=True)
        return MigrationStatusResponse(
            current_revision=None,
            head_revisions=[],
            in_sync=False,
            pending_migrations=[{"revision": "error", "description": str(exc)}],
        )


@router.get("/audit-query", response_model=AuditQueryResponse)
def audit_query(
    start_at: str = Query(...),
    end_at: str = Query(...),
    agent_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    confirm: bool = Query(default=False),
    agent: AgentContext = Depends(require_scope("admin_actions.audit.read")),
    db: Session = Depends(get_db),
):
    try:
        start_dt = datetime.fromisoformat(start_at)
        end_dt = datetime.fromisoformat(end_at)
    except ValueError:
        raise HTTPException(status_code=422, detail="start_at/end_at must be ISO 8601")

    if (end_dt - start_dt).days > 30 and not confirm:
        raise HTTPException(
            status_code=422,
            detail="Query spans > 30 days. Add confirm=true to proceed.",
        )

    query = "SELECT * FROM audit_log WHERE occurred_at >= :start AND occurred_at <= :end"
    params: dict = {"start": start_dt, "end": end_dt}

    if agent_id:
        query += " AND agent_id = :agent_id"
        params["agent_id"] = agent_id
    if action_type:
        query += " AND action_type = :action_type"
        params["action_type"] = action_type
    if outcome:
        query += " AND outcome = :outcome"
        params["outcome"] = outcome

    query += " ORDER BY occurred_at DESC LIMIT :lim"
    params["lim"] = limit

    rows = db.execute(text(query), params).fetchall()

    return AuditQueryResponse(
        rows=[
            AuditQueryRow(
                id=str(r.id),
                trace_id=r.trace_id,
                agent_id=r.agent_id,
                action_type=r.action_type,
                target_type=r.target_type,
                target_id=r.target_id,
                payload_redacted=r.payload_redacted,
                outcome=r.outcome,
                outcome_detail=r.outcome_detail,
                occurred_at=r.occurred_at,
            )
            for r in rows
        ],
        total_returned=len(rows),
    )


@router.get("/service-status", response_model=ServiceStatusResponse)
def service_status(
    service: str = Query(default="api"),
    agent: AgentContext = Depends(require_scope("admin_actions.service.read")),
    db: Session = Depends(get_db),
):
    """Returns service status. The API runs inside a container, so we use
    in-process checks rather than docker CLI (which isn't available inside)."""
    if service == "api":
        # We're running — the fact this endpoint responds proves it.
        import time as _time
        try:
            # /proc/1 is the main process (uvicorn) inside the container.
            with open("/proc/1/stat") as f:
                stat = f.read().split()
            # Field 22 is starttime in clock ticks since boot.
            start_ticks = int(stat[21])
            with open("/proc/uptime") as f:
                boot_uptime = float(f.read().split()[0])
            clk_tck = os.sysconf("SC_CLK_TCK")
            process_uptime = boot_uptime - (start_ticks / clk_tck)
            uptime_seconds = max(0, int(process_uptime))
        except Exception:
            uptime_seconds = None

        # Memory from /proc/self/status.
        memory_mb = None
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        memory_mb = round(int(line.split()[1]) / 1024, 1)
                        break
        except Exception:
            pass

        return ServiceStatusResponse(
            service="api",
            active=True,
            sub_state="running",
            uptime_seconds=uptime_seconds,
            memory_mb=memory_mb,
        )

    elif service == "postgres":
        try:
            row = db.execute(text("SELECT 1")).fetchone()
            return ServiceStatusResponse(
                service="postgres", active=row is not None, sub_state="running",
            )
        except Exception:
            return ServiceStatusResponse(
                service="postgres", active=False, sub_state="unreachable",
            )

    elif service == "redis":
        try:
            import redis as _redis
            from app.core.config import settings
            r = _redis.from_url(settings.redis_url)
            pong = r.ping()
            return ServiceStatusResponse(
                service="redis", active=pong, sub_state="running" if pong else "unhealthy",
            )
        except Exception:
            return ServiceStatusResponse(
                service="redis", active=False, sub_state="unreachable",
            )

    else:
        raise HTTPException(status_code=422, detail=f"Unknown service: {service}")


@router.get("/env-verify", response_model=EnvVerifyResponse)
def env_verify(
    service: str = Query(default="api"),
    expected_vars: str = Query(default="DATABASE_URL,REDIS_URL,JWT_SECRET_KEY"),
    agent: AgentContext = Depends(require_scope("admin_actions.env.read")),
):
    """Verify environment variable presence — NEVER returns actual values."""
    expected = [v.strip() for v in expected_vars.split(",") if v.strip()]
    present = []
    missing = []

    for var in expected:
        if os.environ.get(var) is not None:
            present.append(var)
        else:
            missing.append(var)

    return EnvVerifyResponse(
        service=service,
        vars_present=present,
        vars_missing=missing,
    )


@router.get("/pipeline-report", response_model=PipelineReportResponse)
def pipeline_report(
    agent: AgentContext = Depends(require_scope("admin_actions.pipeline.read")),
    db: Session = Depends(get_db),
):
    """Pipeline snapshot: deals by stage, stalled count."""
    rows = db.execute(text(
        "SELECT stage, count(*) AS cnt FROM deals GROUP BY stage ORDER BY stage"
    )).fetchall()

    stages = [PipelineStage(stage=r.stage, count=r.cnt) for r in rows]

    closed_states = {"CLOSED_WON", "CLOSED_LOST", "DELIVERED"}
    total_active = sum(s.count for s in stages if s.stage not in closed_states)
    total_closed = sum(s.count for s in stages if s.stage in closed_states)

    # Stalled: deals with no activity in >72 hours, not in a terminal state.
    stalled_row = db.execute(text(
        "SELECT count(*) AS cnt FROM deals "
        "WHERE stage NOT IN ('CLOSED_WON','CLOSED_LOST','DELIVERED','DISQUALIFIED') "
        "  AND updated_at < NOW() - INTERVAL '72 hours'"
    )).fetchone()
    stalled_count = stalled_row.cnt if stalled_row else 0

    return PipelineReportResponse(
        stages=stages,
        total_active=total_active,
        total_closed=total_closed,
        stalled_count=stalled_count,
    )


@router.get("/agent-stats", response_model=AgentStatsResponse)
def agent_stats(
    agent_id_filter: str | None = Query(default=None, alias="agent_id"),
    hours: int = Query(default=24, le=720),
    agent: AgentContext = Depends(require_scope("admin_actions.agent_stats.read")),
    db: Session = Depends(get_db),
):
    period_start = datetime.now(UTC) - timedelta(hours=hours)
    period_end = datetime.now(UTC)

    base_query = "SELECT action_type, outcome, count(*) AS cnt FROM audit_log WHERE occurred_at >= :start"
    params: dict = {"start": period_start}

    if agent_id_filter:
        base_query += " AND agent_id = :agent_id"
        params["agent_id"] = agent_id_filter

    base_query += " GROUP BY action_type, outcome"
    rows = db.execute(text(base_query), params).fetchall()

    actions_by_type: dict[str, int] = {}
    success_count = 0
    rejected_count = 0
    total = 0
    for r in rows:
        actions_by_type[r.action_type] = actions_by_type.get(r.action_type, 0) + r.cnt
        total += r.cnt
        if r.outcome == "success":
            success_count += r.cnt
        elif r.outcome in ("policy_rejected", "rate_limited"):
            rejected_count += r.cnt

    return AgentStatsResponse(
        agent_id=agent_id_filter,
        total_actions=total,
        actions_by_type=actions_by_type,
        success_count=success_count,
        rejected_count=rejected_count,
        period_start=period_start,
        period_end=period_end,
    )


@router.get("/stalled-deals", response_model=StalledDealsResponse)
def stalled_deals(
    stall_hours: int = Query(default=72),
    limit: int = Query(default=50, le=200),
    agent: AgentContext = Depends(require_scope("admin_actions.pipeline.read")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            "SELECT id, stage, updated_at, ghl_contact_id, assigned_agent "
            "FROM deals "
            "WHERE stage NOT IN ('CLOSED_WON','CLOSED_LOST','DELIVERED','DISQUALIFIED') "
            "  AND updated_at < NOW() - make_interval(hours => :hours) "
            "ORDER BY updated_at ASC LIMIT :lim"
        ),
        {"hours": stall_hours, "lim": limit},
    ).fetchall()

    return StalledDealsResponse(
        deals=[
            StalledDealEntry(
                deal_id=r.id,
                stage=r.stage,
                stalled_since=r.updated_at,
                contact_id=r.ghl_contact_id,
                assigned_agent=r.assigned_agent,
            )
            for r in rows
        ],
        total=len(rows),
    )


# ═══════════════════════════════════════════════════════════════════════════
# BATCH 2 — Write/operational endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/fleet-state-update", response_model=FleetStateUpdateResponse)
def fleet_state_update(
    payload: FleetStateUpdateRequest,
    agent: AgentContext = Depends(require_scope("admin_actions.fleet_state.write")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    # Upsert into fleet_state.
    db.execute(
        text(
            "INSERT INTO fleet_state "
            "(vps_hostname, wg_ip, reported_by_agent, reported_at, runtime_status, "
            " openclaw_node_uptime_seconds, active_workflows, queue_depth, "
            " pending_approvals, drift_alerts, free_disk_gb, free_memory_gb, recent_errors) "
            "VALUES (:host, CAST(:wg_ip AS inet), :agent, NOW(), :status, "
            " :uptime, :workflows, :queue, :approvals, :drift, :disk, :mem, :errors) "
            "ON CONFLICT (vps_hostname) DO UPDATE SET "
            "  wg_ip = EXCLUDED.wg_ip, "
            "  reported_by_agent = EXCLUDED.reported_by_agent, "
            "  reported_at = EXCLUDED.reported_at, "
            "  runtime_status = EXCLUDED.runtime_status, "
            "  openclaw_node_uptime_seconds = EXCLUDED.openclaw_node_uptime_seconds, "
            "  active_workflows = EXCLUDED.active_workflows, "
            "  queue_depth = EXCLUDED.queue_depth, "
            "  pending_approvals = EXCLUDED.pending_approvals, "
            "  drift_alerts = EXCLUDED.drift_alerts, "
            "  free_disk_gb = EXCLUDED.free_disk_gb, "
            "  free_memory_gb = EXCLUDED.free_memory_gb, "
            "  recent_errors = EXCLUDED.recent_errors"
        ),
        {
            "host": payload.vps_hostname,
            "wg_ip": payload.wg_ip,
            "agent": agent.agent_id,
            "status": payload.runtime_status,
            "uptime": payload.openclaw_node_uptime_seconds,
            "workflows": payload.active_workflows,
            "queue": payload.queue_depth,
            "approvals": payload.pending_approvals,
            "drift": json.dumps(payload.drift_alerts) if payload.drift_alerts else None,
            "disk": payload.free_disk_gb,
            "mem": payload.free_memory_gb,
            "errors": json.dumps(payload.recent_errors) if payload.recent_errors else None,
        },
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="fleet_state.update", target_type="fleet_state",
        target_id=payload.vps_hostname,
        payload_redacted={"runtime_status": payload.runtime_status},
        outcome="success",
    )
    db.commit()

    return FleetStateUpdateResponse(
        vps_hostname=payload.vps_hostname,
        audit_log_id=audit_id,
    )


@router.post("/openclaw-dispatch-log", response_model=DispatchLogResponse)
def openclaw_dispatch_log(
    payload: DispatchLogRequest,
    agent: AgentContext = Depends(require_scope("admin_actions.dispatch_log.write")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    dispatch_id = _write_dispatch_log(
        db,
        trace_id=trace_id,
        admin_agent_id=agent.agent_id,
        action_type=payload.action_type,
        target_vps=payload.target_vps,
        target_resource=payload.target_resource,
        payload_redacted=payload.payload_redacted,
        approval_required=payload.approval_required,
        approval_status=payload.approval_status,
        approved_by=payload.approved_by,
        outcome=payload.outcome,
        outcome_detail=payload.outcome_detail,
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="dispatch_log.write", target_type="openclaw_dispatch_log",
        target_id=dispatch_id,
        payload_redacted={"action_type": payload.action_type, "outcome": payload.outcome},
        outcome="success",
    )
    db.commit()

    return DispatchLogResponse(
        dispatch_log_id=dispatch_id,
        audit_log_id=audit_id,
    )


@router.post("/approval-request", response_model=ApprovalResponse)
def approval_request(
    payload: ApprovalRequest,
    agent: AgentContext = Depends(require_scope("admin_actions.approval.create")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)
    approval_id = str(uuid.uuid4())

    db.execute(
        text(
            "INSERT INTO pending_approvals "
            "(id, resume_token, proposing_agent, workflow_name, preview, "
            " notified_channels, expires_at) "
            "VALUES (:id, :token, :agent, :workflow, :preview, :channels, :expires)"
        ),
        {
            "id": approval_id,
            "token": payload.resume_token,
            "agent": agent.agent_id,
            "workflow": payload.workflow_name,
            "preview": json.dumps(payload.preview),
            "channels": payload.notified_channels or [],
            "expires": payload.expires_at,
        },
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="approval.create", target_type="pending_approval",
        target_id=approval_id,
        payload_redacted={"workflow_name": payload.workflow_name},
        outcome="success",
    )
    db.commit()

    return ApprovalResponse(
        approval_id=approval_id,
        audit_log_id=audit_id,
    )


@router.post("/approval-response", response_model=ApprovalResolveResponse)
def approval_response(
    payload: ApprovalResolveRequest,
    agent: AgentContext = Depends(require_scope("admin_actions.approval.respond")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)

    row = db.execute(
        text("SELECT id, resume_token, resolved_at FROM pending_approvals WHERE id = :id"),
        {"id": payload.approval_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")
    if row.resolved_at is not None:
        raise HTTPException(status_code=409, detail="Approval already resolved")

    db.execute(
        text(
            "UPDATE pending_approvals SET "
            "  resolved_at = NOW(), resolution = :resolution, resolved_by = :by "
            "WHERE id = :id"
        ),
        {
            "id": payload.approval_id,
            "resolution": payload.resolution,
            "by": payload.resolved_by,
        },
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="approval.respond", target_type="pending_approval",
        target_id=payload.approval_id,
        payload_redacted={"resolution": payload.resolution, "resolved_by": payload.resolved_by},
        outcome="success",
    )
    db.commit()

    return ApprovalResolveResponse(
        approval_id=payload.approval_id,
        resume_token=row.resume_token,
        audit_log_id=audit_id,
    )


@router.post("/restart-service", response_model=RestartServiceResponse)
def restart_service(
    payload: RestartServiceRequest,
    agent: AgentContext = Depends(require_scope("admin_actions.service.restart")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
    x_lobster_workflow_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)
    _require_admin_mc_hub(agent)

    if not x_lobster_workflow_id:
        raise HTTPException(
            status_code=403,
            detail="Restart requires X-Lobster-Workflow-Id header (Lobster-gated)",
        )

    # Verify approval_token against pending_approvals.
    approval = db.execute(
        text(
            "SELECT id, resolved_at, resolution FROM pending_approvals "
            "WHERE resume_token = :token"
        ),
        {"token": payload.approval_token},
    ).fetchone()
    if not approval:
        raise HTTPException(status_code=403, detail="Invalid approval_token")
    if approval.resolved_at is None or approval.resolution != "approved":
        raise HTTPException(status_code=403, detail="Approval not granted")

    if payload.service not in ("api", "orchestrator"):
        raise HTTPException(status_code=422, detail=f"Unknown service: {payload.service}")

    # The backend runs inside Docker. Container restarts must be issued from
    # the host (docker restart). This endpoint records the approved restart
    # request in the dispatch log. The operator or a host-level script can
    # then act on it. A self-restart of the API would kill this response.
    _write_dispatch_log(
        db, trace_id=trace_id, admin_agent_id=agent.agent_id,
        action_type="service.restart", target_vps="backend-vps",
        target_resource=payload.service,
        payload_redacted={"reason": payload.reason},
        approval_required=True, approval_status="approved",
        outcome="restart_requested",
        outcome_detail="Restart must be executed from host: docker restart virtual-carhub-backend-1",
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="service.restart", target_type="service",
        target_id=payload.service,
        payload_redacted={"reason": payload.reason},
        outcome="restart_requested",
    )
    db.commit()

    return RestartServiceResponse(
        status="restart_requested",
        service=payload.service,
        audit_log_id=audit_id,
        detail="Approved and logged. Execute from host: docker restart virtual-carhub-backend-1",
    )


@router.post("/rotate-service-token", response_model=RotateTokenResponse)
def rotate_service_token(
    payload: RotateTokenRequest,
    agent: AgentContext = Depends(require_scope("admin_actions.token.rotate")),
    db: Session = Depends(get_db),
    x_trace_id: str | None = Header(default=None),
    x_lobster_workflow_id: str | None = Header(default=None),
):
    trace_id = _resolve_trace_id(x_trace_id)
    _require_admin_mc_hub(agent)

    if not x_lobster_workflow_id:
        raise HTTPException(
            status_code=403,
            detail="Token rotation requires X-Lobster-Workflow-Id header (Lobster-gated)",
        )

    # Safety: admin-mc-hub cannot rotate its own token.
    if payload.agent_id == "admin-mc-hub":
        raise HTTPException(
            status_code=403,
            detail="admin-mc-hub cannot rotate its own token for safety",
        )

    # Verify approval token.
    approval = db.execute(
        text(
            "SELECT id, resolved_at, resolution FROM pending_approvals "
            "WHERE resume_token = :token"
        ),
        {"token": payload.approval_token},
    ).fetchone()
    if not approval:
        raise HTTPException(status_code=403, detail="Invalid approval_token")
    if approval.resolved_at is None or approval.resolution != "approved":
        raise HTTPException(status_code=403, detail="Approval not granted")

    # Find current active token for the target agent.
    old_token = db.execute(
        text(
            "SELECT id FROM agent_service_tokens "
            "WHERE agent_id = :agent_id AND revoked_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"agent_id": payload.agent_id},
    ).fetchone()

    # Generate new token.
    raw_token = generate_raw_token()
    token_hash = hash_token(raw_token)
    new_token_id = str(uuid.uuid4())

    db.execute(
        text(
            "INSERT INTO agent_service_tokens "
            "(id, agent_id, token_hash, scopes, rotated_from, notes) "
            "SELECT :new_id, :agent_id, :hash, scopes, :old_id, :notes "
            "FROM agent_service_tokens WHERE id = :old_id"
        ) if old_token else text(
            "INSERT INTO agent_service_tokens "
            "(id, agent_id, token_hash, scopes, notes) "
            "VALUES (:new_id, :agent_id, :hash, ARRAY['agent_actions.healthcheck']::text[], :notes)"
        ),
        {
            "new_id": new_token_id,
            "agent_id": payload.agent_id,
            "hash": token_hash,
            "old_id": str(old_token.id) if old_token else None,
            "notes": f"Rotated: {payload.reason}",
        },
    )

    # Schedule old token revocation for 24h later.
    revoke_at = datetime.now(UTC) + timedelta(hours=24)
    if old_token:
        db.execute(
            text(
                "UPDATE agent_service_tokens SET revoked_at = :revoke_at WHERE id = :id"
            ),
            {"id": str(old_token.id), "revoke_at": revoke_at},
        )

    _write_dispatch_log(
        db, trace_id=trace_id, admin_agent_id=agent.agent_id,
        action_type="token.rotate", target_vps="backend-vps",
        target_resource=payload.agent_id,
        payload_redacted={"reason": payload.reason},
        approval_required=True, approval_status="approved",
        outcome="success",
    )

    audit_id = _write_audit(
        db, trace_id=trace_id, agent_id=agent.agent_id,
        action_type="token.rotate", target_type="agent_service_token",
        target_id=payload.agent_id,
        payload_redacted={"reason": payload.reason, "old_revokes_at": revoke_at.isoformat()},
        outcome="success",
    )
    db.commit()

    return RotateTokenResponse(
        agent_id=payload.agent_id,
        new_token=raw_token,
        old_token_revokes_at=revoke_at,
        audit_log_id=audit_id,
    )
