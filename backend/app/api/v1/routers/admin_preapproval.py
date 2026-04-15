"""Admin endpoints for managing user pre-approval status"""

from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from app.db.session import get_db
from app.models.entities import User, Deal
from app.core.constants import FundingState
from app.api.deps import get_current_user, is_admin_user
from app.services.external_sync_service import get_external_sync_service


router = APIRouter()


class PreApprovalUpdate(BaseModel):
    is_preapproved: bool = Field(..., description="Whether the user is pre-approved")
    preapproved_amount: Optional[float] = Field(None, description="Maximum approved loan amount")
    preapproved_until: Optional[datetime] = Field(None, description="Pre-approval expiration date")
    external_financing_bank: Optional[str] = Field(None, description="External financing bank name")
    external_financing_status: Optional[str] = Field(None, description="Status of external financing")


class DocumentStatusUpdate(BaseModel):
    identity_verified: bool = Field(False, description="Whether identity documents are verified")
    income_verified: bool = Field(False, description="Whether income documents are verified")
    preapproval_letter_url: Optional[str] = Field(None, description="URL to pre-approval letter")
    loan_documents_url: Optional[str] = Field(None, description="URL to loan documents")
    documents_collected: Optional[dict] = Field(default_factory=dict, description="Map of document types to URLs")


@router.get("/users/{user_id}/preapproval")
def get_user_preapproval_status(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get pre-approval and document status for a user"""
    # Allow users to see their own status, admins can see anyone's
    if user_id != current_user.id and not is_admin_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Get the latest deal for document status
    latest_deal = db.query(Deal).filter(Deal.user_id == user_id).order_by(Deal.created_at.desc()).first()

    return {
        "user_id": user.id,
        "email": user.email,
        "is_preapproved": user.is_preapproved,
        "preapproved_amount": user.preapproved_amount,
        "preapproved_until": user.preapproved_until.isoformat() if user.preapproved_until else None,
        "preapproval_expired": user.preapproved_until < datetime.now(UTC) if user.preapproved_until else False,
        "deal_status": {
            "has_deal": latest_deal is not None,
            "funding_state": latest_deal.funding_state.value if latest_deal else None,
            "identity_verified": latest_deal.identity_verified if latest_deal else False,
            "income_verified": latest_deal.income_verified if latest_deal else False,
            "external_financing_bank": latest_deal.external_financing_bank if latest_deal else None,
            "external_financing_status": latest_deal.external_financing_status if latest_deal else None,
            "documents_collected": latest_deal.documents_collected if latest_deal else {},
        } if latest_deal else None,
    }


@router.put("/users/{user_id}/preapproval")
def update_user_preapproval(
    user_id: str,
    update: PreApprovalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update pre-approval status for a user (admin only)"""
    if not is_admin_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update user pre-approval fields
    user.is_preapproved = update.is_preapproved
    if update.preapproved_amount is not None:
        user.preapproved_amount = update.preapproved_amount
    if update.preapproved_until is not None:
        user.preapproved_until = update.preapproved_until

    # Update the latest deal if external financing info is provided
    latest_deal = db.query(Deal).filter(Deal.user_id == user_id).order_by(Deal.created_at.desc()).first()
    if update.external_financing_bank or update.external_financing_status:
        if latest_deal:
            if update.external_financing_bank:
                latest_deal.external_financing_bank = update.external_financing_bank
            if update.external_financing_status:
                latest_deal.external_financing_status = update.external_financing_status

            # If user is pre-approved via external financing, update funding state
            if update.is_preapproved and latest_deal.funding_state == FundingState.CREDIT_APP_PENDING:
                latest_deal.funding_state = FundingState.PRE_APPROVED

    try:
        get_external_sync_service().sync_contact_snapshot(db, user=user, deal=latest_deal)
    except Exception:
        pass

    db.commit()
    db.refresh(user)

    return {
        "message": "Pre-approval status updated successfully",
        "user_id": user.id,
        "is_preapproved": user.is_preapproved,
        "preapproved_amount": user.preapproved_amount,
        "preapproved_until": user.preapproved_until.isoformat() if user.preapproved_until else None,
    }


@router.put("/deals/{deal_id}/documents")
def update_deal_documents(
    deal_id: str,
    update: DocumentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update document status for a deal (admin only)"""
    if not is_admin_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    # Update document verification status
    deal.identity_verified = update.identity_verified
    deal.income_verified = update.income_verified

    # Update document URLs
    if update.preapproval_letter_url:
        deal.preapproval_letter_url = update.preapproval_letter_url
    if update.loan_documents_url:
        deal.loan_documents_url = update.loan_documents_url

    # Merge document collection tracking
    if update.documents_collected:
        current_docs = deal.documents_collected or {}
        current_docs.update(update.documents_collected)
        deal.documents_collected = current_docs

    db.commit()
    db.refresh(deal)

    return {
        "message": "Document status updated successfully",
        "deal_id": deal.id,
        "identity_verified": deal.identity_verified,
        "income_verified": deal.income_verified,
        "documents_collected": deal.documents_collected,
    }


@router.get("/preapproval/pending")
def get_pending_preapprovals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get list of users pending pre-approval (admin only)"""
    if not is_admin_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    # Find deals in CREDIT_APP_SUBMITTED state with no pre-approval
    pending_deals = (
        db.query(Deal)
        .join(User)
        .filter(
            Deal.funding_state == FundingState.CREDIT_APP_SUBMITTED,
            User.is_preapproved == False,
        )
        .all()
    )

    return {
        "pending_count": len(pending_deals),
        "pending_users": [
            {
                "user_id": deal.user_id,
                "deal_id": deal.id,
                "email": deal.user.email,
                "name": f"{deal.user.first_name or ''} {deal.user.last_name or ''}".strip() or "N/A",
                "created_at": deal.created_at.isoformat(),
                "external_financing_bank": deal.external_financing_bank,
                "documents_collected": len(deal.documents_collected) if deal.documents_collected else 0,
            }
            for deal in pending_deals
        ],
    }
