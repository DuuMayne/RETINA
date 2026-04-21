from __future__ import annotations
import httpx
from .base import BaseConnector


class VantaConnector(BaseConnector):
    """Connector for Vanta compliance platform people access review.

    Uses the Vanta REST API v1 to list people in the organization.
    Required: API token with People read scope.
    """

    DEFAULT_BASE_URL = "https://api.vanta.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_token", "label": "API Token", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return VantaConnector.DEFAULT_BASE_URL

    # Mapping from Vanta employment status to our internal status.
    _STATUS_MAP = {
        "CURRENT": "active",
        "ON_LEAVE": "active",
        "UPCOMING": "active",
        "INACTIVE": "inactive",
        "FORMER": "inactive",
    }

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Bearer {self.credentials['api_token'].strip()}",
            "Accept": "application/json",
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            cursor = None
            while True:
                params: dict = {"pageSize": 100}
                if cursor:
                    params["pageCursor"] = cursor

                resp = await client.get(
                    f"{base}/v1/people",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()

                result_data = body.get("results", body)
                people = result_data.get("data", [])

                for person in people:
                    name_obj = person.get("name", {})
                    display_name = name_obj.get("display", "")
                    email = person.get("emailAddress", "")

                    employment = person.get("employment", {})

                    roles = []
                    job_title = employment.get("jobTitle", "")
                    if job_title:
                        roles.append(job_title)
                    if not roles:
                        roles.append("Employee")

                    # Determine status from employment.status enum
                    emp_status = employment.get("status", "")
                    status = self._STATUS_MAP.get(emp_status, "active")

                    results.append({
                        "id": person.get("id", ""),
                        "email": email,
                        "name": display_name,
                        "roles": roles,
                        "status": status,
                        "last_login": "",
                        "created_at": employment.get("startDate", ""),
                    })

                page_info = result_data.get("pageInfo", {})
                if not page_info.get("hasNextPage", False):
                    break
                cursor = page_info.get("endCursor")
                if not cursor:
                    break

        return results
