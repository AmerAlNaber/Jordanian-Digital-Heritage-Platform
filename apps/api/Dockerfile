# API image. Multi-stage: uv resolves the locked workspace, the runtime stage carries only the
# virtual environment and the sources. Runs as a non-root user; no build tools at runtime.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/metadata/pyproject.toml packages/metadata/pyproject.toml
COPY packages/ai-adapters/pyproject.toml packages/ai-adapters/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package jdhp-api
COPY apps/api apps/api
COPY packages packages
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package jdhp-api --extra seed

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home jdhp
WORKDIR /app
COPY --from=build --chown=jdhp:jdhp /app/.venv /app/.venv
COPY --from=build --chown=jdhp:jdhp /app/apps/api /app/apps/api
COPY --from=build --chown=jdhp:jdhp /app/packages /app/packages
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER jdhp
EXPOSE 8000 8010
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://localhost:8010/healthz || exit 1
CMD ["uvicorn", "jdhp_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
