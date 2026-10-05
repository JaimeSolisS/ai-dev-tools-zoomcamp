# Incident 20261005T031240Z-order-tracker-5xx-responses

- Received: 2026-10-05T03:12:40.233997+00:00
- Notification status: firing
- Evidence window: 2026-10-05T03:02:30+00:00 to 2026-10-05T03:12:40.014657+00:00
- Endpoints: /api/orders/{order_id}

## Alert 1: Order Tracker 5xx responses (firing)

- Endpoint: /api/orders/{order_id}
- Time window: 5m
- Started: 2026-10-05T03:12:30Z
- Summary: /api/orders/{order_id} returned 1 5xx response(s) in the last 5m
- Description: Server errors (HTTP 5xx) on endpoint /api/orders/{order_id} during the last 5 minutes. Check the dashboard's error traces and logs for the stack trace.
- Dashboard: http://localhost:3000/d/order-tracker/order-tracker?from=now-30m&to=now&var-route=%2Fapi%2Forders%2F%7Border_id%7D
- Panel: http://localhost:3000/d/order-tracker?orgId=1&viewPanel=6
- Rule: http://localhost:3000/alerting/grafana/order-tracker-5xx/view?orgId=1
- Labels: `{"alertname": "Order Tracker 5xx responses", "grafana_folder": "Order Tracker", "http_route": "/api/orders/{order_id}", "service": "order-tracker", "severity": "critical"}`

## 5xx responses in the window

- /api/orders/{order_id} 500 ValueError: 1.02

## Warning and error logs (6, newest first)

- 2026-10-05T03:12:38.969422+00:00 ERROR: Unhandled exception in FastAPI request (trace_id=cadf3cbf9606503f72f2d0be1d8cd25c)
- 2026-10-05T03:12:38.968731+00:00 ERROR: Order lookup crashed: ValueError (order_id=express-1002, trace_id=cadf3cbf9606503f72f2d0be1d8cd25c)
- 2026-10-05T03:12:37.937222+00:00 ERROR: Unhandled exception in FastAPI request (trace_id=7587d0d92db3f8515d81a5fdd5421ad8)
- 2026-10-05T03:12:37.936301+00:00 ERROR: Order lookup crashed: ValueError (order_id=express-1002, trace_id=7587d0d92db3f8515d81a5fdd5421ad8)
- 2026-10-05T03:12:13.487885+00:00 ERROR: Unhandled exception in FastAPI request (trace_id=dca3b36404a3f80cad7fff1011963cde)
- 2026-10-05T03:12:13.486850+00:00 ERROR: Order lookup crashed: ValueError (order_id=express-1002, trace_id=dca3b36404a3f80cad7fff1011963cde)

Latest stack trace:

```
Traceback (most recent call last):
  File "/app/.venv/lib/python3.12/site-packages/fastapi/telemetry/_asgi.py", line 151, in __call__
    await self.app(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/app/.venv/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/app/.venv/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/starlette/routing.py", line 676, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 2786, in app
    await route.handle(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 1310, in handle
    await super().handle(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/starlette/routing.py", line 282, in handle
    await self.app(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 165, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/app/.venv/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/app/.venv/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 151, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 727, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/.venv/lib/python3.12/site-packages/fastapi/routing.py", line 362, in run_endpoint_function
    return await run_in_threadpool(
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/.venv/lib/python3.12/site-packages/starlette/concurrency.py", line 34, in run_in_threadpool
    return await anyio.to_thread.run_sync(func)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/.venv/lib/python3.12/site-packages/anyio/to_thread.py", line 65, in run_sync
    return await get_async_backend().run_sync_in_worker_thread(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 2706, in run_sync_in_worker_thread
    return await future
           ^^^^^^^^^^^^
  File "/app/.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 1100, in run
    result = context.run(func, *args)
             ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/.venv/lib/python3.12/site-packages/fastapi/telemetry/_api.py", line 240, in _run_sync_endpoint
    return function(**arguments)
           ^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/main.py", line 129, in get_order
    order = fetch_order(order_id)
            ^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/main.py", line 117, in fetch_order
    return order_detail(row)
           ^^^^^^^^^^^^^^^^^
  File "/app/app/main.py", line 69, in order_detail
    estimated_at = placed_at.replace(day=placed_at.day + 2)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
ValueError: day is out of range for month
```

## Error traces (2)

- dca3b36404a3f80cad7fff1011963cde: fastapi.endpoint (error), GET /api/orders/{order_id} (error), order lookup (ValueError), fastapi.endpoint (error), GET /api/orders/{order_id} (error), order lookup (ValueError)
- 7587d0d92db3f8515d81a5fdd5421ad8: fastapi.endpoint (error), GET /api/orders/{order_id} (error), order lookup (ValueError), fastapi.endpoint (error), GET /api/orders/{order_id} (error), order lookup (ValueError)

Files: alert.json, metrics.json, logs.json, traces.json, traces/<trace id>.json
