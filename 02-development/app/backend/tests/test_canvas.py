import pytest

from app import canvas

from .conftest import assert_error, create_link, create_session, join


def shape(element_id: str, clock: int, actor: str = "a", **extra) -> dict:
    return {
        "id": element_id,
        "kind": "shape",
        "componentType": "server",
        "x": 0,
        "y": 0,
        "w": 150,
        "h": 72,
        "label": "Server",
        "z": 1,
        "version": {"clock": clock, "actor": actor},
        "createdBy": actor,
        "createdAt": "2026-09-01T12:00:00Z",
        "updatedBy": actor,
        **extra,
    }


def op(op_id: str, *changes: dict, actor: str = "a") -> canvas.CanvasOperation:
    return canvas.parse_operation({"id": op_id, "actorId": actor, "changes": list(changes)})


def put(element: dict) -> dict:
    return {"type": "put", "element": element}


def delete(element_id: str, clock: int, actor: str = "a") -> dict:
    return {"type": "delete", "id": element_id, "version": {"clock": clock, "actor": actor}}


class TestMerge:
    def test_newer_version_wins_regardless_of_order(self):
        older = op("1", put(shape("n", 1, label="old")))
        newer = op("2", put(shape("n", 2, label="new")))
        a = canvas.apply_operation(canvas.apply_operation({}, older), newer)
        b = canvas.apply_operation(canvas.apply_operation({}, newer), older)
        assert a == b
        assert a["n"]["label"] == "new"

    def test_actor_breaks_ties(self):
        x = op("1", put(shape("n", 5, actor="alice", label="alice")))
        y = op("2", put(shape("n", 5, actor="bob", label="bob")), actor="bob")
        assert canvas.apply_operation(canvas.apply_operation({}, x), y)["n"]["label"] == "bob"
        assert canvas.apply_operation(canvas.apply_operation({}, y), x)["n"]["label"] == "bob"

    def test_tombstones_beat_older_puts(self):
        doc = canvas.apply_operation({}, op("1", delete("n", 3)))
        doc = canvas.apply_operation(doc, op("2", put(shape("n", 2))))
        assert canvas.is_tombstone(doc["n"])
        assert canvas.live_count(doc) == 0

    def test_is_idempotent(self):
        o = op("1", put(shape("n", 1)))
        once = canvas.apply_operation({}, o)
        assert canvas.apply_operation(once, o) == once

    def test_elements_keep_their_camel_case_json_shape(self):
        connector = {
            "id": "c", "kind": "connector", "z": 2, "version": {"clock": 1, "actor": "a"},
            "createdBy": "a", "createdAt": "t", "updatedBy": "a",
            "from": {"elementId": "n", "anchor": "auto", "x": 0, "y": 0}, "to": {"x": 5, "y": 5},
            "routing": "elbow", "arrowStart": False, "arrowEnd": True, "label": "HTTPS",
            "dashed": False, "color": "#000", "width": 2,
        }  # fmt: skip
        stored = canvas.apply_operation({}, op("1", put(connector)))["c"]
        assert stored == connector


class TestValidation:
    @pytest.mark.parametrize(
        "change",
        [
            put(shape("n", 1, kind="image")),
            put(shape("n", 1, componentType="teleporter")),
            put(shape("n", 1, label="x" * 2001)),
            put(shape("n", 1, w=0)),
            {"type": "move", "id": "n"},
        ],
    )
    def test_rejects_invalid_changes(self, change):
        with pytest.raises(canvas.InvalidOperation):
            canvas.parse_operation({"id": "1", "actorId": "a", "changes": [change]})

    def test_rejects_oversized_operations(self):
        changes = [put(shape(f"n{i}", 1)) for i in range(501)]
        with pytest.raises(canvas.InvalidOperation):
            canvas.parse_operation({"id": "1", "actorId": "a", "changes": changes})


