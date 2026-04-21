from app.integrations.base_client import ExternalServiceClient, ServicePolicy


class GHLClient(ExternalServiceClient):
    def __init__(
        self,
        api_key: str,
        *,
        api_base_url: str = "https://services.leadconnectorhq.com",
        api_version: str = "2021-07-28",
        live: bool = False,
    ):
        self.live = live
        super().__init__(
            base_url=api_base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Version": api_version,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if api_key
            else {},
            policy=ServicePolicy(max_retries=3, timeout_seconds=15, failure_threshold=10, recovery_seconds=120),
        )

    def create_contact(self, payload: dict) -> dict:
        if not self.live:
            return {"contact": {"id": "stub-contact", **payload}, "source": "stub"}
        return self._request("POST", "/contacts/", json=payload)

    def get_contact(self, contact_id: str) -> dict:
        if not self.live:
            return {"contact": {"id": contact_id}, "source": "stub"}
        return self._request("GET", f"/contacts/{contact_id}")

    def search_contacts(self, *, location_id: str, query: str) -> dict:
        if not self.live:
            return {"contacts": [], "source": "stub"}
        return self._request("GET", "/contacts/", params={"locationId": location_id, "query": query})

    def update_contact(self, contact_id: str, payload: dict) -> dict:
        if not self.live:
            return {"contact": {"id": contact_id, **payload}, "source": "stub"}
        return self._request("PUT", f"/contacts/{contact_id}", json=payload)

    def add_contact_note(self, contact_id: str, body: str, user_id: str | None = None) -> dict:
        payload: dict[str, str] = {"body": body}
        if user_id:
            payload["userId"] = user_id
        if not self.live:
            return {"id": "stub-note", "contactId": contact_id, "source": "stub"}
        return self._request("POST", f"/contacts/{contact_id}/notes", json=payload)

    def create_opportunity(self, payload: dict) -> dict:
        if not self.live:
            return {"id": "stub-opportunity", **payload, "source": "stub"}
        return self._request("POST", "/opportunities/", json=payload)

    def update_opportunity(self, opportunity_id: str, payload: dict) -> dict:
        if not self.live:
            return {"id": opportunity_id, **payload, "source": "stub"}
        return self._request("PUT", f"/opportunities/{opportunity_id}", json=payload)

    def create_task(self, payload: dict) -> dict:
        if not self.live:
            return {"id": "stub-task", "payload": payload, "source": "stub"}
        return self._request("POST", "/tasks", json=payload)

    def update_opportunity_stage(self, opportunity_id: str, stage: str) -> dict:
        payload = {"pipelineStageId": stage}
        return self.update_opportunity(opportunity_id=opportunity_id, payload=payload)

    def send_document_template(
        self,
        *,
        location_id: str,
        template_id: str,
        contact_id: str,
        custom_values: dict | None = None,
        endpoint_path: str = "/proposals/templates/send",
    ) -> dict:
        payload = {
            "locationId": location_id,
            "templateId": template_id,
            "contactId": contact_id,
            "customValues": custom_values or {},
        }
        if not self.live:
            return {"id": "stub-contract-send", "status": "queued", "payload": payload, "source": "stub"}
        return self._request("POST", endpoint_path, json=payload)

    def create_custom_object_schema(self, payload: dict) -> dict:
        if not self.live:
            return {"id": "stub-object-schema", "payload": payload, "source": "stub"}
        return self._request("POST", "/objects/schemas", json=payload)

    def create_custom_object_record(self, object_key: str, payload: dict) -> dict:
        if not self.live:
            return {"id": "stub-object-record", "objectKey": object_key, "payload": payload, "source": "stub"}
        return self._request("POST", f"/objects/{object_key}/records", json=payload)
