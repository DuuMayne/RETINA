from __future__ import annotations
import httpx
from .base import BaseConnector


class EntraIDConnector(BaseConnector):
    """Connector for Microsoft Entra ID (Azure AD) user access review.

    Uses OAuth2 client credentials flow with Microsoft Graph API.
    Required permissions: User.Read.All, Directory.Read.All
    Optional: AuditLog.Read.All (for signInActivity)
    """

    DEFAULT_BASE_URL = "https://graph.microsoft.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "tenant_id", "label": "Tenant ID", "type": "text"},
            {"name": "client_id", "label": "Client ID", "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return EntraIDConnector.DEFAULT_BASE_URL

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        tenant_id = self.credentials["tenant_id"].strip()
        resp = await client.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials["client_id"].strip(),
                "client_secret": self.credentials["client_secret"].strip(),
                "scope": "https://graph.microsoft.com/.default",
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

        select_fields = ",".join([
            "id",
            "displayName",
            "mail",
            "userPrincipalName",
            "accountEnabled",
            "createdDateTime",
            "signInActivity",
            "assignedLicenses",
            "userType",
            "jobTitle",
            "department",
        ])

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            results = []
            url = f"{base}/v1.0/users?$select={select_fields}"
            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                for user in data.get("value", []):
                    email = user.get("mail") or user.get("userPrincipalName", "")

                    roles = []
                    user_type = user.get("userType", "")
                    if user_type:
                        roles.append(user_type)
                    job_title = user.get("jobTitle", "")
                    if job_title:
                        roles.append(job_title)
                    if not roles:
                        roles.append("Member")

                    enabled = user.get("accountEnabled")
                    status = "active" if enabled else "disabled"

                    # signInActivity requires AuditLog.Read.All — handle gracefully
                    sign_in = user.get("signInActivity") or {}
                    last_login = sign_in.get("lastSignInDateTime", "")

                    results.append({
                        "id": user.get("id", ""),
                        "email": email,
                        "name": user.get("displayName", ""),
                        "roles": roles,
                        "status": status,
                        "last_login": last_login,
                        "created_at": user.get("createdDateTime", ""),
                        "department": user.get("department", ""),
                        "has_licenses": str(bool(user.get("assignedLicenses"))),
                    })

                url = data.get("@odata.nextLink")

        return results
