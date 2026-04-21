from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import DealState, FundingState
from app.integrations import GHLClient
from app.models.entities import BuyerProfile, Deal, FundingCase, OveDetailRequest, OveVehicleDetail, User, Vehicle
from app.services.audit_service import log_event
from app.services.email_service import send_condition_report_ready_email
from app.services.notification_service import create_notification

logger = logging.getLogger("vch.ghl_lifecycle")


def _titleize(value: str) -> str:
    return value.replace("_", " ").title()


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if _is_blank(value):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        normalized = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


class GHLLifecycleService:
    def __init__(self) -> None:
        self.ghl = GHLClient(
            api_key=settings.ghl_api_key,
            api_base_url=settings.ghl_api_base_url,
            api_version=settings.ghl_api_version,
            live=settings.has_ghl,
        )

    def pipeline_stage_for_state(self, state: DealState) -> str | None:
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
        return stage_map.get(state) or None

    def fallback_state_for_pipeline_stage(self, stage_id: str | None) -> DealState | None:
        if not stage_id:
            return None
        stage_map = {
            settings.ghl_stage_new_deal_submitted: DealState.LEAD,
            settings.ghl_stage_conditional_approval: DealState.QUALIFIED,
            settings.ghl_stage_final_approval: DealState.VEHICLE_SELECTED,
            settings.ghl_stage_documents_ready: DealState.FUNDING,
            settings.ghl_stage_original_docs_qc_review: DealState.ACQUISITION_PENDING,
            settings.ghl_stage_deal_funded: DealState.IN_TRANSIT,
            settings.ghl_stage_declined: DealState.CLOSED_LOST,
        }
        return stage_map.get(stage_id)

    def bind_contact_ids(self, *, user: User, deal: Deal | None = None, contact_id: str | None = None) -> str | None:
        canonical = contact_id or user.ghl_contact_id or (deal.ghl_contact_id if deal else None)
        if not canonical:
            return None
        if user.ghl_contact_id != canonical:
            user.ghl_contact_id = canonical
        if deal and deal.ghl_contact_id != canonical:
            deal.ghl_contact_id = canonical
        return canonical

    def sync_contact_snapshot(self, db: Session, *, user: User, deal: Deal | None = None) -> dict | None:
        contact_id = self.bind_contact_ids(user=user, deal=deal)
        if not settings.has_ghl or not contact_id:
            return None

        payload: dict[str, Any] = {
            "firstName": user.first_name or "Buyer",
            "lastName": user.last_name or "Contact",
            "email": user.email,
            "phone": user.phone,
        }
        custom_fields = self._build_contact_custom_fields(db, user=user, deal=deal)
        if custom_fields:
            payload["customFields"] = custom_fields
        self.ghl.update_contact(contact_id, payload)
        return payload

    def reconcile_contact_from_ghl(self, db: Session, *, user: User) -> dict:
        """Pull current contact state from GHL and apply to VCH (GHL wins)."""
        contact_id = user.ghl_contact_id
        if not settings.has_ghl or not contact_id:
            return {"skipped": True, "reason": "no_ghl_contact_id"}

        response = self.ghl.get_contact(contact_id)
        contact = response.get("contact", response)

        # Reshape GHL GET response into webhook-compatible payload
        payload: dict[str, Any] = {
            "type": "ghl_reconcile",
            "contactId": contact_id,
            "firstName": contact.get("firstName"),
            "lastName": contact.get("lastName"),
            "email": contact.get("email"),
            "phone": contact.get("phone"),
            "customFields": contact.get("customFields", []),
        }

        deal = self._resolve_deal(
            db, payload=payload, opportunity_id=None,
            contact_id=contact_id, user=user,
        )

        updated_fields: list[str] = []
        updated_fields.extend(
            self._apply_user_updates(db, payload=payload, user=user, deal=deal, contact_id=contact_id)
        )
        if deal:
            updated_fields.extend(
                self._apply_deal_updates(
                    db, payload=payload, deal=deal, user=user,
                    opportunity_id=None, contact_id=contact_id,
                )
            )

        return {
            "user_id": user.id,
            "contact_id": contact_id,
            "updated_fields": updated_fields,
            "updated": bool(updated_fields),
        }

    def _update_contact_custom_fields(self, contact_id: str, fields: list[dict[str, Any]]) -> None:
        if not settings.has_ghl or not contact_id or not fields:
            return
        self.ghl.update_contact(contact_id, {"customFields": fields})

    def record_condition_report_requested(
        self,
        *,
        user: User,
        deal: Deal,
        vin: str,
        requested_at: datetime | None = None,
    ) -> None:
        contact_id = self.bind_contact_ids(user=user, deal=deal)
        if not settings.has_ghl or not contact_id:
            return
        ts = (requested_at or datetime.now(UTC)).isoformat()
        note = f"Client requested CR on {vin} at {ts}."
        self.ghl.add_contact_note(contact_id, note)
        self._update_contact_custom_fields(
            contact_id,
            [
                {
                    "id": settings.ghl_contact_cf_vch_cr_last_requested_at,
                    "value": ts,
                }
            ],
        )

    def record_condition_report_completed(
        self,
        *,
        user: User,
        deal: Deal,
        vin: str,
        report_url: str | None,
        completed_at: datetime | None = None,
    ) -> None:
        contact_id = self.bind_contact_ids(user=user, deal=deal)
        if not settings.has_ghl or not contact_id:
            return
        ts = (completed_at or datetime.now(UTC)).isoformat()
        note = f"CR completed for {vin} at {ts}."
        if report_url:
            note += f" Report: {report_url}"
        self.ghl.add_contact_note(contact_id, note)
        fields = [
            {
                "id": settings.ghl_contact_cf_vch_cr_last_completed_at,
                "value": ts,
            }
        ]
        if report_url:
            fields.append({"id": settings.ghl_contact_cf_vch_cr_last_url, "value": report_url})
        self._update_contact_custom_fields(contact_id, fields)

    def record_garage_acquisition_started(
        self,
        *,
        user: User,
        deal: Deal,
        vin: str,
        started_at: datetime | None = None,
    ) -> None:
        contact_id = self.bind_contact_ids(user=user, deal=deal)
        if not settings.has_ghl or not contact_id:
            return
        ts = (started_at or datetime.now(UTC)).isoformat()
        self.ghl.add_contact_note(contact_id, f"Buyer clicked Start Acquisition for {vin} at {ts}.")

    def handle_condition_report_completion(
        self,
        db: Session,
        *,
        detail: OveVehicleDetail,
        completed_requests: list[OveDetailRequest],
    ) -> None:
        report_url = self._extract_condition_report_url(detail)
        vehicle = db.get(Vehicle, detail.vin)
        for request in completed_requests:
            metadata = request.metadata_json or {}
            user_id = metadata.get("user_id")
            deal_id = metadata.get("deal_id")
            if not user_id or not deal_id:
                continue
            user = db.get(User, user_id)
            deal = db.get(Deal, deal_id)
            if not user or not deal:
                continue

            self.record_condition_report_completed(
                user=user,
                deal=deal,
                vin=detail.vin,
                report_url=report_url,
                completed_at=request.completed_at or datetime.now(UTC),
            )
            create_notification(
                db,
                user_id=user.id,
                deal_id=deal.id,
                message=f"Your condition report for {detail.vin} is now ready.",
            )
            send_condition_report_ready_email(
                user=user,
                vin=detail.vin,
                vehicle=vehicle,
                detail=detail,
                report_url=report_url,
            )
            log_event(
                db,
                deal_id=deal.id,
                event_type="buyer_condition_report_completed",
                actor="system",
                payload={
                    "vin": detail.vin,
                    "request_id": request.id,
                    "report_url": report_url,
                },
            )

    def process_webhook(self, db: Session, payload: dict) -> dict:
        event_name = self._event_name(payload)
        contact_id = self._contact_id_from_payload(payload, event_name)
        opportunity_id = self._opportunity_id_from_payload(payload, event_name)

        user = self._resolve_user(db, payload=payload, contact_id=contact_id)
        deal = self._resolve_deal(
            db,
            payload=payload,
            opportunity_id=opportunity_id,
            contact_id=contact_id,
            user=user,
        )

        updated_fields: list[str] = []
        if user:
            updated_fields.extend(self._apply_user_updates(db, payload=payload, user=user, deal=deal, contact_id=contact_id))
        if deal:
            if user:
                self.bind_contact_ids(user=user, deal=deal, contact_id=contact_id)
            updated_fields.extend(
                self._apply_deal_updates(
                    db,
                    payload=payload,
                    deal=deal,
                    user=user,
                    opportunity_id=opportunity_id,
                    contact_id=contact_id,
                )
            )

        return {
            "accepted": True,
            "event": event_name or "unknown",
            "updated": bool(updated_fields),
            "updated_fields": updated_fields,
            "deal_id": deal.id if deal else None,
            "user_id": user.id if user else None,
        }

    def _build_contact_custom_fields(self, db: Session, *, user: User, deal: Deal | None = None) -> list[dict[str, Any]]:
        profile = db.scalar(select(BuyerProfile).where(BuyerProfile.user_id == user.id))
        funding_case = db.scalar(select(FundingCase).where(FundingCase.deal_id == deal.id)) if deal else None
        fields: list[dict[str, Any]] = []

        def add(field_id: str, value: Any) -> None:
            if not field_id or _is_blank(value):
                return
            fields.append({"id": field_id, "value": value})

        add(settings.ghl_contact_cf_vch_user_id, user.id)
        add(settings.ghl_contact_cf_vch_preapproved, str(user.is_preapproved).lower())
        add(settings.ghl_contact_cf_vch_preapproval_amount, user.preapproved_amount)
        add(
            settings.ghl_contact_cf_vch_preapproval_until,
            user.preapproved_until.astimezone(UTC).isoformat() if user.preapproved_until else None,
        )

        if profile:
            add(settings.ghl_contact_cf_vch_profile_tier, profile.profile_tier.value)
            add(settings.ghl_contact_cf_vch_profile_completion_pct, self._profile_completion_pct(profile))

        if deal:
            add(settings.ghl_contact_cf_vch_deal_id, deal.id)
            add(settings.ghl_contact_cf_vch_deal_stage, deal.stage.value)
            add(settings.ghl_contact_cf_vch_funding_state, deal.funding_state.value)
            add(settings.ghl_contact_cf_vch_selected_vin, deal.selected_vin)
            add(settings.ghl_contact_cf_vch_lender_name, deal.external_financing_bank)

        if funding_case:
            add(settings.ghl_contact_cf_vch_lender_name, funding_case.lender_id)

        return fields

    def _profile_completion_pct(self, profile: BuyerProfile) -> int:
        completed_steps = len(profile.intake_steps_complete or [])
        if profile.is_complete:
            return 100
        return min(int((completed_steps / 24) * 100), 99)

    def _apply_user_updates(
        self,
        db: Session,
        *,
        payload: dict,
        user: User,
        deal: Deal | None,
        contact_id: str | None,
    ) -> list[str]:
        updated: list[str] = []
        if contact_id and user.ghl_contact_id != contact_id:
            user.ghl_contact_id = contact_id
            updated.append("user.ghl_contact_id")

        first_name = self._extract_value(payload, "firstName", "contact.firstName", "contact.first_name")
        last_name = self._extract_value(payload, "lastName", "contact.lastName", "contact.last_name")
        email = self._extract_value(payload, "email", "contact.email")
        phone = self._extract_value(payload, "phone", "contact.phone")

        for attr, value in (
            ("first_name", first_name),
            ("last_name", last_name),
            ("email", email),
            ("phone", phone),
        ):
            if value and getattr(user, attr) != value:
                setattr(user, attr, value)
                updated.append(f"user.{attr}")

        previous_preapproved = user.is_preapproved
        preapproved = _parse_bool(self._configured_custom_field(payload, settings.ghl_contact_cf_vch_preapproved))
        if preapproved is not None and user.is_preapproved != preapproved:
            user.is_preapproved = preapproved
            updated.append("user.is_preapproved")

        amount = self._configured_custom_field(payload, settings.ghl_contact_cf_vch_preapproval_amount)
        if not _is_blank(amount):
            try:
                amount_value = float(amount)
            except (TypeError, ValueError):
                amount_value = None
            if amount_value is not None and user.preapproved_amount != amount_value:
                user.preapproved_amount = amount_value
                updated.append("user.preapproved_amount")

        until = _parse_datetime(self._configured_custom_field(payload, settings.ghl_contact_cf_vch_preapproval_until))
        if until and user.preapproved_until != until:
            user.preapproved_until = until
            updated.append("user.preapproved_until")

        if previous_preapproved != user.is_preapproved:
            message = (
                "You are now pre-approved in My Garage."
                if user.is_preapproved
                else "Your pre-approval status was updated in My Garage."
            )
            create_notification(db, user_id=user.id, deal_id=deal.id if deal else None, message=message)

        return updated

    def _apply_deal_updates(
        self,
        db: Session,
        *,
        payload: dict,
        deal: Deal,
        user: User | None,
        opportunity_id: str | None,
        contact_id: str | None,
    ) -> list[str]:
        updated: list[str] = []
        if opportunity_id and deal.ghl_opportunity_id != opportunity_id:
            deal.ghl_opportunity_id = opportunity_id
            updated.append("deal.ghl_opportunity_id")
        if contact_id and deal.ghl_contact_id != contact_id:
            deal.ghl_contact_id = contact_id
            updated.append("deal.ghl_contact_id")

        explicit_stage = self._configured_custom_field(payload, settings.ghl_contact_cf_vch_deal_stage)
        if explicit_stage:
            new_state = self._parse_deal_state(explicit_stage)
        else:
            stage_id = self._extract_value(
                payload,
                "pipelineStageId",
                "stageId",
                "opportunity.pipelineStageId",
                "objectData.pipelineStageId",
            )
            new_state = self.fallback_state_for_pipeline_stage(stage_id)
        if new_state and deal.stage != new_state:
            previous = deal.stage
            deal.stage = new_state
            if new_state == DealState.DELIVERED and not deal.delivered_at:
                deal.delivered_at = datetime.now(UTC)
            if new_state in {DealState.CLOSED_WON, DealState.CLOSED_LOST}:
                deal.closed_at = datetime.now(UTC)
            updated.append("deal.stage")
            log_event(
                db,
                deal_id=deal.id,
                event_type="ghl_stage_applied",
                actor="system",
                previous_state=previous.value,
                new_state=new_state.value,
                payload={"event": self._event_name(payload)},
            )
            if user:
                create_notification(
                    db,
                    user_id=user.id,
                    deal_id=deal.id,
                    message=f"Your deal moved to {_titleize(new_state.value)}.",
                )

        explicit_funding = self._configured_custom_field(payload, settings.ghl_contact_cf_vch_funding_state)
        new_funding_state = self._parse_funding_state(explicit_funding)
        if new_funding_state and deal.funding_state != new_funding_state:
            deal.funding_state = new_funding_state
            updated.append("deal.funding_state")

        selected_vin = self._configured_custom_field(payload, settings.ghl_contact_cf_vch_selected_vin)
        if selected_vin and deal.selected_vin != selected_vin:
            deal.selected_vin = str(selected_vin).strip().upper()
            updated.append("deal.selected_vin")

        return updated

    def _resolve_user(self, db: Session, *, payload: dict, contact_id: str | None) -> User | None:
        explicit_user_id = self._configured_custom_field(payload, settings.ghl_contact_cf_vch_user_id)
        if explicit_user_id:
            user = db.get(User, str(explicit_user_id))
            if user:
                return user

        if contact_id:
            user = db.scalar(select(User).where(User.ghl_contact_id == contact_id))
            if user:
                return user

            deal = db.scalar(
                select(Deal)
                .where(Deal.ghl_contact_id == contact_id)
                .order_by(Deal.created_at.desc())
                .limit(1)
            )
            if deal:
                return db.get(User, deal.user_id)
        return None

    def _resolve_deal(
        self,
        db: Session,
        *,
        payload: dict,
        opportunity_id: str | None,
        contact_id: str | None,
        user: User | None,
    ) -> Deal | None:
        explicit_deal_id = self._configured_custom_field(payload, settings.ghl_contact_cf_vch_deal_id) or payload.get("deal_id")
        if explicit_deal_id:
            deal = db.get(Deal, str(explicit_deal_id))
            if deal:
                return deal

        if opportunity_id:
            deal = db.scalar(select(Deal).where(Deal.ghl_opportunity_id == opportunity_id))
            if deal:
                return deal

        if contact_id:
            deal = db.scalar(
                select(Deal)
                .where(or_(Deal.ghl_contact_id == contact_id, Deal.user_id == (user.id if user else None)))
                .order_by(Deal.created_at.desc())
                .limit(1)
            )
            if deal:
                return deal

        if user:
            return db.scalar(select(Deal).where(Deal.user_id == user.id).order_by(Deal.created_at.desc()).limit(1))
        return None

    def _configured_custom_field(self, payload: dict, field_id: str) -> Any:
        if not field_id:
            return None
        for item in self._iter_custom_fields(payload):
            key = str(item.get("id") or item.get("fieldId") or item.get("key") or "").strip()
            if key != field_id:
                continue
            for value_key in ("value", "fieldValue", "valueString", "valueNumber", "valueBoolean", "valueDate"):
                value = item.get(value_key)
                if not _is_blank(value):
                    return value
        return None

    # Map from GHL custom field display name → settings attribute holding the field ID.
    # Used to resolve flat key-value payloads from GHL workflow webhooks.
    _FIELD_NAME_TO_SETTING: dict[str, str] = {
        "VCH User ID": "ghl_contact_cf_vch_user_id",
        "VCH Deal ID": "ghl_contact_cf_vch_deal_id",
        "VCH Deal Stage": "ghl_contact_cf_vch_deal_stage",
        "VCH Funding State": "ghl_contact_cf_vch_funding_state",
        "VCH Selected VIN": "ghl_contact_cf_vch_selected_vin",
        "VCH Profile Tier": "ghl_contact_cf_vch_profile_tier",
        "VCH Profile Completion %": "ghl_contact_cf_vch_profile_completion_pct",
        "VCH Preapproved": "ghl_contact_cf_vch_preapproved",
        "VCH Preapproval Amount": "ghl_contact_cf_vch_preapproval_amount",
        "VCH Preapproval Until": "ghl_contact_cf_vch_preapproval_until",
        "VCH CR Last Requested At": "ghl_contact_cf_vch_cr_last_requested_at",
        "VCH CR Last Completed At": "ghl_contact_cf_vch_cr_last_completed_at",
        "VCH CR Last URL": "ghl_contact_cf_vch_cr_last_url",
        "RouteOne Application ID": "ghl_contact_cf_routeone_app_id",
        "VCH Lender Name": "ghl_contact_cf_vch_lender_name",
    }

    def _iter_custom_fields(self, payload: dict) -> list[dict]:
        entries: list[dict] = []
        for candidate in (
            payload.get("customFields"),
            payload.get("custom_fields"),
            self._extract_value(payload, "contact.customFields"),
            self._extract_value(payload, "contact.custom_fields"),
            self._extract_value(payload, "opportunity.customFields"),
            self._extract_value(payload, "opportunity.custom_fields"),
            self._extract_value(payload, "objectData.customFields"),
            self._extract_value(payload, "data.customFields"),
            self._extract_value(payload, "record.customFields"),
            self._extract_value(payload, "properties"),
        ):
            if isinstance(candidate, list):
                entries.extend([item for item in candidate if isinstance(item, dict)])

        # GHL workflow webhooks send custom fields as flat top-level keys by
        # display name (e.g. "VCH Preapproved": "Yes") instead of the
        # customFields array. Synthesize entries so downstream matching by
        # field ID works unchanged.
        if not entries:
            for name, setting_attr in self._FIELD_NAME_TO_SETTING.items():
                value = payload.get(name)
                if not _is_blank(value):
                    field_id = getattr(settings, setting_attr, "")
                    if field_id:
                        entries.append({"id": field_id, "value": value})

        return entries

    def _event_name(self, payload: dict) -> str:
        for path in ("type", "event", "eventType", "webhookType"):
            value = self._extract_value(payload, path)
            if value:
                return str(value)
        return ""

    def _contact_id_from_payload(self, payload: dict, event_name: str) -> str | None:
        candidates = (
            "contactId",
            "contact_id",
            "contact.id",
            "objectData.contactId",
            "opportunity.contactId",
            "data.contactId",
        )
        value = self._extract_value(payload, *candidates)
        if value:
            return str(value)
        if "contact" in event_name.lower():
            contact_id = self._extract_value(payload, "id", "objectData.id")
            if contact_id:
                return str(contact_id)
        return None

    def _opportunity_id_from_payload(self, payload: dict, event_name: str) -> str | None:
        candidates = ("opportunityId", "opportunity.id", "objectData.id")
        value = self._extract_value(payload, *candidates)
        if value:
            return str(value)
        stage_hint = self._extract_value(payload, "pipelineStageId", "stageId", "opportunity.pipelineStageId")
        if stage_hint or "opportun" in event_name.lower():
            opportunity_id = self._extract_value(payload, "id")
            if opportunity_id:
                return str(opportunity_id)
        return None

    def _extract_value(self, payload: dict, *paths: str) -> Any:
        for path in paths:
            current: Any = payload
            found = True
            for segment in path.split("."):
                if not isinstance(current, dict) or segment not in current:
                    found = False
                    break
                current = current[segment]
            if found and not _is_blank(current):
                return current
        return None

    def _parse_deal_state(self, value: Any) -> DealState | None:
        if _is_blank(value):
            return None
        try:
            return DealState(str(value).strip().upper())
        except ValueError:
            return None

    def _parse_funding_state(self, value: Any) -> FundingState | None:
        if _is_blank(value):
            return None
        try:
            return FundingState(str(value).strip().upper())
        except ValueError:
            return None

    def _extract_condition_report_url(self, detail: OveVehicleDetail) -> str | None:
        report = detail.condition_report_json or {}
        metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
        link = metadata.get("report_link") if isinstance(metadata, dict) else None
        if isinstance(link, dict):
            href = link.get("href")
            if href:
                return str(href)
        for key in ("condition_report_url", "report_link", "url"):
            value = report.get(key)
            if value:
                return str(value)
        return None
