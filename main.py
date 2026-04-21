import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import init_db, get_db, Application, AccessSnapshot
from crypto import encrypt_credentials, decrypt_credentials
from connectors import get_connector, CONNECTORS
from scheduler import (
    start_scheduler, stop_scheduler, schedule_app, unschedule_app,
    get_scheduled_jobs, SCHEDULE_PRESETS, sync_application_task,
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


# ── Pages ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── API: Connector metadata ──

@app.get("/api/connectors")
async def list_connectors():
    result = {}
    for key, cls in CONNECTORS.items():
        result[key] = {
            "fields": cls.credential_fields(),
            "default_base_url": cls.default_base_url(),
        }
    return result


# ── API: Applications CRUD ──

@app.get("/api/applications")
async def list_applications(db: Session = Depends(get_db)):
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
async def create_application(body: dict, db: Session = Depends(get_db)):
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
async def get_application(app_id: str, db: Session = Depends(get_db)):
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
async def update_application(app_id: str, body: dict, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    if "name" in body:
        a.name = body["name"]
    if "base_url" in body:
        a.base_url = body["base_url"] or None
    if "credentials" in body:
        new_creds = body["credentials"]
        # Merge: only update fields that aren't masked placeholder values
        existing_creds = decrypt_credentials(a.credentials_encrypted)
        for k, v in new_creds.items():
            if v and not v.startswith("********"):
                existing_creds[k] = v
        a.credentials_encrypted = encrypt_credentials(existing_creds)
    db.commit()
    return {"ok": True}


@app.delete("/api/applications/{app_id}")
async def delete_application(app_id: str, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    db.query(AccessSnapshot).filter(AccessSnapshot.application_id == app_id).delete()
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── API: Sync ──

@app.post("/api/applications/{app_id}/sync")
async def sync_application(app_id: str, db: Session = Depends(get_db)):
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
async def list_snapshots(app_id: str, db: Session = Depends(get_db)):
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
async def get_snapshot(snapshot_id: str, db: Session = Depends(get_db)):
    s = db.query(AccessSnapshot).filter(AccessSnapshot.id == snapshot_id).first()
    if not s:
        raise HTTPException(404, "Snapshot not found")
    return {"id": s.id, "synced_at": s.synced_at.isoformat(), "users": s.users}


# ── API: Scheduling ──

@app.get("/api/schedules")
async def list_schedules(db: Session = Depends(get_db)):
    """List all applications with their schedule configuration."""
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
async def list_presets():
    """Return available schedule presets."""
    return SCHEDULE_PRESETS


@app.get("/api/schedules/jobs")
async def list_jobs():
    """Return currently active scheduled jobs."""
    return get_scheduled_jobs()


@app.put("/api/applications/{app_id}/schedule")
async def set_schedule(app_id: str, body: dict, db: Session = Depends(get_db)):
    """Set or update the sync schedule for an application."""
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
async def trigger_sync_now(app_id: str, db: Session = Depends(get_db)):
    """Trigger an immediate sync (regardless of schedule)."""
    a = db.query(Application).filter(Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")

    # Run the sync task directly
    await sync_application_task(app_id)

    # Refresh from DB to get updated status
    db.refresh(a)
    return {
        "app_id": app_id,
        "last_sync": a.last_sync.isoformat() if a.last_sync else None,
        "last_sync_status": a.last_sync_status,
    }


# ── API: Cross-reference (Okta as identity baseline) ──

@app.get("/api/cross-reference")
async def cross_reference(db: Session = Depends(get_db)):
    """Cross-reference all application access against Okta as the identity source.

    Returns a unified view of users across all applications, with Okta as the
    baseline. Flags users who exist in an app but not in Okta, users who haven't
    logged in recently, and entitlements that may be unused.
    """
    # Find Okta application(s)
    okta_apps = db.query(Application).filter(Application.connector_type == "okta").all()
    if not okta_apps:
        raise HTTPException(400, "No Okta application configured. Add an Okta connector to use cross-referencing.")

    # Get latest Okta snapshot
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

    # Get all other applications and their latest snapshots
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
                # Check if Okta status is not active
                okta_status = okta_match.get("status", "").lower()
                if okta_status in ("suspended", "deprovisioned", "deactivated"):
                    flags.append("okta_inactive")

                # Check for stale access (no login in 90 days)
                last_login = user.get("last_login", "")
                if last_login:
                    try:
                        from datetime import datetime, timezone
                        # Handle various date formats
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

                # Check MFA
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

    # Summary stats
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
