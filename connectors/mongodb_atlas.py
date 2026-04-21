from __future__ import annotations
import httpx
from .base import BaseConnector


class MongoDBAtlasConnector(BaseConnector):
    """Connector for MongoDB Atlas organization user and role access review.

    Uses the Atlas Administration API v2 with HTTP Digest authentication.
    Required: Organization Read Only or higher role for the API key.
    """

    DEFAULT_BASE_URL = "https://cloud.mongodb.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "public_key", "label": "Public API Key", "type": "text"},
            {"name": "private_key", "label": "Private API Key", "type": "password"},
            {"name": "org_id", "label": "Organization ID", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return MongoDBAtlasConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        org_id = self.credentials["org_id"].strip()
        auth = httpx.DigestAuth(
            self.credentials["public_key"].strip(),
            self.credentials["private_key"].strip(),
        )

        results = []
        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            page_num = 1
            while True:
                resp = await client.get(
                    f"{base}/api/atlas/v2/orgs/{org_id}/users",
                    headers={"Accept": "application/vnd.atlas.2023-01-01+json"},
                    params={"pageNum": page_num, "itemsPerPage": 100},
                )
                resp.raise_for_status()
                body = resp.json()

                for user in body.get("results", []):
                    # Extract org-level roles matching our org_id
                    org_roles = []
                    for role in user.get("roles", []):
                        if role.get("orgId") == org_id:
                            role_name = role.get("roleName", "")
                            if role_name:
                                org_roles.append(role_name)

                    first = user.get("firstName", "")
                    last = user.get("lastName", "")
                    name = f"{first} {last}".strip()

                    results.append({
                        "id": user.get("id", ""),
                        "email": user.get("emailAddress", ""),
                        "name": name,
                        "roles": org_roles if org_roles else ["Member"],
                        "status": "active",
                        "last_login": user.get("lastAuth", ""),
                        "created_at": user.get("created", ""),
                    })

                total_count = body.get("totalCount", 0)
                if page_num * 100 >= total_count:
                    break
                page_num += 1

        return results
