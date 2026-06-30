import io
import csv
import secrets
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import (
    init_db, get_db,
    Application, AccessSnapshot,
    RetinaUser, ReviewItem, AuditLog,
)
from crypto import encrypt_credentials, decrypt_credentials
from connectors import get_connector, CONNECTORS
from scheduler import (
    start_scheduler, stop_scheduler, schedule_app, unschedule_app,
    get_scheduled_jobs, SCHEDULE_PRESETS, sync_application_task,
)
from auth import (
    get_session, require_auth, require_admin,
    okta_authorize_url, okta_exchange_code,
    google_authorize_url, google_exchange_code,
    upsert_retina_user, make_session_cookie,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="RETINA", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Auth ──

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.get("/auth/login")
async def auth_login():
    state = secrets.token_urlsafe(16)
    resp = RedirectResponse(okta_authorize_url(state))
    resp.set_cookie("okta_state", state, httponly=True, samesite="lax", max_age=600)
    return resp


@app.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    db: Session = Depends(get_db),
):
    if error:
        return RedirectResponse(f"/login?error={error_description or error}")

    expected = request.cookies.get("okta_state")
    if not state or state != expected:
        return RedirectResponse("/login?error=Invalid+state+parameter")

    try:
        userinfo = await okta_exchange_code(code)
        user = upsert_retina_user(db, userinfo)
    except Exception as e:
        return RedirectResponse(f"/login?error={str(e)}")

    resp = RedirectResponse("/")
    resp.set_cookie(
        "retina_session",
        make_session_cookie(user.email, user.name, user.role),
        httponly=True, samesite="lax", max_age=86400 * 7,
    )
    resp.delete_cookie("okta_state")
    return resp


@app.get("/auth/google/login")
async def google_login():
    state = secrets.token_urlsafe(16)
    resp = RedirectResponse(google_authorize_url(state))
    resp.set_cookie("okta_state", state, httponly=True, samesite="lax", max_age=600)
    return resp


@app.get("/auth/google/callback")
async def google_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    db: Session = Depends(get_db),
):
    if error:
        return RedirectResponse(f"/login?error={error_description or error}")

    expected = request.cookies.get("okta_state")
    if not state or state != expected:
        return RedirectResponse("/login?error=Invalid+state+parameter")

    try:
        userinfo = await google_exchange_code(code)
        user = upsert_retina_user(db, userinfo)
    except Exception as e:
        return RedirectResponse(f"/login?error={str(e)}")

    resp = RedirectResponse("/")
    resp.set_cookie(
        "retina_session",
        make_session_cookie(user.email, user.name, user.role),
        httponly=True, samesite="lax", max_age=86400 * 7,
    )
    resp.delete_cookie("okta_state")
    return resp


@app.get("/auth/logout")
async def auth_logout():
    resp = RedirectResponse("/login")
    resp.delete_cookie("retina_session")
    return resp


@app.get("/auth/me")
async def auth_me(session: dict = Depends(require_auth)):
    return session


# ── Pages ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": session})


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    session = get_session(request)
    if not session:
        return RedirectResponse("/login")
    return templates.TemplateResponse("review.html", {"request": request, "user": session})


# ── API: Connector metadata ──

@app.get("/api/connectors")
async def list_connectors(session: dict = Depends(require_auth)):
    result = {}
    for key, cls in CONNECTORS.items():
        result[key] = {
            "fields": cls.credential_fields(),
            "default_base_url": cls.default_base_url(),
        }
    return result


# ── API: Applications CRUD ──

@app.get("/api/applications")
async def list_applications(db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    apps = db.query(Application).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "connector_type": a.connector_type,
            "base_url": a.base_url,
            "last_sync": a.last_sync.isoformat() if a.last_sync else None,
        }
        for a in apps
    ]


