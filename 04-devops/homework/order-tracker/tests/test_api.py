import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "orders.db")
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_and_seeded_orders(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    orders = client.get("/api/orders").json()
    assert len(orders) == 3
    assert {order["priority"] for order in orders} == {"standard", "express"}


def test_create_and_update_order(client):
    response = client.post(
        "/api/orders",
        json={"customer": "Taylor", "item": "Mug", "priority": "standard"},
    )
    assert response.status_code == 201
    order_id = response.json()["id"]
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "received"
    updated = client.patch(f"/api/orders/{order_id}", json={"status": "shipped"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "shipped"


def test_missing_order(client):
    assert client.get("/api/orders/missing").status_code == 404


def test_express_order_placed_at_month_end(client):
    # Regression: the estimate used replace(day=day + 2), which crashed near month end.
    assert client.get("/api/orders/express-1002").status_code == 200
    with main.connect() as db:
        db.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
            ("express-eom", "Jo", "Lamp", "express", "received", "2026-09-30T23:00:00+00:00"),
        )
    response = client.get("/api/orders/express-eom")
    assert response.status_code == 200
    assert response.json()["estimated_delivery"] == "2026-10-02"


def request_counts(metric_reader):
    counts = {}
    for resource_metrics in metric_reader.get_metrics_data().resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "http.server.request.duration":
                    for point in metric.data.data_points:
                        key = (point.attributes["http.route"], point.attributes["http.response.status_code"])
                        counts[key] = counts.get(key, 0) + point.count
    return counts


def test_order_lookup_telemetry(client, telemetry, monkeypatch):
    span_exporter, metric_reader, log_exporter = telemetry
    before = request_counts(metric_reader)
    client.get("/api/orders/standard-1001")
    client.get("/api/orders/missing")
    monkeypatch.setattr(main, "order_detail", lambda row: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        client.get("/api/orders/standard-1001")

    after = request_counts(metric_reader)
    for status in (200, 404, 500):
        key = ("/api/orders/{order_id}", status)
        assert after[key] - before.get(key, 0) == 1

    lookups = [span for span in span_exporter.get_finished_spans() if span.name == "order lookup"]
    assert [span.attributes["order.id"] for span in lookups] == ["standard-1001", "missing", "standard-1001"]
    assert [span.status.is_ok for span in lookups] == [True, True, False]

    bodies = [log.log_record.body for log in log_exporter.get_finished_logs() if log.log_record.body.startswith("Order")]
    assert bodies == [
        "Order lookup succeeded",
        "Order lookup failed: Order not found",
        "Order lookup crashed: ZeroDivisionError",
    ]
