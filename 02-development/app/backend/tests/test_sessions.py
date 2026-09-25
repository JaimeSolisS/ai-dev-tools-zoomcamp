from .conftest import assert_error, create_link, create_session, join, sign_up


def test_session_endpoints_require_authentication(client):
    assert_error(client.get("/v1/sessions"), 401, "UNAUTHENTICATED")
    assert_error(client.post("/v1/sessions", json={"title": "x"}), 401, "UNAUTHENTICATED")


def test_create_returns_a_draft_with_all_fields(client, owner):
    session = create_session(client, owner, prompt="Home timeline", durationMinutes=45)
    assert session["state"] == "draft"
    assert session["title"] == "Design Twitter"
    assert session["durationMinutes"] == 45
    assert session["candidateEditingEnabled"] is True
    assert session["startedAt"] is None and session["scheduledAt"] is None
    assert set(session) == {
        "id", "ownerUserId", "title", "prompt", "state", "candidateEditingEnabled", "showCursors",
        "durationMinutes", "scheduledAt", "startedAt", "endedAt", "createdAt", "updatedAt",
    }  # fmt: skip


def test_create_validates_input(client, owner):
    response = client.post("/v1/sessions", json={"title": "   "}, headers=owner)
    assert_error(response, 422, "VALIDATION")
    assert response.json()["message"] == "Title is required."
    response = client.post("/v1/sessions", json={"title": "ok", "durationMinutes": 1}, headers=owner)
    assert response.json()["message"] == "Duration must be between 5 and 480 minutes."
    assert_error(client.post("/v1/sessions", json={"title": "x" * 121}, headers=owner), 422, "VALIDATION")


def test_list_returns_summaries_newest_first(client, owner, clock):
    first = create_session(client, owner, title="First")
    clock.advance(minutes=1)
    second = create_session(client, owner, title="Second")
    link = create_link(client, owner, first["id"])
    join(client, link["token"], "Linus")
    clock.advance(minutes=1)
    client.patch(f"/v1/sessions/{first['id']}", json={"prompt": "updated"}, headers=owner)

    sessions = client.get("/v1/sessions", headers=owner).json()
    assert [s["id"] for s in sessions] == [first["id"], second["id"]]
    assert sessions[0]["participantNames"] == ["Linus"]
    assert sessions[0]["activeGuestLink"]["uses"] == 1
    assert "token" not in sessions[0]["activeGuestLink"]
    assert sessions[1]["activeGuestLink"] is None


def test_sessions_are_private_to_their_owner(client, store, owner):
    session = create_session(client, owner)
    stranger = sign_up(client, store, "mallory@example.com")
    assert client.get("/v1/sessions", headers=stranger).json() == []
    for method, path in [
        ("get", f"/v1/sessions/{session['id']}"),
        ("post", f"/v1/sessions/{session['id']}/start"),
        ("post", f"/v1/sessions/{session['id']}/end"),
        ("post", f"/v1/sessions/{session['id']}/archive"),
        ("post", f"/v1/sessions/{session['id']}/duplicate"),
        ("get", f"/v1/sessions/{session['id']}/guest-links"),
        ("get", f"/v1/sessions/{session['id']}/canvas"),
    ]:
        assert_error(getattr(client, method)(path, headers=stranger), 404, "NOT_FOUND")
    assert_error(client.get("/v1/sessions/does-not-exist", headers=owner), 404, "NOT_FOUND")


def test_lifecycle_transitions(client, owner, store):
    sid = create_session(client, owner)["id"]
    assert_error(client.post(f"/v1/sessions/{sid}/reopen", headers=owner), 409, "CONFLICT")

    live = client.post(f"/v1/sessions/{sid}/start", headers=owner).json()
    assert live["state"] == "live" and live["startedAt"]
    assert_error(client.post(f"/v1/sessions/{sid}/start", headers=owner), 409, "CONFLICT")

    ended = client.post(f"/v1/sessions/{sid}/end", headers=owner).json()
    assert ended["state"] == "ended" and ended["endedAt"]
    assert_error(client.post(f"/v1/sessions/{sid}/end", headers=owner), 409, "CONFLICT")
    reasons = [s["reason"] for s in client.get(f"/v1/sessions/{sid}/canvas/snapshots", headers=owner).json()]
    assert reasons == ["final"]

    reopened = client.post(f"/v1/sessions/{sid}/reopen", headers=owner).json()
    assert reopened["state"] == "live" and reopened["endedAt"] is None

    archived = client.post(f"/v1/sessions/{sid}/archive", headers=owner).json()
    assert archived["state"] == "archived" and archived["endedAt"]

    actions = [e.action for e in store.audit_log()]
    assert actions == [
        "session.created", "session.started", "session.ended", "session.reopened", "session.archived",
    ]  # fmt: skip


