from __future__ import annotations
import httpx
from .base import BaseConnector


class CloudflareConnector(BaseConnector):
    """Connector for Cloudflare account member and role access review."""

    DEFAULT_BASE_URL = "https://api.cloudflare.com/client/v4"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_token", "label": "API Token (Account Members:Read)", "type": "password"},
            {"name": "account_id", "label": "Account ID", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return CloudflareConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        account_id = self.credentials["account_id"].strip()
        headers = {
            "Authorization": f"Bearer {self.credentials['api_token'].strip()}",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            page = 1
            while True:
                resp = await client.get(
                    f"{base}/accounts/{account_id}/members",
                    headers=headers,
                    params={"page": page, "per_page": 50},
                )
                resp.raise_for_status()
                data = resp.json()

                if not data.get("success"):
                    errors = data.get("errors", [])
                    raise Exception(f"Cloudflare API error: {errors}")

                for member in data.get("result", []):
                    user = member.get("user", {})
                    roles = [r.get("name", r.get("id", "")) for r in member.get("roles", [])]
                    policies = member.get("policies", [])
                    if policies:
                        for p in policies:
                            effect = p.get("effect", "")
                            resources = list(p.get("resources", {}).keys())
                            perm_groups = [pg.get("name", pg.get("id", "")) for pg in p.get("permission_groups", [])]
                            for pg_name in perm_groups:
                                roles.append(f"{effect}: {pg_name}")

                    results.append({
                        "id": member.get("id", ""),
                        "email": user.get("email", ""),
                        "name": user.get("first_name", "") + " " + user.get("last_name", ""),
                        "roles": roles if roles else ["Member"],
                        "status": member.get("status", "unknown"),
                        "last_login": "",
                        "created_at": "",
                        "two_factor_enabled": str(user.get("two_factor_authentication_enabled", False)),
                    })

                result_info = data.get("result_info", {})
                total_pages = result_info.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1

        return results
