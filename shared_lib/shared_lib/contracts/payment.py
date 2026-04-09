from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class PaymentValidateRequest(BaseModel):
    payer_user_id: str
    beneficiary_id: str
    amount: Decimal = Field(..., gt=Decimal("0"))
    currency: Literal["AED"] = "AED"
    payment_method_id: str


class PaymentValidateResponse(BaseModel):
    valid: bool
    reason: str | None = None


class PaymentTransferRequest(BaseModel):
    payer_user_id: str
    session_id: str = Field(..., min_length=3)
    beneficiary_id: str
    amount: Decimal = Field(..., gt=Decimal("0"))
    currency: Literal["AED"] = "AED"
    payment_method_id: str
    purpose: str = Field(default="")
    auth_context_id: str
    idempotency_key: str = Field(..., min_length=8)
    simulate_failure_code: str | None = None


class PaymentTransferResponse(BaseModel):
    transaction_id: str
    status: Literal["SUCCESS", "FAILED", "PENDING"]
    message: str
    timestamp: str | None = None
    external_ref: str | None = None
    failure_code: str | None = None


class TransactionStatusResponse(BaseModel):
    transaction_id: str
    status: Literal["SUCCESS", "FAILED", "PENDING", "REFUNDED", "REVERSED"]
    amount: Decimal
    currency: Literal["AED"]
    payer_user_id: str
    beneficiary_id: str
    failure_code: str | None = None
    failure_reason: str | None = None


class RefundRequest(BaseModel):
    transaction_id: str
    amount: Decimal = Field(..., gt=Decimal("0"))
    reason: str = "requested_refund"


class ReversalRequest(BaseModel):
    transaction_id: str
    reason: str = "network_reversal"


class BalanceResponse(BaseModel):
    user_id: str
    currency: Literal["AED"]
    available_balance: Decimal


class VerifyReceiverRequest(BaseModel):
    sender_user_id: str
    receiver_hint: str = Field(..., min_length=1)


class VerifyReceiverResponse(BaseModel):
    found: bool
    beneficiary_id: str | None = None
    display_name: str | None = None
    masked_identifier: str | None = None
    verification_status: Literal["verified", "unverified", "not_found"] = "not_found"
