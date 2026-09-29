"""Database engine and session management (Role 5).

* ``get_db``        — FastAPI dependency: one session per request.
* ``session_scope`` — context manager for Celery tasks, the CLI and scripts.

Transaction policy: **services commit, the dependency never does.** A request that fails
half-way therefore can't leave partial writes behind.
"""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,  # transparently replace connections dropped by the DB / proxy
        pool_recycle=1800,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    with get_sessionmaker()() as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for non-request code: commit on success, roll back on error."""
    with get_sessionmaker()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
