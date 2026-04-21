from __future__ import annotations
import httpx
from .base import BaseConnector


class BoxConnector(BaseConnector):
    """Connector for Box enterprise user access review.

    Uses the Box Content API v2 user management endpoints.
    Required: Access token with Manage users permission.
    """

    DEFAULT_BASE_URL = "https://api.box.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "access_token", "label": "Access Token (Developer Token or OAuth)", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return BoxConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Bearer {self.credentials['access_token'].strip()}",
            "Accept": "application/json",
        }

        results = []
        offset = 0
        limit = 1000

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{base}/2.0/users",
                    headers=headers,
                    params={"offset": offset, "limit": limit},
                )
                resp.raise_for_status()
                body = resp.json()

                for user in body.get("entries", []):
                    role = user.get("role", "user")
                    roles = [role]
                    if role in ("admin", "coadmin"):
                        is_admin = "True"
                    else:
                        is_admin = "False"

                    results.append({
                        "id": str(user.get("id", "")),
                        "email": user.get("login", ""),
                        "name": user.get("name", ""),
                        "roles": roles,
                        "status": user.get("status", "unknown"),
                        "last_login": "",
                        "created_at": user.get("created_at", ""),
                        "is_admin": is_admin,
                    })

                total_count = body.get("total_count", 0)
                offset += len(body.get("entries", []))
                if offset >= total_count:
                    break

        return results
