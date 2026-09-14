from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repositories.database import create_engine_for_url


@pytest.fixture
def settings() -> Settings:
    return Settings(
        jwt_secret="test-secret-at-least-32-bytes-long!!", jwt_expiration_hours=8, app_currency="MXN"
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    engine = create_engine_for_url("sqlite:///:memory:", in_memory=True)
    return create_app(engine=engine, settings=settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/setup",
        json={"username": "admin", "display_name": "Admin", "password": "admin1234"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    return auth_headers(admin_token)


def default_password(username: str) -> str:
    """A deterministic, always->=8-char temporary password for test users."""
    return f"{username}-12345678"


def create_user(
    client: TestClient, admin_headers: dict[str, str], username: str, display_name: str | None = None
) -> dict:
    response = client.post(
        "/api/v1/users",
        json={
            "username": username,
            "display_name": display_name or username.capitalize(),
            "temporary_password": default_password(username),
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def login_as(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]  # type: ignore[no-any-return]
