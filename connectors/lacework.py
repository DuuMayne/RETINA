from __future__ import annotations
import httpx
from .base import BaseConnector


class LaceworkConnector(BaseConnector):
    """Connector for Lacework/Fortinet user and role access review."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "account", "label": "Account Name (e.g. yourcompany.lacework.net)", "type": "text"},
            {"name": "key_id", "label": "API Key ID", "type": "text"},
            {"name": "secret", "label": "API Secret", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def _get_token(self, client: httpx.AsyncClient, base: str) -> str:
        resp = await client.post(
            f"{base}/api/v2/access/tokens",
            json={
                "keyId": self.credentials["key_id"].strip(),
                "expiryTime": 3600,
            },
            headers={
                "X-LW-UAKS": self.credentials["secret"].strip(),
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()["token"]

    async def fetch_users(self) -> list[dict]:
        account = self.credentials["account"].strip()
        if not account.startswith("https://"):
            account = f"https://{account}"
        base = account.rstrip("/")

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client, base)
            headers = {"Authorization": f"Bearer {token}"}

            # Get team members
            resp = await client.get(f"{base}/api/v2/TeamMembers", headers=headers)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for member in data.get("data", []):
                props = member.get("props", member)
                user_name = member.get("userName", props.get("userName", ""))
                account_admin = props.get("accountAdmin", False)

                # Collect org-level and account-level roles
                org_roles = []
                org_admin = props.get("orgAdmin", False)
                org_user = props.get("orgUser", False)
                if org_admin:
                    org_roles.append("Organization Admin")
                if org_user:
                    org_roles.append("Organization User")
                if account_admin:
                    org_roles.append("Account Admin")

                if not org_roles:
                    org_roles = [props.get("userType", "User")]

                results.append({
                    "id": member.get("userGuid", ""),
                    "email": user_name,
                    "name": f"{props.get('firstName', '')} {props.get('lastName', '')}".strip() or user_name,
                    "roles": org_roles,
                    "status": "enabled" if member.get("userEnabled", True) else "disabled",
                    "last_login": props.get("lastLoginTime", ""),
                    "created_at": props.get("createdTime", ""),
                })

        return results
