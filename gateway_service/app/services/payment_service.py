from sqlalchemy.orm import Session

from app.services.provider_factory import build_provider
from shared_lib.contracts.payment import (
    PaymentTransferRequest,
    PaymentTransferResponse,
    PaymentValidateRequest,
    PaymentValidateResponse,
    RefundRequest,
    ReversalRequest,
    TransactionStatusResponse,
)


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.provider = build_provider(db)

    def validate(self, payload: PaymentValidateRequest) -> PaymentValidateResponse:
        return self.provider.validate(payload)

    def transfer(self, payload: PaymentTransferRequest) -> PaymentTransferResponse:
        return self.provider.transfer(payload)

    def get_status(self, transaction_id: str) -> TransactionStatusResponse:
        return self.provider.get_status(transaction_id)

    def refund(self, payload: RefundRequest) -> PaymentTransferResponse:
        return self.provider.refund(payload)

    def reverse(self, payload: ReversalRequest) -> PaymentTransferResponse:
        return self.provider.reverse(payload)
