import os
import uuid
from datetime import datetime, timezone

from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db, RetinaUser

# RETINA expects to sit behind an authenticating reverse proxy (Cloudflare
# Access, oauth2-proxy, nginx + auth_request, etc.) that has already verified
# the user against Okta/Google and injects their identity as a header.
AUTH_EMAIL_HEADER = os.environ.get("AUTH_EMAIL_HEADER", "Cf-Access-Authenticated-User-Email")
AUTH_NAME_HEADER = os.environ.get("AUTH_NAME_HEADER", "")

# Comma-separated list of emails that get the admin role. If unset, the
# first person to ever access RETINA becomes admin (convenient for a first
# deploy, but set this explicitly once you know who your admins are).
ADMIN_EMAILS = {
    e.strip().lower() for e in os.environ.get("RETINA_ADMIN_EMAILS", "").split(",") if e.strip()
}

# Local-dev convenience only: used when no proxy is in front of the app,
# e.g. running `uv run python main.py` directly. Never set this in production.
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "")


def _resolve_identity(request: Request) -> tuple[str, str]:
    email = request.headers.get(AUTH_EMAIL_HEADER, "").strip().lower()
    if not email and DEV_USER_EMAIL:
        email = DEV_USER_EMAIL.strip().lower()
    if not email:
        raise HTTPException(
            401,
            f"No identity header found (expected '{AUTH_EMAIL_HEADER}'). RETINA relies on "
            "an authenticating reverse proxy in front of it — see README for setup.",
        )
    name = request.headers.get(AUTH_NAME_HEADER, "").strip() if AUTH_NAME_HEADER else ""
    return email, name or email


def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    email, name = _resolve_identity(request)

    user = db.query(RetinaUser).filter(RetinaUser.email == email).first()
    if not user:
        is_first = db.query(RetinaUser).count() == 0
        role = "admin" if (email in ADMIN_EMAILS or (is_first and not ADMIN_EMAILS)) else "reviewer"
        user = RetinaUser(id=str(uuid.uuid4()), email=email, name=name, role=role)
        db.add(user)
    else:
        user.name = name
        if ADMIN_EMAILS:
            user.role = "admin" if email in ADMIN_EMAILS else "reviewer"

    if user.is_active == "false":
        raise HTTPException(403, "This account has been deactivated in RETINA.")

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    return {"email": user.email, "name": user.name, "role": user.role}


async def require_auth(user: dict = Depends(get_current_user)) -> dict:
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user
