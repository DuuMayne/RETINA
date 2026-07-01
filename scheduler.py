"""Scheduled sync engine for RETINA."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from database import (
    SessionLocal, Application, AccessSnapshot,
    Product, ProductReviewer, ReviewCycle, ReviewItem, SentReminder, AuditLog,
)
from crypto import decrypt_credentials, decrypt_secret
from connectors import get_connector

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)

REMINDER_THRESHOLDS_DAYS = (7, 3, 1)
GLOBAL_SLACK_WEBHOOK_URL = os.environ.get("RETINA_SLACK_WEBHOOK_URL", "")
REMINDER_INTERVAL_HOURS = int(os.environ.get("RETINA_REMINDER_INTERVAL_HOURS", "6"))

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


async def _post_to_slack(webhook_url: str, text: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json={"text": text})
            resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")
        return False


async def check_cycle_reminders_task():
    """Runs periodically. For each active review cycle, sends a Slack reminder
    to a product's reviewers at 7/3/1 days before the due date (once each,
    deduped via SentReminder), and a repeating overdue escalation (at most
    once per product per day) once the due date has passed."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        today_str = now.date().isoformat()

        cycles = db.query(ReviewCycle).filter(ReviewCycle.status == "active").all()
        for cycle in cycles:
            due_date = cycle.due_date
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=timezone.utc)
            days_until_due = (due_date.date() - now.date()).days

            pending_by_product: dict[Optional[str], int] = {}
            pending_items = (
                db.query(ReviewItem)
                .filter(ReviewItem.cycle_id == cycle.id, ReviewItem.status == "pending")
                .all()
            )
            for item in pending_items:
                pending_by_product[item.product_id] = pending_by_product.get(item.product_id, 0) + 1

            if not pending_by_product:
                continue

            if days_until_due < 0:
                threshold = f"overdue_{today_str}"
                is_escalation = True
            elif days_until_due in REMINDER_THRESHOLDS_DAYS:
                threshold = f"{days_until_due}d"
                is_escalation = False
            else:
                continue

            for product_id, pending_count in pending_by_product.items():
                pid_key = product_id or ""
                already_sent = (
                    db.query(SentReminder)
                    .filter(
                        SentReminder.cycle_id == cycle.id,
                        SentReminder.product_id == pid_key,
                        SentReminder.threshold == threshold,
                    )
                    .first()
                )
                if already_sent:
                    continue

                product_name = "Ungrouped applications"
                webhook_url = GLOBAL_SLACK_WEBHOOK_URL
                if product_id:
                    product = db.query(Product).filter(Product.id == product_id).first()
                    if product:
                        product_name = product.name
                        if product.slack_webhook_url_encrypted:
                            webhook_url = decrypt_secret(product.slack_webhook_url_encrypted)

                if not webhook_url:
                    logger.warning(f"No Slack webhook configured for product '{product_name}' — skipping reminder")
                    continue

                if is_escalation:
                    message = (
                        f":rotating_light: *OVERDUE* — @here Review cycle *{cycle.name}* is past its due date "
                        f"({due_date.date().isoformat()}) with *{pending_count}* pending item(s) in *{product_name}*."
                    )
                    action = "escalation_sent"
                else:
                    message = (
                        f":bell: Reminder — Review cycle *{cycle.name}* is due in *{days_until_due} day(s)* "
                        f"with *{pending_count}* pending item(s) in *{product_name}*."
                    )
                    action = "reminder_sent"

                sent = await _post_to_slack(webhook_url, message)
                if sent:
                    db.add(SentReminder(
                        id=str(uuid.uuid4()),
                        cycle_id=cycle.id,
                        product_id=pid_key,
                        threshold=threshold,
                    ))
                    db.add(AuditLog(
                        id=str(uuid.uuid4()),
                        action=action,
                        actor_email="system",
                        application_name=product_name,
                        details=f"{pending_count} pending item(s), due {due_date.date().isoformat()}",
                        cycle_id=cycle.id,
                    ))
                    db.commit()

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
        sched.add_job(
            check_cycle_reminders_task,
            trigger=IntervalTrigger(hours=REMINDER_INTERVAL_HOURS),
            id="cycle_reminders",
            name="Review cycle reminder/escalation check",
            replace_existing=True,
        )
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
