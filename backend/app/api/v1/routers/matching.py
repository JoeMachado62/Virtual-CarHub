from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import BuyerProfile, Deal, VehicleMatch
from app.services.matching_service import run_matching

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/run/{buyer_id}")
def run_match(buyer_id: str, db: Session = Depends(get_db)) -> dict:
    profile = db.scalar(select(BuyerProfile).where(BuyerProfile.user_id == buyer_id))
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    deal = db.scalar(select(Deal).where(Deal.user_id == buyer_id).order_by(Deal.created_at.desc()).limit(1))
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    rows = run_matching(db, profile=profile, deal=deal)
    db.commit()
    return ok({"buyer_id": buyer_id, "count": len(rows)})


@router.get("/results/{buyer_id}")
def get_match_results(buyer_id: str, db: Session = Depends(get_db)) -> dict:
    deal = db.scalar(select(Deal).where(Deal.user_id == buyer_id).order_by(Deal.created_at.desc()).limit(1))
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    rows = db.scalars(
        select(VehicleMatch)
        .where(VehicleMatch.deal_id == deal.id)
        .order_by(VehicleMatch.match_score.desc())
        .limit(100)
    ).all()

    return ok(
        [
            {
                "vin": row.vin,
                "score": row.match_score,
                "explainability": row.explainability_text,
                "estimated_otd": row.estimated_otd,
            }
            for row in rows
        ]
    )
