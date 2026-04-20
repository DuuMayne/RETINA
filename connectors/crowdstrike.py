from __future__ import annotations
import httpx
from .base import BaseConnector


class CrowdStrikeConnector(BaseConnector):
    """Connector for CrowdStrike Falcon user/role access review.

    Uses the User Management v2 API endpoints.
    Required API scopes: User Management: Read, Flight Control: Read
    """

    DEFAULT_BASE_URL = "https://api.crowdstrike.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "client_id", "label": "Client ID", "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "type": "password"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return CrowdStrikeConnector.DEFAULT_BASE_URL

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        base = self.base_url or self.DEFAULT_BASE_URL
        resp = await client.post(
            f"{base}/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
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
            raise Exception(f"Auth failed ({resp.status_code}): {detail}")
        return resp.json()["access_token"]

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            # 1. Get all user UUIDs via user-management v2 API
            user_ids = []
            offset = 0
            while True:
                resp = await client.get(
                    f"{base}/user-management/queries/users/v2",
                    headers=headers,
                    params={"offset": offset, "limit": 500},
                )
                resp.raise_for_status()
                body = resp.json()
                batch = body.get("resources", [])
                if not batch:
                    break
                user_ids.extend(batch)
                if len(batch) < 500:
                    break
                offset += len(batch)

            if not user_ids:
                return []

            # 2. Get user details in batches of 500
            users_detail = []
            for i in range(0, len(user_ids), 500):
                chunk = user_ids[i : i + 500]
                resp = await client.post(
                    f"{base}/user-management/entities/users/GET/v2",
                    headers=headers,
                    json={"ids": chunk},
                )
                resp.raise_for_status()
                users_detail.extend(resp.json().get("resources", []))

            # 3. Get available roles for mapping ID -> name
            resp = await client.get(
                f"{base}/user-management/queries/roles/v1",
                headers=headers,
            )
            resp.raise_for_status()
            all_role_ids = resp.json().get("resources", [])

            role_map = {}
            if all_role_ids:
                resp = await client.get(
                    f"{base}/user-management/entities/roles/v1",
                    headers=headers,
                    params={"ids": all_role_ids},
                )
                resp.raise_for_status()
                for role in resp.json().get("resources", []):
                    role_map[role["id"]] = role.get("display_name", role.get("name", role["id"]))

            # 4. Build results with roles from user detail
            results = []
            for user in users_detail:
                uuid = user.get("uuid", "")
                # v2 includes roles in user detail response
                user_role_ids = user.get("roles", [])
                role_names = [role_map.get(rid, rid) for rid in user_role_ids]

                # Fallback: query roles per user if not in detail
                if not user_role_ids:
                    resp = await client.get(
                        f"{base}/user-management/queries/roles/v1",
                        headers=headers,
                        params={"user_uuid": uuid},
                    )
                    if resp.status_code == 200:
                        user_role_ids = resp.json().get("resources", [])
                        role_names = [role_map.get(rid, rid) for rid in user_role_ids]

                results.append({
                    "id": uuid,
                    "email": user.get("uid", ""),
                    "name": f"{user.get('firstName', '')} {user.get('lastName', '')}".strip(),
                    "roles": role_names,
                    "status": user.get("status", "unknown"),
                    "last_login": user.get("lastLoginAt", ""),
                    "created_at": user.get("createdAt", ""),
                })

            return results
