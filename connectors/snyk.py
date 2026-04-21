from __future__ import annotations

import urllib.parse

import httpx

from .base import BaseConnector


class SnykConnector(BaseConnector):
    """Connector for Snyk organization member access review.

    Uses the Snyk REST API ``/orgs/{org_id}/memberships`` endpoint
    (version 2024-10-15) which returns org memberships in JSON:API format.

    Required permission on the API token: View Organization Memberships
    (``org.membership.read``).
    """

    DEFAULT_BASE_URL = "https://api.snyk.io"
    API_VERSION = "2024-10-15"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_token", "label": "API Token", "type": "password"},
            {"name": "org_id", "label": "Organization ID", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return SnykConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        api_token = self.credentials["api_token"].strip()
        org_id = self.credentials["org_id"].strip()

        headers = {
            "Authorization": f"token {api_token}",
            "Accept": "application/vnd.api+json",
        }

        results: list[dict] = []

        async with httpx.AsyncClient(timeout=30) as client:
            starting_after: str | None = None

            while True:
                params: dict = {
                    "version": self.API_VERSION,
                    "limit": 100,
                }
                if starting_after:
                    params["starting_after"] = starting_after

                resp = await client.get(
                    f"{base}/rest/orgs/{org_id}/memberships",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()

                for membership in body.get("data", []):
                    attrs = membership.get("attributes", {})
                    rels = membership.get("relationships", {})

                    # User info
                    user_data = rels.get("user", {}).get("data", {})
                    user_attrs = user_data.get("attributes", {})
                    user_id = user_data.get("id", "")

                    # Role info
                    role_data = rels.get("role", {}).get("data", {})
                    role_attrs = role_data.get("attributes", {})
                    role_name = role_attrs.get("name", "")

                    results.append({
                        "id": user_id,
                        "email": user_attrs.get("email", ""),
                        "name": user_attrs.get("name", ""),
                        "username": user_attrs.get("username", ""),
                        "roles": [role_name] if role_name else [],
                        "status": "active",
                        "last_login": "",
                        "created_at": attrs.get("created_at", ""),
                        "login_method": user_attrs.get("login_method", ""),
                        "membership_id": membership.get("id", ""),
                    })

                # Cursor-based pagination: follow links.next
                next_url = (body.get("links") or {}).get("next")
                if not next_url:
                    break

                # next_url may be a full URL or a relative path; extract
                # the starting_after param from it for the next request.
                if "starting_after=" in str(next_url):
                    parsed = urllib.parse.urlparse(str(next_url))
                    qs = urllib.parse.parse_qs(parsed.query)
                    starting_after = qs.get("starting_after", [None])[0]
                    if not starting_after:
                        break
                else:
                    break

        return results
