from __future__ import annotations
import httpx
from .base import BaseConnector


class SplunkConnector(BaseConnector):
    """Connector for Splunk Cloud user and role access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "base_url", "label": "Splunk URL (e.g. https://yourinstance.splunkcloud.com:8089)", "type": "text"},
            {"name": "token", "label": "Bearer Token (or session key)", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        base = self.credentials["base_url"].strip().rstrip("/")
        headers = {"Authorization": f"Bearer {self.credentials['token'].strip()}"}

        results = []
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            # Get all users via REST API
            resp = await client.get(
                f"{base}/services/authentication/users",
                headers=headers,
                params={"output_mode": "json", "count": 0},
            )
            resp.raise_for_status()
            data = resp.json()

            for entry in data.get("entry", []):
                content = entry.get("content", {})
                roles = content.get("roles", [])
                name = entry.get("name", "")
                real_name = content.get("realname", "")
                email = content.get("email", "")

                results.append({
                    "id": name,
                    "email": email,
                    "name": real_name or name,
                    "roles": roles if roles else ["user"],
                    "status": "locked" if content.get("locked-out") else "active",
                    "last_login": "",
                    "created_at": "",
                    "default_app": content.get("defaultApp", ""),
                })

        return results
