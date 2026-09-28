from contextlib import contextmanager

import pytest
from starlette.websockets import WebSocketDisconnect

from .conftest import create_link, join
from .test_canvas import put, shape


def ws_url(session_id: str, headers: dict[str, str]) -> str:
    if "Authorization" in headers:
        return f"/v1/sessions/{session_id}/ws?access_token={headers['Authorization'].removeprefix('Bearer ')}"
    return f"/v1/sessions/{session_id}/ws?guest_credential={headers['X-Guest-Credential']}"


@contextmanager
def connect(client, session_id: str, headers: dict[str, str]):
    with client.websocket_connect(ws_url(session_id, headers)) as ws:
        joined = ws.receive_json()
        assert joined["type"] == "room_joined", joined
        yield ws, joined["participantId"]


def next_of(ws, kind: str, limit: int = 20) -> dict:
    """Read messages until one of `kind` arrives (skipping presence noise)."""
    for _ in range(limit):
        message = ws.receive_json()
        if message["type"] == kind:
            return message
    raise AssertionError(f"no {kind} message")


def barrier(ws) -> list[dict]:
    """Messages received before a pong: proves what was (not) delivered so far."""
    ws.send_json({"type": "ping"})
    seen = []
    while (message := ws.receive_json())["type"] != "pong":
        seen.append(message)
    return seen


def operation(op_id: str, actor: str, *changes: dict) -> dict:
    return {"type": "document_update", "op": {"id": op_id, "actorId": actor, "changes": list(changes)}}


def test_rejects_connections_without_credentials(client, interview):
    with client.websocket_connect(f"/v1/sessions/{interview['session_id']}/ws") as ws:
        message = ws.receive_json()
        assert message["type"] == "error" and message["code"] == "UNAUTHENTICATED"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401


def test_rejects_unknown_sessions(client, owner):
    with client.websocket_connect(ws_url("nope", owner)) as ws:
        assert ws.receive_json()["code"] == "NOT_FOUND"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4404


def test_messages_are_enveloped(client, interview):
    with connect(client, interview["session_id"], interview["owner"]) as (ws, _):
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        assert pong["v"] == 1 and pong["sessionId"] == interview["session_id"] and pong["id"].startswith("m_")


def test_operations_are_acked_persisted_and_fanned_out(client, interview):
    sid = interview["session_id"]
    with (
        connect(client, sid, interview["owner"]) as (owner_ws, owner_id),
        connect(client, sid, interview["candidate"]) as (cand_ws, cand_id),
    ):
        assert cand_id == interview["candidate_id"]
        cand_ws.send_json(operation("op1", cand_id, put(shape("db", 1, actor=cand_id))))
        ack = next_of(cand_ws, "document_ack")
        assert ack["opId"] == "op1" and ack["cursor"] == 1

        update = next_of(owner_ws, "document_update")
        assert update["op"]["id"] == "op1" and update["cursor"] == 1
        assert update["op"]["changes"][0]["element"]["componentType"] == "server"
        # The sender does not get its own update back.
        assert not [m for m in barrier(cand_ws) if m["type"] == "document_update"]

    room = client.get(f"/v1/sessions/{sid}/canvas", headers=interview["owner"]).json()
    assert list(room["canvas"]["elements"]) == ["db"] and room["cursor"] == 1


def test_duplicate_operations_are_acked_but_not_reapplied(client, interview):
    sid = interview["session_id"]
    with (
        connect(client, sid, interview["owner"]) as (owner_ws, _),
        connect(client, sid, interview["candidate"]) as (cand_ws, cand_id),
    ):
        message = operation("dup", cand_id, put(shape("x", 1, actor=cand_id)))
        cand_ws.send_json(message)
        cand_ws.send_json(message)
        assert next_of(cand_ws, "document_ack")["cursor"] == 1
        assert next_of(cand_ws, "document_ack")["cursor"] == 1
        updates = [next_of(owner_ws, "document_update")] + [
            m for m in barrier(owner_ws) if m["type"] == "document_update"
        ]
        assert len(updates) == 1


def test_candidate_edits_are_rejected_while_locked(client, interview):
    sid = interview["session_id"]
    client.patch(f"/v1/sessions/{sid}", json={"candidateEditingEnabled": False}, headers=interview["owner"])
    with connect(client, sid, interview["candidate"]) as (ws, cand_id):
        ws.send_json(operation("locked", cand_id, put(shape("n", 1, actor=cand_id))))
        error = next_of(ws, "error")
        assert error["code"] == "EDIT_LOCKED" and error["opId"] == "locked"
    assert client.get(f"/v1/sessions/{sid}/canvas", headers=interview["owner"]).json()["canvas"]["elements"] == {}


