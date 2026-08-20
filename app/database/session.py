"""Database engine and session helpers."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.database.models import Base


def create_database_engine(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine from application settings."""

    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    return create_engine(
        settings.database_url, future=True, pool_pre_ping=True, connect_args=connect_args
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    """Create tables directly.

    Production deployments should use Alembic migrations. This helper is useful for tests and
    first local smoke checks.
    """

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
