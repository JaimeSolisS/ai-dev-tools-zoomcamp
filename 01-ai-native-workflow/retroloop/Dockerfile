FROM python:3.14-slim AS base

# _docs/architecture.md pins ffmpeg 8.1, but Debian trixie (this image's
# base) only carries 7.1.5 in apt, and there is no well-maintained,
# checksum-pinned distribution of an exact ffmpeg 8.1 build to install
# instead (static-build mirrors track "latest", not a fixed version). Using
# apt's 7.1.5 here is a deliberate, flagged deviation -- see the comment on
# issue #2. Revisit once trixie or a backports repo carries 8.1.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg gosu \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.9.*

# Non-root user the app runs as. UID/GID fixed and known so compose.yaml's
# entrypoint can chown the scratch volume's mount point to match, even
# though a fresh named volume is created root-owned by the Docker daemon.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /bin/bash app

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# App directory is owned by the non-root user so it can write .pyc caches,
# etc. The scratch volume mount point is fixed up by entrypoint.sh at
# container start, since volumes mount root-owned regardless of this.
RUN chown -R app:app /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
