"""Collect the metrics, logs, and traces around an alert into an incident directory."""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090")
LOKI_URL = os.getenv("LOKI_URL", "http://127.0.0.1:3100")
TEMPO_URL = os.getenv("TEMPO_URL", "http://127.0.0.1:3200")

SERVICE = "order-tracker"
REQUESTS = f'http_server_request_duration_seconds_count{{job="{SERVICE}"}}'
DEFAULT_WINDOW = timedelta(minutes=5)
# Extra time before the alert's window, so the first failing requests are included.
LOOKBACK_PADDING = timedelta(minutes=5)
MAX_LOGS = 100
MAX_TRACES = 5


def parse_duration(value, default=DEFAULT_WINDOW):
    match = re.fullmatch(r"(\d+)([smhd])", (value or "").strip())
    if not match:
        return default
    amount, unit = int(match[1]), match[2]
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{units[unit]: amount})


def parse_time(value):
    """Grafana sends RFC 3339 timestamps; the zero time means 'unset'."""
    if not value or value.startswith("0001-"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def alert_endpoint(alert):
    endpoint = alert.get("labels", {}).get("http_route") or alert.get("annotations", {}).get("endpoint")
    return endpoint if endpoint and endpoint != "<no value>" else None


def time_range(alerts, now):
    window = max((parse_duration(a.get("annotations", {}).get("time_window")) for a in alerts), default=DEFAULT_WINDOW)
    starts = [t for a in alerts if (t := parse_time(a.get("startsAt"))) and t <= now]
    start = min(starts, default=now) - window - LOOKBACK_PADDING
    return start, now


def prom_string(value):
    return json.dumps(value)  # a JSON string literal is a valid PromQL / TraceQL string


def collect_metrics(client, endpoints, start, end):
    # Backticks make a raw PromQL string, so the regex escapes survive.
    route = f", http_route=~`{'|'.join(re.escape(e) for e in endpoints)}`" if endpoints else ""
    selector = REQUESTS[:-1] + route + "}"
    seconds = max(int((end - start).total_seconds()), 60)
    queries = {
        "requests_by_route_status": f"sum by (http_route, http_response_status_code) (increase({selector}[{seconds}s]))",
        "server_errors_by_route_error_type": (
            f'sum by (http_route, http_response_status_code, error_type) '
            f'(increase({selector[:-1]}, http_response_status_code=~"5.."}}[{seconds}s]))'
        ),
        "request_totals": f"sum by (http_route, http_response_status_code) ({selector})",
    }
    results = {}
    for name, query in queries.items():
        response = client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query, "time": end.timestamp()})
        response.raise_for_status()
        results[name] = {
            "query": query,
            "result": [
                {"labels": r["metric"], "value": round(float(r["value"][1]), 2)}
                for r in response.json()["data"]["result"]
            ],
        }
    return results


def collect_logs(client, start, end):
    query = f'{{service_name="{SERVICE}"}} | severity_number >= 13'  # WARN and above
    response = client.get(
        f"{LOKI_URL}/loki/api/v1/query_range",
        params={
            "query": query,
            "start": int(start.timestamp() * 1e9),
            "end": int(end.timestamp() * 1e9),
            "limit": MAX_LOGS,
            "direction": "backward",
        },
    )
    response.raise_for_status()
    entries = []
    for stream in response.json()["data"]["result"]:
        labels = stream["stream"]
        for timestamp, line in stream["values"]:
            entries.append({
                "time": datetime.fromtimestamp(int(timestamp) / 1e9, timezone.utc).isoformat(),
                "level": labels.get("severity_text") or labels.get("detected_level"),
                "message": line,
                **{
                    key: labels[key]
                    for key in ("scope_name", "order_id", "trace_id", "span_id",
                                "exception_type", "exception_message", "exception_stacktrace")
                    if key in labels
                },
            })
    entries.sort(key=lambda e: e["time"], reverse=True)
    return {"query": query, "entries": entries}


