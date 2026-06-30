import os
import hmac
import hashlib
import secrets
import json
import base64
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session

OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN", "")
OKTA_CLIENT_ID = os.environ.get("OKTA_CLIENT_ID", "")
OKTA_CLIENT_SECRET = os.environ.get("OKTA_CLIENT_SECRET", "")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000")

OKTA_REDIRECT_URI   = f"{APP_BASE_URL}/auth/callback"
GOOGLE_REDIRECT_URI = f"{APP_BASE_URL}/auth/google/callback"


def _load_session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET", "")
    if secret:
        return secret
    key_path = os.path.join(os.environ.get("RETINA_DATA_DIR", "."), "session.key")
    if os.path.exists(key_path):
        with open(key_path) as f:
            return f.read().strip()
    secret = secrets.token_hex(32)
    with open(key_path, "w") as f:
        f.write(secret)
    os.chmod(key_path, 0o600)
    return secret


SESSION_SECRET = _load_session_secret()


def _mac(data: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


def make_session_cookie(email: str, name: str, role: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": email, "name": name, "role": role}).encode()
    ).decode()
    return f"{payload}.{_mac(payload)}"


def read_session_cookie(cookie: str) -> Optional[dict]:
    try:
        payload, sig = cookie.rsplit(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_mac(payload), sig):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(payload).decode())
    except Exception:
        return None


def get_session(request: Request) -> Optional[dict]:
    cookie = request.cookies.get("retina_session")
    return read_session_cookie(cookie) if cookie else None


async def require_auth(request: Request) -> dict:
    session = get_session(request)
    if not session:
        raise HTTPException(401, "Not authenticated")
    return session


async def require_admin(request: Request) -> dict:
    session = get_session(request)
    if not session:
        raise HTTPException(401, "Not authenticated")
    if session.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return session


def okta_authorize_url(state: str) -> str:
    return (
        f"https://{OKTA_DOMAIN}/oauth2/v1/authorize?"
        + urlencode({
            "client_id": OKTA_CLIENT_ID,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": OKTA_REDIRECT_URI,
            "state": state,
        })
    )


async def okta_exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        token_r = await client.post(
            f"https://{OKTA_DOMAIN}/oauth2/v1/token",
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": OKTA_REDIRECT_URI},
            auth=(OKTA_CLIENT_ID, OKTA_CLIENT_SECRET),
            headers={"Accept": "application/json"},
        )
        token_r.raise_for_status()
        access_token = token_r.json()["access_token"]

        info_r = await client.get(
            f"https://{OKTA_DOMAIN}/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info_r.raise_for_status()
        return info_r.json()


def google_authorize_url(state: str) -> str:
    return (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "state": state,
            "access_type": "online",
        })
    )


async def google_exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        token_r = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
            },
            headers={"Accept": "application/json"},
        )
        token_r.raise_for_status()
        access_token = token_r.json()["access_token"]

        info_r = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info_r.raise_for_status()
        return info_r.json()


def upsert_retina_user(db: Session, userinfo: dict):
    from database import RetinaUser, AuditLog
    email = (userinfo.get("email") or "").lower().strip()
    if not email:
        raise ValueError("IdP userinfo missing email")

    is_first = db.query(RetinaUser).count() == 0
    user = db.query(RetinaUser).filter(RetinaUser.email == email).first()
    if not user:
        user = RetinaUser(
            id=str(uuid.uuid4()),
            email=email,
            name=userinfo.get("name", email),
            okta_sub=userinfo.get("sub", ""),
            role="admin" if is_first else "reviewer",
        )
        db.add(user)
    else:
        user.name = userinfo.get("name", user.name)
        user.okta_sub = userinfo.get("sub", user.okta_sub)

    user.last_login = datetime.now(timezone.utc)

    db.add(AuditLog(
        id=str(uuid.uuid4()),
        action="login",
        actor_email=email,
    ))
    db.commit()
    db.refresh(user)
    return user
