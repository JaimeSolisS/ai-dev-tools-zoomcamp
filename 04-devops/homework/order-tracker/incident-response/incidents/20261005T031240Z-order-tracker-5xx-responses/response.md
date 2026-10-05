I fixed the bug, deployed it, and `/api/orders/express-1002` now returns 200 instead of 500. Nothing has been committed.

**Root cause:** `order_detail()` at `app/main.py:69` worked out the express delivery date with `placed_at.replace(day=placed_at.day + 2)`. That doesn't roll over into the next month, so any express order placed in the last two days of a month raised `ValueError: day is out of range for month`, which came back as a 500.

The sample order `express-1002` is always created on the last day of the previous month (here, Sep 30), so every lookup of it failed. All 3 error logs and every errored trace in the evidence are for `express-1002` and show this same error.

**Fix:**
- **`app/main.py`:** the estimate is now `placed_at + timedelta(days=2)`, which crosses month and year ends correctly.
- **`tests/test_api.py`:** I added a regression test, `test_express_order_placed_at_month_end`. It checks that `express-1002` returns 200, and that an express order placed on 2026-09-30 gets `estimated_delivery` 2026-10-02.

**Tests:** before the fix, `uv run --frozen pytest -q` gave 1 failed, 4 passed; the new test failed with the same error as production. After the fix: 5 passed.

**Verification:** I rebuilt and restarted with `docker compose up --build -d --wait app`, and the container came up healthy. Repeating the requests on localhost:8000:
- `express-1002` returned 200 with `estimated_delivery: 2026-10-02`.
- `standard-1001` returned 200, as before.
- `missing` returned 404, which is expected.

The alert should clear once 5 minutes pass with no new 5xx responses.

The full write-up (root cause, evidence, fix, test results, verification) is in `incident-response/incidents/20261005T031240Z-order-tracker-5xx-responses/report.md`.

RESULT: fixed
