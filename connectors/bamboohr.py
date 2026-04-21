from __future__ import annotations

import httpx
from .base import BaseConnector


class BambooHRConnector(BaseConnector):
    """Connector for BambooHR employee directory access review.

    Uses the BambooHR Employee Directory API.
    Auth: Basic auth with API key as username and "x" as password.
    Required: API key with employee directory read access.
    """

    DEFAULT_BASE_URL = "https://api.bamboohr.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "API Key", "type": "password"},
            {
                "name": "company_domain",
                "label": "Company Subdomain (e.g. yourcompany)",
                "type": "text",
            },
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return BambooHRConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        api_key = self.credentials["api_key"].strip()
        company_domain = self.credentials["company_domain"].strip()

        auth = httpx.BasicAuth(username=api_key, password="x")
        headers = {
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            resp = await client.get(
                f"{base}/api/gateway.php/{company_domain}/v1/employees/directory",
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()

        employees = body.get("employees", [])
        results = []

        for emp in employees:
            first = emp.get("firstName", "")
            last = emp.get("lastName", "")
            display_name = emp.get("displayName", "")
            name = display_name or f"{first} {last}".strip()

            email = emp.get("workEmail", "")

            # BambooHR status field is typically "Active" or "Inactive"
            raw_status = (emp.get("status", "") or "").lower()
            if raw_status == "active":
                status = "active"
            elif raw_status in ("inactive", "terminated"):
                status = "inactive"
            else:
                status = raw_status or "unknown"

            # Build roles from job title and department
            roles = []
            job_title = emp.get("jobTitle", "")
            department = emp.get("department", "")
            if job_title:
                roles.append(job_title)
            if department:
                roles.append(department)
            if not roles:
                roles.append("Employee")

            results.append({
                "id": str(emp.get("id", "")),
                "email": email,
                "name": name,
                "roles": roles,
                "status": status,
                "last_login": "",
                "created_at": emp.get("hireDate", ""),
                "department": department,
                "job_title": job_title,
                "location": emp.get("location", ""),
                "division": emp.get("division", ""),
                "supervisor": emp.get("supervisor", ""),
                "photo_url": emp.get("photoUrl", ""),
            })

        return results
