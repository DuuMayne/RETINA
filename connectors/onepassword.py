from __future__ import annotations
import httpx
from .base import BaseConnector


class OnePasswordConnector(BaseConnector):
    """Connector for 1Password Business user access review via SCIM bridge.

    Uses the 1Password SCIM Bridge API (SCIM 2.0 / RFC 7644) to list users.
    The SCIM bridge must be deployed and accessible.
    Required: SCIM bearer token and SCIM bridge URL.
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "bearer_token", "label": "SCIM Bearer Token", "type": "password"},
            {"name": "scim_bridge_url", "label": "SCIM Bridge URL", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        bridge_url = self.credentials["scim_bridge_url"].strip().rstrip("/")
        if not bridge_url.startswith("https://") and not bridge_url.startswith("http://"):
            bridge_url = f"https://{bridge_url}"

        headers = {
            "Authorization": f"Bearer {self.credentials['bearer_token'].strip()}",
            "Accept": "application/scim+json",
        }

        results: list[dict] = []
        start_index = 1
        count = 100

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{bridge_url}/Users",
                    headers=headers,
                    params={"startIndex": start_index, "count": count},
                )
                resp.raise_for_status()
                body = resp.json()

                resources = body.get("Resources", [])
                for user in resources:
                    name_obj = user.get("name", {}) or {}
                    display_name = user.get("displayName", "")
                    formatted_name = name_obj.get("formatted", "")
                    given = name_obj.get("givenName", "")
                    family = name_obj.get("familyName", "")
                    name = formatted_name or display_name or f"{given} {family}".strip()

                    # userName is the primary identifier (typically email)
                    user_name = user.get("userName", "")

                    # Extract primary email from emails array, fall back to userName
                    email = user_name
                    emails = user.get("emails", [])
                    if emails:
                        for em in emails:
                            if isinstance(em, dict) and em.get("primary"):
                                email = em.get("value", email)
                                break
                        if email == user_name and isinstance(emails[0], dict):
                            email = emails[0].get("value", email)

                    active = user.get("active", False)
                    status = "active" if active else "suspended"

                    # Extract group memberships from the groups attribute
                    groups_raw = user.get("groups", [])
                    roles: list[str] = []
                    for g in groups_raw:
                        if isinstance(g, dict):
                            roles.append(g.get("display", g.get("value", "")))
                        elif isinstance(g, str):
                            roles.append(g)
                    roles = [r for r in roles if r]
                    if not roles:
                        roles = ["member"]

                    # SCIM meta block carries timestamps
                    meta = user.get("meta", {}) or {}

                    results.append({
                        "id": user.get("id", ""),
                        "email": email,
                        "name": name,
                        "roles": roles,
                        "status": status,
                        "last_login": "",  # SCIM bridge does not expose last login
                        "created_at": meta.get("created", ""),
                        "last_modified": meta.get("lastModified", ""),
                        "account_type": user.get("userType", "user"),
                        "mfa_enabled": "",  # Not available via SCIM
                    })

                total_results = body.get("totalResults", 0)
                items_per_page = body.get("itemsPerPage", count)
                start_index += items_per_page
                if start_index > total_results or not resources:
                    break

        return results
