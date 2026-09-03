FROM python:3.14-slim AS base

# _docs/architecture.md pins ffmpeg 8.1. Debian trixie's apt only carries
# 7.1.5, so instead of apt we pull the statically-linked ffmpeg/ffprobe 8.1.2
# binaries straight from BtbN/FFmpeg-Builds, a well-known CI that publishes
# tagged (non-"latest") releases per build date with a checksums.sha256 file
# per release. We pin one specific dated tag (not the "latest" alias, which
# is a moving target) and verify the download against a hardcoded sha256
# before trusting it. Re-verified working: `ffmpeg -version` inside this
# image reports `ffmpeg version n8.1.2-...`.
ARG FFMPEG_RELEASE_TAG=autobuild-2026-08-27-16-45
ARG FFMPEG_BUILD=n8.1.2-47-g156bb4d299
ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu curl xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && case "$TARGETARCH" in \
         amd64) FF_ARCH=linux64; FF_SHA256=5422737149e93e157bd736b699be798e1f6d9ecbd97751a761e2518593004a89 ;; \
         arm64) FF_ARCH=linuxarm64; FF_SHA256=a1499a1e8c475afe45db54e553eeaf35164220c65d58d1f6617046c095e9bee7 ;; \
         *) echo "unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
       esac \
    && FF_ASSET="ffmpeg-${FFMPEG_BUILD}-${FF_ARCH}-gpl-8.1.tar.xz" \
    && curl -fsSL -o /tmp/ffmpeg.tar.xz \
         "https://github.com/BtbN/FFmpeg-Builds/releases/download/${FFMPEG_RELEASE_TAG}/${FF_ASSET}" \
    && echo "${FF_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
    && mkdir -p /tmp/ffmpeg-extract \
    && tar -xf /tmp/ffmpeg.tar.xz -C /tmp/ffmpeg-extract --strip-components=1 \
    && install -m 755 /tmp/ffmpeg-extract/bin/ffmpeg /usr/local/bin/ffmpeg \
    && install -m 755 /tmp/ffmpeg-extract/bin/ffprobe /usr/local/bin/ffprobe \
    && rm -rf /tmp/ffmpeg.tar.xz /tmp/ffmpeg-extract \
    && apt-get purge -y curl xz-utils \
    && apt-get autoremove -y \
    && ffmpeg -version

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
