"""The backend matches ../openapi.yaml: same operations, and responses validate against its schemas."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from app.config import Settings
from app.main import ROUTER_MODULES, create_app
from app.seed import DEMO_CANDIDATE_TOKEN, DEMO_PASSWORD

from .test_canvas import put, shape
from .test_realtime import next_of

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"
SPEC: dict[str, Any] = yaml.safe_load(SPEC_PATH.read_text())
REGISTRY = Registry().with_resource("urn:spec", Resource.from_contents(SPEC, default_specification=DRAFT202012))
METHODS = {"get", "post", "patch", "put", "delete"}


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def spec_operations() -> set[tuple[str, str]]:
    return {(m.upper(), _normalize(p)) for p, item in SPEC["paths"].items() for m in item if m in METHODS}


def app_operations() -> set[tuple[str, str]]:
    ops = set()
    for module in ROUTER_MODULES:
        for route in module.router.routes:
            if isinstance(route, APIRoute):
                ops |= {(m, _normalize(route.path)) for m in route.methods}
            elif isinstance(route, APIWebSocketRoute):
                ops.add(("GET", _normalize(route.path)))
    return ops


def test_every_spec_operation_is_implemented_and_nothing_else():
    assert spec_operations() == app_operations()


def validator_for(ref: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"urn:spec{ref}"}, registry=REGISTRY)


def response_schema(method: str, template: str, status: int) -> dict | None:
    operation = SPEC["paths"][template][method.lower()]
    response = operation["responses"].get(str(status))
    assert response is not None, f"{method} {template} does not document status {status}"
    if "$ref" in response:
        response = SPEC["components"]["responses"][response["$ref"].rsplit("/", 1)[1]]
    content = response.get("content")
    return content["application/json"]["schema"] if content else None


class SpecClient:
    """Wraps TestClient: every call names its spec path and is validated against the documented response."""

    def __init__(self, client: TestClient):
        self.client = client
        self.checked: set[tuple[str, str, int]] = set()

    def call(self, method: str, template: str, params: dict[str, str] | None = None, **kwargs):
        path = template
        for name, value in (params or {}).items():
            path = path.replace("{" + name + "}", value)
        response = self.client.request(method, path, **kwargs)
        schema = response_schema(method, template, response.status_code)
        if schema is None:
            assert not response.content, f"{method} {template} should have no body"
        else:
            errors = list(Draft202012Validator(schema, registry=REGISTRY).iter_errors(response.json()))
            if "$ref" in schema:
                errors = list(validator_for(schema["$ref"].removeprefix("urn:spec")).iter_errors(response.json()))
            assert not errors, (
                f"{method} {template} {response.status_code}: {errors[0].message} at {list(errors[0].path)}"
            )
        self.checked.add((method, template, response.status_code))
        return response


def _fix_refs(node: Any) -> Any:
    """Point local $refs at the registered spec resource."""
    if isinstance(node, dict):
        return {k: (f"urn:spec{v}" if k == "$ref" and v.startswith("#") else _fix_refs(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_fix_refs(v) for v in node]
    return node


# Rewrite refs once so inline schemas resolve through the registry.
for _item in SPEC["paths"].values():
    for _key in list(_item):
        _item[_key] = _fix_refs(_item[_key])
for _name, _response in SPEC["components"]["responses"].items():
    SPEC["components"]["responses"][_name] = _fix_refs(_response)


@pytest.fixture
def api():
    with TestClient(create_app(Settings(seed=True, dev_mode=True))) as client:
        yield SpecClient(client)


def test_responses_match_the_spec(api: SpecClient):
    call = api.call
    # auth
    call("GET", "/v1/auth/me")
    call("POST", "/v1/auth/login", json={"email": "ada@example.com", "password": "wrong"})
    call("POST", "/v1/auth/magic-link", json={"email": "nope"})
    dev_token = call("POST", "/v1/auth/magic-link", json={"email": "new@example.com"}).json()["devToken"]
    call("POST", "/v1/auth/magic-link/verify", json={"token": dev_token})
    call("POST", "/v1/auth/magic-link/verify", json={"token": dev_token})
    token = call("POST", "/v1/auth/login", json={"email": "ada@example.com", "password": DEMO_PASSWORD}).json()[
        "accessToken"
    ]
    ada = {"Authorization": f"Bearer {token}"}
    call("GET", "/v1/auth/me", headers=ada)

    # sessions
    sessions = call("GET", "/v1/sessions", headers=ada).json()
    assert any(s["activeGuestLink"] for s in sessions)
    call("POST", "/v1/sessions", json={"title": ""}, headers=ada)
    sid = call("POST", "/v1/sessions", json={"title": "Contract", "durationMinutes": 30}, headers=ada).json()["id"]
    p = {"sessionId": sid}
    call("GET", "/v1/sessions/{sessionId}", p, headers=ada)
    call("GET", "/v1/sessions/{sessionId}", {"sessionId": "missing"}, headers=ada)
    call("PATCH", "/v1/sessions/{sessionId}", p, json={"prompt": "P"}, headers=ada)
    call("POST", "/v1/sessions/{sessionId}/reopen", p, headers=ada)
    call("POST", "/v1/sessions/{sessionId}/start", p, headers=ada)

    # links + join
    call("GET", "/v1/sessions/{sessionId}/guest-links", p, headers=ada)
    created = call("POST", "/v1/sessions/{sessionId}/guest-links", p, json={"maxUses": 5}, headers=ada).json()
    call("POST", "/v1/sessions/{sessionId}/guest-links", p, json={"maxUses": 0}, headers=ada)
    t = {"token": created["token"]}
    call("GET", "/v1/join/{token}", t)
    call("GET", "/v1/join/{token}", {"token": "bogus"})
    call("POST", "/v1/join/{token}", t, json={"displayName": ""})
    joined = call("POST", "/v1/join/{token}", t, json={"displayName": "Linus"}).json()
    cand = {"X-Guest-Credential": joined["credential"]}
    call("GET", "/v1/sessions/{sessionId}/participants", p, headers=cand)
    call("GET", "/v1/sessions/{sessionId}/participants", p)

    # canvas
    room = call("GET", "/v1/sessions/{sessionId}/canvas", p, headers=cand).json()
    call("GET", "/v1/sessions/{sessionId}/canvas", p, headers={"X-Guest-Credential": "forged"})

    # realtime: every server message validates against ServerMessage
    server_message = validator_for("#/components/schemas/ServerMessage")
    creds = f"guest_credential={joined['credential']}"
    with api.client.websocket_connect(f"/v1/sessions/{sid}/ws?{creds}") as ws:
        messages = [ws.receive_json()]
        me = room["me"]["id"]
        ws.send_json(
            {"type": "document_update", "op": {"id": "o1", "actorId": me, "changes": [put(shape("n", 1, actor=me))]}}
        )
        messages.append(next_of(ws, "document_ack"))
        ws.send_json({"type": "document_update", "op": {"id": "o2", "actorId": "x", "changes": []}})
        messages.append(next_of(ws, "error"))
        call("PATCH", "/v1/sessions/{sessionId}", p, json={"candidateEditingEnabled": False}, headers=ada)
        messages.append(next_of(ws, "session_updated"))
        call("POST", "/v1/sessions/{sessionId}/canvas/clear", p, headers=ada)
        messages.append(next_of(ws, "canvas_reset"))
        ws.send_json({"type": "ping"})
        messages.append(next_of(ws, "pong"))
        for message in messages:
            errors = list(server_message.iter_errors(message))
            assert not errors, f"{message['type']}: {errors[0].message}"

    snapshots = call("GET", "/v1/sessions/{sessionId}/canvas/snapshots", p, headers=ada).json()
    call(
        "POST",
        "/v1/sessions/{sessionId}/canvas/snapshots/{snapshotId}/restore",
        {**p, "snapshotId": snapshots[0]["id"]},
        headers=ada,
    )
    call(
        "POST",
        "/v1/sessions/{sessionId}/canvas/snapshots/{snapshotId}/restore",
        {**p, "snapshotId": "nope"},
        headers=ada,
    )

    # participants + links cleanup
    call(
        "DELETE",
        "/v1/sessions/{sessionId}/participants/{participantId}",
        {**p, "participantId": joined["participant"]["id"]},
        headers=ada,
    )
    call("GET", "/v1/sessions/{sessionId}/canvas", p, headers=cand)
    call("DELETE", "/v1/sessions/{sessionId}/guest-links/{linkId}", {**p, "linkId": created["link"]["id"]}, headers=ada)
    call("GET", "/v1/join/{token}", t)

    # lifecycle
    call("POST", "/v1/sessions/{sessionId}/duplicate", p, headers=ada)
    call("POST", "/v1/sessions/{sessionId}/end", p, headers=ada)
    call("POST", "/v1/sessions/{sessionId}/end", p, headers=ada)
    call("POST", "/v1/sessions/{sessionId}/canvas/clear", p, headers=ada)
    call("POST", "/v1/sessions/{sessionId}/guest-links", p, headers=ada)
    call("POST", "/v1/sessions/{sessionId}/archive", p, headers=ada)
    call("GET", "/v1/join/{token}", {"token": DEMO_CANDIDATE_TOKEN})
    call("POST", "/v1/auth/logout", headers=ada)

    # Every HTTP operation in the spec was exercised at least once.
    exercised = {(m, _normalize(tpl)) for m, tpl, _ in api.checked}
    http_ops = {op for op in spec_operations() if not op[1].endswith("/ws")}
    assert http_ops <= exercised, sorted(http_ops - exercised)
