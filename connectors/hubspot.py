from __future__ import annotations
import httpx
from .base import BaseConnector


class HubSpotConnector(BaseConnector):
    """Connector for HubSpot account user and role access review.

    Uses the HubSpot Settings API v3 user-provisioning endpoints.
    Requires a Private App access token with the ``settings.users.read``
    and ``settings.users.roles.read`` scopes.
    """

    DEFAULT_BASE_URL = "https://api.hubapi.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "access_token", "label": "Private App Access Token", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return HubSpotConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        token = self.credentials["access_token"].strip()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            # Pre-fetch roles so we can map roleId -> name
            role_map = await self._fetch_role_map(client, base, headers)

            # Paginate through users
            results: list[dict] = []
            after: str | None = None
            while True:
                params: dict[str, str | int] = {"limit": 100}
                if after:
                    params["after"] = after

                resp = await client.get(
                    f"{base}/settings/v3/users/",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()

                for user in body.get("results", []):
                    role_ids = user.get("roleIds") or []
                    role_names = [role_map.get(rid, rid) for rid in role_ids]
                    if user.get("superAdmin"):
                        role_names.insert(0, "Super Admin")
                    if not role_names:
                        role_names.append("Member")

                    first = user.get("firstName") or ""
                    last = user.get("lastName") or ""
                    name = f"{first} {last}".strip()

                    results.append({
                        "id": str(user.get("id", "")),
                        "email": user.get("email", ""),
                        "name": name,
                        "roles": role_names,
                        "status": "active",
                        "last_login": "",
                        "created_at": "",
                        "is_admin": str(user.get("superAdmin", False)),
                        "primary_team_id": str(user.get("primaryTeamId") or ""),
                    })

                # Cursor-based pagination: paging.next.after
                paging = body.get("paging") or {}
                next_info = paging.get("next") or {}
                after = next_info.get("after")
                if not after:
                    break

        return results

    @staticmethod
    async def _fetch_role_map(
        client: httpx.AsyncClient,
        base: str,
        headers: dict[str, str],
    ) -> dict[str, str]:
        """Fetch HubSpot user roles and return a {roleId: roleName} mapping."""
        role_map: dict[str, str] = {}
        resp = await client.get(
            f"{base}/settings/v3/users/roles",
            headers=headers,
        )
        if resp.status_code == 200:
            for role in resp.json().get("results", []):
                role_map[str(role.get("id", ""))] = role.get("name", str(role.get("id", "")))
        return role_map
