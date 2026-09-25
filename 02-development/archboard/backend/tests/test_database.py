"""Database behaviour: persistence, configuration, portability and concurrency."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, Table, insert, select, text

from app.config import Settings
from app.db import DEFAULT_DATABASE_URL, UTCDateTime, create_db_engine, create_schema, create_session_factory
from app.seed import DEMO_PASSWORD
from app.store import StoreContext

from .conftest import StoreProxy, bearer, create_link, create_session, join, sign_up
from .test_canvas import put, shape


def login(client: TestClient, email: str = "ada@example.com", password: str = DEMO_PASSWORD) -> dict[str, str]:
    return bearer(client.post("/v1/auth/login", json={"email": email, "password": password}).json()["accessToken"])


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def publish(self, session_id, payload, exclude=None):
        self.events.append((session_id, payload))

    def disconnect_participant(self, session_id, participant_id):
        self.events.append((session_id, {"type": "disconnect", "participantId": participant_id}))


def test_data_survives_a_restart(make_app):
    with TestClient(make_app("shared.db")) as client:
        headers = sign_up(client, StoreProxy(client.app.state.store_context))
        session = create_session(client, headers, prompt="Persist me")
        client.post(f"/v1/sessions/{session['id']}/start", headers=headers)
        link = create_link(client, headers, session["id"])
        guest = join(client, link["token"])
        pid = guest["participant"]["id"]
        store = StoreProxy(client.app.state.store_context)
        assert store.apply_client_operation(
            session["id"], pid, {"id": "op1", "actorId": pid, "changes": [put(shape("db", 1, actor=pid))]}
        ).ok

    # A new app on the same database file: tokens, sessions, participants and canvas are still there.
    with TestClient(make_app("shared.db")) as client:
        assert client.get("/v1/auth/me", headers=headers).status_code == 200
        [summary] = client.get("/v1/sessions", headers=headers).json()
        assert summary["prompt"] == "Persist me" and summary["state"] == "live"
        assert summary["participantNames"] == ["Linus"]
        room = client.get(f"/v1/sessions/{session['id']}/canvas", headers={"X-Guest-Credential": guest["credential"]})
        assert list(room.json()["canvas"]["elements"]) == ["db"] and room.json()["cursor"] == 1
        # The operation log still de-duplicates after a restart.
        store = StoreProxy(client.app.state.store_context)
        result = store.apply_client_operation(
            session["id"], pid, {"id": "op1", "actorId": pid, "changes": [put(shape("db", 1, actor=pid))]}
        )
        assert result.ok and result.duplicate and result.cursor == 1


def test_demo_data_is_seeded_only_into_an_empty_database(make_app):
    for _ in range(2):
        with TestClient(make_app("seeded.db", seed=True)) as client:
            sessions = client.get("/v1/sessions", headers=login(client)).json()
            assert len(sessions) == 3
            assert sum(s["title"].startswith("Example") for s in sessions) == 1


def test_database_url_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Settings().database_url == DEFAULT_DATABASE_URL == "sqlite:///./archboard.db"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pw@db.example.com/archboard")
    assert Settings().database_url == "postgresql+psycopg://user:pw@db.example.com/archboard"


def test_env_var_selects_the_database_file(tmp_path, monkeypatch):
    path = tmp_path / "from-env.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    from app.main import create_app

    with TestClient(create_app(Settings(seed=False))) as client:
        assert client.post("/v1/auth/magic-link", json={"email": "a@b.co"}).status_code == 200
    assert path.exists()


def test_sqlite_enforces_foreign_keys(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'fk.db'}")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_in_memory_sqlite_works_for_single_threaded_use():
    engine = create_db_engine("sqlite://")
    create_schema(engine)
    ctx = StoreContext(session_factory=create_session_factory(engine))
    with ctx.store() as store:
        store.create_user("mem@example.com")
    with ctx.store() as store:
        assert store.find_user_by_email("mem@example.com") is not None


def test_utc_datetimes_round_trip_as_aware_utc():
    engine = create_db_engine("sqlite://")
    table = Table("t", MetaData(), Column("at", UTCDateTime))
    table.metadata.create_all(engine)
    local = datetime(2026, 9, 1, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    with engine.begin() as conn:
        conn.execute(insert(table).values(at=local))
        stored = conn.execute(select(table.c.at)).scalar()
    assert stored == datetime(2026, 9, 1, 12, 0, tzinfo=UTC) and stored.tzinfo is UTC
    with pytest.raises(Exception, match="naive"), engine.begin() as conn:
        conn.execute(insert(table).values(at=datetime(2026, 9, 1, 12, 0)))


@pytest.fixture
def ctx(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'unit.db'}")
    create_schema(engine)
    sink = RecordingSink()
    context = StoreContext(session_factory=create_session_factory(engine), events=sink)
    context.sink = sink  # type: ignore[attr-defined]
    yield context
    engine.dispose()


def live_session(ctx: StoreContext) -> tuple[str, str]:
    with ctx.store() as store:
        owner = store.create_user("owner@example.com")
        session = store.insert_session(owner, title="T", state="live")
        return session.id, store.list_participants(session.id)[0].id


def test_last_writer_wins_is_enforced_by_the_database(ctx):
    sid, pid = live_session(ctx)

    def apply(op_id: str, clock: int, label: str):
        with ctx.store() as store:
            return store.apply_client_operation(
                sid, pid, {"id": op_id, "actorId": pid, "changes": [put(shape("n", clock, actor=pid, label=label))]}
            )

    assert apply("a", 5, "newer").ok
    assert apply("b", 3, "older").ok  # accepted, but loses
    with ctx.store() as store:
        assert store.canvas_elements(sid)["n"]["label"] == "newer"
        assert store.canvas_cursor(sid) == 2


def test_events_are_published_only_after_commit(ctx):
    sid, _ = live_session(ctx)
    ctx.sink.events.clear()
    with pytest.raises(RuntimeError), ctx.store() as store:
        store.publish(sid, {"type": "canvas_reset"})
        raise RuntimeError("boom")
    assert ctx.sink.events == []
    with ctx.store() as store:
        store.publish(sid, {"type": "canvas_reset"})
        assert ctx.sink.events == []  # not yet: still inside the transaction
    assert ctx.sink.events == [(sid, {"type": "canvas_reset"})]


def test_failed_requests_roll_back(client, store, owner):
    session = create_session(client, owner)
    # Archiving then failing inside one unit of work leaves the session untouched.
    user = store.find_user_by_email("ada@example.com")
    with pytest.raises(RuntimeError), client.app.state.store_context.store() as s:
        s.archive_session(user, session["id"])
        raise RuntimeError("boom")
    assert client.get(f"/v1/sessions/{session['id']}", headers=owner).json()["state"] == "draft"


def test_concurrent_operations_all_land(ctx):
    sid, pid = live_session(ctx)

    def apply(i: int):
        with ctx.store() as store:
            return store.apply_client_operation(
                sid, pid, {"id": f"op{i}", "actorId": pid, "changes": [put(shape(f"n{i}", 1, actor=pid))]}
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(apply, range(40)))
    assert all(r.ok for r in results)
    assert sorted(r.cursor for r in results) == list(range(1, 41))
    with ctx.store() as store:
        assert len(store.canvas_elements(sid)) == 40
        assert store.canvas_cursor(sid) == 40
