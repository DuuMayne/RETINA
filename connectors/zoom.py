from __future__ import annotations
import base64
import httpx
from .base import BaseConnector


class ZoomConnector(BaseConnector):
    """Connector for Zoom user access review.

    Uses Server-to-Server OAuth2 for authentication.
    Required scopes: user:read:admin
    """

    DEFAULT_BASE_URL = "https://api.zoom.us"

    ZOOM_TYPE_MAP = {
        1: "Basic",
        2: "Licensed",
        3: "On-Prem",
    }

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "account_id", "label": "Account ID", "type": "text"},
            {"name": "client_id", "label": "Client ID", "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return ZoomConnector.DEFAULT_BASE_URL

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        client_id = self.credentials["client_id"].strip()
        client_secret = self.credentials["client_secret"].strip()
        account_id = self.credentials["account_id"].strip()

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        resp = await client.post(
            "https://zoom.us/oauth/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "account_credentials",
                "account_id": account_id,
            },
        )
        if resp.status_code not in (200, 201):
            detail = resp.text
            try:
                detail = resp.json()
            except Exception:
                pass
            raise Exception(f"Auth failed ({resp.status_code}): {detail}")
        return resp.json()["access_token"]

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            results = []
            next_page_token = ""
            while True:
                params = {"page_size": 300, "status": "active"}
                if next_page_token:
                    params["next_page_token"] = next_page_token

                resp = await client.get(
                    f"{base}/v2/users",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                for user in data.get("users", []):
                    user_type = user.get("type", 0)
                    type_label = self.ZOOM_TYPE_MAP.get(user_type, f"Type {user_type}")

                    roles = [type_label]
                    if user.get("role_name"):
                        roles.append(user["role_name"])

                    first = user.get("first_name", "")
                    last = user.get("last_name", "")
                    name = f"{first} {last}".strip()

                    results.append({
                        "id": user.get("id", ""),
                        "email": user.get("email", ""),
                        "name": name,
                        "roles": roles,
                        "status": user.get("status", "unknown"),
                        "last_login": user.get("last_login_time", ""),
                        "created_at": user.get("created_at", ""),
                        "dept": user.get("dept", ""),
                    })

                next_page_token = data.get("next_page_token", "")
                if not next_page_token:
                    break

        return results
