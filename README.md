# Banking API — SLO Demo with Dynatrace & OpenTelemetry

A Python FastAPI banking application purpose-built to demonstrate **Service Level Objectives (SLOs)** on Dynatrace. The app ships full OpenTelemetry telemetry (traces, metrics, logs) to a Dynatrace tenant and includes **intentional bugs** so you can observe SLO breaches and anomalies in distributed tracing, dashboards, and alerting.

---

## What This Demo Shows

| Dynatrace Feature | What You Will See |
|---|---|
| **Distributed Tracing** | End-to-end traces with slow spans, N+1 child spans, span events on timeout/retry |
| **SLO Monitoring** | Error budget burn from the 20% withdrawal failure rate |
| **Metrics Explorer** | Custom `banking.*` counters and histograms per endpoint |
| **Log Viewer** | Structured logs correlated to traces via `trace_id` / `span_id` |
| **Alerting** | Threshold alerts on `banking.withdrawal.failures.total` and `banking.http.request.duration` |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  load_generator.py                  │
│        (Playwright · 5 async workers)               │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP
                       ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Banking API                    │
│                                                     │
│  GET  /health                                       │
│  GET  /accounts/{account_id}   <- slow query bug   │
│  POST /accounts/{id}/withdrawal <- 20% 500 bug     │
│  POST /transfers                <- N+1 + timeout   │
│                                                     │
│  ┌───────────────┐   ┌─────────────────────────┐   │
│  │  SQLite DB    │   │  OpenTelemetry SDK       │   │
│  │  (no indexes  │   │  Traces / Metrics / Logs │   │
│  │   on hot cols)│   │  BatchSpanProcessor      │   │
│  └───────────────┘   └──────────┬──────────────┘   │
└─────────────────────────────────┼───────────────────┘
                                  │ OTLP/HTTP
                                  ▼
                    ┌─────────────────────────┐
                    │   Dynatrace Tenant      │
                    │  <your-env>.apps.       │
                    │  dynatrace.com          │
                    │                         │
                    │  /otlp/v1/traces        │
                    │  /otlp/v1/metrics       │
                    │  /otlp/v1/logs          │
                    └─────────────────────────┘
```

---

## Project Structure

```
slo-dynatrace-services/
├── app/
│   ├── config.py                 # Dynatrace endpoints & token (loaded from env vars)
│   ├── database.py               # SQLAlchemy sync engine + session factory
│   ├── models.py                 # ORM: Account, Transaction — missing indexes intentional
│   ├── schemas.py                # Pydantic v2 request/response models
│   ├── main.py                   # FastAPI app factory + OTel wiring + HTTP middleware
│   ├── routers/
│   │   ├── health.py             # GET /health
│   │   ├── accounts.py           # GET /accounts/{account_id}  [BUG: slow query]
│   │   ├── withdrawals.py        # POST /accounts/{id}/withdrawal  [BUG: 20% 500]
│   │   └── transfers.py          # POST /transfers  [BUG: N+1 + timeout]
│   └── telemetry/
│       ├── setup.py              # OTel SDK bootstrap — tracer, meter, logger providers
│       └── metrics.py            # Named instruments: banking.* counters & histograms
├── seed.py                       # Populate SQLite with 20 test accounts
├── load_generator.py             # Playwright async load generator (5 workers)
├── Dockerfile                    # Container image (API + load generator in one image)
├── .dockerignore
└── requirements.txt
```

---

## Environment Variables

Both run methods rely on the same variables. `DT_ENDPOINT_BASE` and `DT_API_TOKEN` are **required** — without them, telemetry will not reach Dynatrace.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DT_ENDPOINT_BASE` | **Yes** | *(empty)* | Dynatrace OTLP base URL — `https://<env-id>.apps.dynatrace.com/api/v2/otlp/v1` |
| `DT_API_TOKEN` | **Yes** | *(empty)* | Dynatrace API token — needs `openTelemetryTrace.ingest`, `metrics.ingest`, `logs.ingest` scopes |
| `SERVICE_NAME` | No | `banking-api` | OTel `service.name` shown in Dynatrace |
| `SERVICE_VERSION` | No | `1.0.0` | OTel `service.version` resource attribute |
| `DEPLOYMENT_ENVIRONMENT` | No | `demo` | OTel `deployment.environment` resource attribute |
| `DB_URL` | No | `sqlite:///./banking.db` | SQLAlchemy DB URL — override when using Docker volume |

---

## Running the Demo

Choose the method that suits your setup.

---

### Option A — Local (Python)

**Prerequisites:** Python 3.11+, internet access to your Dynatrace tenant.

