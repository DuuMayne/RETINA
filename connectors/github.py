from __future__ import annotations
import httpx
from .base import BaseConnector


class GitHubConnector(BaseConnector):
    """Connector for GitHub organization member and role access review."""

    DEFAULT_BASE_URL = "https://api.github.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "token", "label": "Personal Access Token (admin:org scope)", "type": "password"},
            {"name": "org", "label": "Organization Slug", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return GitHubConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        org = self.credentials["org"].strip()
        headers = {
            "Authorization": f"Bearer {self.credentials['token'].strip()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2024-11-25",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Get members without 2FA to flag them
            no_2fa_members = set()
            page = 1
            while True:
                resp = await client.get(
                    f"{base}/orgs/{org}/members",
                    headers=headers,
                    params={"per_page": 100, "page": page, "filter": "2fa_disabled"},
                )
                if resp.status_code == 200:
                    members_no_2fa = resp.json()
                    if not members_no_2fa:
                        break
                    no_2fa_members.update(m["login"] for m in members_no_2fa)
                    if len(members_no_2fa) < 100:
                        break
                    page += 1
                else:
                    break

            # Get org members with roles
            page = 1
            while True:
                resp = await client.get(
                    f"{base}/orgs/{org}/members",
                    headers=headers,
                    params={"per_page": 100, "page": page},
                )
                resp.raise_for_status()
                members = resp.json()
                if not members:
                    break

                for member in members:
                    # Get membership details (role: admin or member)
                    mem_resp = await client.get(
                        f"{base}/orgs/{org}/memberships/{member['login']}",
                        headers=headers,
                    )
                    mem_resp.raise_for_status()
                    membership = mem_resp.json()

                    results.append({
                        "id": str(member["id"]),
                        "email": member.get("email", ""),
                        "name": member.get("name", member["login"]),
                        "roles": [membership.get("role", "member")],
                        "status": membership.get("state", "active"),
                        "last_login": "",
                        "created_at": member.get("created_at", ""),
                        "username": member["login"],
                        "mfa_enabled": str(member["login"] not in no_2fa_members),
                        "site_admin": str(member.get("site_admin", False)),
                    })

                if len(members) < 100:
                    break
                page += 1

        return results
