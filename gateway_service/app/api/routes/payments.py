from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.security import require_internal_service_token
from app.db.session import get_db
from app.services.payment_service import PaymentService
from shared_lib.contracts.payment import (
    BalanceResponse,
    PaymentTransferRequest,
    PaymentTransferResponse,
    PaymentValidateRequest,
    PaymentValidateResponse,
    RefundRequest,
    ReversalRequest,
    TransactionStatusResponse,
    VerifyReceiverRequest,
    VerifyReceiverResponse,
)

router = APIRouter(tags=["payments"], dependencies=[Depends(require_internal_service_token)])


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


@router.get("/accounts/{target_user_id}/balance", response_model=BalanceResponse)
def get_balance(
    target_user_id: str,
    requestor_user_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> BalanceResponse:
    try:
        return PaymentService(db).get_balance(requestor_user_id, target_user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/receivers/verify", response_model=VerifyReceiverResponse)
def verify_receiver(
    payload: VerifyReceiverRequest,
    db: Session = Depends(get_db),
) -> VerifyReceiverResponse:
    return PaymentService(db).verify_receiver(payload)
