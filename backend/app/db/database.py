"""Database engine, session factory, and base model.

Uses SQLAlchemy 2.0 style declarative base with sync sessions.
The async variant is intentionally avoided to keep the existing
synchronous service layer unchanged.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the global engine, creating it on first call."""
    global _engine, _SessionLocal
    if _engine is None:
        dsn = settings.postgres_dsn
        if not dsn:
            raise RuntimeError("QUANT_POSTGRES_DSN is not configured")
        _engine = create_engine(
            dsn,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
            echo=settings.debug,
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
        logger.info("database engine created for %s", _engine.url.drivername)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def session_scope() -> Session:
    """Context manager that yields a session and auto-commits/rolls-back."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables.  Used for development / first-run."""
    # Import models so that they register on Base.metadata
    from app.db import orm_models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("database tables created (if not exists)")


def check_db_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("database connection check failed: %s", exc)
        return False
