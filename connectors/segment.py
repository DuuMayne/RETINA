from __future__ import annotations
import httpx
from .base import BaseConnector


class SegmentConnector(BaseConnector):
    """Connector for Segment workspace user and role access review."""

    DEFAULT_BASE_URL = "https://api.segmentapis.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "token", "label": "Public API Token (Workspace Owner)", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return SegmentConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        headers = {
            "Authorization": f"Bearer {self.credentials['token'].strip()}",
            "Content-Type": "application/json",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            cursor = None
            while True:
                params = {"pagination.count": 100}
                if cursor:
                    params["pagination.cursor"] = cursor

                resp = await client.get(f"{base}/users", headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json().get("data", {})

                for user in data.get("users", []):
                    permissions = user.get("permissions", [])
                    roles = []
                    for perm in permissions:
                        role_name = perm.get("roleName", perm.get("roleId", ""))
                        resource = perm.get("resources", [{}])
                        if role_name:
                            roles.append(role_name)
                    if not roles:
                        roles = ["Member"]

                    results.append({
                        "id": user.get("id", ""),
                        "email": user.get("email", ""),
                        "name": user.get("name", ""),
                        "roles": roles,
                        "status": "active",
                        "last_login": "",
                        "created_at": "",
                    })

                pagination = data.get("pagination", {})
                cursor = pagination.get("next")
                if not cursor:
                    break

        return results
