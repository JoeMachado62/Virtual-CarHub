from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.responses import ok
from app.db.session import get_db
from app.schemas.ove_inventory import (
    OveBulkIngestRequest,
    OveDetailPushRequest,
    OveDetailRequestEnqueueRequest,
)
from app.services.audit_service import log_event
from app.services.ove_inventory_service import (
    enqueue_ove_detail_request,
    get_pending_ove_detail_requests,
    ingest_ove_inventory,
    serialize_request_timestamp,
    upsert_ove_vehicle_detail,
)

router = APIRouter(dependencies=[Depends(require_service_token)])


def _normalized_vin(vin: str) -> str:
    cleaned = vin.strip().upper()
    if len(cleaned) != 17:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VIN must be 17 characters")
    return cleaned


@router.post("/ingest")
def ingest_ove(payload: OveBulkIngestRequest, db: Session = Depends(get_db)) -> dict:
    report = ingest_ove_inventory(db, payload)
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


@router.post("/detail/{vin}")
def push_ove_detail(vin: str, payload: OveDetailPushRequest, db: Session = Depends(get_db)) -> dict:
    vin = _normalized_vin(vin)
    try:
        detail, completed_requests, hero_job_queued = upsert_ove_vehicle_detail(db, vin=vin, payload=payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

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


@router.get("/detail/pending")
def pending_ove_detail_requests(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
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
