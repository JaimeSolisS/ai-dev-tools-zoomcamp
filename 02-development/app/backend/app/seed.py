"""Demo data so the frontend has something to show.

Users (password for both: `password123`):

* ada@example.com   — owns an ended example, a live interview and a draft
* grace@example.com — owns one draft

The live "Design a chat app" interview has an active candidate link with the fixed
token `DEMO_CANDIDATE_TOKEN`, so a candidate can join at
`http://localhost:5173/join/demo-candidate-link-for-the-chat-app-interview`.
The token is intentionally predictable: it is only for local demos.

New users created later (e.g. through a magic link) get their own copy of the
example session, as described in openapi.yaml.
"""

from datetime import timedelta
from typing import Any
from uuid import uuid4

from .models import CreateGuestLinkInput, InterviewSession
from .store import CanvasRecord, Store, UserRecord

DEMO_PASSWORD = "password123"
DEMO_CANDIDATE_TOKEN = "demo-candidate-link-for-the-chat-app-interview"

# (width, height) per component type, matching frontend/src/canvas/catalog.ts
_SIZES: dict[str, tuple[int, int]] = {
    "browser": (130, 72), "mobile": (130, 72), "load-balancer": (150, 72), "api-gateway": (150, 72),
    "server": (150, 72), "worker": (150, 72), "cache": (150, 72), "sql-db": (130, 100),
    "nosql-db": (130, 100), "queue": (170, 64), "stream": (170, 64), "sticky": (160, 140),
    "boundary": (360, 240), "cdn": (150, 72), "object-storage": (150, 72),
}  # fmt: skip


class _Diagram:
    """Builds canvas element dicts in the same JSON shape the frontend writes."""

    def __init__(self, created_at: str):
        self.elements: dict[str, dict[str, Any]] = {}
        self.z = 0
        self.meta = {
            "version": {"clock": 1, "actor": "seed"},
            "createdBy": "seed",
            "createdAt": created_at,
            "updatedBy": "seed",
            "groupId": None,
        }

    def _add(self, element: dict[str, Any]) -> dict[str, Any]:
        self.elements[element["id"]] = element
        return element

    def shape(self, component: str, x: float, y: float, label: str, **extra: Any) -> dict[str, Any]:
        self.z += 1
        w, h = _SIZES.get(component, (150, 72))
        return self._add(
            {
                "id": f"el_{uuid4()}",
                "kind": "shape",
                "componentType": component,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "label": label,
                "z": self.z,
                **self.meta,
                **extra,
            }
        )

    def link(self, a: dict[str, Any], b: dict[str, Any], label: str = "", dashed: bool = False) -> None:
        self.z += 1
        self._add(
            {
                "id": f"el_{uuid4()}",
                "kind": "connector",
                "from": {"elementId": a["id"], "anchor": "auto", "x": a["x"], "y": a["y"]},
                "to": {"elementId": b["id"], "anchor": "auto", "x": b["x"], "y": b["y"]},
                "routing": "straight",
                "arrowStart": False,
                "arrowEnd": True,
                "label": label,
                "dashed": dashed,
                "color": "#334155",
                "width": 2,
                "z": self.z,
                **self.meta,
            }
        )


def _put_canvas(store: Store, session: InterviewSession, elements: dict[str, dict[str, Any]]) -> None:
    store.canvases[session.id] = CanvasRecord(
        session_id=session.id, elements=elements, cursor=0, updated_at=session.updated_at
    )


def create_example_session(store: Store, owner: UserRecord) -> InterviewSession:
    """An ended "URL shortener" interview with a finished diagram."""
    now = store.now()
    started = now - timedelta(minutes=42)
    session = store.insert_session(
        owner,
        title="Example: Design a URL shortener",
        prompt=(
            "Design a service like bit.ly.\n\n"
            "• 100M new URLs per month, 10:1 read/write ratio\n"
            "• Short links should redirect in < 50 ms (p95)\n"
            "• Collect click analytics\n\n"
            "Start with the API, then the data model, then scale it."
        ),
        state="ended",
        duration_minutes=45,
        started_at=started,
        ended_at=now,
        created_at=started,
    )
    d = _Diagram(started.isoformat())
    d.shape("boundary", 250, -30, "Region us-east-1", w=640, h=420, z=-10)
    client = d.shape("browser", 0, 120, "Browser")
    lb = d.shape("load-balancer", 290, 120, "Load balancer")
    api = d.shape("server", 520, 120, "API servers")
    cache = d.shape("cache", 740, 20, "Redis cache")
    db = d.shape("sql-db", 750, 200, "URL store")
    queue = d.shape("queue", 480, 290, "Click events")
    worker = d.shape("worker", 280, 290, "Analytics worker")
    d.shape("sticky", 0, 300, "Base62 IDs from a counter service; 7 chars ≈ 3.5T URLs", fill="#fef08a")
    d.link(client, lb, "HTTPS")
    d.link(lb, api)
    d.link(api, cache, "read")
    d.link(api, db, "read/write")
    d.link(api, queue, "events", dashed=True)
    d.link(queue, worker)
    _put_canvas(store, session, d.elements)
    store.save_snapshot(session.id, "final")
    return session


def seed(store: Store) -> None:
    """Load demo users and sessions, and give future users an example session."""
    ada = store.create_user("ada@example.com", "Ada Lovelace", DEMO_PASSWORD)
    grace = store.create_user("grace@example.com", "Grace Hopper", DEMO_PASSWORD)

    create_example_session(store, ada)

    # A live interview with a candidate already in the room.
    now = store.now()
    chat = store.insert_session(
        ada,
        title="Design a chat app",
        prompt="1:1 and group chat for 50M daily active users.\n\n• Message delivery < 200 ms\n• Offline sync\n• Read receipts",
        state="live",
        duration_minutes=60,
        started_at=now - timedelta(minutes=12),
        created_at=now - timedelta(hours=1),
    )
    d = _Diagram((now - timedelta(minutes=10)).isoformat())
    mobile = d.shape("mobile", 0, 100, "Mobile app")
    gateway = d.shape("api-gateway", 260, 100, "WebSocket gateway")
    chat_svc = d.shape("server", 520, 100, "Chat service")
    store_db = d.shape("nosql-db", 780, 90, "Messages (Cassandra)")
    d.link(mobile, gateway, "WSS")
    d.link(gateway, chat_svc)
    d.link(chat_svc, store_db, "write")
    d.shape("sticky", 260, 260, "How do we fan out to group members?", fill="#bfdbfe")
    _put_canvas(store, chat, d.elements)
    store.create_link(ada, chat.id, CreateGuestLinkInput(role_granted="candidate"), token=DEMO_CANDIDATE_TOKEN)
    store.resolve_principal(chat.id, ada, None)  # creates Ada's owner participant
    store.add_participant(chat.id, None, "Linus Torvalds", "candidate", credential_hash=None)

    limiter = store.insert_session(
        ada,
        title="Design a rate limiter",
        prompt="Distributed rate limiting for a public API (1M requests/second).",
        duration_minutes=45,
        scheduled_at=now + timedelta(days=1),
    )
    store.ensure_canvas(limiter.id)

    blank = store.insert_session(grace, title="Design a news feed", prompt="Ranked feed for a social network.")
    store.ensure_canvas(blank.id)

    store.on_user_created = create_example_session
