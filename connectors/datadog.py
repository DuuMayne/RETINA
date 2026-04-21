from __future__ import annotations
import httpx
from .base import BaseConnector


class DatadogConnector(BaseConnector):
    """Connector for Datadog organization user and role access review.

    Uses the Datadog API v2 user management endpoints.
    Required: API key + Application key with user_access_read scope.
    """

    DEFAULT_BASE_URL = "https://api.datadoghq.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "API Key", "type": "password"},
            {"name": "app_key", "label": "Application Key", "type": "password"},
            {"name": "site", "label": "Datadog Site (e.g. datadoghq.com, datadoghq.eu)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return DatadogConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        site = self.credentials.get("site", "").strip()
        if site:
            base = f"https://api.{site}"
        else:
            base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")

        headers = {
            "DD-API-KEY": self.credentials["api_key"].strip(),
            "DD-APPLICATION-KEY": self.credentials["app_key"].strip(),
            "Accept": "application/json",
        }

        # Fetch roles for ID → name mapping
        role_map: dict[str, str] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            roles_resp = await client.get(
                f"{base}/api/v2/roles",
                headers=headers,
            )
            if roles_resp.status_code == 200:
                for role in roles_resp.json().get("data", []):
                    role_map[role["id"]] = role.get("attributes", {}).get("name", role["id"])

            # Fetch users with pagination
            results = []
            page_number = 0
            page_size = 100
            while True:
                resp = await client.get(
                    f"{base}/api/v2/users",
                    headers=headers,
                    params={
                        "page[size]": page_size,
                        "page[number]": page_number,
                    },
                )
                resp.raise_for_status()
                body = resp.json()

                users = body.get("data", [])
                if not users:
                    break

                for user in users:
                    attrs = user.get("attributes", {})
                    relationships = user.get("relationships", {})

                    # Resolve role names
                    role_data = relationships.get("roles", {}).get("data", [])
                    role_names = [role_map.get(r.get("id", ""), r.get("id", "")) for r in role_data]

                    status = attrs.get("status", "unknown")
                    if attrs.get("disabled"):
                        status = "Disabled"

                    results.append({
                        "id": user.get("id", ""),
                        "email": attrs.get("email", ""),
                        "name": attrs.get("name", ""),
                        "roles": role_names if role_names else ["Standard"],
                        "status": status,
                        "last_login": attrs.get("last_login_time", ""),
                        "created_at": attrs.get("created_at", ""),
                        "mfa_enabled": str(attrs.get("mfa_enabled", "")),
                        "is_service_account": str(attrs.get("service_account", False)),
                    })

                if len(users) < page_size:
                    break
                page_number += 1

        return results
