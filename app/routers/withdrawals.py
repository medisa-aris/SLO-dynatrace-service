import logging
import random
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Transaction
from app.schemas import WithdrawalRequest, WithdrawalResponse
from app.telemetry.metrics import (
    db_query_duration,
    http_errors_total,
    http_requests_total,
    withdrawal_attempts_total,
    withdrawal_failures_total,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["withdrawals"])
tracer = trace.get_tracer(__name__)


@router.post("/{account_id}/withdrawal", response_model=WithdrawalResponse)
def withdrawal(account_id: str, request: WithdrawalRequest, db: Session = Depends(get_db)):
    http_requests_total.add(1, {"endpoint": "withdrawal"})
    withdrawal_attempts_total.add(1, {"account_id": account_id})

    with tracer.start_as_current_span("account.withdrawal") as span:
        span.set_attribute("account.id", account_id)
        span.set_attribute("withdrawal.amount", request.amount)
        span.set_attribute("withdrawal.currency", request.currency)

        # Intentional bug: ~20% random internal server error
        if random.random() < 0.20:
            err = RuntimeError("Payment processor unavailable — upstream timeout")
            span.set_status(StatusCode.ERROR, str(err))
            span.set_attribute("bug.random_failure", True)
            span.record_exception(err)
            withdrawal_failures_total.add(1, {"account_id": account_id, "reason": "random_failure"})
            http_errors_total.add(1, {"endpoint": "withdrawal", "status_code": "500"})
            logger.error("Withdrawal failed (random fault): account=%s amount=%.2f", account_id, request.amount)
            raise HTTPException(status_code=500, detail="Internal processing error — payment processor unavailable")

        t0 = time.perf_counter()
        account = db.query(Account).filter(Account.account_id == account_id).first()
        db_query_duration.record(
            time.perf_counter() - t0,
            {"endpoint": "withdrawal", "operation": "select_account"},
        )

        if account is None:
            span.set_status(StatusCode.ERROR, "Account not found")
            withdrawal_failures_total.add(1, {"account_id": account_id, "reason": "not_found"})
            http_errors_total.add(1, {"endpoint": "withdrawal", "status_code": "404"})
            raise HTTPException(status_code=404, detail="Account not found")

        if not account.is_active:
            span.set_status(StatusCode.ERROR, "Account inactive")
            withdrawal_failures_total.add(1, {"account_id": account_id, "reason": "inactive"})
            raise HTTPException(status_code=422, detail="Account is inactive")

        if account.balance < request.amount:
            span.set_status(StatusCode.ERROR, "Insufficient funds")
            withdrawal_failures_total.add(1, {"account_id": account_id, "reason": "insufficient_funds"})
            raise HTTPException(status_code=422, detail="Insufficient funds")

        account.balance -= request.amount
        txn = Transaction(
            transaction_id=str(uuid4()),
            from_account=account_id,
            amount=request.amount,
            transaction_type="withdrawal",
            status="success",
        )
        db.add(txn)

        t1 = time.perf_counter()
        db.commit()
        db_query_duration.record(
            time.perf_counter() - t1,
            {"endpoint": "withdrawal", "operation": "commit"},
        )

        span.set_attribute("account.new_balance", account.balance)
        span.set_attribute("transaction.id", txn.transaction_id)
        logger.info(
            "Withdrawal success: account=%s amount=%.2f new_balance=%.2f txn=%s",
            account_id, request.amount, account.balance, txn.transaction_id,
        )
        return WithdrawalResponse(
            transaction_id=txn.transaction_id,
            account_id=account_id,
            amount=request.amount,
            new_balance=account.balance,
            status="success",
        )
