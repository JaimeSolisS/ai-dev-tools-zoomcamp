"""WebSocket fan-out.

`Hub` implements the store's `EventSink`: publishing puts an enveloped message on
each connection's queue, and a per-connection task writes the queue to the
socket, so messages to one connection are delivered in order.

Requests run in FastAPI's threadpool, so `publish` may be called from any
thread; it hands the work to the event loop with `call_soon_threadsafe`. Room
bookkeeping itself only ever runs on the event loop.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

PROTOCOL_VERSION = 1

# WebSocket close codes (4000-4999 are application-defined).
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404


def envelope(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "v": PROTOCOL_VERSION, "sessionId": session_id, "id": f"m_{uuid4()}"}


@dataclass
class Connection:
    session_id: str
    participant_id: str
    websocket: WebSocket
    id: str = field(default_factory=lambda: f"conn_{uuid4()}")
    # None is a sentinel meaning "close the socket after sending what came before".
    queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[str, Connection]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach to the server's event loop (called at startup)."""
        self.loop = loop

    def _on_loop(self, fn: Callable[..., None], *args: Any) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return  # no server running (e.g. scripts): nobody to notify
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            fn(*args)
        else:
            loop.call_soon_threadsafe(fn, *args)

    def register(self, conn: Connection) -> None:
        self.rooms.setdefault(conn.session_id, {})[conn.id] = conn

    def unregister(self, conn: Connection) -> None:
        room = self.rooms.get(conn.session_id)
        if room is None:
            return
        room.pop(conn.id, None)
        if not room:
            del self.rooms[conn.session_id]

    def connections(self, session_id: str) -> list[Connection]:
        return list(self.rooms.get(session_id, {}).values())

    def send(self, conn: Connection, payload: dict[str, Any]) -> None:
        conn.queue.put_nowait(envelope(conn.session_id, payload))

    # EventSink ---------------------------------------------------------------

    def publish(self, session_id: str, payload: dict[str, Any], exclude: str | None = None) -> None:
        self._on_loop(self._publish, session_id, payload, exclude)

    def disconnect_participant(self, session_id: str, participant_id: str) -> None:
        self._on_loop(self._disconnect, session_id, participant_id)

    def _publish(self, session_id: str, payload: dict[str, Any], exclude: str | None) -> None:
        for conn in self.connections(session_id):
            if conn.id != exclude:
                self.send(conn, payload)

    def _disconnect(self, session_id: str, participant_id: str) -> None:
        for conn in self.connections(session_id):
            if conn.participant_id == participant_id:
                conn.queue.put_nowait(None)


async def pump(conn: Connection) -> None:
    """Write queued messages to the socket until the close sentinel arrives."""
    while True:
        message = await conn.queue.get()
        if message is None:
            await conn.websocket.close(code=CLOSE_FORBIDDEN, reason="Removed from the interview")
            return
        await conn.websocket.send_json(message)
