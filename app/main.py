import logging
import time

from fastapi import FastAPI, Request, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Bootstrap OTel before importing routers or metrics
from app.telemetry.setup import setup_telemetry

setup_telemetry()

# Now safe to import instrumented modules
from app.database import Base, engine  # noqa: E402
from app.routers import accounts, health, transfers, withdrawals  # noqa: E402
from app.telemetry.metrics import http_errors_total, http_request_duration, http_requests_total  # noqa: E402

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Banking API Demo",
    description="SLO demo — intentional bugs included for distributed tracing visibility",
    version="1.0.0",
)

FastAPIInstrumentor.instrument_app(app)

logger = logging.getLogger(__name__)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next) -> Response:
    t0 = time.perf_counter()
    response: Response = await call_next(request)
    duration = time.perf_counter() - t0

    route = request.url.path
    http_request_duration.record(duration, {"route": route, "method": request.method, "status_code": str(response.status_code)})

    if response.status_code >= 500:
        http_errors_total.add(1, {"route": route, "status_code": str(response.status_code)})

    return response


app.include_router(health.router)
app.include_router(accounts.router, prefix="/accounts")
app.include_router(withdrawals.router, prefix="/accounts")
app.include_router(transfers.router)

logger.info("Banking API started — OTel instrumentation active")
