from __future__ import annotations
import httpx
from .base import BaseConnector


class KandjiConnector(BaseConnector):
    """Connector for Kandji user/device access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_token", "label": "API Token", "type": "password"},
            {"name": "subdomain", "label": "Subdomain (e.g. yourcompany.api.kandji.io)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        subdomain = self.credentials["subdomain"].strip()
        if not subdomain.startswith("https://"):
            subdomain = f"https://{subdomain}"
        base = subdomain.rstrip("/")
        headers = {"Authorization": f"Bearer {self.credentials['api_token'].strip()}"}

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Get users from Kandji
            offset = 0
            while True:
                resp = await client.get(
                    f"{base}/api/v1/users",
                    headers=headers,
                    params={"limit": 300, "offset": offset},
                )
                resp.raise_for_status()
                users = resp.json()
                if not users:
                    break

                for user in users:
                    # Kandji users are directory users synced from IdP
                    results.append({
                        "id": user.get("id", ""),
                        "email": user.get("email", ""),
                        "name": user.get("name", ""),
                        "roles": [user.get("user_type", "Standard")],
                        "status": "active" if not user.get("is_archived") else "archived",
                        "last_login": "",
                        "created_at": "",
                        "devices": str(user.get("device_count", 0)),
                    })

                if len(users) < 300:
                    break
                offset += len(users)

        return results
