from __future__ import annotations
import httpx
from .base import BaseConnector


class NPMConnector(BaseConnector):
    """Connector for NPM organization member and team access review."""

    DEFAULT_BASE_URL = "https://registry.npmjs.org"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "token", "label": "NPM Access Token (with org read)", "type": "password"},
            {"name": "org", "label": "Organization Name (without @)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return NPMConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        org = self.credentials["org"].strip().lstrip("@")
        headers = {"Authorization": f"Bearer {self.credentials['token'].strip()}"}

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Get org members
            resp = await client.get(
                f"{base}/-/org/{org}/user",
                headers=headers,
            )
            resp.raise_for_status()
            members = resp.json()  # {"username": "role", ...}

            # Get teams
            resp = await client.get(
                f"{base}/-/org/{org}/team",
                headers=headers,
            )
            teams = []
            if resp.status_code == 200:
                teams = resp.json()  # list of team names

            # Get team memberships
            user_teams = {}
            for team in teams:
                resp = await client.get(
                    f"{base}/-/team/{org}/{team}/user",
                    headers=headers,
                )
                if resp.status_code == 200:
                    team_members = resp.json()
                    for username in team_members:
                        user_teams.setdefault(username, []).append(team)

            for username, role in members.items():
                member_teams = user_teams.get(username, [])
                roles = [role] + [f"Team: {t}" for t in member_teams]

                results.append({
                    "id": username,
                    "email": "",
                    "name": username,
                    "roles": roles,
                    "status": "active",
                    "last_login": "",
                    "created_at": "",
                })

        return results