@app.post("/api/applications")
async def create_application(body: dict, db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    app_id = str(uuid.uuid4())
    connector_type = body["connector_type"]
    if connector_type not in CONNECTORS:
        raise HTTPException(400, f"Unknown connector: {connector_type}")

    credentials = body.get("credentials", {})
    a = Application(
        id=app_id,
        name=body["name"],
        connector_type=connector_type,
        credentials_encrypted=encrypt_credentials(credentials),
        base_url=body.get("base_url") or None,
    )
    db.add(a)
    db.commit()
    return {"id": app_id, "name": a.name}


@app.get("/api/applications/{app_id}")
async def get_application(app_id: str, db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    creds = decrypt_credentials(a.credentials_encrypted)
    masked = {k: ("*" * 8 + v[-4:] if len(v) > 4 else "****") for k, v in creds.items()}
    return {
        "id": a.id,
        "name": a.name,
        "connector_type": a.connector_type,
        "base_url": a.base_url,
        "credentials": masked,
    }


@app.put("/api/applications/{app_id}")
async def update_application(app_id: str, body: dict, db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    if "name" in body:
        a.name = body["name"]
    if "base_url" in body:
        a.base_url = body["base_url"] or None
    if "credentials" in body:
        new_creds = body["credentials"]
        existing_creds = decrypt_credentials(a.credentials_encrypted)
        for k, v in new_creds.items():
            if v and not v.startswith("********"):
                existing_creds[k] = v
        a.credentials_encrypted = encrypt_credentials(existing_creds)
    db.commit()
    return {"ok": True}


@app.delete("/api/applications/{app_id}")
async def delete_application(app_id: str, db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    db.query(AccessSnapshot).filter(AccessSnapshot.application_id == app_id).delete()
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── API: Sync ──

@app.post("/api/applications/{app_id}/sync")
async def sync_application(app_id: str, db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")

    credentials = decrypt_credentials(a.credentials_encrypted)
    connector = get_connector(a.connector_type, credentials, a.base_url)

    try:
        users = await connector.fetch_users()
    except Exception as e:
        raise HTTPException(502, f"Sync failed: {e}")

    snapshot = AccessSnapshot(
        id=str(uuid.uuid4()),
        application_id=app_id,
        synced_at=datetime.now(timezone.utc),
        users=users,
    )
    db.add(snapshot)
    a.last_sync = snapshot.synced_at
    db.commit()

    return {"snapshot_id": snapshot.id, "user_count": len(users), "users": users}


# ── API: Snapshots ──

@app.get("/api/applications/{app_id}/snapshots")
async def list_snapshots(app_id: str, db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    snaps = (
        db.query(AccessSnapshot)
        .filter(AccessSnapshot.application_id == app_id)
        .order_by(AccessSnapshot.synced_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": s.id,
            "synced_at": s.synced_at.isoformat(),
            "user_count": len(s.users),
        }
        for s in snaps
    ]


@app.get("/api/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str, db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    s = db.query(AccessSnapshot).filter(AccessSnapshot.id == snapshot_id).first()
    if not s:
        raise HTTPException(404, "Snapshot not found")
    return {"id": s.id, "synced_at": s.synced_at.isoformat(), "users": s.users}


# ── API: Scheduling ──

@app.get("/api/schedules")
async def list_schedules(db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    apps = db.query(Application).all()
    return [
        {
            "app_id": a.id,
            "app_name": a.name,
            "sync_schedule": a.sync_schedule,
            "sync_enabled": a.sync_enabled == "true",
            "last_sync": a.last_sync.isoformat() if a.last_sync else None,
            "last_sync_status": a.last_sync_status,
        }
        for a in apps
    ]


@app.get("/api/schedules/presets")
async def list_presets(session: dict = Depends(require_auth)):
    return SCHEDULE_PRESETS


@app.get("/api/schedules/jobs")
async def list_jobs(session: dict = Depends(require_auth)):
    return get_scheduled_jobs()


@app.put("/api/applications/{app_id}/schedule")
async def set_schedule(app_id: str, body: dict, db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")

    schedule = body.get("schedule", "").strip()
    enabled = body.get("enabled", False)

    a.sync_schedule = schedule if schedule else None
    a.sync_enabled = "true" if enabled else "false"
    db.commit()

    if enabled and schedule:
        schedule_app(app_id, schedule)
    else:
        unschedule_app(app_id)

    return {
        "app_id": app_id,
        "sync_schedule": a.sync_schedule,
        "sync_enabled": a.sync_enabled == "true",
    }


@app.post("/api/applications/{app_id}/sync-now")
async def trigger_sync_now(app_id: str, db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")

    await sync_application_task(app_id)

    db.refresh(a)
    return {
        "app_id": app_id,
        "last_sync": a.last_sync.isoformat() if a.last_sync else None,
        "last_sync_status": a.last_sync_status,
    }


# ── API: Cross-reference ──

@app.get("/api/cross-reference")
async def cross_reference(db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    okta_apps = db.query(Application).filter(Application.connector_type == "okta").all()
    if not okta_apps:
        raise HTTPException(400, "No Okta application configured. Add an Okta connector to use cross-referencing.")

    okta_users_by_email = {}
    for okta_app in okta_apps:
        snap = (
            db.query(AccessSnapshot)
            .filter(AccessSnapshot.application_id == okta_app.id)
            .order_by(AccessSnapshot.synced_at.desc())
            .first()
        )
        if snap:
            for user in snap.users:
                email = (user.get("email") or "").lower().strip()
                if email:
                    okta_users_by_email[email] = user

    if not okta_users_by_email:
        raise HTTPException(400, "No Okta snapshot available. Sync your Okta connector first.")

    all_apps = db.query(Application).filter(Application.connector_type != "okta").all()
    cross_ref_results = []

    for app_record in all_apps:
        snap = (
            db.query(AccessSnapshot)
            .filter(AccessSnapshot.application_id == app_record.id)
            .order_by(AccessSnapshot.synced_at.desc())
            .first()
        )
        if not snap:
            continue

        app_users = []
        for user in snap.users:
            email = (user.get("email") or "").lower().strip()
            okta_match = okta_users_by_email.get(email)

            flags = []
            if not email:
                flags.append("no_email")
            elif not okta_match:
                flags.append("not_in_okta")
            else:
                okta_status = okta_match.get("status", "").lower()
                if okta_status in ("suspended", "deprovisioned", "deactivated"):
                    flags.append("okta_inactive")

                last_login = user.get("last_login", "")
                if last_login:
                    try:
                        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                            try:
                                login_dt = datetime.strptime(last_login[:26].rstrip("Z") + "Z", fmt if "Z" in fmt else fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            login_dt = None
                        if login_dt:
                            days_since = (datetime.now(timezone.utc) - login_dt.replace(tzinfo=timezone.utc)).days
                            if days_since > 90:
                                flags.append(f"stale_{days_since}d")
                    except Exception:
                        pass
                elif email and okta_match:
                    flags.append("no_login_data")

                mfa = user.get("mfa_enabled", user.get("two_factor_enabled", ""))
                if mfa.lower() in ("false", "0", "no"):
                    flags.append("mfa_disabled")

            app_users.append({
                "email": email or user.get("id", "unknown"),
                "name": user.get("name", ""),
                "app_status": user.get("status", ""),
                "okta_status": okta_match.get("status", "") if okta_match else "NOT FOUND",
                "roles": user.get("roles", []),
                "last_login": user.get("last_login", ""),
                "okta_last_login": okta_match.get("last_login", "") if okta_match else "",
                "mfa_enabled": user.get("mfa_enabled", user.get("two_factor_enabled", "")),
                "flags": flags,
            })

        cross_ref_results.append({
            "app_id": app_record.id,
            "app_name": app_record.name,
            "connector_type": app_record.connector_type,
            "total_users": len(app_users),
            "flagged_users": len([u for u in app_users if u["flags"]]),
            "users": app_users,
        })

    total_unique_emails = set()
    total_flagged = 0
    not_in_okta_count = 0
    okta_inactive_count = 0
    stale_count = 0
    mfa_disabled_count = 0

    for app_result in cross_ref_results:
        for user in app_result["users"]:
            total_unique_emails.add(user["email"])
            if user["flags"]:
                total_flagged += 1
            if "not_in_okta" in user["flags"]:
                not_in_okta_count += 1
            if "okta_inactive" in user["flags"]:
                okta_inactive_count += 1
            if any(f.startswith("stale_") for f in user["flags"]):
                stale_count += 1
            if "mfa_disabled" in user["flags"]:
                mfa_disabled_count += 1

    return {
        "okta_user_count": len(okta_users_by_email),
        "apps_reviewed": len(cross_ref_results),
        "total_entitlements": sum(a["total_users"] for a in cross_ref_results),
        "total_unique_users": len(total_unique_emails),
        "total_flagged": total_flagged,
        "flags_summary": {
            "not_in_okta": not_in_okta_count,
            "okta_inactive": okta_inactive_count,
            "stale_access": stale_count,
            "mfa_disabled": mfa_disabled_count,
        },
        "applications": cross_ref_results,
    }


# ── API: User Access Review ──

@app.get("/api/review/users")
async def review_users(db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    """All latest-snapshot users across every app, with their current review status."""
    result = []
    for app_record in db.query(Application).all():
        snap = (
            db.query(AccessSnapshot)
            .filter(AccessSnapshot.application_id == app_record.id)
            .order_by(AccessSnapshot.synced_at.desc())
            .first()
        )
        if not snap:
            continue

        for user in snap.users:
            email = (user.get("email") or "").lower().strip()
            review = (
                db.query(ReviewItem)
                .filter(
                    ReviewItem.application_id == app_record.id,
                    ReviewItem.user_email == email,
                )
                .order_by(ReviewItem.created_at.desc())
                .first()
            )
            result.append({
                "application_id": app_record.id,
                "application_name": app_record.name,
                "snapshot_id": snap.id,
                "snapshot_at": snap.synced_at.isoformat(),
                "email": email,
                "name": user.get("name", ""),
                "app_status": user.get("status", ""),
                "last_login": user.get("last_login", ""),
                "roles": user.get("roles", []),
                "mfa_enabled": user.get("mfa_enabled", ""),
                "review_status": review.status if review else "pending",
                "review_notes": review.notes if review else "",
                "reviewed_by": review.reviewed_by if review else "",
                "reviewed_at": review.reviewed_at.isoformat() if (review and review.reviewed_at) else "",
            })

    return result


@app.post("/api/review/action")
async def review_action(body: dict, db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    """Flag or approve a user entry."""
    action = body.get("action")
    if action not in ("flag", "approve", "resolve"):
        raise HTTPException(400, "action must be: flag, approve, or resolve")

    application_id = body["application_id"]
    application_name = body["application_name"]
    snapshot_id = body["snapshot_id"]
    user_email = (body.get("user_email") or "").lower().strip()
    user_name = body.get("user_name", "")
    notes = body.get("notes", "")
    actor_email = session["email"]

    status_map = {"flag": "flagged", "approve": "approved", "resolve": "resolved"}
    now = datetime.now(timezone.utc)

    existing = (
        db.query(ReviewItem)
        .filter(ReviewItem.application_id == application_id, ReviewItem.user_email == user_email)
        .first()
    )
    if existing:
        existing.status = status_map[action]
        existing.notes = notes
        existing.reviewed_by = actor_email
        existing.reviewed_at = now
        existing.snapshot_id = snapshot_id
    else:
        db.add(ReviewItem(
            id=str(uuid.uuid4()),
            application_id=application_id,
            application_name=application_name,
            snapshot_id=snapshot_id,
            user_email=user_email,
            user_name=user_name,
            status=status_map[action],
            notes=notes,
            reviewed_by=actor_email,
            reviewed_at=now,
        ))

    db.add(AuditLog(
        id=str(uuid.uuid4()),
        action=action,
        actor_email=actor_email,
        target_email=user_email,
        application_name=application_name,
        details=notes,
    ))
    db.commit()
    return {"ok": True}


@app.get("/api/review/audit-log")
async def review_audit_log(db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(500).all()
    return [
        {
            "action": l.action,
            "actor_email": l.actor_email,
            "target_email": l.target_email,
            "application_name": l.application_name,
            "details": l.details,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]


@app.get("/api/review/export")
async def review_export(db: Session = Depends(get_db), session: dict = Depends(require_auth)):
    """Export all review decisions as CSV for compliance evidence."""
    items = db.query(ReviewItem).order_by(ReviewItem.reviewed_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Application", "User Email", "User Name", "Review Status",
        "Notes", "Reviewed By", "Reviewed At", "Created At",
    ])
    for item in items:
        writer.writerow([
            item.application_name,
            item.user_email,
            item.user_name or "",
            item.status,
            item.notes or "",
            item.reviewed_by or "",
            item.reviewed_at.isoformat() if item.reviewed_at else "",
            item.created_at.isoformat(),
        ])

    output.seek(0)
    filename = f"retina_review_{datetime.now(timezone.utc).date()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── API: RETINA users (admin only) ──

@app.get("/api/users")
async def list_retina_users(db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    users = db.query(RetinaUser).order_by(RetinaUser.created_at).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@app.put("/api/users/{user_id}")
async def update_retina_user(user_id: str, body: dict, db: Session = Depends(get_db), session: dict = Depends(require_admin)):
    user = db.query(RetinaUser).filter(RetinaUser.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.email == session["email"]:
        raise HTTPException(400, "Cannot modify your own account")
    if "role" in body and body["role"] in ("admin", "reviewer"):
        user.role = body["role"]
    if "is_active" in body:
        user.is_active = "true" if body["is_active"] else "false"
    db.commit()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