def test_update_applies_only_given_fields(client, owner):
    session = create_session(client, owner, prompt="original", durationMinutes=45)
    updated = client.patch(f"/v1/sessions/{session['id']}", json={"title": "Renamed"}, headers=owner).json()
    assert updated["title"] == "Renamed"
    assert updated["prompt"] == "original" and updated["durationMinutes"] == 45
    cleared = client.patch(f"/v1/sessions/{session['id']}", json={"durationMinutes": None}, headers=owner).json()
    assert cleared["durationMinutes"] is None
    assert_error(client.patch(f"/v1/sessions/{session['id']}", json={"title": None}, headers=owner), 422, "VALIDATION")


def test_candidates_cannot_change_settings_or_lock(client, interview):
    sid, candidate = interview["session_id"], interview["candidate"]
    assert client.get(f"/v1/sessions/{sid}", headers=candidate).status_code == 200
    assert_error(client.patch(f"/v1/sessions/{sid}", json={"title": "Hacked"}, headers=candidate), 403, "FORBIDDEN")
    response = client.patch(f"/v1/sessions/{sid}", json={"candidateEditingEnabled": False}, headers=candidate)
    assert_error(response, 403, "FORBIDDEN")
    # Guests can never use owner-only endpoints, which require a user token.
    assert_error(client.post(f"/v1/sessions/{sid}/end", headers=candidate), 401, "UNAUTHENTICATED")


def test_invited_interviewer_can_lock_but_not_manage(client, store, interview):
    sid, owner = interview["session_id"], interview["owner"]
    colleague = sign_up(client, store, "grace@example.com")
    link = create_link(client, owner, sid, roleGranted="interviewer")
    join(client, link["token"], "Grace", headers=colleague)

    # The session now shows up on the colleague's dashboard and they can open it with their user token.
    assert [s["id"] for s in client.get("/v1/sessions", headers=colleague).json()] == [sid]
    locked = client.patch(f"/v1/sessions/{sid}", json={"candidateEditingEnabled": False}, headers=colleague)
    assert locked.status_code == 200 and locked.json()["candidateEditingEnabled"] is False
    assert_error(client.patch(f"/v1/sessions/{sid}", json={"prompt": "x"}, headers=colleague), 403, "FORBIDDEN")
    assert_error(client.post(f"/v1/sessions/{sid}/end", headers=colleague), 404, "NOT_FOUND")
    assert [e.action for e in store.audit_log()][-1] == "permissions.changed"


def test_duplicate_copies_prompt_and_canvas_into_a_new_draft(client, owner, store):
    session = create_session(client, owner, prompt="P", durationMinutes=30)
    client.post(f"/v1/sessions/{session['id']}/start", headers=owner)
    store.put_elements(
        session["id"],
        {"el_1": {"id": "el_1", "deleted": True, "version": {"clock": 1, "actor": "a"}}},
    )
    copy = client.post(f"/v1/sessions/{session['id']}/duplicate", headers=owner)
    assert copy.status_code == 201
    body = copy.json()
    assert body["title"] == "Design Twitter (copy)"
    assert body["state"] == "draft" and body["prompt"] == "P" and body["durationMinutes"] == 30
    room = client.get(f"/v1/sessions/{body['id']}/canvas", headers=owner).json()
    assert list(room["canvas"]["elements"]) == ["el_1"]


def test_create_from_template_requires_ownership(client, store, owner):
    template = create_session(client, owner, title="Template")
    store.put_elements(template["id"], {"x": {"id": "x", "deleted": True, "version": {"clock": 1, "actor": "a"}}})
    created = create_session(client, owner, title="From template", templateSessionId=template["id"])
    assert list(client.get(f"/v1/sessions/{created['id']}/canvas", headers=owner).json()["canvas"]["elements"]) == ["x"]
    stranger = sign_up(client, store, "mallory@example.com")
    response = client.post("/v1/sessions", json={"title": "t", "templateSessionId": template["id"]}, headers=stranger)
    assert_error(response, 404, "NOT_FOUND")
