import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from responder.agent import run_agent
from responder.evidence import alert_endpoint, collect_evidence, write_json


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("responder")

REPO_DIR = Path(os.getenv("RESPONDER_REPO_DIR", Path(__file__).resolve().parents[2]))
INCIDENTS_DIR = Path(os.getenv("RESPONDER_INCIDENTS_DIR", Path(__file__).resolve().parents[1] / "incidents"))
AGENT_ENABLED = os.getenv("RESPONDER_AGENT", "on") != "off"
# Grafana re-sends a firing alert on every group change and repeat interval.
# Within this window, the same alert (name + endpoints) does not start a second agent.
COOLDOWN = timedelta(minutes=int(os.getenv("RESPONDER_COOLDOWN_MINUTES", "15")))

app = FastAPI(title="Order Tracker incident responder")
_agent_lock = threading.Lock()
_last_started: dict[str, datetime] = {}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "alert"


def is_test(alerts):
    return all(a.get("labels", {}).get("test") == "true" for a in alerts)


def new_incident_dir(alerts, now):
    name = alerts[0].get("labels", {}).get("alertname", "alert")
    base = INCIDENTS_DIR / f"{now:%Y%m%dT%H%M%SZ}-{slug(name)}"
    incident_dir, n = base, 1
    while incident_dir.exists():
        n += 1
        incident_dir = base.with_name(f"{base.name}-{n}")
    incident_dir.mkdir(parents=True)
    return incident_dir


def write_summary(incident_dir, payload, alerts, evidence):
    lines = [f"# Incident {incident_dir.name}", ""]
    lines += [f"- Received: {datetime.now(timezone.utc).isoformat()}",
              f"- Notification status: {payload.get('status', 'unknown')}",
              f"- Evidence window: {evidence['start']} to {evidence['end']}",
              f"- Endpoints: {', '.join(evidence['endpoints']) or 'not given in the alert'}"]
    if is_test(alerts):
        lines.append("- **Test notification** (label test=\"true\"): no incident to fix.")
    for i, alert in enumerate(alerts, 1):
        labels, annotations = alert.get("labels", {}), alert.get("annotations", {})
        lines += ["", f"## Alert {i}: {labels.get('alertname', 'unnamed')} ({alert.get('status', 'unknown')})", ""]
        lines.append(f"- Endpoint: {alert_endpoint(alert) or 'unknown'}")
        lines.append(f"- Time window: {annotations.get('time_window', 'unknown')}")
        lines.append(f"- Started: {alert.get('startsAt', 'unknown')}")
        for key in ("summary", "description"):
            if annotations.get(key):
                lines.append(f"- {key.capitalize()}: {annotations[key]}")
        for label, url in (("Dashboard", annotations.get("dashboard_url") or alert.get("dashboardURL")),
                           ("Panel", alert.get("panelURL")), ("Rule", alert.get("generatorURL"))):
            if url:
                lines.append(f"- {label}: {url}")
        lines.append(f"- Labels: `{json.dumps(labels)}`")

    errors = evidence.get("metrics", {}).get("server_errors_by_route_error_type", {}).get("result", [])
    lines += ["", "## 5xx responses in the window", ""]
    lines += [f"- {e['labels'].get('http_route')} {e['labels'].get('http_response_status_code')} "
              f"{e['labels'].get('error_type', '')}: {e['value']:g}" for e in errors if e["value"]] or ["- none recorded"]

    logs = evidence.get("logs", {}).get("entries", [])
    lines += ["", f"## Warning and error logs ({len(logs)}, newest first)", ""]
    for entry in logs[:10]:
        context = ", ".join(f"{k}={entry[k]}" for k in ("order_id", "trace_id") if k in entry)
        lines.append(f"- {entry['time']} {entry.get('level')}: {entry['message']} ({context})")
    stack = next((e["exception_stacktrace"] for e in logs if e.get("exception_stacktrace")), None)
    if stack:
        lines += ["", "Latest stack trace:", "", "```", stack.rstrip(), "```"]

    traces = evidence.get("traces", {}).get("traces", [])
    lines += ["", f"## Error traces ({len(traces)})", ""]
    for trace in traces:
        failing = [s for s in trace["spans"] if s["status"].get("code") in (2, "STATUS_CODE_ERROR")]
        names = ", ".join(f"{s['name']} ({s['status'].get('message', 'error')})" for s in failing) or "no error span"
        lines.append(f"- {trace['trace_id']}: {names}")

    if evidence["errors"]:
        lines += ["", "## Evidence that could not be collected", ""]
        lines += [f"- {name}: {error}" for name, error in evidence["errors"].items()]
    lines += ["", "Files: alert.json, metrics.json, logs.json, traces.json, traces/<trace id>.json", ""]
    (incident_dir / "summary.md").write_text("\n".join(lines))


def respond(payload, alerts, incident_dir, key):
    """Background job: save evidence, then start the agent if no other agent is running."""
    try:
        evidence = collect_evidence(alerts, incident_dir)
        write_summary(incident_dir, payload, alerts, evidence)
        logger.info("Saved evidence in %s", incident_dir)
        if not AGENT_ENABLED:
            return
        if not _agent_lock.acquire(blocking=False):
            (incident_dir / "agent-skipped.txt").write_text("Another agent was already running.\n")
            logger.info("Agent already running; %s saved without starting another", incident_dir.name)
            return
        try:
            logger.info("Starting agent for %s", incident_dir.name)
            returncode = run_agent(incident_dir, REPO_DIR, is_test(alerts))
            logger.info("Agent for %s finished with exit code %s", incident_dir.name, returncode)
        finally:
            _agent_lock.release()
    except Exception:
        _last_started.pop(key, None)
        logger.exception("Responding to %s failed", incident_dir.name)


@app.get("/healthz")
def health():
    return {"status": "ok", "agent_running": _agent_lock.locked()}


@app.post("/alerts", status_code=202)
async def receive_alerts(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Body must be JSON")
    if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list):
        raise HTTPException(422, "Expected a Grafana webhook with an `alerts` list")

    now = datetime.now(timezone.utc)
    firing = [a for a in payload["alerts"] if a.get("status", "firing") == "firing"]
    incident_dir = new_incident_dir(payload["alerts"] or [{}], now)
    write_json(incident_dir / "alert.json", payload)
    if not firing:
        logger.info("Saved %s; no firing alerts, so no agent", incident_dir.name)
        return {"incident": incident_dir.name, "agent": "not started: no firing alerts"}

    name = firing[0].get("labels", {}).get("alertname", "alert")
    key = json.dumps([name, sorted(filter(None, map(alert_endpoint, firing))), is_test(firing)])
    last = _last_started.get(key)
    if last and now - last < COOLDOWN and not is_test(firing):
        (incident_dir / "agent-skipped.txt").write_text(f"Same alert started an agent at {last.isoformat()}.\n")
        return {"incident": incident_dir.name, "agent": "not started: already handled recently"}
    _last_started[key] = now

    threading.Thread(target=respond, args=(payload, firing, incident_dir, key), daemon=True).start()
    agent = "starting" if AGENT_ENABLED else "disabled"
    return {"incident": incident_dir.name, "agent": agent}
