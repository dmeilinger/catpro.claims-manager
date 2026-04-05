"""SQLAlchemy engine and session factory for SQLite (WAL mode)."""

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _build_engine():
    settings = get_settings()
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        # Resolve relative to the repo root (two levels up from backend/app/)
        db_path = Path(__file__).resolve().parents[2] / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine)


async def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — async def avoids thread-pool deadlock (#3205)."""
    with Session(engine) as session:
        yield session
