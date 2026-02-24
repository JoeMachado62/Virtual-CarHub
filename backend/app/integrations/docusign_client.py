from app.integrations.base_client import ExternalServiceClient, ServicePolicy


class DocuSignClient(ExternalServiceClient):
    def __init__(
        self,
        integration_key: str,
        secret_key: str,
        account_id: str,
        *,
        base_url: str = "https://demo.docusign.net/restapi",
        live: bool = False,
    ):
        self.live = live
        self.account_id = account_id
        super().__init__(
            base_url=f"{base_url}/v2.1/accounts/{account_id}" if account_id else base_url,
            headers={
                "X-DocuSign-Integration-Key": integration_key,
                "X-DocuSign-Secret-Key": secret_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if integration_key
            else {},
            policy=ServicePolicy(max_retries=3, timeout_seconds=30, failure_threshold=5, recovery_seconds=300),
        )

    def create_envelope(self, payload: dict) -> dict:
        if not self.live:
            return {"envelopeId": "stub-envelope", "status": payload.get("status", "sent"), "source": "stub"}
        return self._request("POST", "/envelopes", json=payload)

    def get_envelope(self, envelope_id: str) -> dict:
        if not self.live:
            return {"envelopeId": envelope_id, "status": "completed", "source": "stub"}
        return self._request("GET", f"/envelopes/{envelope_id}")
