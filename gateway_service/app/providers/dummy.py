from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import TransactionStatus
from app.db.repository import PaymentRepository
from app.providers.base import PaymentProvider
import re

from shared_lib.contracts.payment import (
    AddBeneficiaryRequest,
    AddBeneficiaryResponse,
    BalanceResponse,
    BeneficiaryItem,
    BeneficiaryListResponse,
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
        timestamp = datetime.now(UTC).isoformat()
        existing = self.repo.get_transaction_by_idempotency(payload.idempotency_key)
        if existing:
            status = existing.status.value if existing.status.value in {"SUCCESS", "FAILED", "PENDING"} else "FAILED"
            return PaymentTransferResponse(
                transaction_id=existing.id,
                status=status,
                message="Idempotent replay.",
                timestamp=timestamp,
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
            session_id=payload.session_id,
            auth_context_id=payload.auth_context_id,
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
                timestamp=timestamp,
                failure_code=payload.simulate_failure_code,
            )

        if not validation.valid:
            self.repo.mark_failed(txn, "VALIDATION_FAILED", validation.reason or "Validation failed")
            self.db.commit()
            return PaymentTransferResponse(
                transaction_id=txn.id,
                status="FAILED",
                message=validation.reason or "Validation failed.",
                timestamp=timestamp,
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
                timestamp=timestamp,
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
                timestamp=timestamp,
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
            timestamp=timestamp,
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

    def get_balance(self, requestor_user_id: str, target_user_id: str) -> BalanceResponse:
        if requestor_user_id != target_user_id:
            raise PermissionError("Access denied: you can only fetch your own balance.")
        account = self.repo.get_account_for_user(target_user_id, "AED")
        if not account:
            raise LookupError("Account not found.")
        return BalanceResponse(
            user_id=target_user_id,
            currency="AED",
            available_balance=Decimal(account.available_balance),
        )

    def verify_receiver(self, payload: VerifyReceiverRequest) -> VerifyReceiverResponse:
        hint = payload.receiver_hint.strip()

        # 1. Look up existing beneficiary by name, email, or id first.
        existing = self.repo.get_beneficiary_by_hint(payload.sender_user_id, hint)
        if existing:
            verification_status = "verified" if existing.is_verified else "unverified"
            return VerifyReceiverResponse(
                found=True,
                beneficiary_id=existing.id,
                display_name=existing.display_name,
                masked_identifier=self._mask_identifier(existing.identifier),
                verification_status=verification_status,
            )

        # 2. If hint looks like an email, try to find the user and auto-create beneficiary.
        if not self._is_email(hint):
            return VerifyReceiverResponse(found=False, verification_status="not_found")

        receiver_user = self.repo.get_user_by_email(hint.lower())
        if not receiver_user or receiver_user.status != "active":
            return VerifyReceiverResponse(found=False, verification_status="not_found")

        if receiver_user.id == payload.sender_user_id:
            return VerifyReceiverResponse(found=False, verification_status="not_found")

        beneficiary = self.repo.get_or_create_verified_beneficiary_for_user(
            owner_user_id=payload.sender_user_id,
            receiver_user_id=receiver_user.id,
            receiver_email=hint.lower(),
            display_name=receiver_user.full_name or (receiver_user.email or receiver_user.id),
        )
        self.db.commit()

        verification_status = "verified" if beneficiary.is_verified else "unverified"
        return VerifyReceiverResponse(
            found=True,
            beneficiary_id=beneficiary.id,
            display_name=beneficiary.display_name,
            masked_identifier=self._mask_identifier(beneficiary.identifier),
            verification_status=verification_status,
        )

    def add_beneficiary(self, payload: AddBeneficiaryRequest) -> AddBeneficiaryResponse:
        email = payload.email.strip().lower()
        receiver_user = self.repo.get_user_by_email(email)
        if not receiver_user or receiver_user.status != "active":
            return AddBeneficiaryResponse(
                beneficiary_id="",
                display_name=payload.display_name,
                masked_identifier=self._mask_identifier(email),
                status="not_found",
            )

        existing = self.repo.get_beneficiary_by_hint(payload.owner_user_id, email)
        status = "already_exists" if existing else "added"

        beneficiary = self.repo.get_or_create_verified_beneficiary_for_user(
            owner_user_id=payload.owner_user_id,
            receiver_user_id=receiver_user.id,
            receiver_email=email,
            display_name=payload.display_name,
        )
        self.db.commit()

        return AddBeneficiaryResponse(
            beneficiary_id=beneficiary.id,
            display_name=beneficiary.display_name,
            masked_identifier=self._mask_identifier(beneficiary.identifier),
            status=status,
        )

    def list_beneficiaries(self, owner_user_id: str) -> BeneficiaryListResponse:
        rows = self.repo.get_beneficiaries_for_user(owner_user_id)
        return BeneficiaryListResponse(
            beneficiaries=[
                BeneficiaryItem(
                    beneficiary_id=row.id,
                    display_name=row.display_name,
                    masked_identifier=self._mask_identifier(row.identifier),
                    is_verified=row.is_verified,
                )
                for row in rows
            ]
        )

    def refund(self, payload: RefundRequest) -> PaymentTransferResponse:
        txn = self.repo.get_transaction(payload.transaction_id)
        if not txn:
            return PaymentTransferResponse(
                transaction_id=payload.transaction_id,
                status="FAILED",
                message="Transaction not found.",
                timestamp=datetime.now(UTC).isoformat(),
                failure_code="NOT_FOUND",
            )
        txn.status = TransactionStatus.REFUNDED
        txn.failure_reason = payload.reason
        self.db.commit()
        return PaymentTransferResponse(
            transaction_id=txn.id,
            status="SUCCESS",
            message="Refund simulated.",
            timestamp=datetime.now(UTC).isoformat(),
        )

    def reverse(self, payload: ReversalRequest) -> PaymentTransferResponse:
        txn = self.repo.get_transaction(payload.transaction_id)
        if not txn:
            return PaymentTransferResponse(
                transaction_id=payload.transaction_id,
                status="FAILED",
                message="Transaction not found.",
                timestamp=datetime.now(UTC).isoformat(),
                failure_code="NOT_FOUND",
            )
        txn.status = TransactionStatus.REVERSED
        txn.failure_reason = payload.reason
        self.db.commit()
        return PaymentTransferResponse(
            transaction_id=txn.id,
            status="SUCCESS",
            message="Reversal simulated.",
            timestamp=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _is_email(hint: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", hint.strip()))

    @staticmethod
    def _mask_identifier(identifier: str) -> str:
        if len(identifier) <= 4:
            return "*" * len(identifier)
        return f"{identifier[:4]}{'*' * (len(identifier) - 8)}{identifier[-4:]}"
