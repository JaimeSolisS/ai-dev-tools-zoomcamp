"""Integration tests against the real deployment: `../docker-compose.yaml` (app image + Postgres).

One stack is started for the whole run on a free port, under its own compose project name
so it never touches a stack you are running yourself, and is deleted (with its volume) at
the end. Run with `make test-compose` from the repo root, or `uv run pytest integration_tests`.
"""

import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from websockets.sync.client import ClientConnection, connect

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.yaml"
DEMO_EMAIL = "ada@example.com"
DEMO_PASSWORD = "password123"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # The first test also builds the image and starts the stack; the 30s unit-test limit is too short.
    here = Path(__file__).parent
    for item in items:
        if here in item.path.parents:
            item.add_marker(pytest.mark.timeout(600))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Stack:
    """A running compose project, with helpers to poke at it from the outside."""

    def __init__(self, project: str, port: int):
        self.project = project
        self.port = port
        self.base_url = f"http://localhost:{port}"
        self.ws_url = f"ws://localhost:{port}"
        self.env = {"APP_PORT": str(port)}

    def compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", self.project, *args],
            env={**os.environ, **self.env},
            capture_output=True,
            text=True,
            check=check,
        )

    def sql(self, query: str) -> list[str]:
        """Run a query in the Postgres container; returns one string per row."""
        out = self.compose("exec", "-T", "db", "psql", "-U", "archboard", "-d", "archboard", "-tAc", query).stdout
        return [line for line in out.splitlines() if line]

    def wait_until_ready(self, timeout: float = 60) -> None:
        """Wait until the app answers HTTP (healthy containers alone don't prove the port is mapped)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if httpx.get(self.base_url + "/", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise AssertionError(f"app not ready after {timeout}s:\n{self.compose('logs', check=False).stdout[-4000:]}")

    def up(self, *args: str) -> None:
        self.compose("up", "-d", "--wait", *args)
        self.wait_until_ready()


@pytest.fixture(scope="session")
def stack() -> Iterator[Stack]:
    if shutil.which("docker") is None or subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("Docker is not available")
    s = Stack(f"archboard-it-{uuid.uuid4().hex[:8]}", free_port())
    try:
        s.up("--build")
        yield s
    except subprocess.CalledProcessError as err:
        pytest.fail(f"docker compose failed:\n{err.stdout}\n{err.stderr}")
    finally:
        s.compose("down", "-v", "--remove-orphans", check=False)


@pytest.fixture
def http(stack: Stack) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack.base_url, timeout=10) as client:
        yield client


def login(http: httpx.Client, email: str = DEMO_EMAIL, password: str = DEMO_PASSWORD) -> dict[str, str]:
    response = http.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def unique(prefix: str) -> str:
    """Test data names are unique, because every test shares one database."""
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def live_interview(http: httpx.Client) -> dict[str, Any]:
    """A started session with a share link and a candidate who joined through it."""
    owner = login(http)
    title = unique("Integration")
    session = http.post("/v1/sessions", json={"title": title, "prompt": "Design a URL shortener"}, headers=owner)
    assert session.status_code == 201, session.text
    sid = session.json()["id"]
    assert http.post(f"/v1/sessions/{sid}/start", headers=owner).status_code == 200
    link = http.post(f"/v1/sessions/{sid}/guest-links", json={"roleGranted": "candidate"}, headers=owner)
    assert link.status_code == 201, link.text
    token = link.json()["token"]
    joined = http.post(f"/v1/join/{token}", json={"displayName": "Linus"})
    assert joined.status_code == 200, joined.text
    return {
        "session_id": sid,
        "title": title,
        "owner": owner,
        "token": token,
        "candidate": {"X-Guest-Credential": joined.json()["credential"]},
        "candidate_id": joined.json()["participant"]["id"],
    }


def shape(element_id: str, actor: str, clock: int = 1) -> dict[str, Any]:
    return {
        "id": element_id,
        "kind": "shape",
        "componentType": "server",
        "x": 10,
        "y": 20,
        "w": 150,
        "h": 72,
        "label": "API server",
        "z": 1,
        "version": {"clock": clock, "actor": actor},
        "createdBy": actor,
        "createdAt": "2026-09-01T12:00:00Z",
        "updatedBy": actor,
    }


class Socket:
    """A realtime connection to the app's WebSocket endpoint, through the published port."""

    def __init__(self, ws: ClientConnection):
        self.ws = ws
        joined = self.receive()
        assert joined["type"] == "room_joined", joined
        self.participant_id: str = joined["participantId"]

    def send(self, message: dict[str, Any]) -> None:
        self.ws.send(json.dumps(message))

    def receive(self, timeout: float = 10) -> dict[str, Any]:
        return json.loads(self.ws.recv(timeout=timeout))

    def next_of(self, kind: str, limit: int = 50) -> dict[str, Any]:
        """Read messages until one of `kind` arrives (skipping presence noise)."""
        for _ in range(limit):
            message = self.receive()
            assert message["type"] != "error" or kind == "error", message
            if message["type"] == kind:
                return message
        raise AssertionError(f"no {kind} message")


@contextmanager
def open_socket(stack: Stack, session_id: str, headers: dict[str, str]) -> Iterator[Socket]:
    if "Authorization" in headers:
        query = "access_token=" + headers["Authorization"].removeprefix("Bearer ")
    else:
        query = "guest_credential=" + headers["X-Guest-Credential"]
    with connect(f"{stack.ws_url}/v1/sessions/{session_id}/ws?{query}", open_timeout=10) as ws:
        yield Socket(ws)
