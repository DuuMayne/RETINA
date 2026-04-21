from __future__ import annotations
import httpx
from .base import BaseConnector


class DropboxConnector(BaseConnector):
    """Connector for Dropbox Business team member access review.

    Uses the Dropbox Business API team member endpoints.
    Required: Team access token with Team member management permission.
    """

    DEFAULT_BASE_URL = "https://api.dropboxapi.com"

    ROLE_MAP = {
        "team_admin": "Team Admin",
        "user_management_admin": "User Management Admin",
        "support_admin": "Support Admin",
        "member_only": "Member",
    }

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "access_token", "label": "Team Access Token", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return DropboxConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Bearer {self.credentials['access_token'].strip()}",
            "Content-Type": "application/json",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Initial request
            resp = await client.post(
                f"{base}/2/team/members/list_v2",
                headers=headers,
                json={"limit": 1000},
            )
            resp.raise_for_status()
            body = resp.json()

            while True:
                for member in body.get("members", []):
                    profile = member.get("profile", {})
                    role = member.get("role", {})
                    role_tag = role.get(".tag", "member_only") if isinstance(role, dict) else "member_only"
                    role_name = self.ROLE_MAP.get(role_tag, role_tag)

                    name_info = profile.get("name", {})
                    display_name = name_info.get("display_name", "")

                    status_info = profile.get("status", {})
                    status_tag = status_info.get(".tag", "unknown") if isinstance(status_info, dict) else "unknown"

                    results.append({
                        "id": profile.get("team_member_id", ""),
                        "email": profile.get("email", ""),
                        "name": display_name,
                        "roles": [role_name],
                        "status": status_tag,
                        "last_login": "",
                        "created_at": profile.get("joined_on", ""),
                    })

                if not body.get("has_more", False):
                    break

                # Continue with cursor
                cursor = body.get("cursor", "")
                resp = await client.post(
                    f"{base}/2/team/members/list_v2/continue",
                    headers=headers,
                    json={"cursor": cursor},
                )
                resp.raise_for_status()
                body = resp.json()

        return results
