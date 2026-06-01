# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

WORKDIR /app

# ── system deps ──────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── python deps ──────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright is only needed for the load generator; install the browser here
# so the single image can run either role.
RUN playwright install --with-deps chromium

# ── application code ─────────────────────────────────────────────────────────
COPY app/      ./app/
COPY seed.py   ./seed.py
COPY load_generator.py ./load_generator.py

# ── Dynatrace / OTel configuration (must be supplied at runtime) ──────────────
# DT_ENDPOINT_BASE  — e.g. https://<your-env>.apps.dynatrace.com/api/v2/otlp/v1
# DT_API_TOKEN      — Dynatrace API token with OTLP ingest scopes
ENV DT_ENDPOINT_BASE="" \
    DT_API_TOKEN="" \
    SERVICE_NAME="banking-api" \
    SERVICE_VERSION="1.0.0" \
    DEPLOYMENT_ENVIRONMENT="demo" \
    DB_URL="sqlite:///./banking.db"

# ── data volume for SQLite ────────────────────────────────────────────────────
VOLUME ["/app/data"]

# ── healthcheck ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# ── entrypoint ───────────────────────────────────────────────────────────────
# Seed the DB, then start the API.
# Override CMD to run the load generator instead:
#   docker run ... banking-api python load_generator.py
CMD ["sh", "-c", "python seed.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
