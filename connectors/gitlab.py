from __future__ import annotations
import httpx
from .base import BaseConnector


class GitLabConnector(BaseConnector):
    """Connector for GitLab user and role access review.

    Uses the GitLab REST API v4 to list all users.  Requires an admin-scoped
    personal access token with the ``read_api`` (or ``api``) scope so that
    the ``GET /api/v4/users`` endpoint returns the full user list including
    admin-only fields such as ``email``, ``is_admin``, and
    ``two_factor_enabled``.

    Works with both GitLab.com (SaaS) and self-hosted GitLab instances — pass
    a custom base_url for self-hosted.
    """

    DEFAULT_BASE_URL = "https://gitlab.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {
                "name": "api_token",
                "label": "Personal Access Token (admin, read_api scope)",
                "type": "password",
            },
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return GitLabConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "PRIVATE-TOKEN": self.credentials["api_token"].strip(),
        }

        results: list[dict] = []
        async with httpx.AsyncClient(timeout=30) as client:
            page = 1
            while True:
                resp = await client.get(
                    f"{base}/api/v4/users",
                    headers=headers,
                    params={"page": page, "per_page": 100, "order_by": "id", "sort": "asc"},
                )
                resp.raise_for_status()
                users = resp.json()

                if not users:
                    break

                for u in users:
                    # Build role list from available flags
                    roles: list[str] = []
                    if u.get("is_admin"):
                        roles.append("Admin")
                    if u.get("bot"):
                        roles.append("Bot")
                    if not roles:
                        roles.append("User")

                    # Collect external identity providers if present
                    identity_providers = [
                        ident.get("provider", "")
                        for ident in u.get("identities", [])
                        if ident.get("provider")
                    ]

                    results.append({
                        "id": str(u.get("id", "")),
                        "email": u.get("email", ""),
                        "name": u.get("name", ""),
                        "username": u.get("username", ""),
                        "roles": roles,
                        "status": u.get("state", "unknown"),
                        "last_login": u.get("last_sign_in_at", "") or "",
                        "created_at": u.get("created_at", ""),
                        "is_admin": str(u.get("is_admin", False)),
                        "two_factor_enabled": str(u.get("two_factor_enabled", False)),
                        "account_type": "bot" if u.get("bot") else "user",
                        "identity_providers": identity_providers,
                    })

                # GitLab returns total pages in the x-total-pages header.
                # If that header is missing, fall back to checking whether
                # a full page was returned (meaning there could be more).
                total_pages_hdr = resp.headers.get("x-total-pages")
                if total_pages_hdr:
                    if page >= int(total_pages_hdr):
                        break
                else:
                    if len(users) < 100:
                        break

                page += 1

        return results
