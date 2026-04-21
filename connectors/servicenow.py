from __future__ import annotations

import httpx
from .base import BaseConnector

_FIELDS = ",".join([
    "sys_id",
    "email",
    "name",
    "user_name",
    "active",
    "locked_out",
    "last_login_time",
    "sys_created_on",
    "roles",
    "title",
    "department",
])

_PAGE_SIZE = 500


class ServiceNowConnector(BaseConnector):
    """Connector for ServiceNow user and role access review via the Table API."""

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {
                "name": "instance_url",
                "label": "Instance URL (e.g. https://yourorg.service-now.com)",
                "type": "text",
            },
            {"name": "username", "label": "Username", "type": "text"},
            {"name": "password", "label": "Password", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def fetch_users(self) -> list[dict]:
        instance_url = self.credentials["instance_url"].strip().rstrip("/")
        username = self.credentials["username"].strip()
        password = self.credentials["password"]

        endpoint = f"{instance_url}/api/now/table/sys_user"

        results: list[dict] = []
        offset = 0

        async with httpx.AsyncClient(
            timeout=30,
            auth=(username, password),
            headers={"Accept": "application/json"},
        ) as client:
            while True:
                resp = await client.get(
                    endpoint,
                    params={
                        "sysparm_fields": _FIELDS,
                        "sysparm_display_value": "true",
                        "sysparm_limit": _PAGE_SIZE,
                        "sysparm_offset": offset,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                records = data.get("result", [])
                if not records:
                    break

                for rec in records:
                    active = str(rec.get("active", "")).lower()
                    locked = str(rec.get("locked_out", "")).lower()

                    if locked == "true":
                        status = "locked"
                    elif active == "true":
                        status = "active"
                    else:
                        status = "inactive"

                    roles_raw = rec.get("roles", "")
                    if isinstance(roles_raw, str):
                        roles = [r.strip() for r in roles_raw.split(",") if r.strip()]
                    elif isinstance(roles_raw, list):
                        roles = roles_raw
                    else:
                        roles = []

                    dept = rec.get("department", "")
                    if isinstance(dept, dict):
                        dept = dept.get("display_value", "") or dept.get("value", "")

                    results.append({
                        "id": rec.get("sys_id", ""),
                        "email": rec.get("email", ""),
                        "name": rec.get("name", ""),
                        "user_name": rec.get("user_name", ""),
                        "roles": roles if roles else ["user"],
                        "status": status,
                        "last_login": rec.get("last_login_time", ""),
                        "created_at": rec.get("sys_created_on", ""),
                        "title": rec.get("title", ""),
                        "department": dept,
                    })

                # Check if there are more pages via X-Total-Count header
                total = resp.headers.get("X-Total-Count") or resp.headers.get("x-total-count")
                if total is not None:
                    if offset + _PAGE_SIZE >= int(total):
                        break
                else:
                    # Fallback: stop when fewer records than page size returned
                    if len(records) < _PAGE_SIZE:
                        break

                offset += _PAGE_SIZE

        return results
