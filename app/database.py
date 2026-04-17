"""Database engine and session management for AWS RDS PostgreSQL."""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.logging import get_logger
from app.models import Base


logger = get_logger()

_engine = None
_SessionLocal = None


def _get_engine():
    """Get or create the SQLAlchemy engine (lazy singleton)."""
    global _engine
    if _engine is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return None
        try:
            from urllib.parse import parse_qs, urlparse

            connect_args = {}
            # Parse query parameters from URL to handle SSL and other options
            parsed_url = urlparse(database_url)
            query_params = parse_qs(parsed_url.query)

            if "sslmode" in query_params:
                connect_args["sslmode"] = query_params["sslmode"][0]

            _engine = create_engine(
                database_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args=connect_args,
            )
            logger.info("Database engine created successfully.")
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            return None
    return _engine


def _get_session_factory():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = _get_engine()
        if engine is None:
            return None
        _SessionLocal = sessionmaker(bind=engine)
    return _SessionLocal


@contextmanager
def get_session():
    """Context manager that yields a database session.

    Usage:
        with get_session() as session:
            session.query(Model).all()
    """
    factory = _get_session_factory()
    if factory is None:
        raise RuntimeError(
            "Database not configured. Set DATABASE_URL environment variable."
        )
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables defined in models.py."""
    engine = _get_engine()
    if engine is None:
        logger.error("Cannot initialize database: DATABASE_URL not set.")
        return False
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully.")
    return True


def is_db_configured() -> bool:
    """Check if database connection is configured and reachable."""
    engine = _get_engine()
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as e:
        logger.debug(f"Database connection check failed: {e}")
        return False
