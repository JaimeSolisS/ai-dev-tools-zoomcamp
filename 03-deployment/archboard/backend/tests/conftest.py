import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.main import create_app
from app.store import Store, StoreContext

PASSWORD = "correct horse battery staple"


class Clock:
    """Controllable time for expiry tests."""

    def __init__(self) -> None:
        self.current = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)


@pytest.fixture
def clock() -> Clock:
    return Clock()


class StoreProxy:
    """Test access to the database: every method call runs in its own committed unit of work."""

    def __init__(self, ctx: StoreContext):
        self.ctx = ctx

    def query(self, fn: Callable[[Store], Any]) -> Any:
        with self.ctx.store() as store:
            return fn(store)

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            with self.ctx.store() as store:
                return getattr(store, name)(*args, **kwargs)

        return call


@pytest.fixture
def database_url(tmp_path: Path) -> Iterator[Callable[[str], str]]:
    """Map a database name to a fresh, test-private database URL.

    SQLite by default. Set TEST_DATABASE_URL (e.g. postgresql+psycopg://postgres:postgres@localhost/postgres)
    to run against Postgres: each name gets its own database, dropped after the test.
    """
    server_url = os.environ.get("TEST_DATABASE_URL")
    if not server_url:
        yield lambda name: f"sqlite:///{tmp_path / name}"
        return

    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    created: dict[str, str] = {}

    def url_for(name: str) -> str:
        if name not in created:
            db_name = f"archboard_test_{uuid4().hex}"
            with admin.connect() as conn:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            created[name] = make_url(server_url).set(database=db_name).render_as_string(hide_password=False)
        return created[name]

    yield url_for
    with admin.connect() as conn:
        for url in created.values():
            conn.execute(text(f'DROP DATABASE IF EXISTS "{make_url(url).database}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def make_app(database_url: Callable[[str], str]) -> Callable[..., FastAPI]:
    """Build an app on a fresh database (or the same one again, to test restarts)."""

    def build(db_name: str = "test.db", **settings: Any) -> FastAPI:
        settings.setdefault("seed", False)
        settings.setdefault("dev_mode", True)
        return create_app(Settings(database_url=database_url(db_name), **settings))

    return build


@pytest.fixture
def app(make_app: Callable[..., FastAPI], clock: Clock) -> FastAPI:
    app = make_app()
    app.state.store_context.clock = clock
    return app


@pytest.fixture
def store(app: FastAPI) -> StoreProxy:
    return StoreProxy(app.state.store_context)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager keeps one event loop for HTTP and WebSocket traffic.
    with TestClient(app) as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def guest(credential: str) -> dict[str, str]:
    return {"X-Guest-Credential": credential}


def sign_up(client: TestClient, store: StoreProxy, email: str = "ada@example.com") -> dict[str, str]:
    """Create a user with a password, log in, and return auth headers."""
    store.create_user(email, password=PASSWORD)
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return bearer(response.json()["accessToken"])


@pytest.fixture
def owner(client: TestClient, store: StoreProxy) -> dict[str, str]:
    return sign_up(client, store)


def create_session(client: TestClient, headers: dict[str, str], **body) -> dict:
    response = client.post("/v1/sessions", json={"title": "Design Twitter", **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def create_link(client: TestClient, headers: dict[str, str], session_id: str, **body) -> dict:
    response = client.post(f"/v1/sessions/{session_id}/guest-links", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def join(client: TestClient, token: str, name: str = "Linus", headers: dict[str, str] | None = None) -> dict:
    response = client.post(f"/v1/join/{token}", json={"displayName": name}, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert response.json()["message"]


@pytest.fixture
def interview(client: TestClient, owner: dict[str, str]) -> dict:
    """A live session with a candidate who has joined. Returns ids, headers and tokens."""
    session = create_session(client, owner, prompt="Timeline at scale")
    client.post(f"/v1/sessions/{session['id']}/start", headers=owner)
    link = create_link(client, owner, session["id"])
    joined = join(client, link["token"])
    return {
        "session_id": session["id"],
        "owner": owner,
        "link": link,
        "candidate": guest(joined["credential"]),
        "candidate_id": joined["participant"]["id"],
    }
