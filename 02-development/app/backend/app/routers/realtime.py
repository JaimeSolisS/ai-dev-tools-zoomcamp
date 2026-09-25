"""WS /v1/sessions/{sessionId}/ws — the collaboration channel (see openapi.yaml `connectRealtime`)."""

import asyncio
import json
import math
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..errors import ApiError
from ..realtime import (
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    CLOSE_UNAUTHENTICATED,
    Connection,
    Hub,
    envelope,
    pump,
)
from ..store import ParticipantRecord, Store

router = APIRouter(tags=["realtime"])

MAX_SELECTION = 500
CLOSE_CODES = {401: CLOSE_UNAUTHENTICATED, 404: CLOSE_NOT_FOUND}


def _error(code: str, message: str, op_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "error", "code": code, "message": message}
    if op_id is not None:
        payload["opId"] = op_id
    return payload


def _clean_presence(raw: Any, participant: ParticipantRecord) -> dict[str, Any] | None:
    """Build a presence message from client input; identity fields come from the server."""
    if not isinstance(raw, dict):
        return None
    cursor = raw.get("cursor")
    if cursor is not None:
        if not isinstance(cursor, dict):
            return None
        x, y = cursor.get("x"), cursor.get("y")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y)):
            return None
        cursor = {"x": x, "y": y}
    selection = raw.get("selection", [])
    if not isinstance(selection, list) or not all(isinstance(s, str) for s in selection):
        return None
    ts = raw.get("ts")
    return {
        "participantId": participant.id,
        "displayName": participant.display_name,
        "color": participant.color,
        "role": participant.role,
        "cursor": cursor,
        "selection": selection[:MAX_SELECTION],
        "ts": ts if isinstance(ts, (int, float)) else 0,
    }


def _handle(store: Store, hub: Hub, conn: Connection, message: Any) -> None:
    if not isinstance(message, dict):
        hub.send(conn, _error("VALIDATION", "Messages must be JSON objects."))
        return
    kind = message.get("type")
    if kind == "ping":
        hub.send(conn, {"type": "pong"})
    elif kind == "presence_update":
        participant = store.participants.get(conn.participant_id)
        presence = _clean_presence(message.get("presence"), participant) if participant else None
        if presence is None:
            hub.send(conn, _error("VALIDATION", "Invalid presence update."))
            return
        store.mark_seen(conn.participant_id)
        hub.publish(conn.session_id, {"type": "presence_update", "presence": presence}, exclude=conn.id)
    elif kind == "document_update":
        op = message.get("op")
        op_id = op.get("id") if isinstance(op, dict) and isinstance(op.get("id"), str) else None
        # Authorization is re-checked for every operation inside the store.
        result = store.apply_client_operation(conn.session_id, conn.participant_id, op, connection_id=conn.id)
        if result.ok:
            hub.send(conn, {"type": "document_ack", "opId": op_id, "cursor": result.cursor})
        else:
            hub.send(conn, _error(result.code or "FORBIDDEN", result.message or "Rejected.", op_id))
    else:
        hub.send(conn, _error("VALIDATION", f"Unknown message type: {kind!r}."))


@router.websocket("/v1/sessions/{session_id}/ws")
async def connect_realtime(
    websocket: WebSocket,
    session_id: str,
    access_token: str | None = Query(default=None),
    guest_credential: str | None = Query(default=None),
):
    store: Store = websocket.app.state.store
    hub: Hub = websocket.app.state.hub
    await websocket.accept()

    user = store.user_for_access_token(access_token) if access_token else None
    try:
        participant = store.resolve_principal(session_id, user, guest_credential)
    except ApiError as exc:
        await websocket.send_json(envelope(session_id, _error(exc.code, exc.message)))
        await websocket.close(code=CLOSE_CODES.get(exc.status, CLOSE_FORBIDDEN))
        return

    conn = Connection(session_id=session_id, participant_id=participant.id, websocket=websocket)
    hub.register(conn)
    sender = asyncio.create_task(pump(conn))
    store.mark_seen(participant.id)
    hub.send(
        conn, {"type": "room_joined", "participantId": participant.id, "cursor": store.ensure_canvas(session_id).cursor}
    )
    try:
        while True:
            text = await websocket.receive_text()
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                hub.send(conn, _error("VALIDATION", "Messages must be valid JSON."))
                continue
            _handle(store, hub, conn, message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unregister(conn)
        sender.cancel()
        store.mark_seen(participant.id, left=True)
        hub.publish(session_id, {"type": "presence_leave", "participantId": participant.id})
