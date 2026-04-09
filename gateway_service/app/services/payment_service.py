from sqlalchemy.orm import Session

from app.db.models import TransactionStatus
from app.db.repository import PaymentRepository
from app.services.auth_context_store import auth_context_store
from app.services.provider_factory import build_provider
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


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = build_provider(db)
        self.repo = PaymentRepository(db)

    def validate(self, payload: PaymentValidateRequest) -> PaymentValidateResponse:
        return self.provider.validate(payload)

    def transfer(self, payload: PaymentTransferRequest) -> PaymentTransferResponse:
        existing = self.repo.get_transaction_by_idempotency(payload.idempotency_key)
        if existing:
            replay_status = existing.status.value if existing.status in {
                TransactionStatus.SUCCESS,
                TransactionStatus.FAILED,
                TransactionStatus.PENDING,
            } else "FAILED"
            return PaymentTransferResponse(
                transaction_id=existing.id,
                status=replay_status,
                message="Idempotent replay. Returning original transaction.",
                timestamp=existing.updated_at.isoformat() if existing.updated_at else None,
                external_ref=existing.external_ref,
                failure_code=existing.failure_code,
            )

        auth_ok = auth_context_store.consume(
            auth_context_id=payload.auth_context_id,
            user_id=payload.payer_user_id,
            session_id=payload.session_id,
        )
        if not auth_ok:
            return PaymentTransferResponse(
                transaction_id="",
                status="FAILED",
                message="Invalid or expired auth context.",
                failure_code="AUTH_CONTEXT_INVALID",
            )
        return self.provider.transfer(payload)

    def get_status(self, transaction_id: str) -> TransactionStatusResponse:
        return self.provider.get_status(transaction_id)

    def get_balance(self, requestor_user_id: str, target_user_id: str) -> BalanceResponse:
        return self.provider.get_balance(requestor_user_id, target_user_id)

    def verify_receiver(self, payload: VerifyReceiverRequest) -> VerifyReceiverResponse:
        return self.provider.verify_receiver(payload)

    def refund(self, payload: RefundRequest) -> PaymentTransferResponse:
        return self.provider.refund(payload)

    def reverse(self, payload: ReversalRequest) -> PaymentTransferResponse:
        return self.provider.reverse(payload)
