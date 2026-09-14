from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base class for every SQLAlchemy ORM model.

    Business logic never touches this or the ORM models directly - it only
    sees the per-entity repositories in `app.repositories.bundle`, so the
    database engine (SQLite, Postgres, MySQL, ...) can change via
    `DATABASE_URL` without touching route or service code.
    """


def create_engine_for_url(database_url: str, *, in_memory: bool = False) -> Engine:
    connect_args: dict[str, object] = {}
    kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if in_memory:
            # An in-memory SQLite database only exists for the lifetime of a
            # single connection, so tests must share one connection via a
            # StaticPool instead of opening a fresh (empty) database per use.
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, connect_args=connect_args, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    from app.repositories import orm  # noqa: F401  (registers ORM models on Base)

    Base.metadata.create_all(engine)
