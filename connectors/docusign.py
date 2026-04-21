from __future__ import annotations
import httpx
from .base import BaseConnector


class DocuSignConnector(BaseConnector):
    """Connector for DocuSign eSignature account user access review.

    Uses the DocuSign eSignature REST API v2.1 Users:list endpoint.
    Endpoint: GET {base_url}/v2.1/accounts/{account_id}/users
    Auth: OAuth2 Bearer token (Authorization: Bearer {access_token}).
    Pagination: Uses start_position / count query params. The response
    envelope contains resultSetSize, startPosition, endPosition, and
    totalSetSize fields for cursor-based pagination.

    API docs: https://developers.docusign.com/docs/esign-rest-api/reference/users/users/list/
    """

    DEFAULT_BASE_URL = "https://na1.docusign.net/restapi"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "access_token", "label": "OAuth2 Access Token", "type": "password"},
            {"name": "account_id", "label": "Account ID", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return DocuSignConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        account_id = self.credentials["account_id"].strip()
        token = self.credentials["access_token"].strip()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        results: list[dict] = []
        start_position = 0
        page_size = 100

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{base}/v2.1/accounts/{account_id}/users",
                    headers=headers,
                    params={
                        "start_position": start_position,
                        "count": page_size,
                        "additional_info": "true",
                    },
                )
                resp.raise_for_status()
                body = resp.json()

                for user in body.get("users", []):
                    name_parts = [
                        user.get("firstName", ""),
                        user.get("lastName", ""),
                    ]
                    name = " ".join(p for p in name_parts if p) or user.get("userName", "")

                    # Collect roles from permissionProfileName and groupList
                    roles: list[str] = []
                    permission_profile = user.get("permissionProfileName", "")
                    if permission_profile:
                        roles.append(permission_profile)
                    for group in user.get("groupList", []):
                        group_name = group.get("groupName", "") if isinstance(group, dict) else str(group)
                        if group_name and group_name not in roles:
                            roles.append(group_name)
                    if not roles:
                        roles.append("User")

                    # Normalise status: DocuSign returns Active, ClosedAccount,
                    # ActivationRequired, ActivationSent, etc.
                    raw_status = user.get("userStatus", "")
                    status_map = {
                        "Active": "active",
                        "active": "active",
                        "ClosedAccount": "deactivated",
                        "ActivationRequired": "pending",
                        "ActivationSent": "pending",
                    }
                    status = status_map.get(raw_status, raw_status.lower() if raw_status else "unknown")

                    is_admin = "False"
                    if user.get("isAdmin") in (True, "true", "True"):
                        is_admin = "True"
                    elif permission_profile and "admin" in permission_profile.lower():
                        is_admin = "True"

                    results.append({
                        "id": user.get("userId", ""),
                        "email": user.get("email", ""),
                        "name": name,
                        "roles": roles,
                        "status": status,
                        "last_login": user.get("lastLogin", ""),
                        "created_at": user.get("createdDateTime", ""),
                        "is_admin": is_admin,
                        "account_type": user.get("userType", ""),
                        "permission_profile": permission_profile,
                        "groups": [
                            g.get("groupName", "") if isinstance(g, dict) else str(g)
                            for g in user.get("groupList", [])
                        ],
                        "uri": user.get("uri", ""),
                    })

                # Pagination: check if more pages remain
                total_set_size = int(body.get("totalSetSize", 0))
                end_position = int(body.get("endPosition", 0))

                if not body.get("users") or end_position + 1 >= total_set_size:
                    break

                start_position = end_position + 1

        return results
