from __future__ import annotations
import httpx
from .base import BaseConnector


class SentinelOneConnector(BaseConnector):
    """Connector for SentinelOne console user and role access review.

    Uses the SentinelOne Web API v2.1 user management endpoints.
    Required API token scope: Accounts > View
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_token", "label": "API Token", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or "").rstrip("/")
        if not base:
            raise Exception("SentinelOne base URL is required (e.g. https://usea1-partners.sentinelone.net)")
        headers = {
            "Authorization": f"ApiToken {self.credentials['api_token'].strip()}",
            "Accept": "application/json",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            cursor = None
            while True:
                params: dict = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                resp = await client.get(
                    f"{base}/web/api/v2.1/users",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()

                for user in body.get("data", []):
                    # Build role list from scope and role information
                    roles = []
                    scope = user.get("scope", "")
                    role_name = user.get("roleName", "")
                    role_id = user.get("roleId", "")
                    if role_name:
                        roles.append(role_name)
                    elif role_id:
                        roles.append(role_id)
                    if scope and scope not in roles:
                        roles.append(scope)
                    scope_roles = user.get("scopeRoles", [])
                    for sr in scope_roles:
                        sr_name = sr.get("roleName", sr.get("roleId", ""))
                        if sr_name and sr_name not in roles:
                            roles.append(sr_name)

                    results.append({
                        "id": str(user.get("id", "")),
                        "email": user.get("email", ""),
                        "name": user.get("fullName", ""),
                        "roles": roles if roles else ["User"],
                        "status": "active",
                        "last_login": user.get("lastLogin", ""),
                        "created_at": user.get("createdAt", ""),
                        "two_factor_enabled": str(user.get("twoFaEnabled", False)),
                    })

                next_cursor = body.get("pagination", {}).get("nextCursor")
                if not next_cursor:
                    break
                cursor = next_cursor

        return results
