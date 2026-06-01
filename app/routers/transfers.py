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
from app.schemas import TransferRequest, TransferResponse
from app.telemetry.metrics import (
    db_query_duration,
    http_errors_total,
    http_requests_total,
    transfer_amount,
    transfer_attempts_total,
    transfer_failures_total,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transfers"])
tracer = trace.get_tracer(__name__)


@router.post("/transfers", response_model=TransferResponse)
def transfer(request: TransferRequest, db: Session = Depends(get_db)):
    http_requests_total.add(1, {"endpoint": "transfer"})
    transfer_attempts_total.add(1, {"from_account": request.from_account_id})

    with tracer.start_as_current_span("account.transfer") as span:
        span.set_attribute("transfer.from_account", request.from_account_id)
        span.set_attribute("transfer.to_account", request.to_account_id)
        span.set_attribute("transfer.amount", request.amount)
        span.set_attribute("transfer.currency", request.currency)

        # Intentional bug: N+1 — fetch each account in a separate loop iteration
        account_ids = [request.from_account_id, request.to_account_id]
        accounts: dict[str, Account] = {}

        for acc_id in account_ids:
            with tracer.start_as_current_span("db.fetch_account") as inner_span:
                inner_span.set_attribute("account.id", acc_id)
                inner_span.set_attribute("bug.n_plus_one", True)

                t0 = time.perf_counter()
                acc = db.query(Account).filter(Account.account_id == acc_id).first()
                db_query_duration.record(
                    time.perf_counter() - t0,
                    {"endpoint": "transfer", "operation": "fetch_account"},
                )

                if acc is None:
                    span.set_status(StatusCode.ERROR, f"Account {acc_id} not found")
                    transfer_failures_total.add(1, {"reason": "account_not_found"})
                    http_errors_total.add(1, {"endpoint": "transfer", "status_code": "404"})
                    raise HTTPException(status_code=404, detail=f"Account {acc_id} not found")

                accounts[acc_id] = acc

            # Intentional bug: second N+1 — fetch recent transaction history per account
            # (no index on from_account → full table scan each time)
            with tracer.start_as_current_span("db.fetch_recent_transactions") as txn_span:
                txn_span.set_attribute("account.id", acc_id)
                txn_span.set_attribute("bug.n_plus_one", True)
                txn_span.set_attribute("bug.no_index_scan", True)

                t1 = time.perf_counter()
                _ = (
                    db.query(Transaction)
                    .filter(Transaction.from_account == acc_id)
                    .order_by(Transaction.created_at.desc())
                    .limit(10)
                    .all()
                )
                db_query_duration.record(
                    time.perf_counter() - t1,
                    {"endpoint": "transfer", "operation": "fetch_recent_txns"},
                )

        # Intentional bug: ~15% chance of simulated downstream timeout + retry
        if random.random() < 0.15:
            span.set_attribute("bug.simulated_timeout", True)
            timeout_sleep = random.uniform(3.0, 5.0)
            span.add_event("downstream_timeout", {"attempt": 1, "sleep_seconds": round(timeout_sleep, 2)})
            logger.warning("Transfer timeout on attempt 1 — retrying: from=%s to=%s", request.from_account_id, request.to_account_id)
            time.sleep(timeout_sleep)

            retry_sleep = random.uniform(1.0, 2.0)
            span.add_event("retry_attempt", {"attempt": 2, "sleep_seconds": round(retry_sleep, 2)})
            logger.warning("Transfer retry attempt 2: from=%s to=%s", request.from_account_id, request.to_account_id)
            time.sleep(retry_sleep)

        from_account = accounts[request.from_account_id]
        to_account = accounts[request.to_account_id]

        if from_account.balance < request.amount:
            span.set_status(StatusCode.ERROR, "Insufficient funds")
            transfer_failures_total.add(1, {"reason": "insufficient_funds"})
            raise HTTPException(status_code=422, detail="Insufficient funds")

        from_account.balance -= request.amount
        to_account.balance += request.amount

        txn = Transaction(
            transaction_id=str(uuid4()),
            from_account=request.from_account_id,
            to_account=request.to_account_id,
            amount=request.amount,
            transaction_type="transfer",
            status="success",
        )
        db.add(txn)

        t2 = time.perf_counter()
        db.commit()
        db_query_duration.record(
            time.perf_counter() - t2,
            {"endpoint": "transfer", "operation": "commit"},
        )

        transfer_amount.record(request.amount, {"currency": request.currency})
        span.set_attribute("transaction.id", txn.transaction_id)
        span.set_attribute("transfer.from_new_balance", from_account.balance)
        span.set_attribute("transfer.to_new_balance", to_account.balance)

        logger.info(
            "Transfer success: from=%s to=%s amount=%.2f txn=%s",
            request.from_account_id, request.to_account_id, request.amount, txn.transaction_id,
        )
        return TransferResponse(
            transaction_id=txn.transaction_id,
            from_account_id=request.from_account_id,
            to_account_id=request.to_account_id,
            amount=request.amount,
            status="success",
        )
