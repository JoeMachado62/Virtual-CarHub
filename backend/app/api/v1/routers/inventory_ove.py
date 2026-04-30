from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.config import settings as app_settings
from app.core.responses import ok
from app.db.session import get_db
from app.schemas.ove_inventory import (
    OveBulkIngestRequest,
    OveDetailClaimRequest,
    OveDetailCompleteRequest,
    OveDetailFailRequest,
    OveDetailHeartbeatRequest,
    OveDetailPushRequest,
    OveDetailRequestEnqueueRequest,
    OveDetailTerminalRequest,
    OveScraperHeartbeatRequest,
)
from app.services.audit_service import log_event
from app.services.ghl_lifecycle_service import GHLLifecycleService
from app.schemas.hot_deals import HotDealIngestRequest
from app.services.hot_deal_service import HotDealBatchValidationError, ingest_hot_deals, ingest_hot_deals_resilient
from app.services.ove_inventory_service import (
    OveDetailRequestNotFoundError,
    OveDetailRequestOwnershipError,
    OveDetailRequestStateError,
    OveSnapshotRejectedError,
    claim_ove_detail_requests,
    cleanup_stale_ove_inventory,
    complete_ove_detail_request,
    enqueue_ove_detail_request,
    fail_ove_detail_request,
    get_ove_inventory_health,
    get_pending_ove_detail_requests,
    heartbeat_ove_detail_request,
    ingest_ove_inventory,
    prune_unavailable_ove_inventory,
    serialize_request_timestamp,
    terminal_ove_detail_request,
    upsert_ove_vehicle_detail,
    upsert_scraper_heartbeat,
)

router = APIRouter(dependencies=[Depends(require_service_token)])


def _normalized_vin(vin: str) -> str:
    cleaned = vin.strip().upper()
    if len(cleaned) != 17:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VIN must be 17 characters")
    return cleaned


@router.post("/hot-deals/ingest")
def ingest_ove_hot_deals(payload: dict | HotDealIngestRequest, db: Session = Depends(get_db)) -> dict:
    try:
        if isinstance(payload, HotDealIngestRequest):
            report = ingest_hot_deals(db, payload)
        else:
            report = ingest_hot_deals_resilient(db, payload)
    except HotDealBatchValidationError as exc:
        db.rollback()
        log_event(
            db,
            deal_id=None,
            event_type="inventory_ove_hot_deals_rejected",
            actor="system",
            payload=exc.report,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.report,
        ) from exc
    log_event(
        db,
        deal_id=None,
        event_type="inventory_ove_hot_deals_ingest",
        actor="system",
        payload=report,
    )
    db.commit()
    return ok(report)


