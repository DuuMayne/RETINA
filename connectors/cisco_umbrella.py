from __future__ import annotations
import httpx
from .base import BaseConnector


class CiscoUmbrellaConnector(BaseConnector):
    """Connector for Cisco Umbrella admin user access review."""

    DEFAULT_BASE_URL = "https://api.umbrella.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "Management API Key", "type": "text"},
            {"name": "api_secret", "label": "Management API Secret", "type": "password"},
            {"name": "org_id", "label": "Organization ID", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return CiscoUmbrellaConnector.DEFAULT_BASE_URL

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        import base64
        key = self.credentials["api_key"].strip()
        secret = self.credentials["api_secret"].strip()
        encoded = base64.b64encode(f"{key}:{secret}".encode()).decode()

        resp = await client.post(
            "https://api.umbrella.com/auth/v2/token",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        org_id = self.credentials["org_id"].strip()

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            # Get admin users
            resp = await client.get(
                f"{base}/admin/v2/users",
                headers=headers,
            )
            resp.raise_for_status()
            users = resp.json()

            # Get roles
            role_map = {}
            resp = await client.get(
                f"{base}/admin/v2/roles",
                headers=headers,
            )
            if resp.status_code == 200:
                for role in resp.json():
                    role_map[role.get("roleId", "")] = role.get("roleName", "")

            results = []
            for user in users:
                role_id = user.get("roleId", "")
                role_name = role_map.get(role_id, str(role_id))

                results.append({
                    "id": str(user.get("id", "")),
                    "email": user.get("email", ""),
                    "name": f"{user.get('firstname', '')} {user.get('lastname', '')}".strip(),
                    "roles": [role_name] if role_name else ["User"],
                    "status": user.get("status", "active"),
                    "last_login": user.get("lastLoginTime", ""),
                    "created_at": "",
                    "two_factor_enabled": str(user.get("twoFactorEnable", False)),
                })

        return results
