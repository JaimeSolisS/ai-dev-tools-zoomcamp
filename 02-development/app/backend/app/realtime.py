"""WebSocket fan-out.

`Hub` implements the store's `EventSink`: publishing puts an enveloped message on
each connection's queue (synchronously), and a per-connection task writes the
queue to the socket. Messages to one connection are therefore delivered in order.
"""

import asyncio
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
        for conn in self.connections(session_id):
            if conn.id != exclude:
                self.send(conn, payload)

    def disconnect_participant(self, session_id: str, participant_id: str) -> None:
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
