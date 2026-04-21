from __future__ import annotations
import base64
import email.utils
import hashlib
import hmac
import urllib.parse
from datetime import datetime, timezone
import httpx
from .base import BaseConnector


class DuoConnector(BaseConnector):
    """Connector for Duo Security MFA user access review.

    Uses the Duo Admin API v1 with HMAC-SHA1 signed requests.
    Required: Admin API application with Grant read resource permission.
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "integration_key", "label": "Integration Key (ikey)", "type": "text"},
            {"name": "secret_key", "label": "Secret Key (skey)", "type": "password"},
            {"name": "api_hostname", "label": "API Hostname (e.g. api-XXXXXXXX.duosecurity.com)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    def _sign_request(
        self, method: str, host: str, path: str, params: dict,
    ) -> dict[str, str]:
        """Build Duo HMAC-SHA1 signed headers for a request."""
        ikey = self.credentials["integration_key"].strip()
        skey = self.credentials["secret_key"].strip()

        date = email.utils.formatdate()
        canon = "\n".join([
            date,
            method.upper(),
            host.lower(),
            path,
            urllib.parse.urlencode(sorted(params.items())),
        ])
        sig = hmac.new(skey.encode(), canon.encode(), hashlib.sha1).hexdigest()
        auth = base64.b64encode(f"{ikey}:{sig}".encode()).decode()

        return {
            "Date": date,
            "Authorization": f"Basic {auth}",
        }

    @staticmethod
    def _unix_to_iso(ts: int | float | None) -> str:
        """Convert a Unix timestamp to ISO 8601 string, or return empty."""
        if ts is None:
            return ""
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            return ""

    async def fetch_users(self) -> list[dict]:
        host = self.credentials["api_hostname"].strip().rstrip("/")
        path = "/admin/v1/users"
        base_url = f"https://{host}"

        results = []
        offset = 0
        limit = 300

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {"offset": str(offset), "limit": str(limit)}
                headers = self._sign_request("GET", host, path, params)

                resp = await client.get(
                    f"{base_url}{path}",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()

                users = body.get("response", [])
                for user in users:
                    status = user.get("status", "unknown")
                    is_enrolled = user.get("is_enrolled", False)

                    roles = [status]
                    if is_enrolled:
                        roles.append("enrolled")

                    results.append({
                        "id": user.get("user_id", ""),
                        "email": user.get("email", ""),
                        "name": user.get("realname", ""),
                        "roles": roles,
                        "status": status,
                        "last_login": self._unix_to_iso(user.get("last_login")),
                        "created_at": self._unix_to_iso(user.get("created")),
                        "mfa_enabled": str(is_enrolled),
                    })

                metadata = body.get("metadata", {})
                next_offset = metadata.get("next_offset")
                if next_offset is None:
                    break
                offset = next_offset

        return results