def search_error_traces(client, endpoints, start, end):
    base = f'{{resource.service.name="{SERVICE}" && status=error}}'
    queries = [f"{{span.http.route={prom_string(e)}}} && {base}" for e in endpoints] or [base]
    trace_ids = []
    for query in queries:
        response = client.get(
            f"{TEMPO_URL}/api/search",
            params={"q": query, "start": int(start.timestamp()), "end": int(end.timestamp()), "limit": 20},
        )
        response.raise_for_status()
        trace_ids += [t["traceID"] for t in response.json().get("traces", [])]
    return queries, trace_ids


def attribute_value(value):
    return next(iter(value.values()), None) if value else None


def summarize_trace(trace):
    """Flatten Tempo's OTLP JSON into the spans an investigator reads."""
    spans = []
    for batch in trace.get("batches", trace.get("resourceSpans", [])):
        for scope in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
            for span in scope.get("spans", []):
                start_ns, end_ns = int(span.get("startTimeUnixNano", 0)), int(span.get("endTimeUnixNano", 0))
                spans.append({
                    "name": span.get("name"),
                    "span_id": span.get("spanId"),
                    "parent_span_id": span.get("parentSpanId") or None,
                    "status": span.get("status", {}),
                    "duration_ms": round((end_ns - start_ns) / 1e6, 2),
                    "attributes": {a["key"]: attribute_value(a.get("value")) for a in span.get("attributes", [])},
                    "events": [
                        {
                            "name": event.get("name"),
                            "attributes": {a["key"]: attribute_value(a.get("value")) for a in event.get("attributes", [])},
                        }
                        for event in span.get("events", [])
                    ],
                })
    return spans


def collect_traces(client, endpoints, start, end, log_trace_ids, traces_dir):
    queries, search_ids = search_error_traces(client, endpoints, start, end)
    # Error traces from the search first, then the ones referenced by error logs.
    trace_ids = list(dict.fromkeys(search_ids + log_trace_ids))[:MAX_TRACES]
    traces = []
    for trace_id in trace_ids:
        response = client.get(f"{TEMPO_URL}/api/traces/{trace_id}", headers={"Accept": "application/json"})
        if response.status_code == 404:
            continue
        response.raise_for_status()
        raw = response.json()
        traces_dir.mkdir(exist_ok=True)
        write_json(traces_dir / f"{trace_id}.json", raw)
        traces.append({"trace_id": trace_id, "spans": summarize_trace(raw)})
    return {"queries": queries, "traces": traces}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def collect_evidence(alerts, incident_dir: Path, client: httpx.Client | None = None, now=None):
    """Write metrics.json, logs.json, traces.json, and traces/<id>.json; return what was found.

    A backend that fails is recorded in the evidence instead of stopping collection.
    """
    now = now or datetime.now(timezone.utc)
    endpoints = sorted({e for a in alerts if (e := alert_endpoint(a))})
    start, end = time_range(alerts, now)
    evidence = {"endpoints": endpoints, "start": start.isoformat(), "end": end.isoformat(), "errors": {}}
    owns_client = client is None
    client = client or httpx.Client(timeout=10)
    try:
        for name, collect in (
            ("metrics", lambda: collect_metrics(client, endpoints, start, end)),
            ("logs", lambda: collect_logs(client, start, end)),
            ("traces", lambda: collect_traces(
                client, endpoints, start, end,
                [e["trace_id"] for e in evidence.get("logs", {}).get("entries", []) if e.get("trace_id")
                 and e.get("level") in ("ERROR", "error", "FATAL", "fatal")],
                incident_dir / "traces",
            )),
        ):
            try:
                evidence[name] = collect()
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                evidence["errors"][name] = f"{type(exc).__name__}: {exc}"
                evidence[name] = {}
            write_json(incident_dir / f"{name}.json", evidence[name] or {"error": evidence["errors"][name]})
    finally:
        if owns_client:
            client.close()
    return evidence
