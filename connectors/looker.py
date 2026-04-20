from __future__ import annotations
import httpx
from .base import BaseConnector


class LookerConnector(BaseConnector):
    """Connector for Looker user and role access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "base_url", "label": "Looker Instance URL (e.g. https://yourcompany.looker.com:19999)", "type": "text"},
            {"name": "client_id", "label": "API Client ID", "type": "text"},
            {"name": "client_secret", "label": "API Client Secret", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def _get_token(self, client: httpx.AsyncClient, base: str) -> str:
        resp = await client.post(
            f"{base}/api/4.0/login",
            data={
                "client_id": self.credentials["client_id"].strip(),
                "client_secret": self.credentials["client_secret"].strip(),
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def fetch_users(self) -> list[dict]:
        base = self.credentials["base_url"].strip().rstrip("/")
        api = f"{base}/api/4.0"

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client, base)
            headers = {"Authorization": f"token {token}"}

            # Get all roles for mapping
            resp = await client.get(f"{api}/roles", headers=headers)
            resp.raise_for_status()
            role_map = {r["id"]: r.get("name", str(r["id"])) for r in resp.json()}

            # Get all users
            results = []
            page = 1
            while True:
                resp = await client.get(
                    f"{api}/users",
                    headers=headers,
                    params={"page": page, "per_page": 100},
                )
                resp.raise_for_status()
                users = resp.json()
                if not users:
                    break

                for user in users:
                    role_ids = user.get("role_ids", [])
                    roles = [role_map.get(rid, str(rid)) for rid in role_ids]
                    group_ids = user.get("group_ids", [])

                    if user.get("is_disabled"):
                        status = "disabled"
                    else:
                        status = "active"

                    results.append({
                        "id": str(user.get("id", "")),
                        "email": user.get("email", ""),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                        "roles": roles if roles else ["None"],
                        "status": status,
                        "last_login": "",
                        "created_at": user.get("created_at", ""),
                    })

                if len(users) < 100:
                    break
                page += 1

        return results
