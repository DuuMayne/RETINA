from __future__ import annotations
import httpx
from .base import BaseConnector


class FilesComConnector(BaseConnector):
    """Connector for Files.com user and permission access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "API Key", "type": "password"},
            {"name": "subdomain", "label": "Subdomain (e.g. yourcompany.files.com)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        subdomain = self.credentials["subdomain"].strip().replace(".files.com", "")
        base = f"https://{subdomain}.files.com/api/rest/v1"
        headers = {"X-FilesAPI-Key": self.credentials["api_key"].strip()}

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            cursor = None
            while True:
                params = {"per_page": 1000}
                if cursor:
                    params["cursor"] = cursor

                resp = await client.get(f"{base}/users", headers=headers, params=params)
                resp.raise_for_status()
                users = resp.json()

                for user in users:
                    perms = []
                    if user.get("admin_group_ids"):
                        perms.append("Admin")
                    if user.get("site_admin"):
                        perms.append("Site Admin")
                    if user.get("readonly_site_admin"):
                        perms.append("Read-Only Admin")
                    if user.get("sftp_permission"):
                        perms.append("SFTP")
                    if user.get("ftp_permission"):
                        perms.append("FTP")
                    if user.get("dav_permission"):
                        perms.append("WebDAV")
                    if not perms:
                        perms = ["User"]

                    results.append({
                        "id": str(user.get("id", "")),
                        "email": user.get("email", ""),
                        "name": user.get("name", user.get("username", "")),
                        "roles": perms,
                        "status": "disabled" if user.get("disabled") else "active",
                        "last_login": user.get("last_login_at", ""),
                        "created_at": user.get("created_at", ""),
                        "username": user.get("username", ""),
                        "two_factor_enabled": str(user.get("require_2fa", False)),
                    })

                cursor = resp.headers.get("X-Files-Cursor")
                if not cursor or len(users) < 1000:
                    break

        return results
