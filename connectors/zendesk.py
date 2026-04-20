from __future__ import annotations
import httpx
from .base import BaseConnector


class ZendeskConnector(BaseConnector):
    """Connector for Zendesk user and role access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "subdomain", "label": "Subdomain (yourcompany.zendesk.com)", "type": "text"},
            {"name": "email", "label": "Admin Email", "type": "text"},
            {"name": "api_token", "label": "API Token", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        subdomain = self.credentials["subdomain"].strip().replace(".zendesk.com", "")
        base = f"https://{subdomain}.zendesk.com/api/v2"
        email = self.credentials["email"].strip()
        token = self.credentials["api_token"].strip()

        results = []
        async with httpx.AsyncClient(timeout=30, auth=(f"{email}/token", token)) as client:
            # Get custom roles
            role_map = {}
            resp = await client.get(f"{base}/custom_roles.json")
            if resp.status_code == 200:
                for role in resp.json().get("custom_roles", []):
                    role_map[role["id"]] = role["name"]

            # Get all users (agents and admins)
            url = f"{base}/users.json?role[]=admin&role[]=agent"
            while url:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                for user in data.get("users", []):
                    role = user.get("role", "")
                    custom_role_id = user.get("custom_role_id")
                    roles = [role]
                    if custom_role_id and custom_role_id in role_map:
                        roles.append(role_map[custom_role_id])

                    results.append({
                        "id": str(user["id"]),
                        "email": user.get("email", ""),
                        "name": user.get("name", ""),
                        "roles": roles,
                        "status": "suspended" if user.get("suspended") else "active",
                        "last_login": user.get("last_login_at", ""),
                        "created_at": user.get("created_at", ""),
                        "two_factor_enabled": str(user.get("two_factor_auth_enabled", False)),
                    })

                url = data.get("next_page")

        return results
