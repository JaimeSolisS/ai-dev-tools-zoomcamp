"""What only the deployed stack can show: the image, the wiring between containers, and Postgres.

Business rules are covered by the unit tests in `../tests`; these check the deployment.
"""

import re

import httpx2 as httpx

from .conftest import Stack, live_interview, login, open_socket, shape, unique

# --- The image serves the frontend and the API from one origin ---


def test_serves_the_built_frontend(http: httpx.Client):
    page = http.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert '<div id="root">' in page.text

    # Every asset the page references is in the image.
    assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', page.text)
    assert any(a.endswith(".js") for a in assets) and any(a.endswith(".css") for a in assets)
    for asset in assets:
        assert http.get(asset).status_code == 200, asset


def test_client_side_routes_get_the_app_shell(http: httpx.Client):
    # Share links and bookmarks are opened directly, so the server must answer them with the app.
    for path in ("/join/some-token", "/sessions/s_123", "/sessions/s_123/room"):
        response = http.get(path)
        assert response.status_code == 200, path
        assert '<div id="root">' in response.text, path


def test_api_paths_are_not_swallowed_by_the_frontend(http: httpx.Client):
    response = http.get("/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert http.get("/v1/sessions").status_code == 401  # a real API route, not the app shell
    assert http.get("/openapi.json").json()["info"]["title"] == "Archboard API"


# --- The app is wired to Postgres ---


def test_data_is_stored_in_postgres(stack: Stack, http: httpx.Client):
    owner = login(http)
    title = unique("Stored in Postgres")
    assert http.post("/v1/sessions", json={"title": title}, headers=owner).status_code == 201

    assert stack.sql(f"select title from interview_sessions where title = '{title}'") == [title]
    # And not in the image's default SQLite location.
    assert stack.compose("exec", "-T", "app", "ls", "-A", "/data").stdout.strip() == ""


def test_demo_data_is_seeded_on_first_start(http: httpx.Client):
    sessions = http.get("/v1/sessions", headers=login(http)).json()
    assert any(s["title"].startswith("Example") for s in sessions)


# --- A full interview through the published port ---


def test_share_link_flow(http: httpx.Client):
    interview = live_interview(http)
    sid, token = interview["session_id"], interview["token"]

    # What the candidate's browser does with the link: load the page, then the lobby.
    assert '<div id="root">' in http.get(f"/join/{token}").text
    lobby = http.get(f"/v1/join/{token}").json()
    assert lobby == {"sessionTitle": interview["title"], "sessionState": "live", "roleGranted": "candidate"}

    room = http.get(f"/v1/sessions/{sid}/canvas", headers=interview["candidate"])
    assert room.status_code == 200, room.text

    # The owner sees the candidate.
    participants = http.get(f"/v1/sessions/{sid}/participants", headers=interview["owner"]).json()
    assert "Linus" in [p["displayName"] for p in participants]


def test_revoked_link_stops_working(http: httpx.Client):
    interview = live_interview(http)
    sid, owner = interview["session_id"], interview["owner"]
    [link] = http.get(f"/v1/sessions/{sid}/guest-links", headers=owner).json()
    assert http.delete(f"/v1/sessions/{sid}/guest-links/{link['id']}", headers=owner).status_code == 204
    assert http.post(f"/v1/join/{interview['token']}", json={"displayName": "Late"}).status_code in (403, 404, 410)


def test_realtime_collaboration_over_websockets(stack: Stack, http: httpx.Client):
    interview = live_interview(http)
    sid = interview["session_id"]
    with (
        open_socket(stack, sid, interview["owner"]) as owner,
        open_socket(stack, sid, interview["candidate"]) as candidate,
    ):
        op = {"id": unique("op").replace(" ", "-"), "actorId": candidate.participant_id}
        op["changes"] = [{"type": "put", "element": shape("db", candidate.participant_id)}]
        candidate.send({"type": "document_update", "op": op})

        assert candidate.next_of("document_ack")["opId"] == op["id"]
        update = owner.next_of("document_update")
        assert update["op"]["id"] == op["id"]

    # The operation was committed, not only broadcast.
    canvas = http.get(f"/v1/sessions/{sid}/canvas", headers=interview["owner"]).json()["canvas"]
    assert canvas["elements"]["db"]["label"] == "API server"


# --- Restarts: what a deployment does all the time ---


def test_data_survives_recreating_the_app_container(stack: Stack, http: httpx.Client):
    interview = live_interview(http)
    sid = interview["session_id"]

    stack.up("--force-recreate", "app")  # a new container, as on every deploy

    # Tokens, sessions and participants all came from Postgres.
    sessions = http.get("/v1/sessions", headers=interview["owner"]).json()
    assert interview["title"] in [s["title"] for s in sessions]
    assert http.get(f"/v1/sessions/{sid}/canvas", headers=interview["candidate"]).status_code == 200
    # The demo data was not seeded a second time.
    assert stack.sql("select count(*) from users where email = 'ada@example.com'") == ["1"]


def test_app_recovers_when_postgres_restarts(stack: Stack, http: httpx.Client):
    owner = login(http)
    assert http.get("/v1/sessions", headers=owner).status_code == 200  # pool holds connections now

    stack.compose("restart", "db")
    stack.compose("up", "-d", "--wait", "db")

    # Pooled connections died with the old server; the app must reconnect, not fail.
    for _ in range(3):
        assert http.get("/v1/sessions", headers=owner).status_code == 200
    title = unique("After db restart")
    assert http.post("/v1/sessions", json={"title": title}, headers=owner).status_code == 201


def test_health_checks_the_database(http: httpx.Client):
    response = http.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
