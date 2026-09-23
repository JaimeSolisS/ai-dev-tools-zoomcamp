"""Integration test for SPEC.md acceptance scenario 1.

Unlike test_agent_relay.py (in-process TestClient against a scratch
database), this hits a real running server over HTTP and exercises
whatever database it is actually backed by. Start the server first:

    uv run uvicorn main:app --reload

Then run:

    uv run pytest test_integration_scenario1.py -v

Point at a different instance with RELAY_BASE_URL.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("RELAY_BASE_URL", "http://127.0.0.1:8000")


def register(client: httpx.Client, name: str) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/agents", json={"name": name})
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['token']}"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as http_client:
        try:
            health = http_client.get("/health")
        except httpx.ConnectError as exc:
            pytest.skip(f"Agent Relay server not reachable at {BASE_URL}: {exc}")
        if health.status_code != 200:
            pytest.skip(f"Agent Relay server not healthy at {BASE_URL}: {health.text}")
        yield http_client


def test_scenario1_two_agents_exchange_task_and_result(client: httpx.Client):
    """Register two agents, exchange a task and its result, end to end.

    Mirrors SPEC.md acceptance scenario 1: "Register two agents. One
    sends a task; the other claims and completes it; the sender reads
    the result."
    """
    suffix = uuid.uuid4().hex[:8]
    sender, sender_headers = register(client, f"itest-sender-{suffix}")
    recipient, recipient_headers = register(client, f"itest-recipient-{suffix}")
    assert sender["agent_id"] != recipient["agent_id"]

    task_input = "Review this Python function: def add(a, b): return a + b"
    sent = client.post(
        "/api/v1/tasks",
        headers=sender_headers,
        json={"to": recipient["agent_id"], "input": task_input},
    )
    assert sent.status_code == 201, sent.text
    task_id = sent.json()["task_id"]
    assert sent.json()["status"] == "queued"

    claim = client.post(
        "/api/v1/tasks/claim",
        headers=recipient_headers,
        json={"worker_id": f"itest-worker-{suffix}", "wait_seconds": 0},
    )
    assert claim.status_code == 200, claim.text
    claim_data = claim.json()
    assert claim_data["task_id"] == task_id
    assert claim_data["from"] == sender["agent_id"]
    assert claim_data["input"] == task_input
    claim_token = claim_data["claim_token"]

    output = "Looks correct: add() returns the sum with no off-by-one issues."
    complete = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers=recipient_headers,
        json={"claim_token": claim_token, "output": output},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json() == {"task_id": task_id, "status": "completed"}

    result = client.get(f"/api/v1/tasks/{task_id}", headers=sender_headers)
    assert result.status_code == 200, result.text
    result_data = result.json()
    assert result_data["status"] == "completed"
    assert result_data["output"] == output
    assert result_data["error"] is None
    assert result_data["from"] == sender["agent_id"]
    assert result_data["to"] == recipient["agent_id"]