#### 1. Install dependencies

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

On Windows, use `py -3` instead of `python`:

```bash
py -3 -m pip install -r requirements.txt
py -3 -m playwright install chromium
```

#### 2. Set Dynatrace credentials

Create a `.env` file in the project root (it is git-ignored):

```env
DT_ENDPOINT_BASE=https://<your-env-id>.apps.dynatrace.com/api/v2/otlp/v1
DT_API_TOKEN=dt0c01.XXXX...
```

Or export them as shell variables:

```bash
# Linux / macOS
export DT_ENDPOINT_BASE="https://<your-env-id>.apps.dynatrace.com/api/v2/otlp/v1"
export DT_API_TOKEN="dt0c01.XXXX..."

# Windows PowerShell
$env:DT_ENDPOINT_BASE = "https://<your-env-id>.apps.dynatrace.com/api/v2/otlp/v1"
$env:DT_API_TOKEN     = "dt0c01.XXXX..."

# Windows CMD
set DT_ENDPOINT_BASE=https://<your-env-id>.apps.dynatrace.com/api/v2/otlp/v1
set DT_API_TOKEN=dt0c01.XXXX...
```

#### 3. Seed the database

Populates SQLite with 20 test accounts (`ACC001`–`ACC020`). Safe to re-run — idempotent.

```bash
python seed.py
```

Expected output:
```
Seed complete — inserted: 20, skipped (already exist): 0
  ACC001  Test User 01          SAVINGS       $  32007.40
  ACC002  Test User 02          BUSINESS      $   1348.04
  ...
```

#### 4. Start the API server

Open **Terminal 1**:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Expected startup:
```
INFO:  OpenTelemetry configured — service=banking-api env=demo
INFO:  Application startup complete.
INFO:  Uvicorn running on http://0.0.0.0:8000
```

Swagger UI is available at: http://localhost:8000/docs

#### 5. Start the load generator

Open **Terminal 2**:

```bash
python load_generator.py
```

```
Starting 5 load generator workers against http://localhost:8000
Press Ctrl+C to stop.

[W1] GET  /accounts/ACC007        -> 200
[W2] POST /accounts/ACC003/withdrawal -> 500  amount=341.20
[W3] POST /transfers ACC012->ACC018   -> 200  amount=87.50
[W4] GET  /accounts/ACC015        -> 200
[W5] GET  /health                 -> 200
...
```

Press `Ctrl+C` to stop the load generator.

---

### Option B — Docker

**Prerequisites:** Docker installed and running. No Python required on the host.

#### 1. Build the image

```bash
docker build -t banking-api .
```

> The first build downloads the Playwright Chromium binary (~200 MB). Subsequent builds use the Docker layer cache.

#### 2. Start the API server

**Linux / macOS:**

```bash
docker run -d \
  --name banking-api \
  -p 8000:8000 \
  -e DT_ENDPOINT_BASE="https://<your-env-id>.apps.dynatrace.com/api/v2/otlp/v1" \
  -e DT_API_TOKEN="dt0c01.XXXX..." \
  -e DB_URL="sqlite:////app/data/banking.db" \
  -v banking-db:/app/data \
  banking-api
```

**Windows PowerShell:**

```powershell
docker run -d `
  --name banking-api `
  -p 8000:8000 `
  -e DT_ENDPOINT_BASE="https://<your-env-id>.apps.dynatrace.com/api/v2/otlp/v1" `
  -e DT_API_TOKEN="dt0c01.XXXX..." `
  -e DB_URL="sqlite:////app/data/banking.db" `
  -v banking-db:/app/data `
  banking-api
```

The `-v banking-db:/app/data` mount stores the SQLite database on a named volume so data survives container restarts.

Confirm it started:

```bash
docker logs banking-api
docker exec banking-api curl -s http://localhost:8000/health
```

#### 3. Start the load generator

Open a second terminal. On **Linux / macOS** use `--network host`:

```bash
docker run --rm \
  --name load-generator \
  --network host \
  banking-api \
  python load_generator.py
```

On **Windows / macOS Docker Desktop**, `--network host` is not supported — use `host.docker.internal`:

```bash
docker run --rm \
  --name load-generator \
  -e BASE_URL="http://host.docker.internal:8000" \
  banking-api \
  python load_generator.py
```

#### 4. Using an env file (recommended for repeated runs)

Create `.env.docker` in the project root (never commit this file — it is listed in `.dockerignore`):

```env
DT_ENDPOINT_BASE=https://<your-env-id>.apps.dynatrace.com/api/v2/otlp/v1
DT_API_TOKEN=dt0c01.XXXX...
SERVICE_NAME=banking-api
DEPLOYMENT_ENVIRONMENT=demo
DB_URL=sqlite:////app/data/banking.db
```

Then start the API with:

```bash
docker run -d \
  --name banking-api \
  -p 8000:8000 \
  --env-file .env.docker \
  -v banking-db:/app/data \
  banking-api
