from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import DealState
from app.integrations import GHLClient, MarketCheckClient
from app.models.entities import Deal, User
from app.observability.metrics import record_external_sync_error

logger = logging.getLogger("vch.external_sync")


class ExternalSyncService:
    def __init__(self) -> None:
        self.ghl = GHLClient(
            api_key=settings.ghl_api_key,
            api_base_url=settings.ghl_api_base_url,
            api_version=settings.ghl_api_version,
            live=settings.has_ghl,
        )
        self.marketcheck = MarketCheckClient(
            api_key=settings.marketcheck_api_key,
            api_secret=settings.marketcheck_api_secret,
            price_api_key=settings.marketcheck_price_api_key,
            api_base_url=settings.marketcheck_api_base_url,
            live=settings.has_marketcheck,
        )

    def sync_deal_state(self, db: Session, deal: Deal, previous_state: DealState | None, reason: str | None = None) -> None:
        if not settings.has_ghl:
            return

        user = db.get(User, deal.user_id)
        if not user:
            return

        try:
            self._ensure_ghl_contact_and_opportunity(db=db, deal=deal, user=user)
        except Exception as exc:
            record_external_sync_error(provider="ghl", operation="ensure_entities")
            logger.warning("ghl_entity_sync_failed", extra={"deal_id": deal.id, "error": str(exc)})
            return

        try:
            stage_id = self._pipeline_stage_for_state(deal.stage)
            if stage_id and deal.ghl_opportunity_id:
                self.ghl.update_opportunity_stage(deal.ghl_opportunity_id, stage_id)

            if deal.ghl_contact_id:
                note = self._build_stage_note(deal=deal, previous_state=previous_state, reason=reason)
                self.ghl.add_contact_note(deal.ghl_contact_id, note)

            if settings.has_ghl_custom_objects and deal.ghl_contact_id:
                self._sync_operational_custom_objects(deal=deal, user=user)

            if deal.stage == DealState.RETURN_PENDING and deal.ghl_contact_id:
                self.ghl.create_task(
                    {
                        "title": "Return initiated",
                        "description": f"Deal {deal.id} entered RETURN_PENDING",
                        "contactId": deal.ghl_contact_id,
                        "locationId": settings.ghl_location_id,
                        "priority": "high",
                    }
                )

            if deal.stage == DealState.EXCEPTION and deal.ghl_contact_id:
                self.ghl.create_task(
                    {
                        "title": "Deal exception requires manual intervention",
                        "description": (
                            f"Deal {deal.id} moved to EXCEPTION. "
                            "Review quality/funding/title blockers and contact buyer."
                        ),
                        "contactId": deal.ghl_contact_id,
                        "locationId": settings.ghl_location_id,
                        "priority": "high",
                    }
                )

        except Exception as exc:
            record_external_sync_error(provider="ghl", operation="sync_deal_state")
            logger.warning("ghl_stage_sync_failed", extra={"deal_id": deal.id, "error": str(exc)})

    def _ensure_ghl_contact_and_opportunity(self, db: Session, deal: Deal, user: User) -> None:
        if not deal.ghl_contact_id:
            payload = {
                "firstName": user.first_name or "Buyer",
                "lastName": user.last_name or "Contact",
                "email": user.email,
                "phone": user.phone,
                "locationId": settings.ghl_location_id,
                "tags": ["virtual_carhub", "buyer_portal"],
                "source": "Virtual-CarHub",
            }
            try:
                response = self.ghl.create_contact(payload)
                contact = response.get("contact", response)
                deal.ghl_contact_id = contact.get("id")
            except Exception:
                search = self.ghl.search_contacts(location_id=settings.ghl_location_id, query=user.email)
                contacts = search.get("contacts", [])
                if contacts:
                    deal.ghl_contact_id = contacts[0].get("id")

        if not deal.ghl_opportunity_id and deal.ghl_contact_id and settings.ghl_deals_pipeline_id:
            payload = {
                "name": f"Virtual-CarHub Deal {deal.id}",
                "pipelineId": settings.ghl_deals_pipeline_id,
                "pipelineStageId": self._pipeline_stage_for_state(deal.stage) or settings.ghl_stage_new_deal_submitted,
                "locationId": settings.ghl_location_id,
                "contactId": deal.ghl_contact_id,
                "monetaryValue": 0,
                "status": "open",
            }
            response = self.ghl.create_opportunity(payload)
            deal.ghl_opportunity_id = response.get("id")

        db.flush()

    def send_return_authorization(self, user: User, deal: Deal) -> dict | None:
        if not deal.ghl_contact_id:
            return None

        if settings.has_ghl_documents:
            return self.ghl.send_document_template(
                location_id=settings.ghl_location_id,
                template_id=settings.ghl_return_authorization_template_id,
                contact_id=deal.ghl_contact_id,
                custom_values={
                    "deal_id": deal.id,
                    "vin": deal.selected_vin or "UNKNOWN",
                    "buyer_email": user.email,
                },
                endpoint_path=settings.ghl_documents_send_path,
            )

        if settings.has_ghl:
            # Fallback: create an internal task to manually send GHL document template.
            self.ghl.create_task(
                {
                    "title": "Send Return Authorization Document",
                    "description": (
                        f"Deal {deal.id}: send return authorization to {user.email} "
                        "using GHL Documents template."
                    ),
                    "contactId": deal.ghl_contact_id,
                    "locationId": settings.ghl_location_id,
                    "priority": "high",
                }
            )
            return None
        return None

    def _sync_operational_custom_objects(self, deal: Deal, user: User) -> None:
        try:
            if deal.stage in {
                DealState.QUALIFIED,
                DealState.VEHICLE_SELECTED,
                DealState.FUNDING,
                DealState.ACQUISITION_PENDING,
                DealState.ACQUIRED,
                DealState.IN_TRANSIT,
                DealState.DELIVERED,
            }:
                self.ghl.create_custom_object_record(
                    settings.ghl_loan_cases_object_key,
                    {
                        "deal_id": deal.id,
                        "contact_id": deal.ghl_contact_id,
                        "buyer_email": user.email,
                        "funding_state": deal.funding_state.value,
                        "deal_stage": deal.stage.value,
                        "selected_vin": deal.selected_vin,
                    },
                )

            if deal.stage == DealState.RETURN_PENDING:
                self.ghl.create_custom_object_record(
                    settings.ghl_return_cases_object_key,
                    {
                        "deal_id": deal.id,
                        "contact_id": deal.ghl_contact_id,
                        "buyer_email": user.email,
                        "return_state": "RETURN_PENDING",
                        "selected_vin": deal.selected_vin,
                    },
                )
        except Exception:
            record_external_sync_error(provider="ghl", operation="custom_objects_sync")

    def _pipeline_stage_for_state(self, state: DealState) -> str | None:
        stage_map = {
            DealState.LEAD: settings.ghl_stage_new_deal_submitted,
            DealState.PRE_QUALIFYING: settings.ghl_stage_new_deal_submitted,
            DealState.QUALIFIED: settings.ghl_stage_conditional_approval,
            DealState.ENGAGED: settings.ghl_stage_conditional_approval,
            DealState.PROFILED: settings.ghl_stage_conditional_approval,
            DealState.MATCHING: settings.ghl_stage_conditional_approval,
            DealState.VEHICLE_SELECTED: settings.ghl_stage_final_approval,
            DealState.FUNDING: settings.ghl_stage_documents_ready,
            DealState.ACQUISITION_PENDING: settings.ghl_stage_original_docs_qc_review,
            DealState.ACQUIRED: settings.ghl_stage_original_docs_qc_review,
            DealState.IN_TRANSIT: settings.ghl_stage_deal_funded,
            DealState.DELIVERED: settings.ghl_stage_deal_funded,
            DealState.CLOSED_WON: settings.ghl_stage_deal_funded,
            DealState.CLOSED_LOST: settings.ghl_stage_declined,
            DealState.RETURN_PENDING: settings.ghl_stage_declined,
            DealState.EXCEPTION: settings.ghl_stage_new_deal_submitted,
            DealState.DISQUALIFIED: settings.ghl_stage_declined,
        }
        value = stage_map.get(state)
        if value:
            return value
        return None

    def _build_stage_note(self, deal: Deal, previous_state: DealState | None, reason: str | None) -> str:
        prev = previous_state.value if previous_state else "unknown"
        line = f"Deal state updated: {prev} -> {deal.stage.value}."
        if reason:
            line += f" Reason: {reason}."
        return line


@lru_cache(maxsize=1)
def get_external_sync_service() -> ExternalSyncService:
    return ExternalSyncService()
