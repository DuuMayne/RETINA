from __future__ import annotations
import xml.etree.ElementTree as ET
import httpx
from .base import BaseConnector


class NameCheapConnector(BaseConnector):
    """Connector for NameCheap account user access review.

    Uses the NameCheap XML API. Note: NameCheap's API is domain-management
    focused. This connector pulls contacts and sub-accounts where available.
    API access must be enabled and your IP whitelisted in the NameCheap dashboard.
    """

    DEFAULT_BASE_URL = "https://api.namecheap.com/xml.response"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "api_user", "label": "API User", "type": "text"},
            {"name": "api_key", "label": "API Key", "type": "password"},
            {"name": "username", "label": "Username", "type": "text"},
            {"name": "client_ip", "label": "Whitelisted Client IP", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return NameCheapConnector.DEFAULT_BASE_URL

    async def fetch_users(self) -> list[dict]:
        base = self.base_url or self.DEFAULT_BASE_URL
        params = {
            "ApiUser": self.credentials["api_user"].strip(),
            "ApiKey": self.credentials["api_key"].strip(),
            "UserName": self.credentials["username"].strip(),
            "ClientIp": self.credentials["client_ip"].strip(),
        }

        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Get account contacts/users via users.getContacts
            resp = await client.get(
                base,
                params={**params, "Command": "namecheap.users.getContacts"},
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""

            # Primary account holder
            results.append({
                "id": params["UserName"],
                "email": "",
                "name": params["UserName"],
                "roles": ["Account Owner"],
                "status": "active",
                "last_login": "",
                "created_at": "",
            })

            # Parse contacts from response
            for contact_type in ["Registrant", "Tech", "Admin", "AuxBilling"]:
                contact = root.find(f".//{ns}GetContactsResult/{ns}{contact_type}")
                if contact is not None:
                    email = contact.get("EmailAddress", "")
                    name = f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip()
                    if email and not any(r["email"] == email for r in results):
                        results.append({
                            "id": email,
                            "email": email,
                            "name": name,
                            "roles": [f"{contact_type} Contact"],
                            "status": "active",
                            "last_login": "",
                            "created_at": "",
                        })
                    elif email:
                        for r in results:
                            if r["email"] == email:
                                r["roles"].append(f"{contact_type} Contact")

        return results
