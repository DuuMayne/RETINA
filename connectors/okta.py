from __future__ import annotations
import httpx
from .base import BaseConnector


class OktaConnector(BaseConnector):
    """Connector for Okta user and group/role access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_token", "label": "API Token", "type": "password"},
            {"name": "domain", "label": "Okta Domain (e.g. yourorg.okta.com)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        domain = self.credentials["domain"].strip().rstrip("/")
        if not domain.startswith("https://"):
            domain = f"https://{domain}"
        headers = {
            "Authorization": f"SSWS {self.credentials['api_token'].strip()}",
            "Accept": "application/json",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Paginate through all users
            url = f"{domain}/api/v1/users?limit=200"
            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                users = resp.json()

                for user in users:
                    profile = user.get("profile", {})
                    # Get user's groups (which serve as roles in Okta)
                    groups_resp = await client.get(
                        f"{domain}/api/v1/users/{user['id']}/groups",
                        headers=headers,
                    )
                    groups_resp.raise_for_status()
                    groups = [g["profile"]["name"] for g in groups_resp.json()]

                    # Get admin roles
                    roles_resp = await client.get(
                        f"{domain}/api/v1/users/{user['id']}/roles",
                        headers=headers,
                    )
                    admin_roles = []
                    if roles_resp.status_code == 200:
                        admin_roles = [r.get("label", r["type"]) for r in roles_resp.json()]

                    all_roles = admin_roles + groups

                    credentials = user.get("credentials", {})
                    provider = credentials.get("provider", {})

                    results.append({
                        "id": user["id"],
                        "email": profile.get("email", ""),
                        "name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
                        "roles": all_roles,
                        "status": user.get("status", "unknown"),
                        "last_login": user.get("lastLogin", ""),
                        "created_at": user.get("created", ""),
                        "last_password_change": user.get("passwordChanged", ""),
                        "last_updated": user.get("lastUpdated", ""),
                        "mfa_enabled": "",  # Requires separate factor enrollment check
                        "account_type": user.get("type", {}).get("id", "user"),
                        "auth_provider": provider.get("name", ""),
                    })

                # Okta uses Link header for pagination
                next_link = resp.headers.get("link", "")
                url = None
                for part in next_link.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")

        return results
