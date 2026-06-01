import logging
import random
import time

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.schemas import AccountResponse
from app.telemetry.metrics import db_query_duration, http_errors_total, http_requests_total

logger = logging.getLogger(__name__)
router = APIRouter(tags=["accounts"])
tracer = trace.get_tracer(__name__)


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: str, db: Session = Depends(get_db)):
    http_requests_total.add(1, {"endpoint": "account_inquiry"})

    with tracer.start_as_current_span("account.inquiry") as span:
        span.set_attribute("account.id", account_id)
        span.set_attribute("bug.slow_query", True)

        # Intentional bug: artificial sleep simulating slow unindexed lookup
        sleep_duration = random.uniform(0.5, 1.5)
        time.sleep(sleep_duration)
        span.set_attribute("db.artificial_sleep_seconds", round(sleep_duration, 3))

        t0 = time.perf_counter()
        # Intentional bug: filter on unindexed account_type first → full table scan
        account = (
            db.query(Account)
            .filter(Account.account_type != "CLOSED")
            .filter(Account.account_id == account_id)
            .first()
        )
        db_query_duration.record(
            time.perf_counter() - t0,
            {"endpoint": "account_inquiry", "operation": "select"},
        )

        if account is None:
            span.set_status(StatusCode.ERROR, "Account not found")
            http_errors_total.add(1, {"endpoint": "account_inquiry", "status_code": "404"})
            logger.warning("Account not found: %s", account_id)
            raise HTTPException(status_code=404, detail="Account not found")

        span.set_attribute("account.type", account.account_type)
        span.set_attribute("account.balance", account.balance)
        logger.info("Account inquiry successful: %s balance=%.2f", account_id, account.balance)
        return AccountResponse.model_validate(account)
