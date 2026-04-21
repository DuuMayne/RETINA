from __future__ import annotations

import httpx
from .base import BaseConnector


class WorkdayConnector(BaseConnector):
    """Connector for Workday HCM user/worker access review.

    Uses the Workday REST API for Workers with OAuth2 client credentials
    authentication.  The tenant-specific base URL must be provided by the
    user (e.g. https://wd5-services1.myworkday.com).
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "client_id", "label": "OAuth2 Client ID", "type": "text"},
            {"name": "client_secret", "label": "OAuth2 Client Secret", "type": "password"},
            {"name": "tenant", "label": "Tenant ID (e.g. yourcompany)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None  # User provides their Workday service URL

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        """Obtain an OAuth2 access token via client_credentials grant."""
        base = (self.base_url or "").rstrip("/")
        tenant = self.credentials["tenant"].strip()
        token_url = f"{base}/ccx/oauth2/{tenant}/token"

        resp = await client.post(
            token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials["client_id"].strip(),
                "client_secret": self.credentials["client_secret"].strip(),
            },
        )
        if resp.status_code not in (200, 201):
            detail = resp.text
            try:
                detail = resp.json()
            except Exception:
                pass
            raise Exception(f"Workday OAuth2 auth failed ({resp.status_code}): {detail}")

        return resp.json()["access_token"]

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or "").rstrip("/")
        tenant = self.credentials["tenant"].strip()
        workers_url = f"{base}/ccx/api/v1/{tenant}/workers"
        page_size = 100

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._authenticate(client)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            results: list[dict] = []
            offset = 0

            while True:
                resp = await client.get(
                    workers_url,
                    headers=headers,
                    params={"limit": page_size, "offset": offset},
                )
                resp.raise_for_status()
                body = resp.json()

                workers = body.get("data", [])
                if not workers:
                    break

                for worker in workers:
                    worker_id = worker.get("id", "")

                    # descriptor is the display name in the REST response
                    name = worker.get("descriptor", "")

                    # primaryWorkEmail is nested; handle both flat and nested shapes
                    email = ""
                    primary_email = worker.get("primaryWorkEmail")
                    if isinstance(primary_email, dict):
                        email = primary_email.get("emailAddress", "")
                    elif isinstance(primary_email, str):
                        email = primary_email

                    # Roles: use businessTitle and supervisory org as context
                    roles: list[str] = []
                    business_title = worker.get("businessTitle", "")
                    if business_title:
                        roles.append(business_title)
                    sup_org = worker.get("supervisoryOrganization")
                    if isinstance(sup_org, dict):
                        org_name = sup_org.get("descriptor", "")
                        if org_name:
                            roles.append(org_name)
                    elif isinstance(sup_org, str) and sup_org:
                        roles.append(sup_org)

                    # Status
                    is_active = worker.get("active")
                    if is_active is None:
                        # Some API versions nest status differently
                        is_active = worker.get("isActive")
                    if isinstance(is_active, bool):
                        status = "active" if is_active else "inactive"
                    elif isinstance(is_active, str):
                        status = "active" if is_active.lower() in ("true", "1") else "inactive"
                    else:
                        status = "unknown"

                    # Dates
                    last_login = worker.get("lastLogin", "")
                    created_at = worker.get("createdMoment", "") or worker.get("hireDate", "")

                    results.append({
                        "id": worker_id,
                        "email": email,
                        "name": name,
                        "roles": roles,
                        "status": status,
                        "last_login": last_login,
                        "created_at": created_at,
                    })

                total = body.get("total", 0)
                offset += len(workers)
                if offset >= total:
                    break

        return results
