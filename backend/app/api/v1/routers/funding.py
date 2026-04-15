from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.constants import DealState, FundingState
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import Deal, FundingCase
from app.services.audit_service import log_event
from app.services.deal_service import advance_deal_for_trigger

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/{deal_id}/submit-app")
def submit_app(deal_id: str, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    case = db.query(FundingCase).filter(FundingCase.deal_id == deal.id).one_or_none()
    if not case:
        case = FundingCase(deal_id=deal.id, funding_state=FundingState.CREDIT_APP_SUBMITTED)
        db.add(case)
    else:
        case.funding_state = FundingState.CREDIT_APP_SUBMITTED

    deal.funding_state = FundingState.CREDIT_APP_SUBMITTED
    advance_deal_for_trigger(db, deal=deal, trigger="funding_started")

    log_event(db, deal_id=deal.id, event_type="funding_submit_app", actor="agent")
    db.commit()
    return ok({"deal_id": deal.id, "funding_state": deal.funding_state.value})


@router.post("/{deal_id}/confirm")
def confirm_funding(deal_id: str, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    case = db.query(FundingCase).filter(FundingCase.deal_id == deal.id).one_or_none()
    if not case:
        case = FundingCase(deal_id=deal.id, funding_state=FundingState.FULLY_FUNDED)
        db.add(case)
    case.funding_state = FundingState.FULLY_FUNDED
    deal.funding_state = FundingState.FULLY_FUNDED

    advance_deal_for_trigger(db, deal=deal, trigger="funding_confirmed")

    log_event(db, deal_id=deal.id, event_type="funding_confirmed", actor="agent")
    db.commit()
    return ok({"deal_id": deal.id, "funding_state": deal.funding_state.value, "stage": deal.stage.value})
