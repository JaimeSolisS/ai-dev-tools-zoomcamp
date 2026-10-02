"""Serve the built frontend (a single-page app) from the backend, for the all-in-one Docker image."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

# Paths owned by the API. Unknown paths under these return 404 instead of the app shell.
API_PREFIXES = ("v1/", "docs", "redoc", "openapi.json", "health")


def install_frontend(app: FastAPI, static_dir: str) -> None:
    root = Path(static_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"ARCHBOARD_STATIC_DIR={static_dir} has no index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith(API_PREFIXES):
            raise HTTPException(status_code=404)
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(file)
        # Client-side routes (e.g. /sessions/123) get the app shell; React Router takes it from there.
        return FileResponse(index)