def test_open_room_returns_identity_permissions_and_canvas(client, interview):
    room = client.get(f"/v1/sessions/{interview['session_id']}/canvas", headers=interview["owner"]).json()
    assert room["me"]["role"] == "owner"
    assert room["cursor"] == 0
    assert room["canvas"] == {"schemaVersion": 1, "elements": {}}
    assert room["permissions"]["canShare"] is True
    assert [p["role"] for p in room["participants"]] == ["owner", "candidate"]

    candidate_room = client.get(f"/v1/sessions/{interview['session_id']}/canvas", headers=interview["candidate"]).json()
    assert candidate_room["permissions"] == {
        "canView": True, "canEdit": True, "canLockEditing": False, "canShare": False,
        "canRemoveParticipants": False, "canStartOrEnd": False, "canClearCanvas": False, "canEditSettings": False,
    }  # fmt: skip


def test_room_requires_credentials(client, interview):
    assert_error(client.get(f"/v1/sessions/{interview['session_id']}/canvas"), 401, "UNAUTHENTICATED")


def test_candidates_cannot_edit_drafts_and_observers_never_edit(client, owner):
    sid = create_session(client, owner)["id"]
    candidate = join(client, create_link(client, owner, sid)["token"])
    observer = join(client, create_link(client, owner, sid, roleGranted="observer")["token"], "Watcher")
    for joined in (candidate, observer):
        room = client.get(f"/v1/sessions/{sid}/canvas", headers={"X-Guest-Credential": joined["credential"]}).json()
        assert room["permissions"]["canView"] is True
        assert room["permissions"]["canEdit"] is False


def test_ended_sessions_are_hidden_from_candidates_but_not_the_owner(client, interview):
    sid = interview["session_id"]
    client.post(f"/v1/sessions/{sid}/end", headers=interview["owner"])
    assert_error(client.get(f"/v1/sessions/{sid}/canvas", headers=interview["candidate"]), 409, "SESSION_ENDED")
    room = client.get(f"/v1/sessions/{sid}/canvas", headers=interview["owner"]).json()
    assert room["permissions"]["canView"] is True and room["permissions"]["canEdit"] is False


def test_clear_and_restore_keep_recoverable_snapshots(client, store, interview):
    sid, owner = interview["session_id"], interview["owner"]
    me = client.get(f"/v1/sessions/{sid}/canvas", headers=owner).json()["me"]["id"]
    result = store.apply_client_operation(
        sid, me, {"id": "op1", "actorId": me, "changes": [put(shape("keep", 1, actor=me))]}
    )
    assert result.ok

    assert client.post(f"/v1/sessions/{sid}/canvas/clear", headers=owner).status_code == 204
    room = client.get(f"/v1/sessions/{sid}/canvas", headers=owner).json()
    assert room["canvas"]["elements"] == {} and room["cursor"] == 2

    snapshots = client.get(f"/v1/sessions/{sid}/canvas/snapshots", headers=owner).json()
    assert [(s["reason"], s["elementCount"]) for s in snapshots] == [("before-clear", 1)]
    restore = client.post(f"/v1/sessions/{sid}/canvas/snapshots/{snapshots[0]['id']}/restore", headers=owner)
    assert restore.status_code == 204
    assert list(client.get(f"/v1/sessions/{sid}/canvas", headers=owner).json()["canvas"]["elements"]) == ["keep"]
    assert_error(client.post(f"/v1/sessions/{sid}/canvas/snapshots/nope/restore", headers=owner), 404, "NOT_FOUND")


def test_clear_is_owner_only_and_not_after_end(client, interview):
    sid = interview["session_id"]
    assert_error(
        client.post(f"/v1/sessions/{sid}/canvas/clear", headers=interview["candidate"]), 401, "UNAUTHENTICATED"
    )
    client.post(f"/v1/sessions/{sid}/end", headers=interview["owner"])
    assert_error(client.post(f"/v1/sessions/{sid}/canvas/clear", headers=interview["owner"]), 409, "SESSION_ENDED")
