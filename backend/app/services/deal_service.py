from datetime import UTC, datetime
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import DealState
from app.core.deal_state_machine import can_transition
from app.models.entities import Deal, DealOutcome
from app.observability.metrics import record_state_transition
from app.services.audit_service import log_event
from app.services.external_sync_service import get_external_sync_service

DEFAULT_STAGE_PATH: list[DealState] = [
    DealState.LEAD,
    DealState.PRE_QUALIFYING,
    DealState.QUALIFIED,
    DealState.ENGAGED,
    DealState.PROFILED,
    DealState.MATCHING,
    DealState.VEHICLE_SELECTED,
    DealState.FUNDING,
    DealState.ACQUISITION_PENDING,
    DealState.ACQUIRED,
    DealState.IN_TRANSIT,
    DealState.DELIVERED,
    DealState.RETURN_PENDING,
]

NON_SHOPPING_STATES: set[DealState] = {
    DealState.DELIVERED,
    DealState.RETURN_PENDING,
    DealState.CLOSED_WON,
    DealState.CLOSED_LOST,
    DealState.DISQUALIFIED,
}


@dataclass(frozen=True)
class DealStageTriggerRule:
    target_state: DealState
    actor: str
    reason: str
    allowed_current_states: frozenset[DealState]


DEAL_STAGE_TRIGGER_MAP: dict[str, DealStageTriggerRule] = {
    "full_profile_completed": DealStageTriggerRule(
        target_state=DealState.PROFILED,
        actor="buyer",
        reason="full_profile_completed",
        allowed_current_states=frozenset(
            {
                DealState.LEAD,
                DealState.PRE_QUALIFYING,
                DealState.QUALIFIED,
                DealState.ENGAGED,
                DealState.PROFILED,
            }
        ),
    ),
    "matching_run_triggered": DealStageTriggerRule(
        target_state=DealState.MATCHING,
        actor="system",
        reason="matching_run_triggered",
        allowed_current_states=frozenset(
            {
                DealState.LEAD,
                DealState.PRE_QUALIFYING,
                DealState.QUALIFIED,
                DealState.ENGAGED,
                DealState.PROFILED,
                DealState.MATCHING,
            }
        ),
    ),
    "quick_matching_run_triggered": DealStageTriggerRule(
        target_state=DealState.MATCHING,
        actor="system",
        reason="quick_matching_run_triggered",
        allowed_current_states=frozenset(
            {
                DealState.LEAD,
                DealState.PRE_QUALIFYING,
                DealState.QUALIFIED,
                DealState.ENGAGED,
                DealState.PROFILED,
                DealState.MATCHING,
            }
        ),
    ),
    "recommendation_selected": DealStageTriggerRule(
        target_state=DealState.VEHICLE_SELECTED,
        actor="buyer",
        reason="recommendation_selected",
        allowed_current_states=frozenset({DealState.MATCHING}),
    ),
    "garage_vehicle_selected": DealStageTriggerRule(
        target_state=DealState.VEHICLE_SELECTED,
        actor="buyer",
        reason="garage_vehicle_selected",
        allowed_current_states=frozenset(
            {
                DealState.LEAD,
                DealState.PRE_QUALIFYING,
                DealState.QUALIFIED,
                DealState.ENGAGED,
                DealState.PROFILED,
                DealState.MATCHING,
            }
        ),
    ),
    "funding_started": DealStageTriggerRule(
        target_state=DealState.FUNDING,
        actor="agent",
        reason="funding_started",
        allowed_current_states=frozenset({DealState.VEHICLE_SELECTED}),
    ),
    "funding_confirmed": DealStageTriggerRule(
        target_state=DealState.ACQUISITION_PENDING,
        actor="agent",
        reason="funding_confirmed",
        allowed_current_states=frozenset({DealState.FUNDING}),
    ),
    "acquisition_confirmed": DealStageTriggerRule(
        target_state=DealState.ACQUIRED,
        actor="agent",
        reason="acquisition_confirmed",
        allowed_current_states=frozenset({DealState.ACQUISITION_PENDING}),
    ),
    "carrier_booked": DealStageTriggerRule(
        target_state=DealState.IN_TRANSIT,
        actor="agent",
        reason="carrier_booked",
        allowed_current_states=frozenset({DealState.ACQUIRED}),
    ),
    "delivery_confirmed": DealStageTriggerRule(
        target_state=DealState.DELIVERED,
        actor="agent",
        reason="delivery_confirmed",
        allowed_current_states=frozenset({DealState.IN_TRANSIT}),
    ),
    "deal_completed": DealStageTriggerRule(
        target_state=DealState.CLOSED_WON,
        actor="system",
        reason="deal_completed",
        allowed_current_states=frozenset({DealState.DELIVERED}),
    ),
}


