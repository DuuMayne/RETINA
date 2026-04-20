from __future__ import annotations
import httpx
from .base import BaseConnector


class AtlassianConnector(BaseConnector):
    """Connector for Atlassian Cloud (Jira/Confluence) org user access review.

    Uses the Atlassian Admin API with SCIM-compatible user endpoints.
    Required: Organization Admin API key from admin.atlassian.com.
    Docs: https://developer.atlassian.com/cloud/admin/organization/rest/
    """

    DEFAULT_BASE_URL = "https://api.atlassian.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "Organization Admin API Key", "type": "password"},
            {"name": "org_id", "label": "Organization ID", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return AtlassianConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        org_id = self.credentials["org_id"].strip()
        headers = {
            "Authorization": f"Bearer {self.credentials['api_key'].strip()}",
            "Accept": "application/json",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Get org members via SCIM-compatible admin API
            cursor = None
            while True:
                url = f"{base}/admin/v1/orgs/{org_id}/users"
                params = {"maxResults": 100}
                if cursor:
                    params["cursor"] = cursor

                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

                for user in data.get("data", []):
                    account_id = user.get("account_id", "")
                    account_type = user.get("account_type", "")
                    account_status = user.get("account_status", "")
                    name = user.get("name", "")
                    email = user.get("email", "")

                    # Get product access for this user
                    prod_resp = await client.get(
                        f"{base}/admin/v1/orgs/{org_id}/users/{account_id}/product-access",
                        headers=headers,
                    )
                    product_roles = []
                    if prod_resp.status_code == 200:
                        for product in prod_resp.json().get("data", []):
                            pname = product.get("name", "")
                            prole = product.get("role", "")
                            product_roles.append(f"{pname}: {prole}" if prole else pname)

                    if not product_roles:
                        product_roles = [account_type or "member"]

                    # Get managed account details for MFA status
                    mfa_enabled = ""
                    mgmt_resp = await client.get(
                        f"{base}/users/{account_id}/manage",
                        headers=headers,
                    )
                    if mgmt_resp.status_code == 200:
                        mgmt_data = mgmt_resp.json()
                        mfa_enabled = str(mgmt_data.get("account", {}).get("two_step_verification", {}).get("enabled", ""))

                    results.append({
                        "id": account_id,
                        "email": email,
                        "name": name,
                        "roles": product_roles,
                        "status": account_status,
                        "last_login": user.get("last_active", ""),
                        "created_at": "",
                        "account_type": account_type,
                        "mfa_enabled": mfa_enabled,
                    })

                links = data.get("links", {})
                cursor = None
                next_url = links.get("next", "")
                if next_url:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(next_url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    cursor = qs.get("cursor", [None])[0]
                if not cursor:
                    break

        return results
