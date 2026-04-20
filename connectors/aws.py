from __future__ import annotations
import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timezone
import httpx
from .base import BaseConnector


class AWSConnector(BaseConnector):
    """Connector for AWS IAM user and policy access review using SigV4."""

    DEFAULT_BASE_URL = "https://iam.amazonaws.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {"name": "access_key_id", "label": "AWS Access Key ID", "type": "text"},
            {"name": "secret_access_key", "label": "AWS Secret Access Key", "type": "password"},
            {"name": "region", "label": "Region (default: us-east-1)", "type": "text"},
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return AWSConnector.DEFAULT_BASE_URL

    def _sign_v4(self, method, url, headers, body, service="iam"):
        """AWS Signature Version 4 signing."""
        access_key = self.credentials["access_key_id"].strip()
        secret_key = self.credentials["secret_access_key"].strip()
        region = self.credentials.get("region", "us-east-1").strip() or "us-east-1"

        parsed = urllib.parse.urlparse(url)
        now = datetime.now(timezone.utc)
        datestamp = now.strftime("%Y%m%d")
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        headers["x-amz-date"] = amz_date
        headers["host"] = parsed.hostname

        signed_headers = sorted(headers.keys())
        signed_headers_str = ";".join(h.lower() for h in signed_headers)
        canonical_headers = "".join(f"{h.lower()}:{headers[h].strip()}\n" for h in signed_headers)

        payload_hash = hashlib.sha256(body.encode() if isinstance(body, str) else body).hexdigest()

        canonical_request = "\n".join([
            method, parsed.path or "/", parsed.query or "",
            canonical_headers, signed_headers_str, payload_hash,
        ])

        scope = f"{datestamp}/{region}/{service}/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", amz_date, scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])

        def sign(key, msg):
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        k = sign(f"AWS4{secret_key}".encode(), datestamp)
        k = sign(k, region)
        k = sign(k, service)
        k = sign(k, "aws4_request")
        signature = hmac.new(k, string_to_sign.encode(), hashlib.sha256).hexdigest()

        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers_str}, Signature={signature}"
        )
        return headers

    async def _iam_request(self, client, params):
        """Make a signed IAM API request."""
        query = urllib.parse.urlencode(params)
        url = f"https://iam.amazonaws.com/?{query}"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        headers = self._sign_v4("GET", url, headers, "", service="iam")
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text

    async def fetch_users(self) -> list[dict]:
        import xml.etree.ElementTree as ET

        ns = {"iam": "https://iam.amazonaws.com/doc/2010-05-08/"}

        async with httpx.AsyncClient(timeout=30) as client:
            # 1. List all IAM users
            users = []
            marker = None
            while True:
                params = {"Action": "ListUsers", "Version": "2010-05-08", "MaxItems": "1000"}
                if marker:
                    params["Marker"] = marker
                xml_text = await self._iam_request(client, params)
                root = ET.fromstring(xml_text)

                for member in root.findall(".//iam:member", ns):
                    users.append({
                        "user_name": member.findtext("iam:UserName", "", ns),
                        "user_id": member.findtext("iam:UserId", "", ns),
                        "arn": member.findtext("iam:Arn", "", ns),
                        "created": member.findtext("iam:CreateDate", "", ns),
                        "password_last_used": member.findtext("iam:PasswordLastUsed", "", ns),
                    })

                is_truncated = root.findtext(".//iam:IsTruncated", "false", ns)
                if is_truncated.lower() != "true":
                    break
                marker = root.findtext(".//iam:Marker", "", ns)

            # 2. Get groups and policies for each user
            results = []
            for user in users:
                uname = user["user_name"]
                roles = []

                # Get user's groups
                params = {"Action": "ListGroupsForUser", "Version": "2010-05-08", "UserName": uname}
                xml_text = await self._iam_request(client, params)
                root = ET.fromstring(xml_text)
                for member in root.findall(".//iam:member", ns):
                    gname = member.findtext("iam:GroupName", "", ns)
                    if gname:
                        roles.append(f"Group: {gname}")

                # Get attached user policies
                params = {"Action": "ListAttachedUserPolicies", "Version": "2010-05-08", "UserName": uname}
                xml_text = await self._iam_request(client, params)
                root = ET.fromstring(xml_text)
                for member in root.findall(".//iam:member", ns):
                    pname = member.findtext("iam:PolicyName", "", ns)
                    if pname:
                        roles.append(f"Policy: {pname}")

                has_console = bool(user["password_last_used"])

                results.append({
                    "id": user["user_id"],
                    "email": "",
                    "name": uname,
                    "roles": roles if roles else ["No permissions"],
                    "status": "active",
                    "last_login": user["password_last_used"],
                    "created_at": user["created"],
                    "arn": user["arn"],
                    "console_access": str(has_console),
                })

        return results
