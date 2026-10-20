"""Persistence layer. SQLite is supported for local tests; PostgreSQL is used in Compose."""
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, DateTime, Text, Boolean, Float, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def _database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    host = os.getenv("POSTGRES_HOST")
    if host:
        from urllib.parse import quote_plus
        user = quote_plus(os.getenv("POSTGRES_USER", "aegisgrid"))
        password = quote_plus(os.getenv("POSTGRES_PASSWORD", ""))
        dbname = quote_plus(os.getenv("POSTGRES_DB", "aegisgrid"))
        port = os.getenv("POSTGRES_PORT", "5432")
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
    return "sqlite:///./aegisgrid.db"

DATABASE_URL = _database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(60), default="Medical")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="open")
    location: Mapped[str] = mapped_column(String(180), default="Unknown")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class EventRecord(Base):
    __tablename__ = "event_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(80), default="api")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OutboxRecord(Base):
    __tablename__ = "event_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_record_id: Mapped[int] = mapped_column(ForeignKey("event_records.id"), unique=True, index=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140))
    kind: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), default="available", index=True)
    location: Mapped[str] = mapped_column(String(180), default="Control zone")
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True, index=True)
    requested_by: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="reserved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lab_id: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(30), default="ready")
    scenario: Mapped[str] = mapped_column(String(120), default="default")
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    trace: Mapped[str] = mapped_column(Text, default="[]")
    result: Mapped[str] = mapped_column(Text, default="{}")
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
