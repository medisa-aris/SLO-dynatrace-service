from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    account_id = Column(String(20), unique=True, nullable=False)
    owner_name = Column(String(100))
    # Intentionally no index on account_type or balance — causes full table scans
    account_type = Column(String(20))
    balance = Column(Float, default=0.0)
    currency = Column(String(3), default="USD")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    transaction_id = Column(String(36), unique=True, nullable=False)
    # Intentionally no FK indexes on from_account / to_account — forces table scans
    from_account = Column(String(20))
    to_account = Column(String(20), nullable=True)
    amount = Column(Float)
    transaction_type = Column(String(20))  # "withdrawal" | "transfer"
    status = Column(String(20))            # "success" | "failed"
    created_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(String(500), nullable=True)
