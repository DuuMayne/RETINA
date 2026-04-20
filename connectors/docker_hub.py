from __future__ import annotations
import httpx
from .base import BaseConnector


class DockerHubConnector(BaseConnector):
    """Connector for Docker Hub organization member and team access review."""

    DEFAULT_BASE_URL = "https://hub.docker.com/v2"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "username", "label": "Docker Hub Username (admin)", "type": "text"},
            {"name": "pat", "label": "Personal Access Token", "type": "password"},
            {"name": "org", "label": "Organization Name", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return DockerHubConnector.DEFAULT_BASE_URL

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            "https://hub.docker.com/v2/users/login",
            json={
                "username": self.credentials["username"].strip(),
                "password": self.credentials["pat"].strip(),
            },
        )
        resp.raise_for_status()
        return resp.json()["token"]

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        org = self.credentials["org"].strip()

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            # Get org members
            members = []
            url = f"{base}/orgs/{org}/members"
            while url:
                resp = await client.get(url, headers=headers, params={"page_size": 100})
                resp.raise_for_status()
                data = resp.json()
                members.extend(data.get("results", []))
                url = data.get("next")

            # Get teams for role mapping
            teams = []
            url = f"{base}/orgs/{org}/groups"
            while url:
                resp = await client.get(url, headers=headers, params={"page_size": 100})
                resp.raise_for_status()
                data = resp.json()
                teams.extend(data.get("results", []))
                url = data.get("next")

            # Map team members
            user_teams = {}
            for team in teams:
                team_name = team.get("name", "")
                team_id = team.get("id", "")
                t_url = f"{base}/orgs/{org}/groups/{team_name}/members"
                try:
                    resp = await client.get(t_url, headers=headers, params={"page_size": 100})
                    if resp.status_code == 200:
                        for tm in resp.json().get("results", []):
                            username = tm.get("username", "")
                            user_teams.setdefault(username, []).append(team_name)
                except Exception:
                    pass

            results = []
            for member in members:
                username = member.get("username", "")
                role = member.get("role", "member")
                member_teams = user_teams.get(username, [])
                roles = [role] + [f"Team: {t}" for t in member_teams]

                results.append({
                    "id": username,
                    "email": member.get("email", ""),
                    "name": member.get("full_name", username),
                    "roles": roles,
                    "status": "active",
                    "last_login": "",
                    "created_at": member.get("date_joined", ""),
                })

        return results
