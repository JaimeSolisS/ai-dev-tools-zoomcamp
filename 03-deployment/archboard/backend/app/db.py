"""Database engine and portable column types.

The database is chosen with the `DATABASE_URL` environment variable, as a
SQLAlchemy URL, e.g.

    sqlite:///./archboard.db                              (default)
    postgresql+psycopg://user:password@localhost/archboard (needs the psycopg driver)

Everything outside this module is database-agnostic: tables use only portable
types (String, Text, Integer, Boolean, JSON and the UTC datetime below) and
queries use the SQLAlchemy Core/ORM API. Dialect-specific tuning lives here.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

DEFAULT_DATABASE_URL = "sqlite:///./archboard.db"


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every backend.

    Stored as naive UTC (SQLite has no time zone support) and returned as aware
    UTC, so comparisons and JSON serialization behave the same everywhere.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use UTC-aware datetimes")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


def create_db_engine(url: str) -> Engine:
    """Create an engine for `url`, applying per-dialect settings."""
    parsed = make_url(url)
    kwargs: dict[str, Any] = {}
    if parsed.get_backend_name() == "sqlite":
        # Requests run in FastAPI's threadpool; each session gets its own connection.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if parsed.database in (None, "", ":memory:"):
            # An in-memory database only exists inside one connection; share it.
            # Fine for scripts and single-threaded use, not for a real server.
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True

    engine = create_engine(url, **kwargs)

    if parsed.get_backend_name() == "sqlite":
        is_file = parsed.database not in (None, "", ":memory:")

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            if is_file:
                # Readers don't block the writer; better for concurrent requests.
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker:
    # expire_on_commit=False: objects stay readable after commit (the store converts
    # them to Pydantic models, but this avoids surprises).
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    """Create missing tables. (A migration tool such as Alembic can replace this later.)"""
    from . import tables  # noqa: F401  (registers the tables on Base.metadata)

    Base.metadata.create_all(engine)
