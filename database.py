import os
from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

DATA_DIR = os.environ.get("RETINA_DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

engine = create_engine(f"sqlite:///{os.path.join(DATA_DIR, 'retina.db')}")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    connector_type = Column(String, nullable=False)
    credentials_encrypted = Column(Text, nullable=False)
    base_url = Column(String, nullable=True)
    last_sync = Column(DateTime, nullable=True)
    sync_schedule = Column(String, nullable=True)  # cron expression or preset like "daily", "weekly"
    sync_enabled = Column(String, default="false")  # "true" or "false"
    last_sync_status = Column(String, nullable=True)  # "success", "error: message"


class AccessSnapshot(Base):
    __tablename__ = "access_snapshots"

    id = Column(String, primary_key=True)
    application_id = Column(String, nullable=False, index=True)
    synced_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    users = Column(JSON, nullable=False)


class RetinaUser(Base):
    __tablename__ = "retina_users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    okta_sub = Column(String, nullable=True)
    role = Column(String, default="reviewer")  # "admin" or "reviewer"
    is_active = Column(String, default="true")
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ReviewItem(Base):
    __tablename__ = "review_items"

    id = Column(String, primary_key=True)
    application_id = Column(String, nullable=False, index=True)
    application_name = Column(String, nullable=False)
    snapshot_id = Column(String, nullable=False)
    user_email = Column(String, nullable=False, index=True)
    user_name = Column(String, nullable=True)
    status = Column(String, default="pending")  # "pending", "approved", "flagged", "resolved"
    notes = Column(Text, nullable=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True)
    action = Column(String, nullable=False)  # "flag", "approve", "resolve", "login"
    actor_email = Column(String, nullable=False)
    target_email = Column(String, nullable=True)
    application_name = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
