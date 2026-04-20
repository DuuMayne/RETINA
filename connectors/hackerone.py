from __future__ import annotations
import httpx
from .base import BaseConnector


class HackerOneConnector(BaseConnector):
    """Connector for HackerOne program member access review."""

    DEFAULT_BASE_URL = "https://api.hackerone.com/v1"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_identifier", "label": "API Identifier (username)", "type": "text"},
            {"name": "api_token", "label": "API Token", "type": "password"},
            {"name": "program_handle", "label": "Program Handle", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return HackerOneConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        handle = self.credentials["program_handle"].strip()
        auth = (
            self.credentials["api_identifier"].strip(),
            self.credentials["api_token"].strip(),
        )

        results = []
        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            url = f"{base}/programs/{handle}/members"
            while url:
                resp = await client.get(url, params={"page[size]": 100})
                resp.raise_for_status()
                data = resp.json()

                for member in data.get("data", []):
                    attrs = member.get("attributes", {})
                    user_data = member.get("relationships", {}).get("user", {}).get("data", {})
                    user_attrs = user_data.get("attributes", {}) if user_data else {}
                    perms = attrs.get("permissions", [])

                    results.append({
                        "id": member.get("id", ""),
                        "email": attrs.get("email", user_attrs.get("email", "")),
                        "name": user_attrs.get("username", attrs.get("email", "")),
                        "roles": perms if perms else [attrs.get("role", "member")],
                        "status": attrs.get("state", "active"),
                        "last_login": "",
                        "created_at": attrs.get("created_at", ""),
                    })

                next_link = data.get("links", {}).get("next")
                url = next_link if next_link else None

        return results
