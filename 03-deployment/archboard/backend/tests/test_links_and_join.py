from datetime import timedelta

from sqlalchemy import select

from app.tables import GuestLinkRow

from .conftest import assert_error, create_link, create_session, guest, join


def test_links_require_the_owner(client, interview):
    sid = interview["session_id"]
    assert_error(client.get(f"/v1/sessions/{sid}/guest-links"), 401, "UNAUTHENTICATED")
    assert_error(client.get(f"/v1/sessions/{sid}/guest-links", headers=interview["candidate"]), 401, "UNAUTHENTICATED")


def test_created_link_returns_token_once_and_stores_only_a_hash(client, store, owner):
    sid = create_session(client, owner)["id"]
    created = client.post(f"/v1/sessions/{sid}/guest-links", headers=owner)  # body is optional
    assert created.status_code == 201
    body = created.json()
    assert len(body["token"]) >= 43
    assert body["link"]["roleGranted"] == "candidate" and body["link"]["uses"] == 0
    listed = client.get(f"/v1/sessions/{sid}/guest-links", headers=owner)
    assert body["token"] not in listed.text
    hashes = store.query(lambda s: list(s.db.scalars(select(GuestLinkRow.token_hash))))
    assert hashes and body["token"] not in hashes


def test_lobby_info_and_join(client, owner):
    session = create_session(client, owner, title="Design Uber")
    link = create_link(client, owner, session["id"])
    info = client.get(f"/v1/join/{link['token']}")
    assert info.json() == {"sessionTitle": "Design Uber", "sessionState": "draft", "roleGranted": "candidate"}
    joined = join(client, link["token"], "  Linus  ")
    assert joined["sessionId"] == session["id"]
    assert joined["participant"]["displayName"] == "Linus"
    assert joined["participant"]["role"] == "candidate"
    assert joined["participant"]["userId"] is None
    assert joined["credential"]
    room = client.get(f"/v1/sessions/{session['id']}/canvas", headers=guest(joined["credential"]))
    assert room.status_code == 200
    assert room.json()["me"]["id"] == joined["participant"]["id"]


def test_join_requires_a_name(client, interview):
    response = client.post(f"/v1/join/{interview['link']['token']}", json={"displayName": "   "})
    assert_error(response, 422, "VALIDATION")
    assert response.json()["message"] == "Please enter your name."


def test_invalid_revoked_expired_and_exhausted_links(client, owner, clock):
    sid = create_session(client, owner)["id"]
    assert_error(client.get("/v1/join/not-a-token"), 404, "LINK_INVALID")

    revoked = create_link(client, owner, sid)
    assert client.delete(f"/v1/sessions/{sid}/guest-links/{revoked['link']['id']}", headers=owner).status_code == 204
    assert client.delete(f"/v1/sessions/{sid}/guest-links/{revoked['link']['id']}", headers=owner).status_code == 204
    assert_error(client.post(f"/v1/join/{revoked['token']}", json={"displayName": "Eve"}), 410, "LINK_REVOKED")

    expires_at = (clock() + timedelta(hours=1)).isoformat()
    expiring = create_link(client, owner, sid, expiresAt=expires_at)
    assert client.get(f"/v1/join/{expiring['token']}").status_code == 200
    clock.advance(hours=2)
    assert_error(client.get(f"/v1/join/{expiring['token']}"), 410, "LINK_EXPIRED")

    single = create_link(client, owner, sid, maxUses=1)
    join(client, single["token"], "One")
    assert_error(client.post(f"/v1/join/{single['token']}", json={"displayName": "Two"}), 410, "LINK_EXHAUSTED")
    assert_error(client.post(f"/v1/sessions/{sid}/guest-links", json={"maxUses": 0}, headers=owner), 422, "VALIDATION")


def test_rotation_revokes_old_links_but_keeps_participants(client, interview):
    sid, owner = interview["session_id"], interview["owner"]
    rotated = create_link(client, owner, sid, rotate=True)
    assert_error(
        client.post(f"/v1/join/{interview['link']['token']}", json={"displayName": "Late"}), 410, "LINK_REVOKED"
    )
    join(client, rotated["token"], "Newcomer")
    assert client.get(f"/v1/sessions/{sid}/canvas", headers=interview["candidate"]).status_code == 200
    links = client.get(f"/v1/sessions/{sid}/guest-links", headers=owner).json()
    assert [bool(link["revokedAt"]) for link in links] == [False, True]


