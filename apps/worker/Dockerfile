# Worker image: the API package as a library plus libvips and OpenJPEG for derivatives.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/metadata/pyproject.toml packages/metadata/pyproject.toml
COPY packages/ai-adapters/pyproject.toml packages/ai-adapters/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package jdhp-worker
COPY apps apps
COPY packages packages
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package jdhp-worker --extra seed

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libvips42 libopenjp2-7 libfribidi0 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10002 --create-home jdhp
WORKDIR /app
COPY --from=build --chown=jdhp:jdhp /app/.venv /app/.venv
COPY --from=build --chown=jdhp:jdhp /app/apps /app/apps
COPY --from=build --chown=jdhp:jdhp /app/packages /app/packages
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER jdhp
HEALTHCHECK --interval=60s --timeout=25s --retries=3 --start-period=90s CMD celery -A jdhp_worker.celery_app inspect ping -t 15 || exit 1
CMD ["celery", "-A", "jdhp_worker.celery_app", "worker", "--loglevel=INFO", "-Q", "ingest,derivatives,ocr,embeddings,translation,fixity,mail,maintenance,default", "--concurrency=2"]
