from __future__ import annotations
import httpx
from .base import BaseConnector


class SalesforceConnector(BaseConnector):
    """Connector for Salesforce CRM user and role access review.

    Uses OAuth2 password flow for auth, then SOQL queries via REST API.
    Required: Connected App with API access enabled.
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "client_id", "label": "Connected App Client ID", "type": "text"},
            {"name": "client_secret", "label": "Connected App Client Secret", "type": "password"},
            {"name": "username", "label": "Username", "type": "text"},
            {"name": "password", "label": "Password", "type": "password"},
            {"name": "security_token", "label": "Security Token", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None  # User provides their Salesforce instance URL

    async def _authenticate(self, client: httpx.AsyncClient) -> tuple[str, str]:
        """Returns (access_token, instance_url)."""
        login_url = (self.base_url or "https://login.salesforce.com").rstrip("/")
        password = self.credentials["password"].strip() + self.credentials.get("security_token", "").strip()

        resp = await client.post(
            f"{login_url}/services/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "password",
                "client_id": self.credentials["client_id"].strip(),
                "client_secret": self.credentials["client_secret"].strip(),
                "username": self.credentials["username"].strip(),
                "password": password,
            },
        )
        if resp.status_code not in (200, 201):
            detail = resp.text
            try:
                detail = resp.json()
            except Exception:
                pass
            raise Exception(f"Auth failed ({resp.status_code}): {detail}")

        data = resp.json()
        return data["access_token"], data["instance_url"]

    async def fetch_users(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            token, instance_url = await self._authenticate(client)
            headers = {"Authorization": f"Bearer {token}"}

            query = (
                "SELECT Id, Name, Email, Username, IsActive, "
                "Profile.Name, UserRole.Name, LastLoginDate, "
                "CreatedDate, UserType "
                "FROM User"
            )

            results = []
            url = f"{instance_url}/services/data/v59.0/query?q={query}"

            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                for user in data.get("records", []):
                    roles = []
                    profile = user.get("Profile")
                    if profile and profile.get("Name"):
                        roles.append(profile["Name"])
                    user_role = user.get("UserRole")
                    if user_role and user_role.get("Name"):
                        roles.append(user_role["Name"])
                    if not roles:
                        roles.append("Standard User")

                    results.append({
                        "id": user.get("Id", ""),
                        "email": user.get("Email", ""),
                        "name": user.get("Name", ""),
                        "roles": roles,
                        "status": "active" if user.get("IsActive") else "inactive",
                        "last_login": user.get("LastLoginDate", ""),
                        "created_at": user.get("CreatedDate", ""),
                        "account_type": user.get("UserType", ""),
                    })

                next_url = data.get("nextRecordsUrl")
                url = f"{instance_url}{next_url}" if next_url else None

        return results
