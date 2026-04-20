from __future__ import annotations
import httpx
from .base import BaseConnector


class SlackConnector(BaseConnector):
    """Connector for Slack workspace user and role access review."""

    DEFAULT_BASE_URL = "https://slack.com/api"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "token", "label": "Bot/User OAuth Token (users:read, admin.teams:read scopes)", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return SlackConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        headers = {"Authorization": f"Bearer {self.credentials['token'].strip()}"}

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            cursor = None
            while True:
                params = {"limit": 200}
                if cursor:
                    params["cursor"] = cursor

                resp = await client.get(f"{base}/users.list", headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise Exception(f"Slack API error: {data.get('error', 'unknown')}")

                for member in data.get("members", []):
                    if member.get("id") == "USLACKBOT":
                        continue

                    roles = []
                    if member.get("is_owner"):
                        roles.append("Owner")
                    if member.get("is_admin"):
                        roles.append("Admin")
                    if member.get("is_primary_owner"):
                        roles.append("Primary Owner")
                    if member.get("is_restricted"):
                        roles.append("Guest (Multi-Channel)")
                    if member.get("is_ultra_restricted"):
                        roles.append("Guest (Single-Channel)")
                    if not roles:
                        roles.append("Member")

                    profile = member.get("profile", {})
                    status = "active"
                    if member.get("deleted"):
                        status = "deactivated"

                    results.append({
                        "id": member["id"],
                        "email": profile.get("email", ""),
                        "name": profile.get("real_name", member.get("name", "")),
                        "roles": roles,
                        "status": status,
                        "last_login": "",
                        "created_at": "",
                        "two_factor_enabled": str(member.get("has_2fa", False)),
                    })

                cursor = data.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        return results
