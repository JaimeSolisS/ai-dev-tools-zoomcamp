# Archboard: one image with the FastAPI backend serving the built React frontend.
#   docker build -t archboard .
#   docker run -p 8091:8091 archboard     # http://localhost:8091

# --- Stage 1: build the frontend ---
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# "/" = same origin: the API is served by the backend that serves this page.
ENV VITE_BACKEND=http VITE_API_BASE_URL=/
RUN npm run build

# --- Stage 2: the backend, with the frontend's static files ---
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

# The git commit, reported by /health so a deploy can confirm which build is live.
ARG APP_VERSION=dev
ENV ARCHBOARD_VERSION=$APP_VERSION
ENV PATH="/app/.venv/bin:$PATH" \
    ARCHBOARD_STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:////data/archboard.db
RUN mkdir /data
VOLUME /data
EXPOSE 8091
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
