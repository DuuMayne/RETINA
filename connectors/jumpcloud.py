from __future__ import annotations
import httpx
from .base import BaseConnector


class JumpCloudConnector(BaseConnector):
    """Connector for JumpCloud Directory-as-a-Service user access review.

    Uses the JumpCloud V1 System Users API.
    Required: API key with read access.
    """

    DEFAULT_BASE_URL = "https://console.jumpcloud.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "API Key", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return JumpCloudConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "x-api-key": self.credentials["api_key"].strip(),
            "Accept": "application/json",
        }

        results = []
        skip = 0
        limit = 100

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{base}/api/systemusers",
                    headers=headers,
                    params={"skip": skip, "limit": limit},
                )
                resp.raise_for_status()
                body = resp.json()

                users = body.get("results", [])
                for user in users:
                    first = user.get("firstname", "")
                    last = user.get("lastname", "")
                    name = f"{first} {last}".strip()

                    roles = []
                    if user.get("sudo"):
                        roles.append("sudo")
                    if user.get("admin") is not None:
                        roles.append("admin")
                    if not roles:
                        roles.append("user")

                    activated = user.get("activated", False)
                    suspended = user.get("suspended", False)
                    if suspended:
                        status = "suspended"
                    elif activated:
                        status = "active"
                    else:
                        status = "inactive"

                    mfa = user.get("mfa", {})
                    totp_enabled = user.get("totp_enabled", False)
                    mfa_configured = mfa.get("configured", False) if isinstance(mfa, dict) else False

                    results.append({
                        "id": user.get("_id", ""),
                        "email": user.get("email", ""),
                        "name": name,
                        "roles": roles,
                        "status": status,
                        "last_login": "",
                        "created_at": user.get("created", ""),
                        "mfa_enabled": str(totp_enabled or mfa_configured),
                    })

                total = body.get("totalCount", 0)
                skip += len(users)
                if skip >= total or not users:
                    break

        return results
