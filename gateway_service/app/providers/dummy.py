from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import TransactionStatus
from app.db.repository import PaymentRepository
from app.providers.base import PaymentProvider
from shared_lib.contracts.payment import (
    PaymentTransferRequest,
    PaymentTransferResponse,
    PaymentValidateRequest,
    PaymentValidateResponse,
    RefundRequest,
    ReversalRequest,
    TransactionStatusResponse,
)


class DummyPaymentProvider(PaymentProvider):
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PaymentRepository(db)

    def validate(self, payload: PaymentValidateRequest) -> PaymentValidateResponse:
        beneficiary = self.repo.get_verified_beneficiary(payload.payer_user_id, payload.beneficiary_id)
        if not beneficiary:
            return PaymentValidateResponse(valid=False, reason="beneficiary_not_verified")

        payer_account = self.repo.get_account_for_user(payload.payer_user_id, payload.currency)
        if not payer_account:
            return PaymentValidateResponse(valid=False, reason="payer_account_missing")
        if Decimal(payer_account.available_balance) < payload.amount:
            return PaymentValidateResponse(valid=False, reason="insufficient_funds")

        return PaymentValidateResponse(valid=True, reason=None)

    def transfer(self, payload: PaymentTransferRequest) -> PaymentTransferResponse:
        existing = self.repo.get_transaction_by_idempotency(payload.idempotency_key)
        if existing:
            status = existing.status.value if existing.status.value in {"SUCCESS", "FAILED", "PENDING"} else "FAILED"
            return PaymentTransferResponse(
                transaction_id=existing.id,
                status=status,
                message="Idempotent replay.",
                external_ref=existing.external_ref,
                failure_code=existing.failure_code,
            )

        validation = self.validate(
            PaymentValidateRequest(
                payer_user_id=payload.payer_user_id,
                beneficiary_id=payload.beneficiary_id,
                amount=payload.amount,
                currency=payload.currency,
                payment_method_id=payload.payment_method_id,
            )
        )
        txn = self.repo.create_transaction(
            idempotency_key=payload.idempotency_key,
            payer_user_id=payload.payer_user_id,
            beneficiary_id=payload.beneficiary_id,
            amount=payload.amount,
            currency=payload.currency,
            payment_method_id=payload.payment_method_id,
            purpose=payload.purpose,
        )

        if payload.simulate_failure_code:
            self.repo.mark_failed(txn, payload.simulate_failure_code, "Simulated failure")
            self.db.commit()
            return PaymentTransferResponse(
                transaction_id=txn.id,
                status="FAILED",
                message="Simulated failure.",
                failure_code=payload.simulate_failure_code,
            )

        if not validation.valid:
            self.repo.mark_failed(txn, "VALIDATION_FAILED", validation.reason or "Validation failed")
            self.db.commit()
            return PaymentTransferResponse(
                transaction_id=txn.id,
                status="FAILED",
                message=validation.reason or "Validation failed.",
                failure_code="VALIDATION_FAILED",
            )

        beneficiary = self.repo.get_verified_beneficiary(payload.payer_user_id, payload.beneficiary_id)
        assert beneficiary is not None
        payer_account = self.repo.get_account_for_user(payload.payer_user_id, payload.currency)
        assert payer_account is not None
        beneficiary_user_id = beneficiary.beneficiary_user_id or beneficiary.owner_user_id
        beneficiary_account = self.repo.get_account_for_user(beneficiary_user_id, payload.currency)
        if not beneficiary_account:
            self.repo.mark_failed(txn, "BENEFICIARY_ACCOUNT_MISSING", "Beneficiary account missing.")
            self.db.commit()
            return PaymentTransferResponse(
                transaction_id=txn.id,
                status="FAILED",
                message="Beneficiary account missing.",
                failure_code="BENEFICIARY_ACCOUNT_MISSING",
            )

        payer_before = Decimal(payer_account.available_balance)
        beneficiary_before = Decimal(beneficiary_account.available_balance)
        payer_after = payer_before - payload.amount
        beneficiary_after = beneficiary_before + payload.amount
        if payer_after < 0:
            self.repo.mark_failed(txn, "INSUFFICIENT_FUNDS", "Insufficient funds.")
            self.db.commit()
            return PaymentTransferResponse(
                transaction_id=txn.id,
                status="FAILED",
                message="Insufficient funds.",
                failure_code="INSUFFICIENT_FUNDS",
            )

        payer_account.available_balance = payer_after
        beneficiary_account.available_balance = beneficiary_after
        self.repo.create_ledger_entry(
            transaction_id=txn.id,
            account_id=payer_account.id,
            entry_type="debit",
            amount=payload.amount,
            currency=payload.currency,
            before=payer_before,
            after=payer_after,
        )
        self.repo.create_ledger_entry(
            transaction_id=txn.id,
            account_id=beneficiary_account.id,
            entry_type="credit",
            amount=payload.amount,
            currency=payload.currency,
            before=beneficiary_before,
            after=beneficiary_after,
        )
        external_ref = f"ext_{uuid4().hex[:14]}"
        self.repo.mark_success(txn, external_ref=external_ref)
        self.db.commit()
        return PaymentTransferResponse(
            transaction_id=txn.id,
            status="SUCCESS",
            message="Payment processed by dummy provider.",
            external_ref=external_ref,
        )

    def get_status(self, transaction_id: str) -> TransactionStatusResponse:
        txn = self.repo.get_transaction(transaction_id)
        if not txn:
            return TransactionStatusResponse(
                transaction_id=transaction_id,
                status="FAILED",
                amount=Decimal("0"),
                currency="AED",
                payer_user_id="",
                beneficiary_id="",
                failure_code="NOT_FOUND",
                failure_reason="Transaction not found.",
            )
        return TransactionStatusResponse(
            transaction_id=txn.id,
            status=txn.status.value,  # type: ignore[arg-type]
            amount=Decimal(txn.amount),
            currency=txn.currency,  # type: ignore[arg-type]
            payer_user_id=txn.payer_user_id,
            beneficiary_id=txn.beneficiary_id,
            failure_code=txn.failure_code,
            failure_reason=txn.failure_reason,
        )

    def refund(self, payload: RefundRequest) -> PaymentTransferResponse:
        txn = self.repo.get_transaction(payload.transaction_id)
        if not txn:
            return PaymentTransferResponse(
                transaction_id=payload.transaction_id,
                status="FAILED",
                message="Transaction not found.",
                failure_code="NOT_FOUND",
            )
        txn.status = TransactionStatus.REFUNDED
        txn.failure_reason = payload.reason
        self.db.commit()
        return PaymentTransferResponse(
            transaction_id=txn.id,
            status="SUCCESS",
            message="Refund simulated.",
        )

    def reverse(self, payload: ReversalRequest) -> PaymentTransferResponse:
        txn = self.repo.get_transaction(payload.transaction_id)
        if not txn:
            return PaymentTransferResponse(
                transaction_id=payload.transaction_id,
                status="FAILED",
                message="Transaction not found.",
                failure_code="NOT_FOUND",
            )
        txn.status = TransactionStatus.REVERSED
        txn.failure_reason = payload.reason
        self.db.commit()
        return PaymentTransferResponse(
            transaction_id=txn.id,
            status="SUCCESS",
            message="Reversal simulated.",
        )
