"""Scheduled sync engine for RETINA."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from database import SessionLocal, Application, AccessSnapshot
from crypto import decrypt_credentials
from connectors import get_connector

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)

# Schedule presets mapped to cron expressions
SCHEDULE_PRESETS = {
    "hourly": "0 * * * *",
    "every_6_hours": "0 */6 * * *",
    "daily": "0 2 * * *",       # 2 AM
    "weekly": "0 2 * * 1",      # Monday 2 AM
    "monthly": "0 2 1 * *",     # 1st of month 2 AM
}

scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


def parse_schedule(schedule_str: str) -> Optional[CronTrigger]:
    """Parse a schedule string into an APScheduler trigger."""
    if not schedule_str:
        return None

    # Check if it's a preset
    cron_expr = SCHEDULE_PRESETS.get(schedule_str.lower(), schedule_str)

    try:
        parts = cron_expr.split()
        if len(parts) == 5:
            return CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
    except Exception as e:
        logger.error(f"Invalid cron expression '{schedule_str}': {e}")

    return None


async def sync_application_task(app_id: str):
    """Execute a sync for a single application. Called by scheduler."""
    db: Session = SessionLocal()
    try:
        app = db.query(Application).filter(Application.id == app_id).first()
        if not app:
            logger.warning(f"Scheduled sync: app {app_id} not found")
            return

        logger.info(f"Scheduled sync starting: {app.name} ({app_id})")

        credentials = decrypt_credentials(app.credentials_encrypted)
        connector = get_connector(app.connector_type, credentials, app.base_url)

        try:
            users = await connector.fetch_users()

            snapshot = AccessSnapshot(
                id=str(uuid.uuid4()),
                application_id=app_id,
                synced_at=datetime.now(timezone.utc),
                users=users,
            )
            db.add(snapshot)
            app.last_sync = snapshot.synced_at
            app.last_sync_status = "success"
            db.commit()

            logger.info(f"Scheduled sync complete: {app.name} — {len(users)} users")

        except Exception as e:
            error_msg = str(e)[:200]
            app.last_sync_status = f"error: {error_msg}"
            db.commit()
            logger.error(f"Scheduled sync failed: {app.name} — {error_msg}")

    finally:
        db.close()


def schedule_app(app_id: str, schedule_str: str):
    """Add or update a scheduled sync job for an application."""
    sched = get_scheduler()
    job_id = f"sync_{app_id}"

    # Remove existing job if any
    existing = sched.get_job(job_id)
    if existing:
        sched.remove_job(job_id)

    trigger = parse_schedule(schedule_str)
    if trigger is None:
        logger.warning(f"Could not parse schedule '{schedule_str}' for {app_id}")
        return

    sched.add_job(
        sync_application_task,
        trigger=trigger,
        args=[app_id],
        id=job_id,
        name=f"Sync {app_id}",
        replace_existing=True,
    )
    logger.info(f"Scheduled sync for {app_id}: {schedule_str}")


def unschedule_app(app_id: str):
    """Remove a scheduled sync job."""
    sched = get_scheduler()
    job_id = f"sync_{app_id}"
    existing = sched.get_job(job_id)
    if existing:
        sched.remove_job(job_id)
        logger.info(f"Removed scheduled sync for {app_id}")


def load_all_schedules():
    """Load schedules for all apps from database on startup."""
    db: Session = SessionLocal()
    try:
        apps = db.query(Application).filter(
            Application.sync_enabled == "true",
            Application.sync_schedule.isnot(None),
        ).all()

        for app in apps:
            schedule_app(app.id, app.sync_schedule)

        logger.info(f"Loaded {len(apps)} scheduled syncs from database")
    finally:
        db.close()


def start_scheduler():
    """Start the scheduler and load existing schedules."""
    sched = get_scheduler()
    if not sched.running:
        load_all_schedules()
        sched.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    sched = get_scheduler()
    if sched.running:
        sched.shutdown()
        logger.info("Scheduler stopped")


def get_scheduled_jobs() -> list[dict]:
    """Return info about all scheduled jobs."""
    sched = get_scheduler()
    jobs = []
    for job in sched.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs
