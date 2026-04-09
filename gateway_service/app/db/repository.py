from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Beneficiary,
    LedgerEntry,
    Transaction,
    TransactionStatus,
)


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_transaction_by_idempotency(self, idempotency_key: str) -> Transaction | None:
        stmt = select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        return self.db.scalar(stmt)

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        stmt = select(Transaction).where(Transaction.id == transaction_id)
        return self.db.scalar(stmt)

    def get_verified_beneficiary(self, owner_user_id: str, beneficiary_id: str) -> Beneficiary | None:
        stmt = select(Beneficiary).where(
            Beneficiary.owner_user_id == owner_user_id,
            Beneficiary.id == beneficiary_id,
            Beneficiary.is_verified.is_(True),
            Beneficiary.status == "active",
        )
        return self.db.scalar(stmt)

    def get_account_for_user(self, user_id: str, currency: str) -> Account | None:
        stmt = select(Account).where(
            Account.user_id == user_id,
            Account.currency == currency,
            Account.status == "active",
        )
        return self.db.scalar(stmt)

    def create_transaction(
        self,
        idempotency_key: str,
        payer_user_id: str,
        beneficiary_id: str,
        amount: Decimal,
        currency: str,
        payment_method_id: str,
        purpose: str,
    ) -> Transaction:
        row = Transaction(
            id=f"txn_{uuid4().hex[:20]}",
            idempotency_key=idempotency_key,
            payer_user_id=payer_user_id,
            beneficiary_id=beneficiary_id,
            amount=amount,
            currency=currency,
            payment_method_id=payment_method_id,
            purpose=purpose,
            status=TransactionStatus.PENDING,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def mark_failed(self, txn: Transaction, code: str, reason: str) -> None:
        txn.status = TransactionStatus.FAILED
        txn.failure_code = code
        txn.failure_reason = reason

    def mark_success(self, txn: Transaction, external_ref: str | None = None) -> None:
        txn.status = TransactionStatus.SUCCESS
        txn.external_ref = external_ref
        txn.failure_code = None
        txn.failure_reason = None

    def create_ledger_entry(
        self,
        transaction_id: str,
        account_id,
        entry_type: str,
        amount: Decimal,
        currency: str,
        before: Decimal,
        after: Decimal,
    ) -> None:
        self.db.add(
            LedgerEntry(
                transaction_id=transaction_id,
                account_id=account_id,
                entry_type=entry_type,
                amount=amount,
                currency=currency,
                balance_before=before,
                balance_after=after,
            )
        )
