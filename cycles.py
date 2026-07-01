import asyncio
import csv
import io
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import (
    SessionLocal, get_db,
    Application, AccessSnapshot, Product, ProductScope, ProductReviewer,
    ReviewCycle, CycleScope, ReviewItem, AuditLog,
)
from scoping import filter_snapshot_users
from scheduler import sync_application_task
from auth import require_auth, require_admin
from review_common import apply_review_decision, STATUS_MAP

router = APIRouter(prefix="/api/cycles", tags=["cycles"])

SYNC_CONCURRENCY = 3


async def generate_cycle_items(cycle_id: str, actor_email: str) -> dict:
    """Resolve a cycle's scope, sync in-scope applications, apply each
    product's filter, and create ReviewItem rows for every matching user.
    Runs as a background task — has its own DB session, independent of
    whatever request triggered it."""
    db = SessionLocal()
    try:
        cycle = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
        if not cycle or cycle.status != "active":
            return {"error": "cycle not found or not active"}

        cycle.generation_status = "generating"
        db.commit()

        # Resolve (product_id, application_id, filter_field, filter_match, filter_value) tuples
        scope_tuples = []
        if cycle.scope_all_applications == "true":
            for app in db.query(Application).all():
                scope_tuples.append((None, app.id, None, None, None))
        else:
            product_ids = [
                cs.product_id for cs in db.query(CycleScope).filter(CycleScope.cycle_id == cycle_id).all()
            ]
            for product_id in product_ids:
                for s in db.query(ProductScope).filter(ProductScope.product_id == product_id).all():
                    scope_tuples.append((product_id, s.application_id, s.filter_field, s.filter_match, s.filter_value))

        app_ids_to_sync = sorted({t[1] for t in scope_tuples})
        sem = asyncio.Semaphore(SYNC_CONCURRENCY)

        async def sync_one(app_id):
            async with sem:
                await sync_application_task(app_id)

        await asyncio.gather(*(sync_one(a) for a in app_ids_to_sync))

        item_count = 0
        warnings = []

        for product_id, application_id, filter_field, filter_match, filter_value in scope_tuples:
            app = db.query(Application).filter(Application.id == application_id).first()
            if not app:
                continue
            if app.last_sync_status and app.last_sync_status.startswith("error:"):
                warnings.append(f"{app.name}: sync failed ({app.last_sync_status}), using most recent available snapshot")

            snap = (
                db.query(AccessSnapshot)
                .filter(AccessSnapshot.application_id == application_id)
                .order_by(AccessSnapshot.synced_at.desc())
                .first()
            )
            if not snap:
                warnings.append(f"{app.name}: no snapshot available, skipped")
                continue

            matched_users = filter_snapshot_users(snap.users, filter_field, filter_match, filter_value)
            if filter_field and not matched_users:
                warnings.append(f"{app.name}: filter '{filter_field} {filter_match} {filter_value}' matched 0 users")

            reviewer_email = None
            if product_id:
                reviewers = db.query(ProductReviewer).filter(ProductReviewer.product_id == product_id).all()
                reviewer_email = ",".join(r.reviewer_email for r in reviewers) or None

            for user in matched_users:
                email = (user.get("email") or "").lower().strip()
                if not email:
                    continue
                exists = (
                    db.query(ReviewItem)
                    .filter(
                        ReviewItem.cycle_id == cycle_id,
                        ReviewItem.application_id == application_id,
                        ReviewItem.product_id == product_id,
                        ReviewItem.user_email == email,
                    )
                    .first()
                )
                if exists:
                    continue
                db.add(ReviewItem(
                    id=str(uuid.uuid4()),
                    application_id=application_id,
                    application_name=app.name,
                    snapshot_id=snap.id,
                    user_email=email,
                    user_name=user.get("name", ""),
                    status="pending",
                    cycle_id=cycle_id,
                    product_id=product_id,
                    assigned_reviewer_email=reviewer_email,
                ))
                item_count += 1

        cycle.generation_status = "done"
        cycle.generation_summary = json.dumps({"item_count": item_count, "warnings": warnings})
        db.add(AuditLog(
            id=str(uuid.uuid4()),
            action="cycle_generated",
            actor_email=actor_email,
            details=f"{item_count} item(s) generated across {len(app_ids_to_sync)} application(s)"
            + (f"; {len(warnings)} warning(s)" if warnings else ""),
            cycle_id=cycle_id,
        ))
        db.commit()
        return {"item_count": item_count, "warnings": warnings}

    except Exception as e:
        cycle = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
        if cycle:
            cycle.generation_status = "error"
            cycle.generation_summary = json.dumps({"error": str(e)[:500]})
            db.commit()
        raise
    finally:
        db.close()


def _cycle_summary(db: Session, c: ReviewCycle) -> dict:
    total = db.query(ReviewItem).filter(ReviewItem.cycle_id == c.id).count()
    pending = db.query(ReviewItem).filter(ReviewItem.cycle_id == c.id, ReviewItem.status == "pending").count()
    return {
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "due_date": c.due_date.isoformat(),
        "scope_all_applications": c.scope_all_applications == "true",
        "generation_status": c.generation_status,
        "generation_summary": json.loads(c.generation_summary) if c.generation_summary else None,
        "total_items": total,
        "pending_items": pending,
        "created_by": c.created_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "closed_at": c.closed_at.isoformat() if c.closed_at else None,
    }


