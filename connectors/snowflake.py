from __future__ import annotations
import httpx
from .base import BaseConnector


class SnowflakeConnector(BaseConnector):
    """Connector for Snowflake user and role access review via SQL REST API.

    Uses username/password login to obtain a session token, then queries
    user and role information via the SQL API v2 (statements endpoint).
    Docs: https://docs.snowflake.com/en/developer-guide/sql-api/reference
    """

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "account", "label": "Account Identifier (e.g. xy12345.us-east-1)", "type": "text"},
            {"name": "username", "label": "Username", "type": "text"},
            {"name": "password", "label": "Password", "type": "password"},
            {"name": "warehouse", "label": "Warehouse (optional)", "type": "text"},
            {"name": "role", "label": "Role (default: ACCOUNTADMIN)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return None

    async def _get_token(self, client: httpx.AsyncClient, account: str) -> str:
        login_url = f"https://{account}.snowflakecomputing.com/session/v1/login-request"
        resp = await client.post(
            login_url,
            json={
                "data": {
                    "LOGIN_NAME": self.credentials["username"].strip(),
                    "PASSWORD": self.credentials["password"].strip(),
                    "ACCOUNT_NAME": account,
                    "WAREHOUSE": self.credentials.get("warehouse", "").strip() or None,
                    "ROLE": self.credentials.get("role", "").strip() or "ACCOUNTADMIN",
                }
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise Exception(f"Snowflake auth failed: {data.get('message', 'unknown error')}")
        return data["data"]["token"]

    async def _sql_query(self, client: httpx.AsyncClient, base: str, token: str, sql: str) -> dict:
        """Execute a SQL statement via the Snowflake SQL API."""
        import asyncio

        resp = await client.post(
            f"{base}/api/v2/statements",
            headers={
                "Authorization": f'Snowflake Token="{token}"',
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "statement": sql,
                "timeout": 60,
                "resultSetMetaData": {"format": "jsonv2"},
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Handle async execution (statement still running)
        if data.get("code") == "333334":
            handle = data["statementHandle"]
            for _ in range(30):
                await asyncio.sleep(1)
                resp = await client.get(
                    f"{base}/api/v2/statements/{handle}",
                    headers={"Authorization": f'Snowflake Token="{token}"'},
                )
                data = resp.json()
                if data.get("code") != "333334":
                    break
        return data

    async def fetch_users(self) -> list[dict]:
        account = self.credentials["account"].strip()
        base = f"https://{account}.snowflakecomputing.com"

        async with httpx.AsyncClient(timeout=60) as client:
            token = await self._get_token(client, account)

            # Get users via SHOW USERS
            users_data = await self._sql_query(client, base, token, "SHOW USERS")

            # Get role grants per user
            grants_data = await self._sql_query(
                client, base, token,
                "SELECT GRANTEE_NAME, ROLE FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS WHERE DELETED_ON IS NULL"
            )

            role_grants = {}
            if grants_data.get("data"):
                cols = [c["name"] for c in grants_data.get("resultSetMetaData", {}).get("rowType", [])]
                for row in grants_data.get("data", []):
                    row_dict = dict(zip(cols, row))
                    grantee = row_dict.get("GRANTEE_NAME", "")
                    role_name = row_dict.get("ROLE", "")
                    role_grants.setdefault(grantee, []).append(role_name)

            # Parse users
            results = []
            cols = [c["name"] for c in users_data.get("resultSetMetaData", {}).get("rowType", [])]
            for row in users_data.get("data", []):
                row_dict = dict(zip(cols, row))
                name = row_dict.get("name", "")
                login_name = row_dict.get("login_name", "")
                display_name = row_dict.get("display_name", "")
                email = row_dict.get("email", "")
                disabled = row_dict.get("disabled", "false")
                last_login = row_dict.get("last_success_login", "")
                created = row_dict.get("created_on", "")
                default_role = row_dict.get("default_role", "")
                has_password = row_dict.get("has_password", "")
                ext_authn_duo = row_dict.get("ext_authn_duo", "false")
                has_mfa = row_dict.get("has_mfa", "false")

                roles = role_grants.get(name, [])
                if default_role and default_role not in roles:
                    roles.insert(0, default_role)
                if not roles:
                    roles = ["PUBLIC"]

                results.append({
                    "id": name,
                    "email": email,
                    "name": display_name or name,
                    "roles": roles,
                    "status": "disabled" if disabled == "true" else "active",
                    "last_login": last_login,
                    "created_at": created,
                    "login_name": login_name,
                    "mfa_enabled": str(has_mfa == "true" or ext_authn_duo == "true"),
                    "has_password": has_password,
                })

        return results
