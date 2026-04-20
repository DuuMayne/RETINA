from __future__ import annotations
import httpx
from .base import BaseConnector


class NewRelicConnector(BaseConnector):
    """Connector for New Relic user and role access review via NerdGraph."""

    DEFAULT_BASE_URL = "https://api.newrelic.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_key", "label": "User API Key", "type": "password"},
            {"name": "auth_domain_id", "label": "Authentication Domain ID", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return NewRelicConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        headers = {
            "API-Key": self.credentials["api_key"].strip(),
            "Content-Type": "application/json",
        }
        auth_domain_id = self.credentials["auth_domain_id"].strip()

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            cursor = None
            while True:
                cursor_clause = f', cursor: "{cursor}"' if cursor else ""
                query = {
                    "query": f"""{{
                        actor {{
                            organization {{
                                userManagement {{
                                    authenticationDomains(id: "{auth_domain_id}") {{
                                        authenticationDomains {{
                                            users(cursor: null{cursor_clause}) {{
                                                users {{
                                                    id
                                                    name
                                                    email
                                                    type {{
                                                        displayName
                                                    }}
                                                    groups {{
                                                        groups {{
                                                            displayName
                                                        }}
                                                    }}
                                                    timeZone
                                                    lastActive
                                                }}
                                                nextCursor
                                            }}
                                        }}
                                    }}
                                }}
                            }}
                        }}
                    }}"""
                }

                resp = await client.post(f"{base}/graphql", headers=headers, json=query)
                resp.raise_for_status()
                data = resp.json()

                domains = (data.get("data", {}).get("actor", {}).get("organization", {})
                          .get("userManagement", {}).get("authenticationDomains", {})
                          .get("authenticationDomains", []))

                if not domains:
                    break

                domain = domains[0]
                users_data = domain.get("users", {})

                for user in users_data.get("users", []):
                    groups = [g["displayName"] for g in user.get("groups", {}).get("groups", [])]
                    user_type = user.get("type", {}).get("displayName", "")

                    roles = [user_type] if user_type else []
                    roles.extend(groups)

                    results.append({
                        "id": user.get("id", ""),
                        "email": user.get("email", ""),
                        "name": user.get("name", ""),
                        "roles": roles if roles else ["Basic"],
                        "status": "active",
                        "last_login": user.get("lastActive", ""),
                        "created_at": "",
                    })

                cursor = users_data.get("nextCursor")
                if not cursor:
                    break

        return results
