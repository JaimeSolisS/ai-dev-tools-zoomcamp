from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from app.config import Settings, get_settings
from app.errors import AppError
from app.repositories.database import create_engine_for_url, create_session_factory, init_db
from app.routes import (
    admin,
    auth,
    balances,
    categories,
    comments,
    expenses,
    groups,
    refunds,
    settlements,
    users,
)

API_PREFIX = "/api/v1"


def create_app(engine: Engine | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name)

    if engine is None:
        if settings.database_url.startswith("sqlite:///") and settings.database_url != "sqlite:///:memory:":
            db_path = Path(settings.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine_for_url(settings.database_url)
    init_db(engine)

    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"message": exc.message})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        message = "Invalid request."
        if first:
            field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
            message = f"{field}: {first.get('msg')}" if field else str(first.get("msg"))
        return JSONResponse(status_code=422, content={"message": message})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"message": "Something went wrong. Please try again."})

    app.include_router(auth.router, prefix=API_PREFIX, tags=["auth"])
    app.include_router(users.router, prefix=API_PREFIX, tags=["users"])
    app.include_router(groups.router, prefix=API_PREFIX, tags=["groups"])
    app.include_router(categories.router, prefix=API_PREFIX, tags=["categories"])
    app.include_router(expenses.router, prefix=API_PREFIX, tags=["expenses"])
    app.include_router(balances.router, prefix=API_PREFIX, tags=["balances"])
    app.include_router(balances.settlement_suggestions_router, prefix=API_PREFIX, tags=["balances"])
    app.include_router(settlements.router, prefix=API_PREFIX, tags=["settlements"])
    app.include_router(refunds.router, prefix=API_PREFIX, tags=["refunds"])
    app.include_router(admin.router, prefix=API_PREFIX, tags=["admin"])
    # Comments use a broad `/{transaction_type}/{transaction_id}/comments`
    # path (per spec) - register it last so nothing else could ever shadow it.
    app.include_router(comments.router, prefix=API_PREFIX, tags=["comments"])

    return app


app = create_app()
