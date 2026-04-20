from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

engine = create_engine("sqlite:///access_review.db")
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


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
