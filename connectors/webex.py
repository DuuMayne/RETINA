from __future__ import annotations

import httpx

from .base import BaseConnector


class WebexConnector(BaseConnector):
    """Connector for Cisco Webex user access review.

    Uses the Webex People API to enumerate users in the organization.
    Requires a bot or admin access token with the ``spark:people_read``
    scope (or a Compliance Officer / admin-scoped token for full org
    visibility).

    Pagination follows the RFC 5988 Link header approach — each response
    may include a ``Link`` header with ``rel="next"`` pointing to the
    next page URL.
    """

    DEFAULT_BASE_URL = "https://webexapis.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {
                "name": "access_token",
                "label": "Bot or Admin Access Token",
                "type": "password",
            },
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return WebexConnector.DEFAULT_BASE_URL

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_link_next(link_header: str | None) -> str | None:
        """Extract the URL with rel=\"next\" from an RFC 5988 Link header."""
        if not link_header:
            return None
        for part in link_header.split(","):
            segments = part.strip().split(";")
            if len(segments) < 2:
                continue
            url_segment = segments[0].strip()
            for param in segments[1:]:
                if "rel" in param and "next" in param:
                    return url_segment.strip("<>")
        return None

    @staticmethod
    def _status_label(person: dict) -> str:
        """Derive a human-readable status string from a Webex person record."""
        if person.get("invitePending"):
            return "pending"
        if not person.get("loginEnabled", True):
            return "disabled"
        raw = person.get("status", "unknown")
        # Webex returns 'active', 'inactive', 'unknown', etc.
        return raw if raw else "unknown"

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        token = self.credentials["access_token"].strip()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        results: list[dict] = []
        url: str | None = f"{base}/v1/people"
        params: dict | None = {"max": 100}

        async with httpx.AsyncClient(timeout=30) as client:
            while url:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

                for person in data.get("items", []):
                    emails = person.get("emails", [])
                    email = emails[0] if emails else ""

                    first = person.get("firstName", "")
                    last = person.get("lastName", "")
                    display = person.get("displayName", "")
                    name = display or f"{first} {last}".strip()

                    roles = person.get("roles", [])
                    person_type = person.get("type", "")

                    is_admin = "True" if roles else "False"

                    results.append({
                        "id": person.get("id", ""),
                        "email": email,
                        "name": name,
                        "roles": roles if roles else [person_type or "member"],
                        "status": self._status_label(person),
                        "last_login": person.get("lastActivity", ""),
                        "created_at": person.get("created", ""),
                        "account_type": person_type,
                        "is_admin": is_admin,
                        "login_enabled": str(person.get("loginEnabled", "")),
                        "invite_pending": str(person.get("invitePending", False)),
                        "org_id": person.get("orgId", ""),
                    })

                # Pagination: follow Link rel="next" header
                next_url = self._parse_link_next(resp.headers.get("Link"))
                if next_url:
                    url = next_url
                    # The next URL from the Link header is fully qualified
                    # and already contains query parameters, so clear params.
                    params = None
                else:
                    url = None

        return results
