# Order Tracker

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose setup. You add telemetry, alerts, and an incident responder in Homework 4.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000>. The API is at `/api/orders`, and the health check is at `/healthz`. Data is stored in a Docker volume and survives container recreation.

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

## Telemetry

The app sends OpenTelemetry traces, metrics, and logs over OTLP to an OpenTelemetry Collector, which forwards them to Prometheus (metrics), Loki (logs), and Tempo (traces). Grafana reads all three. `docker compose up --build -d --wait` starts the whole stack.

| Service | URL | Purpose |
| --- | --- | --- |
| Grafana | <http://127.0.0.1:3000> | Dashboards and Explore (no login) |
| Prometheus | <http://127.0.0.1:9090> | Metrics |
| Loki | <http://127.0.0.1:3100> | Logs API |
| Tempo | <http://127.0.0.1:3200> | Traces API |

Override ports with `GRAFANA_PORT`, `PROMETHEUS_PORT`, `LOKI_PORT`, and `TEMPO_PORT`. The Collector is only reachable inside the Compose network.

Grafana opens on the **Order Tracker** dashboard: request and error counts, requests and errors by route and status, raw request totals, error traces, and warning/error logs. In a log line's details, the `TraceID` link opens the trace in Tempo; from a span, "Logs for this span" goes back to Loki.

| Signal | Where | What to look for |
| --- | --- | --- |
| Metric | Prometheus | `http_server_request_duration_seconds_count` with `http_route` and `http_response_status_code` |
| Trace | Tempo | An `order lookup` span with `order.id`; crashes are marked as errors with the stack trace |
| Log | Loki, `{service_name="order-tracker"}` | `Order lookup succeeded` / `failed` / `crashed`, with `order_id` and `trace_id` |

FastAPI records the HTTP request span, the request metric, and unhandled-exception logs on its own. The order lookup route adds the `order lookup` span and its log lines. Metrics are exported every 10 seconds (`OTEL_METRIC_EXPORT_INTERVAL`) and Prometheus scrapes the Collector every 10 seconds, so allow about 20 seconds for a request to show up. Without `OTEL_EXPORTER_OTLP_ENDPOINT` (for example, when running the app outside Compose), the app prints telemetry to the console instead.

### Alerting

Grafana evaluates the **Order Tracker 5xx responses** rule every 10 seconds, with one alert instance per endpoint (`http_route`). It fires as soon as an endpoint has returned any 5xx in the last 5 minutes, then goes back to Normal once 5 minutes pass without one. Each alert carries `summary`, `description`, `endpoint`, `time_window`, and `dashboard_url` annotations, and is linked to the dashboard's error panel. If no 5xx has ever been recorded, the query returns 0, so the rule shows Normal instead of No data. Check its state under **Alerting → Alert rules** in Grafana.

Notifications go to the `incident-responder` webhook contact point at `http://host.docker.internal:8001/alerts`, which is the incident responder running on the host (see [Incident response](#incident-response)). The notification policy groups alerts by `alertname` and `http_route`, waits 10 seconds before the first notification, and also sends resolved notifications. If the responder isn't running, Grafana logs a failed delivery and retries on the next notification.

Configuration:

| Path | Contents |
| --- | --- |
| `app/telemetry.py` | Exporter setup |
| `observability/otel-collector/config.yaml` | OTLP receiver and the pipelines to each backend |
| `observability/prometheus/prometheus.yml` | Scrape config for the Collector |
| `observability/loki/config.yaml` | Loki single-node config with OTLP structured metadata |
| `observability/tempo/config.yaml` | Tempo single-node config |
| `observability/grafana/provisioning/` | Data sources, the dashboard provider, and alerting (`alerting/`: the 5xx rule, the responder webhook, and the notification policy) |
| `observability/grafana/dashboards/order-tracker.json` | The Order Tracker dashboard |

## Incident response

`incident-response/` contains a service that receives Grafana alerts at `POST /alerts` on port 8001. For each firing alert it saves the evidence (the alert, the affected endpoint, metrics, logs, traces, and a `summary.md`) to `incident-response/incidents/<incident>/`, then starts Claude Code in headless mode (`claude -p`) to find the root cause, fix and verify it, or escalate. The agent's answer is saved as `response.md` in the same directory.

It runs on the host, next to the Compose stack:

```bash
cd incident-response
uv run --frozen uvicorn responder.main:app --host 127.0.0.1 --port 8001
```

See [incident-response/README.md](incident-response/README.md) for the test alert, the evidence files, the agent's permissions, and configuration.

## Notes

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.
