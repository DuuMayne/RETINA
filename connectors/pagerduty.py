from __future__ import annotations
import httpx
from .base import BaseConnector


class PagerDutyConnector(BaseConnector):
    """Connector for PagerDuty user and role access review.

    Uses the PagerDuty REST API v2 user management endpoints.
    Required: API key (REST API v2, read-only or full access).
    """

    DEFAULT_BASE_URL = "https://api.pagerduty.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "API Key (REST API v2)", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return PagerDutyConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Token token={self.credentials['api_key'].strip()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        results = []
        offset = 0
        limit = 100

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{base}/users",
                    headers=headers,
                    params={
                        "offset": offset,
                        "limit": limit,
                        "include[]": "teams",
                    },
                )
                resp.raise_for_status()
                body = resp.json()

                for user in body.get("users", []):
                    role = user.get("role", "user")
                    roles = [role]

                    # Include team names
                    teams = user.get("teams", [])
                    for team in teams:
                        team_name = team.get("summary", team.get("name", ""))
                        if team_name:
                            roles.append(team_name)

                    invitation_pending = user.get("invitation_pending", False)
                    status = "pending" if invitation_pending else "active"

                    results.append({
                        "id": user.get("id", ""),
                        "email": user.get("email", ""),
                        "name": user.get("name", ""),
                        "roles": roles,
                        "status": status,
                        "last_login": "",
                        "created_at": "",
                    })

                if not body.get("more", False):
                    break
                offset += limit

        return results
