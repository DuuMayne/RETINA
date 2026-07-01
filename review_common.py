import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import ReviewItem, AuditLog

STATUS_MAP = {"flag": "flagged", "approve": "approved", "resolve": "resolved"}


def apply_review_decision(
    db: Session,
    item: ReviewItem,
    action: str,
    notes: str,
    actor_email: str,
    cycle_id: str = None,
):
    """Apply a flag/approve/resolve decision to an existing ReviewItem and
    write the matching AuditLog row. Shared by the ad-hoc review flow and
    cycle-scoped review flow so the audit trail stays consistent."""
    now = datetime.now(timezone.utc)
    item.status = STATUS_MAP[action]
    item.notes = notes
    item.reviewed_by = actor_email
    item.reviewed_at = now

    db.add(AuditLog(
        id=str(uuid.uuid4()),
        action=action,
        actor_email=actor_email,
        target_email=item.user_email,
        application_name=item.application_name,
        details=notes,
        cycle_id=cycle_id,
    ))
    db.commit()
