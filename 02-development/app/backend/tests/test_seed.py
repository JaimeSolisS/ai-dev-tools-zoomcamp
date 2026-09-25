import pytest
from fastapi.testclient import TestClient

from app import canvas
from app.config import Settings
from app.main import create_app
from app.seed import DEMO_CANDIDATE_TOKEN, DEMO_PASSWORD

from .conftest import bearer


@pytest.fixture
def seeded():
    with TestClient(create_app(Settings(seed=True))) as client:
        yield client


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200
    return bearer(response.json()["accessToken"])


def test_demo_users_can_sign_in_and_see_their_sessions(seeded):
    ada = seeded.get("/v1/sessions", headers=login(seeded, "ada@example.com")).json()
    assert {(s["title"], s["state"]) for s in ada} == {
        ("Example: Design a URL shortener", "ended"),
        ("Design a chat app", "live"),
        ("Design a rate limiter", "draft"),
    }
    chat = next(s for s in ada if s["state"] == "live")
    assert chat["participantNames"] == ["Linus Torvalds"]
    assert chat["activeGuestLink"] is not None
    grace = seeded.get("/v1/sessions", headers=login(seeded, "grace@example.com")).json()
    assert [s["title"] for s in grace] == ["Design a news feed"]


def test_demo_candidate_link_joins_the_live_interview(seeded):
    assert seeded.get(f"/v1/join/{DEMO_CANDIDATE_TOKEN}").json()["sessionTitle"] == "Design a chat app"
    joined = seeded.post(f"/v1/join/{DEMO_CANDIDATE_TOKEN}", json={"displayName": "Visitor"}).json()
    room = seeded.get(
        f"/v1/sessions/{joined['sessionId']}/canvas", headers={"X-Guest-Credential": joined["credential"]}
    )
    assert room.status_code == 200
    assert room.json()["permissions"]["canEdit"] is True
    assert len(room.json()["canvas"]["elements"]) == 8


def test_seeded_canvas_elements_match_the_canvas_schema(seeded):
    store = seeded.app.state.store
    elements = [e for record in store.canvases.values() for e in record.elements.values()]
    assert len(elements) > 20
    for element in elements:
        parsed = canvas.parse_operation(
            {"id": "check", "actorId": "seed", "changes": [{"type": "put", "element": element}]}
        )
        # Round-trips unchanged, i.e. exactly what the frontend would write.
        assert canvas.entry_for(parsed.changes[0])[1] == element


def test_new_users_get_an_example_session(seeded):
    token = seeded.post("/v1/auth/magic-link", json={"email": "new@example.com"}).json()["devToken"]
    headers = bearer(seeded.post("/v1/auth/magic-link/verify", json={"token": token}).json()["accessToken"])
    sessions = seeded.get("/v1/sessions", headers=headers).json()
    assert [s["title"] for s in sessions] == ["Example: Design a URL shortener"]
    room = seeded.get(f"/v1/sessions/{sessions[0]['id']}/canvas", headers=headers).json()
    assert room["permissions"]["canEdit"] is False  # ended
    assert len(room["canvas"]["elements"]) == 15