@router.post("/ingest")
def ingest_ove(payload: OveBulkIngestRequest, db: Session = Depends(get_db)) -> dict:
    try:
        report = ingest_ove_inventory(db, payload)
    except OveSnapshotRejectedError as exc:
        # Reject before any destructive operation; prior good snapshot stays.
        db.rollback()
        log_event(
            db,
            deal_id=None,
            event_type="inventory_ove_snapshot_rejected",
            actor="system",
            payload={"reason": str(exc), "sync_metadata": payload.sync_metadata},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    log_event(
        db,
        deal_id=None,
        event_type="inventory_ove_ingest",
        actor="system",
        payload={
            "requested": report.requested,
            "inserted": report.inserted,
            "updated": report.updated,
            "synced_vins": report.synced_vins,
            "sync_metadata": report.sync_metadata,
        },
    )
    db.commit()
    return ok(report.to_dict())


@router.get("/health")
def ove_inventory_health(db: Session = Depends(get_db)) -> dict:
    """Operational health snapshot for the OVE inventory pipeline.

    Combines three signals into a single traffic-light payload:
      - inventory freshness (max ``vehicles.updated_at`` among active OVE rows)
      - detail-request queue counts by status
      - latest scraper heartbeat across all workers

    Thresholds are configurable via ``OVE_HEALTH_*`` env vars. ``overall``
    is the worst subsystem level: ok < unknown < warning < critical. Wire
    this endpoint into an external monitor (UptimeRobot etc.) and alert on
    any response where ``overall in (warning, critical)``.
    """
    return ok(
        get_ove_inventory_health(
            db,
            stale_warning_minutes=app_settings.ove_health_snapshot_warning_minutes,
            stale_critical_minutes=app_settings.ove_health_snapshot_critical_minutes,
            heartbeat_warning_minutes=app_settings.ove_health_heartbeat_warning_minutes,
            heartbeat_critical_minutes=app_settings.ove_health_heartbeat_critical_minutes,
        )
    )


@router.post("/scraper-heartbeat")
def scraper_heartbeat(payload: OveScraperHeartbeatRequest, db: Session = Depends(get_db)) -> dict:
    """Upsert a scraper liveness signal. Expected to be called by the
    scraper's main loop after every sync tick and every claim poll (so
    every ~30s during normal operation). Partial heartbeats are accepted
    — only fields present in the request body are updated, older values
    are preserved.
    """
    row = upsert_scraper_heartbeat(
        db,
        worker_id=payload.worker_id,
        profile=payload.profile,
        scraper_version=payload.scraper_version,
        node_id=payload.node_id,
        last_sync_at=payload.last_sync_at,
        last_poll_at=payload.last_poll_at,
        last_claim_at=payload.last_claim_at,
        pending_claims=payload.pending_claims,
        status_note=payload.status_note,
        details=payload.details or None,
    )
    db.commit()
    return ok(
        {
            "worker_id": row.worker_id,
            "last_heartbeat_at": serialize_request_timestamp(row.last_heartbeat_at),
            "last_sync_at": serialize_request_timestamp(row.last_sync_at),
            "last_poll_at": serialize_request_timestamp(row.last_poll_at),
            "last_claim_at": serialize_request_timestamp(row.last_claim_at),
            "pending_claims": row.pending_claims,
        }
    )


def _raise_for_request_error(exc: Exception) -> None:
    if isinstance(exc, OveDetailRequestNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, OveDetailRequestOwnershipError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, OveDetailRequestStateError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _serialize_claimed_request(row) -> dict:
    return {
        "request_id": row.id,
        "vin": row.vin,
        "source_platform": row.source_platform.value,
        "priority": row.priority,
        "attempts": row.attempts,
        "requested_at": serialize_request_timestamp(row.requested_at),
        "claimed_at": serialize_request_timestamp(row.claimed_at),
        "lease_expires_at": serialize_request_timestamp(row.lease_expires_at),
        "request_source": row.request_source,
        "requested_by": row.requested_by,
        "reason": row.reason,
        "metadata": row.metadata_json,
    }


@router.get("/detail/pending", deprecated=True)
def pending_ove_detail_requests(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """DIAGNOSTIC ONLY. Read-only view of pending requests.

    Workers MUST use POST /detail/claim instead. This endpoint does not lease
    rows, so calling it from worker code can cause duplicate processing when
    multiple workers are running.
    """
    rows = get_pending_ove_detail_requests(db, limit=limit)
    payload = {
        "items": [
            {
                "request_id": row.id,
                "vin": row.vin,
                "source_platform": row.source_platform.value,
                "status": row.status.value,
                "priority": row.priority,
                "attempts": row.attempts,
                "requested_at": serialize_request_timestamp(row.requested_at),
                "last_polled_at": serialize_request_timestamp(row.last_polled_at),
                "request_source": row.request_source,
                "requested_by": row.requested_by,
                "reason": row.reason,
                "metadata": row.metadata_json,
            }
            for row in rows
        ],
        "count": len(rows),
    }
    return ok(payload)


@router.post("/detail/{vin}/request")
def request_ove_detail(vin: str, payload: OveDetailRequestEnqueueRequest, db: Session = Depends(get_db)) -> dict:
    vin = _normalized_vin(vin)
    request, deduplicated = enqueue_ove_detail_request(db, vin=vin, payload=payload)
    response = {
        "request_id": request.id,
        "vin": request.vin,
        "source_platform": request.source_platform.value,
        "status": request.status.value,
        "deduplicated": deduplicated,
        "priority": request.priority,
        "requested_at": serialize_request_timestamp(request.requested_at),
        "request_source": request.request_source,
        "requested_by": request.requested_by,
        "reason": request.reason,
        "metadata": request.metadata_json,
    }
    log_event(
        db,
        deal_id=None,
        event_type="inventory_ove_detail_requested",
        actor="system",
        payload=response,
    )
    db.commit()
    return ok(response)


@router.post("/cleanup-stale")
def cleanup_stale_ove(
    stale_threshold_days: int = Query(default=None, ge=1, le=30),
    max_mark: int = Query(default=None, ge=1, le=10000),
    prune_unavailable: bool = Query(default=True),
    unavailable_retention_days: int = Query(default=None, ge=1, le=365),
    max_delete: int = Query(default=None, ge=1, le=50000),
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    from app.core.config import settings

    threshold = stale_threshold_days if stale_threshold_days is not None else settings.ove_stale_threshold_days
    cap = max_mark if max_mark is not None else settings.ove_stale_cleanup_max_per_run

    stale_result = cleanup_stale_ove_inventory(
        db,
        stale_threshold_days=threshold,
        max_mark=cap,
        dry_run=dry_run,
    )
    prune_result = None
    if prune_unavailable:
        prune_result = prune_unavailable_ove_inventory(
            db,
            retention_days=(
                unavailable_retention_days
                if unavailable_retention_days is not None
                else settings.ove_unavailable_retention_days
            ),
            max_delete=max_delete if max_delete is not None else settings.ove_unavailable_cleanup_max_per_run,
            dry_run=dry_run,
        )

    result = {"stale": stale_result, "pruned_unavailable": prune_result}

    changed = stale_result.get("marked_unavailable", 0) > 0 or (
        prune_result is not None and prune_result.get("deleted", 0) > 0
    )
    if not dry_run and changed:
        log_event(
            db,
            deal_id=None,
            event_type="inventory_ove_stale_cleanup",
            actor="system",
            payload=result,
        )
        db.commit()

    return ok(result)


# ---------------------------------------------------------------------------
# Lease-based claim queue
# ---------------------------------------------------------------------------


@router.post("/detail/claim")
def claim_ove_detail(payload: OveDetailClaimRequest, db: Session = Depends(get_db)) -> dict:
    rows = claim_ove_detail_requests(
        db,
        worker_id=payload.worker_id,
        limit=payload.limit,
        lease_seconds=payload.lease_seconds,
    )
    items = [_serialize_claimed_request(row) for row in rows]
    response = {
        "worker_id": payload.worker_id,
        "lease_seconds": payload.lease_seconds,
        "items": items,
        "count": len(items),
    }
    if items:
        log_event(
            db,
            deal_id=None,
            event_type="inventory_ove_detail_claim",
            actor=payload.worker_id,
            payload={
                "worker_id": payload.worker_id,
                "claimed_count": len(items),
                "lease_seconds": payload.lease_seconds,
                "request_ids": [item["request_id"] for item in items],
            },
        )
    db.commit()
    return ok(response)


@router.post("/detail/{request_id}/complete")
def complete_ove_detail(
    request_id: str,
    payload: OveDetailCompleteRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        request = complete_ove_detail_request(
            db,
            request_id=request_id,
            worker_id=payload.worker_id,
            result=payload.result,
        )
    except (OveDetailRequestNotFoundError, OveDetailRequestOwnershipError, OveDetailRequestStateError) as exc:
        db.rollback()
        _raise_for_request_error(exc)
    response = {
        "request_id": request.id,
        "vin": request.vin,
        "status": request.status.value,
        "completed_at": serialize_request_timestamp(request.completed_at),
        "result": payload.result,
    }
    log_event(
        db,
        deal_id=None,
        event_type="inventory_ove_detail_complete",
        actor=payload.worker_id,
        payload=response,
    )
    db.commit()
    return ok(response)


@router.post("/detail/{request_id}/fail")
def fail_ove_detail(
    request_id: str,
    payload: OveDetailFailRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        request = fail_ove_detail_request(
            db,
            request_id=request_id,
            worker_id=payload.worker_id,
            error_category=payload.error_category,
            error_message=payload.error_message,
            retry_after_seconds=payload.retry_after_seconds,
        )
    except (OveDetailRequestNotFoundError, OveDetailRequestOwnershipError, OveDetailRequestStateError) as exc:
        db.rollback()
        _raise_for_request_error(exc)
    response = {
        "request_id": request.id,
        "vin": request.vin,
        "status": request.status.value,
        "error_category": request.last_error_category,
        "error_message": request.last_error,
        "next_retry_at": serialize_request_timestamp(request.next_retry_at),
        "attempts": request.attempts,
    }
    log_event(
        db,
        deal_id=None,
        event_type="inventory_ove_detail_fail",
        actor=payload.worker_id,
        payload=response,
    )
    db.commit()
    return ok(response)


@router.post("/detail/{request_id}/terminal")
def terminal_ove_detail(
    request_id: str,
    payload: OveDetailTerminalRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        request = terminal_ove_detail_request(
            db,
            request_id=request_id,
            worker_id=payload.worker_id,
            reason=payload.reason,
            message=payload.message,
        )
    except (OveDetailRequestNotFoundError, OveDetailRequestOwnershipError, OveDetailRequestStateError) as exc:
        db.rollback()
        _raise_for_request_error(exc)
    response = {
        "request_id": request.id,
        "vin": request.vin,
        "status": request.status.value,
        "terminal_reason": request.terminal_reason,
        "terminal_message": request.terminal_message,
    }
    log_event(
        db,
        deal_id=None,
        event_type="inventory_ove_detail_terminal",
        actor=payload.worker_id,
        payload=response,
    )
    db.commit()
    return ok(response)


@router.post("/detail/{request_id}/heartbeat")
def heartbeat_ove_detail(
    request_id: str,
    payload: OveDetailHeartbeatRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        request = heartbeat_ove_detail_request(
            db,
            request_id=request_id,
            worker_id=payload.worker_id,
            lease_seconds=payload.lease_seconds,
        )
    except (OveDetailRequestNotFoundError, OveDetailRequestOwnershipError, OveDetailRequestStateError) as exc:
        db.rollback()
        _raise_for_request_error(exc)
    response = {
        "request_id": request.id,
        "vin": request.vin,
        "status": request.status.value,
        "lease_expires_at": serialize_request_timestamp(request.lease_expires_at),
    }
    db.commit()
    return ok(response)


# ---------------------------------------------------------------------------
# Dynamic VIN route — MUST be declared LAST so static /detail/* routes
# (claim, {request_id}/complete, etc.) are matched before this catch-all.
# ---------------------------------------------------------------------------


@router.post("/detail/{vin}")
def push_ove_detail(vin: str, payload: OveDetailPushRequest, db: Session = Depends(get_db)) -> dict:
    vin = _normalized_vin(vin)
    try:
        detail, completed_requests, hero_job_queued = upsert_ove_vehicle_detail(db, vin=vin, payload=payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        GHLLifecycleService().handle_condition_report_completion(db, detail=detail, completed_requests=completed_requests)
    except Exception:
        pass

    response = {
        "vin": detail.vin,
        "source_platform": detail.source_platform.value,
        "detail_saved": True,
        "images_synced": len(payload.images),
        "hero_job_queued": hero_job_queued,
        "completed_request_ids": [row.id for row in completed_requests],
        "seller_comments_present": bool(payload.seller_comments),
        "listing_snapshot_present": bool(
            payload.listing_snapshot.model_dump(exclude_none=True, exclude_defaults=True)
        ),
        "condition_report_present": bool(payload.condition_report),
        "sync_metadata": payload.sync_metadata,
    }
    log_event(
        db,
        deal_id=None,
        event_type="inventory_ove_detail_upsert",
        actor="system",
        payload=response,
    )
    db.commit()
    return ok(response)
