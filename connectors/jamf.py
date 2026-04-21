from __future__ import annotations
import httpx
from .base import BaseConnector


class JamfConnector(BaseConnector):
    """Connector for Jamf Pro user and admin access review.

    Uses OAuth2 client credentials for auth, then the Classic API
    to enumerate Jamf Pro user accounts.
    Required API roles: Read Accounts.
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "client_id", "label": "Client ID", "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None  # User provides their Jamf Pro URL (e.g. https://yourorg.jamfcloud.com)

    async def _get_token(self, client: httpx.AsyncClient, base: str) -> str:
        resp = await client.post(
            f"{base}/api/v1/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials["client_id"].strip(),
                "client_secret": self.credentials["client_secret"].strip(),
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
        base = (self.base_url or "").rstrip("/")
        if not base:
            raise Exception("Jamf Pro base URL is required (e.g. https://yourorg.jamfcloud.com)")

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client, base)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            # Get the list of all accounts via Classic API
            resp = await client.get(
                f"{base}/JSSResource/accounts",
                headers=headers,
            )
            resp.raise_for_status()
            accounts = resp.json().get("accounts", {})
            user_list = accounts.get("users", [])

            results = []
            for user_summary in user_list:
                user_id = user_summary.get("id")
                if user_id is None:
                    continue

                # Get full details for each user
                detail_resp = await client.get(
                    f"{base}/JSSResource/accounts/userid/{user_id}",
                    headers=headers,
                )
                if detail_resp.status_code != 200:
                    # If we can't get details, use summary info
                    results.append({
                        "id": str(user_id),
                        "email": "",
                        "name": user_summary.get("name", ""),
                        "roles": ["User"],
                        "status": "active",
                        "last_login": "",
                        "created_at": "",
                    })
                    continue

                user = detail_resp.json().get("account", {})
                privilege_set = user.get("privilege_set", "Custom")
                email = user.get("email", user.get("email_address", ""))
                name = user.get("full_name", user.get("name", ""))
                access_level = user.get("access_level", "Full Access")

                roles = [privilege_set] if privilege_set else []
                if access_level and access_level != "Full Access":
                    roles.append(access_level)
                if not roles:
                    roles = ["User"]

                # Classic API returns enabled as string "Enabled"/"Disabled"
                enabled_val = user.get("enabled", "Enabled")
                is_enabled = (
                    enabled_val in ("Enabled", True)
                    if isinstance(enabled_val, (str, bool))
                    else bool(enabled_val)
                )

                results.append({
                    "id": str(user_id),
                    "email": email,
                    "name": name,
                    "roles": roles,
                    "status": "active" if is_enabled else "disabled",
                    "last_login": "",
                    "created_at": "",
                })

        return results
