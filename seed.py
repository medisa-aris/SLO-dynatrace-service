"""Populate the SQLite database with 20 test accounts. Idempotent."""

import random
import sys

from app.database import Base, SessionLocal, engine
from app.models import Account

random.seed(42)

ACCOUNT_TYPES = ["CHECKING", "SAVINGS", "BUSINESS"]

SEED_ACCOUNTS = [
    {
        "account_id": f"ACC{i:03d}",
        "owner_name": f"Test User {i:02d}",
        "account_type": ACCOUNT_TYPES[i % 3],
        "balance": round(random.uniform(100.0, 50000.0), 2),
        "currency": "USD",
        "is_active": True,
    }
    for i in range(1, 21)
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    inserted = 0
    skipped = 0
    try:
        for data in SEED_ACCOUNTS:
            existing = db.query(Account).filter(Account.account_id == data["account_id"]).first()
            if existing:
                skipped += 1
                continue
            db.add(Account(**data))
            inserted += 1
        db.commit()
    finally:
        db.close()

    print(f"Seed complete — inserted: {inserted}, skipped (already exist): {skipped}")
    for acc in SEED_ACCOUNTS:
        print(f"  {acc['account_id']}  {acc['owner_name']:<20}  {acc['account_type']:<10}  ${acc['balance']:>10.2f}")


if __name__ == "__main__":
    seed()
