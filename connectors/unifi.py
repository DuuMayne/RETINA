from __future__ import annotations
import httpx
from .base import BaseConnector


class UniFiConnector(BaseConnector):
    """Connector for UniFi Network admin/user access review.

    Works with local UniFi controllers or UniFi Cloud (ui.com).
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "base_url", "label": "Controller URL (e.g. https://192.168.1.1:8443 or https://unifi.ui.com)", "type": "text"},
            {"name": "username", "label": "Admin Username", "type": "text"},
            {"name": "password", "label": "Admin Password", "type": "password"},
            {"name": "site", "label": "Site Name (default: default)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        base = self.credentials["base_url"].strip().rstrip("/")
        site = self.credentials.get("site", "").strip() or "default"

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            # Login
            resp = await client.post(
                f"{base}/api/login",
                json={
                    "username": self.credentials["username"].strip(),
                    "password": self.credentials["password"].strip(),
                },
            )
            # Some controllers use /api/auth/login
            if resp.status_code == 404:
                resp = await client.post(
                    f"{base}/api/auth/login",
                    json={
                        "username": self.credentials["username"].strip(),
                        "password": self.credentials["password"].strip(),
                    },
                )
            resp.raise_for_status()

            results = []

            # Get admins
            resp = await client.get(f"{base}/api/s/{site}/cmd/sitemgr")
            if resp.status_code == 404:
                resp = await client.get(f"{base}/proxy/network/api/s/{site}/cmd/sitemgr")

            # Try listing admins directly
            resp = await client.get(f"{base}/api/s/{site}/stat/admin")
            if resp.status_code == 404:
                resp = await client.get(f"{base}/proxy/network/api/s/{site}/stat/admin")

            if resp.status_code == 200:
                data = resp.json()
                for admin in data.get("data", []):
                    roles = []
                    if admin.get("is_super"):
                        roles.append("Super Admin")
                    role = admin.get("role", "")
                    if role:
                        roles.append(role)
                    if not roles:
                        roles = ["Admin"]

                    results.append({
                        "id": admin.get("_id", admin.get("admin_id", "")),
                        "email": admin.get("email", ""),
                        "name": admin.get("name", admin.get("email", "")),
                        "roles": roles,
                        "status": "active",
                        "last_login": "",
                        "created_at": "",
                    })

            # Get site clients/users (device users, not admin users)
            resp = await client.get(f"{base}/api/s/{site}/rest/user")
            if resp.status_code == 404:
                resp = await client.get(f"{base}/proxy/network/api/s/{site}/rest/user")

            if resp.status_code == 200:
                data = resp.json()
                for user in data.get("data", []):
                    if user.get("is_guest"):
                        continue
                    results.append({
                        "id": user.get("_id", ""),
                        "email": user.get("email", ""),
                        "name": user.get("name", user.get("hostname", "")),
                        "roles": ["Network User"],
                        "status": "blocked" if user.get("blocked") else "active",
                        "last_login": "",
                        "created_at": "",
                        "mac": user.get("mac", ""),
                    })

            # Logout
            await client.post(f"{base}/api/logout")

        return results