@router.get("")
async def list_cycles(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    cycles = db.query(ReviewCycle).order_by(ReviewCycle.created_at.desc()).all()
    return [_cycle_summary(db, c) for c in cycles]


@router.post("")
async def create_cycle(body: dict, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")

    due_date_str = body.get("due_date")
    if not due_date_str:
        raise HTTPException(400, "due_date is required")
    try:
        due_date = datetime.fromisoformat(due_date_str)
    except ValueError:
        raise HTTPException(400, "due_date must be an ISO date/datetime string")
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)

    scope_all = bool(body.get("scope_all_applications"))
    product_ids = body.get("product_ids", [])
    if not scope_all and not product_ids:
        raise HTTPException(400, "Select 'all applications' or at least one product")

    cycle = ReviewCycle(
        id=str(uuid.uuid4()),
        name=name,
        due_date=due_date,
        scope_all_applications="true" if scope_all else "false",
        created_by=user["email"],
    )
    db.add(cycle)
    if not scope_all:
        for pid in product_ids:
            db.add(CycleScope(id=str(uuid.uuid4()), cycle_id=cycle.id, product_id=pid))
    db.commit()

    asyncio.create_task(generate_cycle_items(cycle.id, user["email"]))
    return {"id": cycle.id, "status": "generating"}


@router.get("/{cycle_id}")
async def get_cycle(cycle_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    c = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
    if not c:
        raise HTTPException(404, "Cycle not found")
    return _cycle_summary(db, c)


@router.post("/{cycle_id}/regenerate")
async def regenerate_cycle(cycle_id: str, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    c = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
    if not c:
        raise HTTPException(404, "Cycle not found")
    if c.status != "active":
        raise HTTPException(400, "Cannot regenerate a closed cycle")
    asyncio.create_task(generate_cycle_items(cycle_id, user["email"]))
    return {"status": "generating"}


@router.post("/{cycle_id}/close")
async def close_cycle(cycle_id: str, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    c = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
    if not c:
        raise HTTPException(404, "Cycle not found")
    c.status = "closed"
    c.closed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.get("/{cycle_id}/items")
async def list_cycle_items(cycle_id: str, scope: str = "all", db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    q = db.query(ReviewItem).filter(ReviewItem.cycle_id == cycle_id)
    if scope == "mine" and user["role"] != "admin":
        q = q.filter(ReviewItem.assigned_reviewer_email.like(f"%{user['email']}%"))
    items = q.order_by(ReviewItem.application_name, ReviewItem.user_email).all()
    return [
        {
            "id": i.id,
            "application_id": i.application_id,
            "application_name": i.application_name,
            "product_id": i.product_id,
            "user_email": i.user_email,
            "user_name": i.user_name,
            "status": i.status,
            "notes": i.notes,
            "reviewed_by": i.reviewed_by,
            "reviewed_at": i.reviewed_at.isoformat() if i.reviewed_at else None,
            "assigned_reviewer_email": i.assigned_reviewer_email,
            "can_act": user["role"] == "admin" or bool(
                i.assigned_reviewer_email and user["email"] in i.assigned_reviewer_email.split(",")
            ),
        }
        for i in items
    ]


@router.post("/{cycle_id}/items/{item_id}/action")
async def cycle_item_action(cycle_id: str, item_id: str, body: dict, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    action = body.get("action")
    if action not in STATUS_MAP:
        raise HTTPException(400, "action must be: flag, approve, or resolve")

    item = db.query(ReviewItem).filter(ReviewItem.id == item_id, ReviewItem.cycle_id == cycle_id).first()
    if not item:
        raise HTTPException(404, "Item not found")

    is_admin = user["role"] == "admin"
    is_assigned = bool(item.assigned_reviewer_email and user["email"] in item.assigned_reviewer_email.split(","))
    if not (is_admin or is_assigned):
        raise HTTPException(403, "You are not an assigned reviewer for this item")

    apply_review_decision(db, item, action, body.get("notes", ""), user["email"], cycle_id=cycle_id)
    return {"ok": True}


@router.get("/{cycle_id}/audit-log")
async def cycle_audit_log(cycle_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.cycle_id == cycle_id)
        .order_by(AuditLog.created_at.desc())
        .limit(500)
        .all()
    )
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


@router.get("/{cycle_id}/export")
async def export_cycle(cycle_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    c = db.query(ReviewCycle).filter(ReviewCycle.id == cycle_id).first()
    if not c:
        raise HTTPException(404, "Cycle not found")

    items = db.query(ReviewItem).filter(ReviewItem.cycle_id == cycle_id).order_by(ReviewItem.application_name).all()
    products_by_id = {p.id: p.name for p in db.query(Product).all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Product", "Application", "User Email", "User Name", "Review Status",
        "Assigned Reviewer", "Notes", "Reviewed By", "Reviewed At",
    ])
    for i in items:
        writer.writerow([
            products_by_id.get(i.product_id, "") if i.product_id else "",
            i.application_name,
            i.user_email,
            i.user_name or "",
            i.status,
            i.assigned_reviewer_email or "",
            i.notes or "",
            i.reviewed_by or "",
            i.reviewed_at.isoformat() if i.reviewed_at else "",
        ])

    output.seek(0)
    filename = f"retina_cycle_{c.name.replace(' ', '_')}_{datetime.now(timezone.utc).date()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
