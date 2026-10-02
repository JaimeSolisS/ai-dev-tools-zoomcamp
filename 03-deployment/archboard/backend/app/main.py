"""FastAPI application factory. Run with `uv run uvicorn app.main:app --reload`."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import Settings
from .db import create_db_engine, create_schema, create_session_factory
from .errors import install_error_handlers
from .realtime import Hub
from .routers import auth, canvas, guest_links, join, participants, realtime, sessions
from .seed import create_example_session, seed_if_empty
from .static import install_frontend
from .store import StoreContext

ROUTER_MODULES = (auth, sessions, participants, guest_links, join, canvas, realtime)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_db_engine(settings.database_url)
    create_schema(engine)
    hub = Hub()
    store_context = StoreContext(
        session_factory=create_session_factory(engine),
        settings=settings,
        events=hub,
    )
    if settings.seed:
        seed_if_empty(store_context)
        # Installed after seeding: the demo users get the curated sessions only.
        store_context.on_user_created = create_example_session

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        hub.bind(asyncio.get_running_loop())
        yield
        engine.dispose()

    app = FastAPI(
        title="Archboard API",
        version="1.0.0",
        description="Backend for the system-design interview platform. The contract is `openapi.yaml`.",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.hub = hub
    app.state.store_context = store_context

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Guest-Credential"],
    )
    install_error_handlers(app)

    # Operational, not part of openapi.yaml: load balancers and the deploy pipeline poll it.
    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:  # any failure means unhealthy
            return JSONResponse({"status": "error", "database": "unreachable", "version": settings.version}, 503)
        return JSONResponse({"status": "ok", "database": "ok", "version": settings.version})

    for module in ROUTER_MODULES:
        app.include_router(module.router)
    if settings.static_dir:
        install_frontend(app, settings.static_dir)
    return app


def __getattr__(name: str) -> FastAPI:
    """`app.main:app` for uvicorn, created on first access so importing this module has no side effects."""
    if name == "app":
        instance = create_app()
        globals()["app"] = instance
        return instance
    raise AttributeError(name)
