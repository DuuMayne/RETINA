from __future__ import annotations
import httpx
from .base import BaseConnector


class ExperianConnector(BaseConnector):
    """Connector for Experian partner/enterprise portal user access review.

    Uses the Experian API for managing sub-users in enterprise accounts.
    Note: Experian does not have a widely documented public user management API.
    This connector works with the Experian Connect API or enterprise admin portal API.
    """

    DEFAULT_BASE_URL = "https://us-api.experian.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "client_id", "label": "Client ID", "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "type": "password"},
            {"name": "username", "label": "Admin Username", "type": "text"},
            {"name": "password", "label": "Admin Password", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return ExperianConnector.DEFAULT_BASE_URL

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        base = self.base_url or self.DEFAULT_BASE_URL
        resp = await client.post(
            f"{base}/oauth2/v1/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "password",
                "client_id": self.credentials["client_id"].strip(),
                "client_secret": self.credentials["client_secret"].strip(),
                "username": self.credentials["username"].strip(),
                "password": self.credentials["password"].strip(),
            },
        )
        if resp.status_code not in (200, 201):
            raise Exception(f"Experian auth failed ({resp.status_code}): {resp.text}")
        return resp.json()["access_token"]

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            # Get users - endpoint may vary by Experian product
            resp = await client.get(
                f"{base}/consumerservices/users/v2/users",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for user in data.get("users", data.get("results", [])):
                roles = user.get("roles", [])
                if isinstance(roles, list) and roles and isinstance(roles[0], dict):
                    roles = [r.get("name", str(r)) for r in roles]

                results.append({
                    "id": str(user.get("userId", user.get("id", ""))),
                    "email": user.get("emailAddress", user.get("email", "")),
                    "name": f"{user.get('firstName', '')} {user.get('lastName', '')}".strip(),
                    "roles": roles if roles else ["User"],
                    "status": user.get("status", "active"),
                    "last_login": user.get("lastLoginDate", ""),
                    "created_at": user.get("createdDate", ""),
                })

        return results
