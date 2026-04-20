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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
