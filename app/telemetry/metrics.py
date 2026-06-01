from opentelemetry import metrics

_meter = metrics.get_meter("banking-api.metrics", version="1.0.0")

# --- Counters ---
http_requests_total = _meter.create_counter(
    "banking.http.requests.total",
    unit="1",
    description="Total HTTP requests received",
)

http_errors_total = _meter.create_counter(
    "banking.http.errors.total",
    unit="1",
    description="Total HTTP 5xx errors",
)

withdrawal_attempts_total = _meter.create_counter(
    "banking.withdrawal.attempts.total",
    unit="1",
    description="Total withdrawal attempts",
)

withdrawal_failures_total = _meter.create_counter(
    "banking.withdrawal.failures.total",
    unit="1",
    description="Total failed withdrawals",
)

transfer_attempts_total = _meter.create_counter(
    "banking.transfer.attempts.total",
    unit="1",
    description="Total transfer attempts",
)

transfer_failures_total = _meter.create_counter(
    "banking.transfer.failures.total",
    unit="1",
    description="Total failed transfers",
)

# --- Histograms ---
db_query_duration = _meter.create_histogram(
    "banking.db.query.duration",
    unit="s",
    description="Database query duration in seconds",
)

http_request_duration = _meter.create_histogram(
    "banking.http.request.duration",
    unit="s",
    description="HTTP request duration in seconds",
)

transfer_amount = _meter.create_histogram(
    "banking.transfer.amount",
    unit="USD",
    description="Transfer amount in USD",
)
