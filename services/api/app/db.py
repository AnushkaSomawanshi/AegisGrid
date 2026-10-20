"""Persistence layer. SQLite is supported for local tests; PostgreSQL is used in Compose."""
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, DateTime, Text
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

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Resource(Base):
    """A dispatchable unit, facility, vehicle, or supply pool."""
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    region: Mapped[str] = mapped_column(String(120), default="Unassigned")
    status: Mapped[str] = mapped_column(String(30), default="available", index=True)
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    available: Mapped[int] = mapped_column(Integer, default=1)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Reservation(Base):
    """Durable reservation record; available capacity is decremented in the same DB transaction."""
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_id: Mapped[int] = mapped_column(Integer, index=True)
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    requested_by: Mapped[str] = mapped_column(String(120), default="command-centre")
    units: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="reserved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentRun(Base):
    """Persisted lab execution and evidence; trace/result are JSON serialized for portability."""
    __tablename__ = "experiment_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lab_id: Mapped[str] = mapped_column(String(80), index=True)
    scenario: Mapped[str] = mapped_column(String(160), default="default")
    status: Mapped[str] = mapped_column(String(30), default="ready", index=True)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    trace: Mapped[str] = mapped_column(Text, default="[]")
    result: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
