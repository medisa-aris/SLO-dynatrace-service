from pydantic import BaseModel


class AccountResponse(BaseModel):
    account_id: str
    owner_name: str
    account_type: str
    balance: float
    currency: str
    is_active: bool

    model_config = {"from_attributes": True}


class WithdrawalRequest(BaseModel):
    amount: float
    currency: str = "USD"
    reference: str | None = None


class WithdrawalResponse(BaseModel):
    transaction_id: str
    account_id: str
    amount: float
    new_balance: float
    status: str


class TransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: float
    currency: str = "USD"
    reference: str | None = None


class TransferResponse(BaseModel):
    transaction_id: str
    from_account_id: str
    to_account_id: str
    amount: float
    status: str
