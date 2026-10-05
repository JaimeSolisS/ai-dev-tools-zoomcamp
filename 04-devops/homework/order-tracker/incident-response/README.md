# Incident responder

Receives Grafana alerts for Order Tracker at `POST /alerts` on port 8001, saves the evidence needed to understand the problem, and starts Claude Code in headless mode to investigate.

It runs on the host, not in Docker, because the agent needs the repository, the `claude` CLI, and `docker compose` to rebuild the app.

## Run it

Start the Order Tracker stack first (`docker compose up --build -d --wait` in the repository root), then:

```bash
cd incident-response
uv run --frozen uvicorn responder.main:app --host 127.0.0.1 --port 8001
```

Grafana sends its alerts here automatically through the `incident-responder` webhook contact point (`observability/grafana/provisioning/alerting/responder-webhook.yaml`). From inside Docker it reaches the host as `host.docker.internal`.

Send a test alert:

```bash
curl -X POST http://localhost:8001/alerts \
  -H 'Content-Type: application/json' \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"ResponderTest","test":"true"},"annotations":{"summary":"Test notification; no incident to fix"}}]}'
```

The service replies `202` with the incident name right away, and does the work in the background. The agent's final answer is written to `incidents/<incident>/response.md`. Follow its progress with `tail -f incidents/<incident>/agent.jsonl`.

Run the tests with `uv run --frozen pytest -q`.

## What happens on an alert

1. The webhook is saved to `incidents/<UTC time>-<alert name>/alert.json`.
2. For firing alerts, the service collects evidence from the endpoint in the alert (`http_route` label or `endpoint` annotation), over the alert's `time_window` plus 5 minutes before it:

   | File | Source | Contents |
   | --- | --- | --- |
   | `metrics.json` | Prometheus | Requests and 5xx responses by route, status, and `error_type` |
   | `logs.json` | Loki | WARN and above, with `order_id`, `trace_id`, and stack traces |
   | `traces.json`, `traces/<id>.json` | Tempo | Error traces for the endpoint, and traces referenced by error logs (up to 5) |
   | `summary.md` | | Readable overview: alert, endpoint, window, dashboard link, errors, latest stack trace |

   If a backend cannot be reached, the error is recorded and collection continues.
3. Claude Code starts with `claude -p` in the repository root. Its prompt (`prompt.md`) points it at the evidence and asks it to find the root cause, add a regression test, fix the code, rebuild the app, verify the failing request, and write `report.md`. If it cannot fix the problem safely, it escalates in `report.md` instead. Test alerts (label `test="true"`) only ask for a confirmation.

   The agent runs with `acceptEdits` and an allowlist of commands (tests, `docker compose up/ps/logs`, `curl`, read-only `git`). It does not load MCP servers and does not commit or push. The output goes to `agent.jsonl` (stream-json), `agent.stderr.log`, and `response.md`.

Only one agent runs at a time. Resolved notifications are saved but do not start an agent. Grafana re-sends firing alerts, so the same alert (name and endpoints) does not start a second agent within 15 minutes; those repeats are still saved, with an `agent-skipped.txt` note.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROMETHEUS_URL` | `http://127.0.0.1:9090` | Metrics |
| `LOKI_URL` | `http://127.0.0.1:3100` | Logs |
| `TEMPO_URL` | `http://127.0.0.1:3200` | Traces |
| `RESPONDER_AGENT` | `on` | `off` saves evidence without starting the agent |
| `RESPONDER_AGENT_COMMAND` | `claude -p ...` | Replace the agent command; the prompt is sent on stdin |
| `RESPONDER_AGENT_TIMEOUT` | `1800` | Seconds before the agent is stopped |
| `RESPONDER_COOLDOWN_MINUTES` | `15` | Repeat window for the same alert |
| `RESPONDER_REPO_DIR` | repository root | Where the agent runs |
| `RESPONDER_INCIDENTS_DIR` | `incidents/` | Where evidence is saved |