def test_lock_change_is_broadcast_and_enforced_immediately(client, interview):
    sid = interview["session_id"]
    with connect(client, sid, interview["candidate"]) as (ws, cand_id):
        client.patch(f"/v1/sessions/{sid}", json={"candidateEditingEnabled": False}, headers=interview["owner"])
        assert next_of(ws, "session_updated")["session"]["candidateEditingEnabled"] is False
        ws.send_json(operation("after-lock", cand_id, put(shape("n", 1, actor=cand_id))))
        assert next_of(ws, "error")["code"] == "EDIT_LOCKED"


def test_actor_must_match_the_connection(client, interview):
    with connect(client, interview["session_id"], interview["candidate"]) as (ws, _):
        ws.send_json(operation("spoof", "p_someone_else", put(shape("n", 1, actor="p_someone_else"))))
        assert next_of(ws, "error")["code"] == "FORBIDDEN"


def test_observers_cannot_edit(client, interview):
    sid = interview["session_id"]
    observer = join(client, create_link(client, interview["owner"], sid, roleGranted="observer")["token"], "Watcher")
    with connect(client, sid, {"X-Guest-Credential": observer["credential"]}) as (ws, pid):
        ws.send_json(operation("o", pid, put(shape("n", 1, actor=pid))))
        assert next_of(ws, "error")["code"] == "FORBIDDEN"


def test_invalid_messages_get_validation_errors(client, interview):
    with connect(client, interview["session_id"], interview["candidate"]) as (ws, pid):
        ws.send_text("not json")
        assert next_of(ws, "error")["code"] == "VALIDATION"
        ws.send_json({"type": "teleport"})
        assert next_of(ws, "error")["code"] == "VALIDATION"
        ws.send_json(operation("bad", pid, put(shape("n", 1, actor=pid, componentType="nope"))))
        error = next_of(ws, "error")
        assert error["code"] == "VALIDATION" and error["opId"] == "bad"
        ws.send_json({"type": "presence_update", "presence": {"cursor": "here"}})
        assert next_of(ws, "error")["code"] == "VALIDATION"


def test_presence_is_relayed_with_server_side_identity(client, interview):
    sid = interview["session_id"]
    with (
        connect(client, sid, interview["owner"]) as (owner_ws, _),
        connect(client, sid, interview["candidate"]) as (cand_ws, cand_id),
    ):
        cand_ws.send_json({
            "type": "presence_update",
            "presence": {"participantId": "forged", "displayName": "Evil", "role": "owner",
                         "cursor": {"x": 10, "y": 20}, "selection": ["a"], "ts": 1},
        })  # fmt: skip
        presence = next_of(owner_ws, "presence_update")["presence"]
        assert presence["participantId"] == cand_id
        assert presence["displayName"] == "Linus" and presence["role"] == "candidate"
        assert presence["cursor"] == {"x": 10, "y": 20} and presence["selection"] == ["a"]


def test_presence_leave_is_sent_on_disconnect(client, interview):
    sid = interview["session_id"]
    with connect(client, sid, interview["owner"]) as (owner_ws, _):
        with connect(client, sid, interview["candidate"]) as (_, cand_id):
            pass
        assert next_of(owner_ws, "presence_leave")["participantId"] == cand_id


def test_http_actions_are_broadcast_to_the_room(client, interview):
    sid, owner = interview["session_id"], interview["owner"]
    with connect(client, sid, interview["candidate"]) as (ws, _):
        join(client, create_link(client, owner, sid)["token"], "Second candidate")
        next_of(ws, "participants_changed")

        client.post(f"/v1/sessions/{sid}/canvas/clear", headers=owner)
        next_of(ws, "canvas_reset")

        client.post(f"/v1/sessions/{sid}/end", headers=owner)
        ended = next_of(ws, "session_ended")
        assert ended["session"]["state"] == "ended"


def test_ended_sessions_reject_operations(client, interview):
    sid = interview["session_id"]
    with connect(client, sid, interview["owner"]) as (ws, owner_id):
        client.post(f"/v1/sessions/{sid}/end", headers=interview["owner"])
        next_of(ws, "session_ended")
        ws.send_json(operation("late", owner_id, put(shape("n", 1, actor=owner_id))))
        assert next_of(ws, "error")["code"] == "SESSION_ENDED"


def test_removed_participants_are_notified_and_disconnected(client, interview):
    sid = interview["session_id"]
    with connect(client, sid, interview["candidate"]) as (ws, cand_id):
        client.delete(f"/v1/sessions/{sid}/participants/{cand_id}", headers=interview["owner"])
        assert next_of(ws, "participant_removed")["participantId"] == cand_id
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(5):
                ws.receive_json()
        assert closed.value.code == 4403
    # And cannot reconnect.
    with client.websocket_connect(ws_url(sid, interview["candidate"])) as ws:
        assert ws.receive_json()["code"] == "PARTICIPANT_REMOVED"
