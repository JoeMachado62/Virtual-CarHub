from app.integrations.base_client import ExternalServiceClient, ServicePolicy


class TelnyxClient(ExternalServiceClient):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.telnyx.com/v2",
        live: bool = False,
    ):
        self.live = live
        super().__init__(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if api_key
            else {},
            policy=ServicePolicy(max_retries=3, timeout_seconds=15, failure_threshold=5, recovery_seconds=120),
        )

    def send_sms(self, from_number: str, to_number: str, text: str) -> dict:
        payload = {
            "from": from_number,
            "to": to_number,
            "text": text,
        }
        if not self.live:
            return {"data": {"id": "stub-sms", "record_type": "message"}, "payload": payload, "source": "stub"}
        return self._request("POST", "/messages", json=payload)
