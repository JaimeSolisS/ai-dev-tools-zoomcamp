import json
import sys
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from responder import evidence, main


NOW = datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc)
ALERT = {
    "status": "firing",
    "labels": {"alertname": "Order Tracker 5xx responses", "http_route": "/api/orders/{order_id}"},
    "annotations": {"summary": "/api/orders/{order_id} returned 1 5xx", "time_window": "5m",
                    "dashboard_url": "http://localhost:3000/d/order-tracker"},
    "startsAt": "2026-10-05T02:58:00Z",
}
STACK = "Traceback ...\nValueError: day is out of range for month\n"


def backends(request):
    if request.url.path == "/api/v1/query":
        return httpx.Response(200, json={"data": {"result": [{
            "metric": {"http_route": "/api/orders/{order_id}", "http_response_status_code": "500", "error_type": "ValueError"},
            "value": [0, "1"],
        }]}})
    if request.url.path == "/loki/api/v1/query_range":
        return httpx.Response(200, json={"data": {"result": [{
            "stream": {"severity_text": "ERROR", "order_id": "express-1002", "trace_id": "abc", "exception_stacktrace": STACK},
            "values": [["1791168000000000000", "Order lookup crashed: ValueError"]],
        }]}})
    if request.url.path == "/api/search":
        return httpx.Response(200, json={"traces": [{"traceID": "abc"}]})
    if request.url.path == "/api/traces/abc":
        return httpx.Response(200, json={"batches": [{"scopeSpans": [{"spans": [{
            "name": "order lookup", "spanId": "s1", "startTimeUnixNano": "0", "endTimeUnixNano": "1000000",
            "status": {"code": 2, "message": "ValueError"},
            "attributes": [{"key": "order.id", "value": {"stringValue": "express-1002"}}],
        }]}]}]})
    return httpx.Response(404)


@pytest.fixture
def incidents(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "INCIDENTS_DIR", tmp_path / "incidents")
    monkeypatch.setattr(main, "REPO_DIR", tmp_path)
    main._last_started.clear()
    return tmp_path / "incidents"


def test_collect_evidence_filters_by_endpoint_and_saves_files(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url)
        return backends(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        found = evidence.collect_evidence([ALERT], tmp_path, client, now=NOW)

    assert found["endpoints"] == ["/api/orders/{order_id}"]
    assert found["start"] == "2026-10-05T02:48:00+00:00"  # startsAt - 5m window - 5m padding
    assert not found["errors"]
    prom_query = next(u.params["query"] for u in seen if u.path == "/api/v1/query")
    assert 'http_route=~`/api/orders/\\{order_id\\}`' in prom_query
    tempo_query = next(u.params["q"] for u in seen if u.path == "/api/search")
    assert 'span.http.route="/api/orders/{order_id}"' in tempo_query
    assert json.loads((tmp_path / "logs.json").read_text())["entries"][0]["order_id"] == "express-1002"
    trace = json.loads((tmp_path / "traces.json").read_text())["traces"][0]
    assert trace["spans"][0]["attributes"]["order.id"] == "express-1002"
    assert (tmp_path / "traces" / "abc.json").exists()


def test_unreachable_backend_is_recorded_not_fatal(tmp_path):
    def handler(request):
        raise httpx.ConnectError("refused")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        found = evidence.collect_evidence([ALERT], tmp_path, client, now=NOW)

    assert set(found["errors"]) == {"metrics", "logs", "traces"}
    assert "refused" in json.loads((tmp_path / "logs.json").read_text())["error"]


def test_post_alerts_saves_payload_and_starts_response(incidents, monkeypatch):
    started = []
    monkeypatch.setattr(main, "respond", lambda *args: started.append(args))

    response = TestClient(main.app).post("/alerts", json={"status": "firing", "alerts": [ALERT]})

    assert response.status_code == 202
    incident_dir = incidents / response.json()["incident"]
    assert json.loads((incident_dir / "alert.json").read_text())["alerts"][0] == ALERT
    assert len(started) == 1


def test_resolved_alerts_and_repeats_do_not_start_agent(incidents, monkeypatch):
    started = []
    monkeypatch.setattr(main, "respond", lambda *args: started.append(args))
    client = TestClient(main.app)

    resolved = client.post("/alerts", json={"alerts": [{**ALERT, "status": "resolved"}]})
    client.post("/alerts", json={"alerts": [ALERT]})
    repeat = client.post("/alerts", json={"alerts": [ALERT]})

    assert resolved.json()["agent"].startswith("not started")
    assert repeat.json()["agent"].startswith("not started")
    assert len(started) == 1
    assert len(list(incidents.iterdir())) == 3


def test_rejects_payload_without_alerts(incidents):
    assert TestClient(main.app).post("/alerts", json={"status": "firing"}).status_code == 422


def test_respond_writes_summary_and_runs_agent_headless(incidents, monkeypatch):
    fake_agent = (
        "import json, sys; prompt = sys.stdin.read(); "
        "print(json.dumps({'type': 'result', 'result': 'Got it.\\nRESULT: no action needed'}))"
    )
    monkeypatch.setenv("RESPONDER_AGENT_COMMAND", f"{sys.executable} -c \"{fake_agent}\"")
    monkeypatch.setattr(main, "collect_evidence",
                        lambda alerts, d: evidence.collect_evidence(
                            alerts, d, httpx.Client(transport=httpx.MockTransport(backends)), now=NOW))
    test_alert = {"status": "firing", "labels": {"alertname": "ResponderTest", "test": "true"},
                  "annotations": {"summary": "Test notification; no incident to fix"}}
    incident_dir = main.new_incident_dir([test_alert], NOW)

    main.respond({"alerts": [test_alert]}, [test_alert], incident_dir, "key")

    summary = (incident_dir / "summary.md").read_text()
    assert "Test notification" in summary
    assert "ValueError: day is out of range for month" in summary
    assert 'test="true"' in (incident_dir / "prompt.md").read_text()
    assert (incident_dir / "response.md").read_text().strip().endswith("RESULT: no action needed")
