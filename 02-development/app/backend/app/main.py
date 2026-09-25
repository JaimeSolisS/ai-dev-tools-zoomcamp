"""FastAPI application factory. Run with `uv run uvicorn app.main:app --reload`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .errors import install_error_handlers
from .realtime import Hub
from .routers import auth, canvas, guest_links, join, participants, realtime, sessions
from .seed import seed
from .store import Store

ROUTER_MODULES = (auth, sessions, participants, guest_links, join, canvas, realtime)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Archboard API",
        version="1.0.0",
        description="Backend for the system-design interview platform. The contract is `openapi.yaml`.",
    )
    app.state.hub = Hub()
    app.state.store = Store(settings, events=app.state.hub)
    if settings.seed:
        seed(app.state.store)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Guest-Credential"],
    )
    install_error_handlers(app)
    for module in ROUTER_MODULES:
        app.include_router(module.router)
    return app


app = create_app()
