FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /usr/local/bin/

# Debian trixie ships ffmpeg 7.1; 8.1 is only in sid, so pull just that one
# package from sid while everything else stays pinned to trixie.
RUN echo "deb http://deb.debian.org/debian sid main" > /etc/apt/sources.list.d/sid.list \
    && printf 'Package: *\nPin: release a=sid\nPin-Priority: 1\n' > /etc/apt/preferences.d/sid.pref \
    && apt-get update \
    && apt-get install -y --no-install-recommends -t sid ffmpeg=7:8.1* \
    && rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/sid.list /etc/apt/preferences.d/sid.pref

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .
RUN chown -R app:app /app

USER app

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
