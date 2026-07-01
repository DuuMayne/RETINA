import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, Product, ProductScope, ProductReviewer, Application, AccessSnapshot
from crypto import encrypt_secret, decrypt_secret
from auth import require_admin
from scoping import filter_snapshot_users

router = APIRouter(prefix="/api/products", tags=["products"])


def _product_summary(db: Session, p: Product) -> dict:
    scopes = db.query(ProductScope).filter(ProductScope.product_id == p.id).all()
    reviewers = db.query(ProductReviewer).filter(ProductReviewer.product_id == p.id).all()
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "has_slack_webhook": bool(p.slack_webhook_url_encrypted),
        "scope_count": len(scopes),
        "reviewer_count": len(reviewers),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _product_detail(db: Session, p: Product) -> dict:
    scopes = db.query(ProductScope).filter(ProductScope.product_id == p.id).all()
    reviewers = db.query(ProductReviewer).filter(ProductReviewer.product_id == p.id).all()
    apps_by_id = {a.id: a for a in db.query(Application).all()}

    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "has_slack_webhook": bool(p.slack_webhook_url_encrypted),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "scopes": [
            {
                "id": s.id,
                "application_id": s.application_id,
                "application_name": apps_by_id[s.application_id].name if s.application_id in apps_by_id else "(deleted app)",
                "filter_field": s.filter_field,
                "filter_match": s.filter_match,
                "filter_value": s.filter_value,
            }
            for s in scopes
        ],
        "reviewers": [r.reviewer_email for r in reviewers],
    }


@router.get("")
async def list_products(db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    products = db.query(Product).order_by(Product.name).all()
    return [_product_summary(db, p) for p in products]


@router.post("")
async def create_product(body: dict, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    if db.query(Product).filter(Product.name == name).first():
        raise HTTPException(400, f"A product named '{name}' already exists")

    webhook_url = (body.get("slack_webhook_url") or "").strip()
    p = Product(
        id=str(uuid.uuid4()),
        name=name,
        description=body.get("description") or None,
        slack_webhook_url_encrypted=encrypt_secret(webhook_url) if webhook_url else None,
    )
    db.add(p)
    db.commit()
    return {"id": p.id, "name": p.name}


@router.get("/{product_id}")
async def get_product(product_id: str, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")
    return _product_detail(db, p)


@router.put("/{product_id}")
async def update_product(product_id: str, body: dict, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")

    if "name" in body:
        name = body["name"].strip()
        if not name:
            raise HTTPException(400, "name cannot be empty")
        p.name = name
    if "description" in body:
        p.description = body["description"] or None
    if "slack_webhook_url" in body:
        webhook_url = (body["slack_webhook_url"] or "").strip()
        p.slack_webhook_url_encrypted = encrypt_secret(webhook_url) if webhook_url else None

    db.commit()
    return {"ok": True}


@router.delete("/{product_id}")
async def delete_product(product_id: str, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")
    db.query(ProductScope).filter(ProductScope.product_id == product_id).delete()
    db.query(ProductReviewer).filter(ProductReviewer.product_id == product_id).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{product_id}/scopes")
async def add_scope(product_id: str, body: dict, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")

    application_id = body.get("application_id")
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(400, "Unknown application_id")

    filter_field = (body.get("filter_field") or "").strip() or None
    filter_match = body.get("filter_match") or "contains"
    if filter_match not in ("equals", "contains"):
        raise HTTPException(400, "filter_match must be 'equals' or 'contains'")
    filter_value = (body.get("filter_value") or "").strip() or None
    if filter_field and not filter_value:
        raise HTTPException(400, "filter_value is required when filter_field is set")

    scope = ProductScope(
        id=str(uuid.uuid4()),
        product_id=product_id,
        application_id=application_id,
        filter_field=filter_field,
        filter_match=filter_match if filter_field else None,
        filter_value=filter_value if filter_field else None,
    )
    db.add(scope)
    db.commit()
    return {"id": scope.id}


@router.delete("/{product_id}/scopes/{scope_id}")
async def delete_scope(product_id: str, scope_id: str, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    scope = db.query(ProductScope).filter(ProductScope.id == scope_id, ProductScope.product_id == product_id).first()
    if not scope:
        raise HTTPException(404, "Scope not found")
    db.delete(scope)
    db.commit()
    return {"ok": True}


@router.get("/{product_id}/preview-scope")
async def preview_scope(
    product_id: str,
    application_id: str,
    filter_field: str = "",
    filter_match: str = "contains",
    filter_value: str = "",
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """Dry-run a filter against the application's latest snapshot so an admin
    can see the match count before saving a scope that might silently match zero users."""
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(404, "Application not found")

    snap = (
        db.query(AccessSnapshot)
        .filter(AccessSnapshot.application_id == application_id)
        .order_by(AccessSnapshot.synced_at.desc())
        .first()
    )
    if not snap:
        return {"total_users": 0, "matched_count": 0, "sample": [], "warning": "This application has never been synced."}

    matched = filter_snapshot_users(snap.users, filter_field.strip() or None, filter_match, filter_value.strip() or None)

    warning = None
    if filter_field and not matched:
        warning = f"This filter matches 0 of {len(snap.users)} users in the latest snapshot — check the field name and value."

    return {
        "total_users": len(snap.users),
        "matched_count": len(matched),
        "sample": [
            {"email": u.get("email", ""), "name": u.get("name", ""), "roles": u.get("roles", [])}
            for u in matched[:5]
        ],
        "warning": warning,
    }


@router.put("/{product_id}/reviewers")
async def set_reviewers(product_id: str, body: dict, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")

    emails = [e.strip().lower() for e in body.get("emails", []) if e.strip()]

    db.query(ProductReviewer).filter(ProductReviewer.product_id == product_id).delete()
    for email in emails:
        db.add(ProductReviewer(id=str(uuid.uuid4()), product_id=product_id, reviewer_email=email))
    db.commit()
    return {"ok": True, "reviewers": emails}