```

#### 5. Docker quick-reference

```bash
# Build
docker build -t banking-api .

# Start API
docker run -d --name banking-api -p 8000:8000 \
  -e DT_ENDPOINT_BASE="https://<env-id>.apps.dynatrace.com/api/v2/otlp/v1" \
  -e DT_API_TOKEN="dt0c01.XXXX..." \
  -e DB_URL="sqlite:////app/data/banking.db" \
  -v banking-db:/app/data \
  banking-api

# Start load generator (Linux)
docker run --rm --name load-generator --network host \
  banking-api python load_generator.py

# Start load generator (Windows / macOS)
docker run --rm --name load-generator \
  -e BASE_URL="http://host.docker.internal:8000" \
  banking-api python load_generator.py

# Stream API logs
docker logs -f banking-api

# Stop and clean up
docker stop banking-api && docker rm banking-api
docker volume rm banking-db
```

---

## Manual API Testing

Use these commands to test each endpoint directly, regardless of run method.

### Health check

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok", "db": "ok", "service": "banking-api"}
```

### Account inquiry

```bash
curl http://localhost:8000/accounts/ACC001
```

```json
{
  "account_id": "ACC001",
  "owner_name": "Test User 01",
  "account_type": "SAVINGS",
  "balance": 32007.40,
  "currency": "USD",
  "is_active": true
}
```

> Expect a 500 ms – 1.5 s response time — the slow query bug is active.

### Withdrawal

```bash
curl -X POST http://localhost:8000/accounts/ACC003/withdrawal \
     -H "Content-Type: application/json" \
     -d '{"amount": 100.00}'
```

```json
{
  "transaction_id": "a1b2c3d4-...",
  "account_id": "ACC003",
  "amount": 100.0,
  "new_balance": 13723.96,
  "status": "success"
}
```

> Approximately 1 in 5 calls return HTTP 500 — this is intentional.

### Transfer

```bash
curl -X POST http://localhost:8000/transfers \
     -H "Content-Type: application/json" \
     -d '{"from_account_id": "ACC005", "to_account_id": "ACC009", "amount": 250.00}'
```

```json
{
  "transaction_id": "e5f6g7h8-...",
  "from_account_id": "ACC005",
  "to_account_id": "ACC009",
  "amount": 250.0,
  "status": "success"
}
```

> ~15% of transfers take 4 – 7 seconds due to the simulated timeout + retry.

---

## Intentional Bugs

These bugs are deliberate — each produces a distinct, observable signal in Dynatrace.

### Bug 1 — Slow Query (Account Inquiry)
**File:** [`app/routers/accounts.py`](app/routers/accounts.py)

The account lookup filters on an unindexed column (`account_type != 'CLOSED'`) before the indexed `account_id`, forcing a full table scan. An artificial sleep of **0.5 – 1.5 s** amplifies the latency.

**Dynatrace signal:**
- Long `account.inquiry` spans in Distributed Tracing
- High `banking.db.query.duration` histogram values
- `db.artificial_sleep_seconds` span attribute on every inquiry span

---

### Bug 2 — Random 500 Errors (Withdrawal)
**File:** [`app/routers/withdrawals.py`](app/routers/withdrawals.py)

**~20% of withdrawal requests** raise HTTP 500 (`"Internal processing error — payment processor unavailable"`). The exception is recorded on the span.

**Dynatrace signal:**
- `banking.withdrawal.failures.total` counter spikes
- Error spans with `bug.random_failure = true` and a recorded exception event
- SLO error budget burn when a success-rate SLO is configured on this metric

---

### Bug 3 — N+1 Query (Transfer)
**File:** [`app/routers/transfers.py`](app/routers/transfers.py)

Instead of fetching both accounts in one query, the code loops through account IDs individually. For each account it also runs a second query to fetch recent transaction history — with no index on `from_account`, each is a full table scan.

**Result:** 4 DB child spans per transfer (2× `db.fetch_account` + 2× `db.fetch_recent_transactions`), each tagged `bug.n_plus_one = true`.

**Dynatrace signal:**
- Multiple DB child spans in the trace waterfall
- `bug.n_plus_one` and `bug.no_index_scan` span attributes

---

### Bug 4 — Simulated Timeout + Retry (Transfer)
**File:** [`app/routers/transfers.py`](app/routers/transfers.py)

