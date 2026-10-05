# Incident report: Order Tracker 5xx responses

**Status:** Fixed and deployed (not committed)

## Root cause

`order_detail()` in `app/main.py` calculated the delivery estimate for express orders like this:

```python
estimated_at = placed_at.replace(day=placed_at.day + 2)
```

`datetime.replace(day=...)` doesn't roll over into the next month. When an express order is placed on one of the last two days of a month, the new day number doesn't exist (for example, Sep 30 + 2 = "Sep 32"). Python then raises `ValueError: day is out of range for month`. Nothing catches that error, so `GET /api/orders/{order_id}` returns HTTP 500.

The seeded order `express-1002` is created on the last day of the previous month (`2026-09-30T02:07:23Z`), so every lookup of it failed.

## Evidence

- **summary.md / alert.json:** the "Order Tracker 5xx responses" alert fired for `/api/orders/{order_id}` and recorded a 500 `ValueError`.
- **logs.json:** 3 `Order lookup crashed: ValueError` errors, all for `order_id=express-1002`. They happened at 03:12:13, 03:12:37 and 03:12:38 UTC, with trace IDs `dca3b364…`, `7587d0d9…` and `cadf3cbf…`.
- **traces.json / traces/:** the `order lookup` spans with errors all have `order.id=express-1002`. Their exception is `ValueError: day is out of range for month`.
- **Stack trace:** `get_order` (main.py:129) → `fetch_order` (main.py:117) → `order_detail` (main.py:69) `placed_at.replace(day=placed_at.day + 2)`.

## Fix

Files changed:

- `app/main.py`: the line now reads `estimated_at = placed_at + timedelta(days=2)`. This rolls over correctly across month and year boundaries. `timedelta` was already imported.
- `tests/test_api.py`: added the regression test `test_express_order_placed_at_month_end`. It checks that:
  - the seeded `express-1002` returns 200;
  - an express order placed at `2026-09-30T23:00:00+00:00` returns 200 with `estimated_delivery == "2026-10-02"`.

## Test results

`uv run --frozen pytest -q`:

- Before the fix: `1 failed, 4 passed`. The new test failed with the same `ValueError` seen in production.
- After the fix: `5 passed, 2 warnings`.

## Verification

1. Ran `docker compose up --build -d --wait app`. The app container came up healthy.
2. Sent the requests again against http://localhost:8000:
   - `GET /api/orders/express-1002` returned **HTTP 200**:
     `{"id":"express-1002",...,"created_at":"2026-09-30T02:07:23.873275+00:00","estimated_delivery":"2026-10-02"}`
   - `GET /api/orders/standard-1001` returned HTTP 200 (unchanged).
   - `GET /api/orders/missing` returned HTTP 404 (unchanged; this is expected).

## Follow-ups

- Commit the fix and the test (not done, as instructed).
- The alert should resolve once the 5-minute window passes with no new 5xx responses.
