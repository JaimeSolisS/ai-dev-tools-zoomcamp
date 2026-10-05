You are the on-call responder for Order Tracker, the service in this repository.
Grafana fired an alert, and the evidence is saved in incident-response/incidents/20261005T031240Z-order-tracker-5xx-responses/:

- summary.md: the alert, the affected endpoint, time window, and the key errors
- alert.json: the raw Grafana webhook
- metrics.json, logs.json, traces.json, traces/: the telemetry around the alert

Work through it:

1. Read the evidence and find the root cause in the code. Stack traces and the
   failing order IDs are in logs.json and traces.json.
2. If the cause is a clear bug with a small, safe fix: add a regression test in
   tests/, fix the code, and run `uv run --frozen pytest -q` until it passes.
3. Rebuild and restart the app with `docker compose up --build -d --wait app`.
4. Verify by repeating the failing request against http://localhost:8000 and
   checking that it no longer returns a 5xx.
5. Write incident-response/incidents/20261005T031240Z-order-tracker-5xx-responses/report.md with: root cause, evidence, the fix (files changed),
   test results, and verification.

If you cannot find the cause, the fix is not small and safe, or verification
fails, do not deploy. Write report.md explaining what you found and what a
developer should look at, and say that you are escalating.

Do not commit, push, or delete data. End your answer with one line that starts
with "RESULT:" and says fixed, escalated, or no action needed.