def get_or_create_active_deal(db: Session, user_id: str) -> Deal:
    # Prefer the newest deal that can still move through the shopping funnel.
    deal = db.scalar(
        select(Deal)
        .where(Deal.user_id == user_id)
        .where(Deal.stage.notin_(list(NON_SHOPPING_STATES)))
        .order_by(Deal.created_at.desc())
        .limit(1)
    )
    if deal:
        return deal

    deal = Deal(user_id=user_id, stage=DealState.LEAD)
    db.add(deal)
    db.flush()
    log_event(
        db,
        deal_id=deal.id,
        event_type="deal_created",
        actor="system",
        new_state=deal.stage.value,
    )
    return deal


def transition_deal_state(
    db: Session,
    *,
    deal: Deal,
    new_state: DealState,
    actor: str,
    reason: str | None = None,
    payload: dict | None = None,
) -> Deal:
    current = deal.stage
    if not can_transition(current, new_state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transition: {current.value} -> {new_state.value}",
        )

    deal.stage = new_state
    if new_state == DealState.DELIVERED and not deal.delivered_at:
        deal.delivered_at = datetime.now(UTC)
    if new_state in {DealState.CLOSED_WON, DealState.CLOSED_LOST}:
        deal.closed_at = datetime.now(UTC)

    data = payload or {}
    if reason:
        data["reason"] = reason

    log_event(
        db,
        deal_id=deal.id,
        event_type="deal_state_transition",
        actor=actor,
        previous_state=current.value,
        new_state=new_state.value,
        payload=data,
    )

    if new_state in {DealState.CLOSED_WON, DealState.CLOSED_LOST}:
        _upsert_deal_outcome(db, deal=deal)

    record_state_transition(
        from_state=current.value,
        to_state=new_state.value,
        actor=actor,
    )

    try:
        sync_service = get_external_sync_service()
        sync_service.sync_deal_state(db=db, deal=deal, previous_state=current, reason=reason)
    except Exception:
        # External sync issues should not block lifecycle progression.
        pass

    db.flush()
    return deal


def advance_deal_to(
    db: Session,
    *,
    deal: Deal,
    target_state: DealState,
    actor: str,
    reason: str | None = None,
    payload: dict | None = None,
) -> Deal:
    if deal.stage == target_state:
        return deal

    try:
        current_idx = DEFAULT_STAGE_PATH.index(deal.stage)
        target_idx = DEFAULT_STAGE_PATH.index(target_state)
    except ValueError:
        return transition_deal_state(
            db,
            deal=deal,
            new_state=target_state,
            actor=actor,
            reason=reason,
            payload=payload,
        )

    if target_idx < current_idx:
        return transition_deal_state(
            db,
            deal=deal,
            new_state=target_state,
            actor=actor,
            reason=reason,
            payload=payload,
        )

    for stage in DEFAULT_STAGE_PATH[current_idx + 1 : target_idx + 1]:
        transition_deal_state(
            db,
            deal=deal,
            new_state=stage,
            actor=actor,
            reason=reason,
            payload=payload if stage == target_state else None,
        )
    return deal


def advance_deal_for_trigger(
    db: Session,
    *,
    deal: Deal,
    trigger: str,
    payload: dict | None = None,
) -> Deal:
    rule = DEAL_STAGE_TRIGGER_MAP.get(trigger)
    if not rule:
        raise ValueError(f"Unknown deal stage trigger: {trigger}")

    if deal.stage not in rule.allowed_current_states:
        return deal

    return advance_deal_to(
        db,
        deal=deal,
        target_state=rule.target_state,
        actor=rule.actor,
        reason=rule.reason,
        payload=payload,
    )


def _upsert_deal_outcome(db: Session, *, deal: Deal) -> None:
    outcome = db.scalar(select(DealOutcome).where(DealOutcome.deal_id == deal.id))
    if not outcome:
        outcome = DealOutcome(deal_id=deal.id, user_id=deal.user_id, outcome="won")
        db.add(outcome)

    created_at = _as_utc(deal.created_at)
    closed_at = _as_utc(deal.closed_at)

    outcome.outcome = "won" if deal.stage == DealState.CLOSED_WON else "lost"
    outcome.lead_created_at = created_at
    outcome.closed_at = closed_at
    if created_at and closed_at:
        outcome.cycle_time_days = (closed_at - created_at).days


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
