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

The app emits OpenTelemetry traces, metrics, and logs to the console. Inspect them with:

```bash
docker compose logs app
```

| Signal | What to look for |
| --- | --- |
| Metric | `http.server.request.duration` (count and latency) with `http.route` and `http.response.status_code` |
| Trace | An `order lookup` span with `order.id`; crashes are marked as errors with the stack trace |
| Log | `Order lookup succeeded` / `failed` / `crashed`, with `order.id` and the trace ID |

FastAPI records the HTTP request span, the request metric, and unhandled-exception logs on its own. The order lookup route adds the `order lookup` span and its log lines. Metrics are printed every 10 seconds (`OTEL_METRIC_EXPORT_INTERVAL` in `compose.yaml`). Spans and logs are sent in batches, so they can take a few seconds to show up. Exporter setup is in `app/telemetry.py`.

## Notes

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.