def test_capacity_is_enforced(client, owner):
    # The limit is 10 concurrent participants, and the (recently active) owner is one of them.
    sid = create_session(client, owner)["id"]
    link = create_link(client, owner, sid)
    for i in range(9):
        join(client, link["token"], f"Guest {i}")
    assert_error(client.post(f"/v1/join/{link['token']}", json={"displayName": "Eleven"}), 409, "SESSION_FULL")


def test_idle_participants_do_not_count_towards_capacity(client, owner, clock):
    sid = create_session(client, owner)["id"]
    link = create_link(client, owner, sid)
    for i in range(9):
        join(client, link["token"], f"Guest {i}")
    assert_error(client.post(f"/v1/join/{link['token']}", json={"displayName": "Full"}), 409, "SESSION_FULL")
    clock.advance(minutes=5)
    join(client, link["token"], "Eleven")


def test_rejoin_with_credential_reuses_the_participant(client, interview):
    token = interview["link"]["token"]
    again = join(client, token, "Linus T.", headers=interview["candidate"])
    assert again["participant"]["id"] == interview["candidate_id"]
    assert again["participant"]["displayName"] == "Linus T."
    assert again["credential"] == interview["candidate"]["X-Guest-Credential"]
    link = client.get(f"/v1/sessions/{interview['session_id']}/guest-links", headers=interview["owner"]).json()[0]
    assert link["uses"] == 1


def test_ended_and_archived_sessions_cannot_be_joined(client, owner):
    ended = create_session(client, owner)["id"]
    ended_link = create_link(client, owner, ended)
    client.post(f"/v1/sessions/{ended}/end", headers=owner)
    assert_error(client.get(f"/v1/join/{ended_link['token']}"), 409, "SESSION_ENDED")
    assert_error(client.post(f"/v1/sessions/{ended}/guest-links", headers=owner), 409, "SESSION_ENDED")

    archived = create_session(client, owner)["id"]
    archived_link = create_link(client, owner, archived)
    client.post(f"/v1/sessions/{archived}/archive", headers=owner)
    assert_error(client.get(f"/v1/join/{archived_link['token']}"), 410, "SESSION_ARCHIVED")


def test_guest_credentials_are_scoped_to_one_session(client, interview):
    other = create_session(client, interview["owner"], title="Secret")["id"]
    candidate = interview["candidate"]
    assert_error(client.get(f"/v1/sessions/{other}/canvas", headers=candidate), 401, "UNAUTHENTICATED")
    assert_error(client.get(f"/v1/sessions/{other}", headers=candidate), 401, "UNAUTHENTICATED")
    assert_error(client.get(f"/v1/sessions/{other}/participants", headers=candidate), 401, "UNAUTHENTICATED")


def test_guest_credential_takes_precedence_over_the_user_token(client, interview):
    # The owner opens the candidate link in another tab: same user token, plus a guest credential.
    headers = {**interview["owner"]}
    joined = join(client, interview["link"]["token"], "Test candidate", headers=headers)
    as_guest = client.get(
        f"/v1/sessions/{interview['session_id']}/canvas", headers={**headers, **guest(joined["credential"])}
    )
    assert as_guest.json()["me"]["role"] == "candidate"
    as_owner = client.get(f"/v1/sessions/{interview['session_id']}/canvas", headers=headers)
    assert as_owner.json()["me"]["role"] == "owner"


def test_removed_participants_lose_access(client, store, interview):
    sid, owner = interview["session_id"], interview["owner"]
    url = f"/v1/sessions/{sid}/participants"
    assert [p["role"] for p in client.get(url, headers=interview["candidate"]).json()] == ["owner", "candidate"]
    assert client.delete(f"{url}/{interview['candidate_id']}", headers=owner).status_code == 204
    assert_error(client.get(f"/v1/sessions/{sid}/canvas", headers=interview["candidate"]), 403, "PARTICIPANT_REMOVED")
    assert_error(
        client.post(
            f"/v1/join/{interview['link']['token']}", json={"displayName": "Back"}, headers=interview["candidate"]
        ),
        403,
        "PARTICIPANT_REMOVED",
    )
    assert [p["role"] for p in client.get(url, headers=owner).json()] == ["owner"]

    owner_participant = next(p for p in store.list_participants(sid) if p.role == "owner")
    assert_error(client.delete(f"{url}/{owner_participant.id}", headers=owner), 422, "VALIDATION")
    assert_error(client.delete(f"{url}/nope", headers=owner), 404, "NOT_FOUND")
