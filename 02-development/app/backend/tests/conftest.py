from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.store import Store

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


@pytest.fixture
def app(clock: Clock) -> FastAPI:
    app = create_app(Settings(seed=False, dev_mode=True))
    app.state.store.now = clock
    return app


@pytest.fixture
def store(app: FastAPI) -> Store:
    return app.state.store


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager keeps one event loop for HTTP and WebSocket traffic.
    with TestClient(app) as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def guest(credential: str) -> dict[str, str]:
    return {"X-Guest-Credential": credential}


def sign_up(client: TestClient, store: Store, email: str = "ada@example.com") -> dict[str, str]:
    """Create a user with a password, log in, and return auth headers."""
    store.create_user(email, password=PASSWORD)
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return bearer(response.json()["accessToken"])


@pytest.fixture
def owner(client: TestClient, store: Store) -> dict[str, str]:
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
