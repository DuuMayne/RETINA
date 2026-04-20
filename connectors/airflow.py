from __future__ import annotations
import httpx
from .base import BaseConnector


class AirflowConnector(BaseConnector):
    """Connector for Apache Airflow user and role access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "base_url", "label": "Airflow URL (e.g. https://airflow.yourcompany.com)", "type": "text"},
            {"name": "username", "label": "Username", "type": "text"},
            {"name": "password", "label": "Password", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        base = self.credentials["base_url"].strip().rstrip("/")
        auth = (
            self.credentials["username"].strip(),
            self.credentials["password"].strip(),
        )

        results = []
        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            # Get all users via stable REST API
            offset = 0
            while True:
                resp = await client.get(
                    f"{base}/api/v1/users",
                    params={"limit": 100, "offset": offset},
                )
                resp.raise_for_status()
                data = resp.json()

                for user in data.get("users", []):
                    roles = [r.get("name", "") for r in user.get("roles", [])]

                    results.append({
                        "id": str(user.get("user_id", user.get("username", ""))),
                        "email": user.get("email", ""),
                        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                        "roles": roles if roles else ["Viewer"],
                        "status": "inactive" if user.get("active") is False else "active",
                        "last_login": user.get("last_login", ""),
                        "created_at": user.get("created_on", ""),
                    })

                total = data.get("total_entries", 0)
                offset += len(data.get("users", []))
                if offset >= total:
                    break

        return results
