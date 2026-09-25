"""WS /v1/sessions/{sessionId}/ws — the collaboration channel (see openapi.yaml `connectRealtime`).

Database work for each message runs in the threadpool in its own transaction;
the socket itself is handled on the event loop.
"""

import asyncio
import json
import math
import time
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from ..errors import ApiError
from ..models import Participant
from ..realtime import (
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    CLOSE_UNAUTHENTICATED,
    Connection,
    Hub,
    envelope,
    pump,
)
from ..store import OperationResult, StoreContext

router = APIRouter(tags=["realtime"])

MAX_SELECTION = 500
CLOSE_CODES = {401: CLOSE_UNAUTHENTICATED, 404: CLOSE_NOT_FOUND}
LAST_SEEN_INTERVAL_SECONDS = 10


def _error(code: str, message: str, op_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "error", "code": code, "message": message}
    if op_id is not None:
        payload["opId"] = op_id
    return payload


def _clean_presence(raw: Any, participant: Participant) -> dict[str, Any] | None:
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


class _Session:
    """State of one open socket."""

    def __init__(self, ctx: StoreContext, hub: Hub, conn: Connection, participant: Participant):
        self.ctx = ctx
        self.hub = hub
        self.conn = conn
        self.participant = participant
        self.last_seen_write = time.monotonic()

    def _mark_seen(self, *, left: bool = False) -> None:
        with self.ctx.store() as store:
            store.mark_seen(self.participant.id, left=left)

    def _apply(self, op: Any) -> OperationResult:
        with self.ctx.store() as store:
            # Authorization is re-checked for every operation inside the store.
            return store.apply_client_operation(self.conn.session_id, self.participant.id, op, self.conn.id)

    async def handle(self, message: Any) -> None:
        hub, conn = self.hub, self.conn
        if not isinstance(message, dict):
            hub.send(conn, _error("VALIDATION", "Messages must be JSON objects."))
            return
        kind = message.get("type")
        if kind == "ping":
            hub.send(conn, {"type": "pong"})
        elif kind == "presence_update":
            presence = _clean_presence(message.get("presence"), self.participant)
            if presence is None:
                hub.send(conn, _error("VALIDATION", "Invalid presence update."))
                return
            hub.publish(conn.session_id, {"type": "presence_update", "presence": presence}, exclude=conn.id)
            if time.monotonic() - self.last_seen_write >= LAST_SEEN_INTERVAL_SECONDS:
                self.last_seen_write = time.monotonic()
                await run_in_threadpool(self._mark_seen)
        elif kind == "document_update":
            op = message.get("op")
            op_id = op.get("id") if isinstance(op, dict) and isinstance(op.get("id"), str) else None
            result = await run_in_threadpool(self._apply, op)
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
    ctx: StoreContext = websocket.app.state.store_context
    hub: Hub = websocket.app.state.hub
    await websocket.accept()

    def resolve() -> Participant:
        with ctx.store() as store:
            user = store.user_for_access_token(access_token) if access_token else None
            return store.resolve_principal(session_id, user, guest_credential)

    try:
        participant = await run_in_threadpool(resolve)
    except ApiError as exc:
        await websocket.send_json(envelope(session_id, _error(exc.code, exc.message)))
        await websocket.close(code=CLOSE_CODES.get(exc.status, CLOSE_FORBIDDEN))
        return

    conn = Connection(session_id=session_id, participant_id=participant.id, websocket=websocket)
    # Register before reading the cursor, so no update can fall between the two.
    hub.register(conn)
    sender = asyncio.create_task(pump(conn))
    state = _Session(ctx, hub, conn, participant)

    def cursor() -> int:
        with ctx.store() as store:
            store.mark_seen(participant.id)
            return store.canvas_cursor(session_id)

    try:
        hub.send(
            conn, {"type": "room_joined", "participantId": participant.id, "cursor": await run_in_threadpool(cursor)}
        )
        while True:
            text = await websocket.receive_text()
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                hub.send(conn, _error("VALIDATION", "Messages must be valid JSON."))
                continue
            await state.handle(message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unregister(conn)
        sender.cancel()
        hub.publish(session_id, {"type": "presence_leave", "participantId": participant.id})
        await run_in_threadpool(state._mark_seen, left=True)
