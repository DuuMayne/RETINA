from __future__ import annotations
import json
import time
import hashlib
import hmac
import base64
import httpx
from .base import BaseConnector


class GoogleWorkspaceConnector(BaseConnector):
    """Connector for Google Workspace user and role access review.

    Uses a service account with domain-wide delegation.
    The service account must have the Admin SDK API enabled and
    be granted the following scopes via domain-wide delegation:
    - https://www.googleapis.com/auth/admin.directory.user.readonly
    - https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly
    """

    DEFAULT_BASE_URL = "https://admin.googleapis.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "service_account_json", "label": "Service Account JSON (paste full JSON)", "type": "password"},
            {"name": "admin_email", "label": "Admin Email (for delegation)", "type": "text"},
            {"name": "customer_id", "label": "Customer ID (or 'my_customer')", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return GoogleWorkspaceConnector.DEFAULT_BASE_URL

    def _make_jwt(self, sa: dict, admin_email: str) -> str:
        import struct
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": sa["client_email"],
            "sub": admin_email,
            "scope": "https://www.googleapis.com/auth/admin.directory.user.readonly https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }

        def b64url(data):
            return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()

        segments = f"{b64url(header)}.{b64url(payload)}"

        # Sign with RSA-SHA256 using cryptography lib
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
        signature = private_key.sign(segments.encode(), padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

        return f"{segments}.{sig_b64}"

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        sa = json.loads(self.credentials["service_account_json"])
        admin_email = self.credentials["admin_email"].strip()
        jwt_token = self._make_jwt(sa, admin_email)

        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt_token,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def fetch_users(self) -> list[dict]:
        customer_id = self.credentials.get("customer_id", "my_customer").strip() or "my_customer"

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            # 1. Get role assignments for mapping user -> roles
            role_map = {}  # role_id -> role_name
            resp = await client.get(
                f"https://admin.googleapis.com/admin/directory/v1/customer/{customer_id}/roles",
                headers=headers,
            )
            if resp.status_code == 200:
                for role in resp.json().get("items", []):
                    role_map[role["roleId"]] = role["roleName"]

            # Get role assignments
            user_roles = {}  # user_id -> [role_names]
            page_token = None
            while True:
                params = {"maxResults": 100}
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(
                    f"https://admin.googleapis.com/admin/directory/v1/customer/{customer_id}/roleassignments",
                    headers=headers,
                    params=params,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                for assignment in data.get("items", []):
                    uid = assignment.get("assignedTo", "")
                    rid = assignment.get("roleId", "")
                    role_name = role_map.get(rid, rid)
                    user_roles.setdefault(uid, []).append(role_name)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            # 2. Get all users
            results = []
            page_token = None
            while True:
                params = {"customer": customer_id, "maxResults": 500, "orderBy": "email"}
                if page_token:
                    params["pageToken"] = page_token

                resp = await client.get(
                    f"https://admin.googleapis.com/admin/directory/v1/users",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                for user in data.get("users", []):
                    uid = user.get("id", "")
                    roles = user_roles.get(uid, [])
                    if user.get("isAdmin"):
                        roles.append("Super Admin")
                    if user.get("isDelegatedAdmin"):
                        roles.append("Delegated Admin")
                    if not roles:
                        roles.append("User")

                    results.append({
                        "id": uid,
                        "email": user.get("primaryEmail", ""),
                        "name": user.get("name", {}).get("fullName", ""),
                        "roles": roles,
                        "status": "suspended" if user.get("suspended") else "active",
                        "last_login": user.get("lastLoginTime", ""),
                        "created_at": user.get("creationTime", ""),
                        "org_unit": user.get("orgUnitPath", ""),
                        "two_factor_enabled": str(user.get("isEnrolledIn2Sv", False)),
                    })

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        return results
