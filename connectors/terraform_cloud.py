from __future__ import annotations
import httpx
from .base import BaseConnector


class TerraformCloudConnector(BaseConnector):
    """Connector for Terraform Cloud / HCP Terraform organization user and role access review.

    Uses the Terraform Cloud API v2 organization membership endpoints.
    Required: Organization token or user token with organization read access.
    """

    DEFAULT_BASE_URL = "https://app.terraform.io"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_token", "label": "API Token", "type": "password"},
            {"name": "org_name", "label": "Organization Name", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return TerraformCloudConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        org_name = self.credentials["org_name"].strip()
        headers = {
            "Authorization": f"Bearer {self.credentials['api_token'].strip()}",
            "Content-Type": "application/vnd.api+json",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            page_number = 1
            while True:
                resp = await client.get(
                    f"{base}/api/v2/organizations/{org_name}/organization-memberships",
                    headers=headers,
                    params={
                        "include": "user,teams",
                        "page[size]": 100,
                        "page[number]": page_number,
                    },
                )
                resp.raise_for_status()
                body = resp.json()

                # Build lookup maps from included resources
                included = body.get("included", [])
                users_map: dict[str, dict] = {}
                teams_map: dict[str, str] = {}
                for item in included:
                    if item.get("type") == "users":
                        users_map[item["id"]] = item.get("attributes", {})
                    elif item.get("type") == "teams":
                        teams_map[item["id"]] = item.get("attributes", {}).get("name", "")

                for membership in body.get("data", []):
                    attrs = membership.get("attributes", {})
                    relationships = membership.get("relationships", {})

                    # Resolve user details from included
                    user_ref = relationships.get("user", {}).get("data", {})
                    user_id = user_ref.get("id", "")
                    user_attrs = users_map.get(user_id, {})

                    # Resolve team names from included
                    team_refs = relationships.get("teams", {}).get("data", [])
                    team_names = []
                    for team_ref in team_refs:
                        team_name = teams_map.get(team_ref.get("id", ""), "")
                        if team_name:
                            team_names.append(team_name)

                    two_factor = user_attrs.get("two-factor", {})
                    two_fa_enabled = two_factor.get("enabled", False) if isinstance(two_factor, dict) else False

                    results.append({
                        "id": user_id,
                        "email": user_attrs.get("email", ""),
                        "name": user_attrs.get("username", ""),
                        "roles": team_names if team_names else ["Member"],
                        "status": attrs.get("status", "unknown"),
                        "last_login": "",
                        "created_at": "",
                        "two_factor_enabled": str(two_fa_enabled),
                        "is_service_account": str(user_attrs.get("is-service-account", False)),
                    })

                next_page = body.get("meta", {}).get("pagination", {}).get("next-page")
                if not next_page:
                    break
                page_number = next_page

        return results