**~15% of transfers** simulate a downstream payment-processor timeout:

1. Sleep **3 – 5 s** (attempt 1 timeout)
2. Record `downstream_timeout` span event
3. Sleep **1 – 2 s** (retry)
4. Record `retry_attempt` span event
5. Continue and complete the transfer normally

**Dynatrace signal:**
- Very long `account.transfer` spans (up to 7 s+)
- `downstream_timeout` and `retry_attempt` span events with timestamps visible in the trace
- `bug.simulated_timeout = true` span attribute

---

## Dynatrace: What to Look At

### 1. Distributed Tracing

**Navigate to:** Applications & Microservices > Distributed Traces

Filter by `service.name = banking-api`. You will see:

- `account.inquiry` spans consistently taking 500 ms – 1.5 s
- Red error spans for withdrawals with recorded exceptions
- Transfer traces containing 4 nested DB child spans
- Long transfer traces (4 – 7 s) with `downstream_timeout` and `retry_attempt` events

Click any span to inspect custom attributes: `account.id`, `withdrawal.amount`, `transfer.from_account`, `bug.*`, `db.artificial_sleep_seconds`.

---

### 2. Metrics Explorer

**Navigate to:** Observe and Explore > Metrics

| Suggested query | What it shows |
|---|---|
| `banking.withdrawal.failures.total` | Withdrawal error count over time |
| `banking.http.request.duration` split by `route` | Latency distribution per endpoint |
| `banking.transfer.amount` | Histogram of transfer amounts |
| `banking.withdrawal.failures.total` / `banking.withdrawal.attempts.total` | Withdrawal failure ratio |

---

### 3. SLO Configuration

**Navigate to:** Observe and Explore > SLOs > Create SLO

**Suggested SLO — Withdrawal Availability:**

| Field | Value |
|---|---|
| Name | `Withdrawal Success Rate` |
| Numerator | `banking.withdrawal.attempts.total` minus `banking.withdrawal.failures.total` |
| Denominator | `banking.withdrawal.attempts.total` |
| Target | `80%` (the 20% bug rate pushes you just below) |
| Warning | `85%` |
| Timeframe | Last 1 hour |

**Suggested SLO — Account Inquiry Latency:**

| Field | Value |
|---|---|
| Name | `Account Inquiry P95 Latency` |
| Metric | `banking.http.request.duration` (P95), filtered by `route=/accounts/{account_id}` |
| Target | `< 2 s` |

---

### 4. Log Viewer

**Navigate to:** Observe and Explore > Logs

Filter by `service.name = banking-api`. Each log entry carries `trace_id` and `span_id` attributes — click the trace link on any entry to jump directly to the corresponding span in Distributed Tracing.

---

### 5. Alerting

**Navigate to:** Alerts > Create metric event

| Field | Value |
|---|---|
| Metric | `banking.withdrawal.failures.total` |
| Condition | `> 3` per minute |
| Severity | Error |

---

## Custom Metrics Reference

All metrics are exported every **15 seconds**.

| Metric | Type | Unit | Description |
|---|---|---|---|
| `banking.http.requests.total` | Counter | `1` | Total HTTP requests received |
| `banking.http.errors.total` | Counter | `1` | Total HTTP 5xx errors |
| `banking.withdrawal.attempts.total` | Counter | `1` | Total withdrawal attempts |
| `banking.withdrawal.failures.total` | Counter | `1` | Total failed withdrawals |
| `banking.transfer.attempts.total` | Counter | `1` | Total transfer attempts |
| `banking.transfer.failures.total` | Counter | `1` | Total failed transfers |
| `banking.db.query.duration` | Histogram | `s` | Database operation duration |
| `banking.http.request.duration` | Histogram | `s` | End-to-end HTTP request duration |
| `banking.transfer.amount` | Histogram | `USD` | Transfer amount distribution |

---

## Test Accounts Reference

