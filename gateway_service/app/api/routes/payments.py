from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.payment_service import PaymentService
from shared_lib.contracts.payment import (
    PaymentTransferRequest,
    PaymentTransferResponse,
    PaymentValidateRequest,
    PaymentValidateResponse,
    RefundRequest,
    ReversalRequest,
    TransactionStatusResponse,
)

router = APIRouter(tags=["payments"])


@router.post("/payments/validate", response_model=PaymentValidateResponse)
def validate_payment(
    payload: PaymentValidateRequest,
    db: Session = Depends(get_db),
) -> PaymentValidateResponse:
    return PaymentService(db).validate(payload)


@router.post("/payments/transfer", response_model=PaymentTransferResponse)
def transfer_payment(
    payload: PaymentTransferRequest,
    db: Session = Depends(get_db),
) -> PaymentTransferResponse:
    return PaymentService(db).transfer(payload)


@router.get("/payments/{transaction_id}", response_model=TransactionStatusResponse)
def get_payment_status(
    transaction_id: str,
    db: Session = Depends(get_db),
) -> TransactionStatusResponse:
    return PaymentService(db).get_status(transaction_id)


@router.post("/payments/refund", response_model=PaymentTransferResponse)
def refund_payment(
    payload: RefundRequest,
    db: Session = Depends(get_db),
) -> PaymentTransferResponse:
    return PaymentService(db).refund(payload)


@router.post("/payments/reverse", response_model=PaymentTransferResponse)
def reverse_payment(
    payload: ReversalRequest,
    db: Session = Depends(get_db),
) -> PaymentTransferResponse:
    return PaymentService(db).reverse(payload)
