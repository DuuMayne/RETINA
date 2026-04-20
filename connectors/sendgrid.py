from __future__ import annotations
import httpx
from .base import BaseConnector


class SendGridConnector(BaseConnector):
    """Connector for SendGrid/Twilio SendGrid teammate access review."""

    DEFAULT_BASE_URL = "https://api.sendgrid.com/v3"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "API Key (Full Access or Teammates Read)", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return SendGridConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        headers = {"Authorization": f"Bearer {self.credentials['api_key'].strip()}"}

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Get teammates
            offset = 0
            while True:
                resp = await client.get(
                    f"{base}/teammates",
                    headers=headers,
                    params={"limit": 500, "offset": offset},
                )
                resp.raise_for_status()
                data = resp.json()

                for teammate in data.get("result", []):
                    scopes = teammate.get("scopes", [])
                    role = teammate.get("user_type", "")
                    if teammate.get("is_admin"):
                        role = "admin"

                    results.append({
                        "id": str(teammate.get("username", "")),
                        "email": teammate.get("email", ""),
                        "name": f"{teammate.get('first_name', '')} {teammate.get('last_name', '')}".strip(),
                        "roles": [role] if role else ["teammate"],
                        "status": "active",
                        "last_login": "",
                        "created_at": "",
                    })

                if len(data.get("result", [])) < 500:
                    break
                offset += 500

            # Get pending teammates
            resp = await client.get(f"{base}/teammates/pending", headers=headers)
            if resp.status_code == 200:
                for pending in resp.json().get("result", []):
                    results.append({
                        "id": str(pending.get("token", "")),
                        "email": pending.get("email", ""),
                        "name": "",
                        "roles": [pending.get("user_type", "pending")],
                        "status": "pending",
                        "last_login": "",
                        "created_at": "",
                    })

        return results
