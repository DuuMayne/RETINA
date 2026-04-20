from __future__ import annotations
import httpx
from .base import BaseConnector


class HelloSignConnector(BaseConnector):
    """Connector for Dropbox Sign (formerly HelloSign) team member access review.

    Uses the Dropbox Sign API v3.
    API docs: https://developers.hellosign.com/api/reference/
    Note: HelloSign rebranded to Dropbox Sign. The API base URL
    has migrated to api.hellosign.com but Dropbox also supports
    the new domain. Authentication uses API key via HTTP Basic auth.
    """

    DEFAULT_BASE_URL = "https://api.hellosign.com/v3"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "Dropbox Sign API Key", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return HelloSignConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        api_key = self.credentials["api_key"].strip()

        results = []
        async with httpx.AsyncClient(timeout=30, auth=(api_key, "")) as client:
            # Get team info and members
            resp = await client.get(f"{base}/team")
            resp.raise_for_status()
            team = resp.json().get("team", {})

            # Team members are in accounts array
            accounts = team.get("accounts", [])
            for account in accounts:
                role = account.get("role_code", "")
                role_name = {"a": "Admin", "m": "Member", "d": "Developer"}.get(role, role)

                results.append({
                    "id": account.get("account_id", ""),
                    "email": account.get("email_address", ""),
                    "name": "",
                    "roles": [role_name] if role_name else ["Member"],
                    "status": "active",
                    "last_login": "",
                    "created_at": "",
                })

            # Get invited accounts (pending members)
            invited = team.get("invitees", team.get("invited_accounts", []))
            for inv in invited:
                results.append({
                    "id": "",
                    "email": inv.get("email_address", ""),
                    "name": "",
                    "roles": ["Invited"],
                    "status": "pending",
                    "last_login": "",
                    "created_at": "",
                })

            # Also try to list team members via dedicated endpoint
            page = 1
            while True:
                resp = await client.get(
                    f"{base}/team/members",
                    params={"page": page, "page_size": 100},
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                members = data.get("team_members", [])
                if not members:
                    break

                existing_emails = {r["email"] for r in results}
                for member in members:
                    email = member.get("email_address", "")
                    if email in existing_emails:
                        continue
                    role = member.get("role", "Member")
                    results.append({
                        "id": member.get("account_id", ""),
                        "email": email,
                        "name": member.get("name", ""),
                        "roles": [role],
                        "status": "active",
                        "last_login": "",
                        "created_at": "",
                    })

                list_info = data.get("list_info", {})
                if page >= list_info.get("num_pages", 1):
                    break
                page += 1

        return results