| Account ID | Owner | Type | Starting Balance |
|---|---|---|---|
| ACC001 | Test User 01 | SAVINGS | $32,007.40 |
| ACC002 | Test User 02 | BUSINESS | $1,348.04 |
| ACC003 | Test User 03 | CHECKING | $13,823.96 |
| ACC004 | Test User 04 | SAVINGS | $11,238.22 |
| ACC005 | Test User 05 | BUSINESS | $36,849.91 |
| ACC006 | Test User 06 | CHECKING | $33,867.30 |
| ACC007 | Test User 07 | SAVINGS | $44,619.76 |
| ACC008 | Test User 08 | BUSINESS | $4,438.25 |
| ACC009 | Test User 09 | CHECKING | $21,153.90 |
| ACC010 | Test User 10 | SAVINGS | $1,586.88 |
| ACC011 | Test User 11 | BUSINESS | $11,010.03 |
| ACC012 | Test User 12 | CHECKING | $25,317.23 |
| ACC013 | Test User 13 | SAVINGS | $1,424.14 |
| ACC014 | Test User 14 | BUSINESS | $10,022.00 |
| ACC015 | Test User 15 | CHECKING | $32,529.23 |
| ACC016 | Test User 16 | SAVINGS | $27,292.58 |
| ACC017 | Test User 17 | BUSINESS | $11,099.99 |
| ACC018 | Test User 18 | CHECKING | $29,504.36 |
| ACC019 | Test User 19 | SAVINGS | $40,490.58 |
| ACC020 | Test User 20 | BUSINESS | $424.29 |

---

## OpenTelemetry Details

### Resource attributes (attached to every span, metric, and log)

```
service.name           = banking-api
service.version        = 1.0.0
deployment.environment = demo
telemetry.sdk.language = python
```

### Span names

| Span | Source |
|---|---|
| `GET /accounts/{account_id}` | Auto — FastAPI instrumentation |
| `POST /accounts/{account_id}/withdrawal` | Auto — FastAPI instrumentation |
| `POST /transfers` | Auto — FastAPI instrumentation |
| `account.inquiry` | Custom — wraps the slow-query path |
| `account.withdrawal` | Custom — wraps withdrawal logic |
| `account.transfer` | Custom — wraps transfer logic |
| `db.fetch_account` | Custom — N+1 per-account fetch |
| `db.fetch_recent_transactions` | Custom — N+1 per-account history fetch |
| `SELECT banking.accounts` etc. | Auto — SQLAlchemy instrumentation |

### Export schedule

| Signal | Processor | Schedule |
|---|---|---|
| Traces | `BatchSpanProcessor` | Flushed on span end (batched) |
| Metrics | `PeriodicExportingMetricReader` | Every 15 seconds |
| Logs | `BatchLogRecordProcessor` | Flushed on log emit (batched) |

---

## Troubleshooting

**No data in Dynatrace after 60 seconds**
- Confirm the API is running: `curl http://localhost:8000/health`
- Check terminal or `docker logs banking-api` for lines like `WARNING: DT_ENDPOINT_BASE or DT_API_TOKEN is not set`
- Verify the API token has the scopes: `openTelemetryTrace.ingest`, `metrics.ingest`, `logs.ingest`

**`ModuleNotFoundError: No module named 'opentelemetry'`**
- On Windows, use `py -3 -m pip install -r requirements.txt` to target the correct interpreter
- Confirm installation: `py -3 -c "import opentelemetry; print('ok')"`

**Playwright `Connection closed` errors when stopping the load generator**
- Normal behaviour — `Ctrl+C` kills the Playwright browser IPC mid-flight
- Requests already received by the API are fully traced; only the in-flight request at the moment of kill is lost

**Account balances run to zero**
- Re-seed: `python seed.py` (skips existing accounts, adds none back)
- Full reset: delete `banking.db`, then run `python seed.py`
- Docker full reset: `docker rm -f banking-api && docker volume rm banking-db`, then recreate

**Port 8000 already in use**
- Local: `python -m uvicorn app.main:app --port 8001`
- Docker: change `-p 8000:8000` to `-p 8001:8000`
- Update `BASE_URL` in `load_generator.py` to match the new port

**Docker load generator cannot reach the API**
- Linux: use `--network host`
- macOS / Windows: use `-e BASE_URL="http://host.docker.internal:8000"` (no `--network host`)

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115.5 | Web framework |
| `uvicorn[standard]` | 0.32.1 | ASGI server |
| `sqlalchemy` | 2.0.36 | ORM + SQLite driver |
| `opentelemetry-sdk` | 1.28.2 | OTel core SDK |
| `opentelemetry-exporter-otlp-proto-http` | 1.28.2 | OTLP/HTTP exporter for all three signals |
| `opentelemetry-instrumentation-fastapi` | 0.49b2 | Auto-instrument FastAPI routes |
| `opentelemetry-instrumentation-sqlalchemy` | 0.49b2 | Auto-instrument SQLAlchemy queries |
| `opentelemetry-instrumentation-logging` | 0.49b2 | Bridge Python logging into OTel |
| `pydantic` | 2.10.3 | Request/response validation |
| `pydantic-settings` | 2.6.1 | Settings loaded from env vars / `.env` |
| `playwright` | 1.49.0 | Async HTTP client for load generator |
