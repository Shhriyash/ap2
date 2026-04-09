from __future__ import annotations

from decimal import Decimal
import uuid
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Beneficiary,
    LedgerEntry,
    Transaction,
    TransactionStatus,
    User,
)


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_transaction_by_idempotency(self, idempotency_key: str) -> Transaction | None:
        stmt = select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        return self.db.scalar(stmt)

    def get_user_by_supabase_user_id(self, supabase_user_id: str) -> User | None:
        stmt = select(User).where(User.supabase_user_id == supabase_user_id)
        return self.db.scalar(stmt)

    def get_user_by_id(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        stmt = select(User).where(func.lower(User.email) == normalized)
        return self.db.scalar(stmt)

    def bind_supabase_user_id(self, user: User, supabase_user_id: str) -> User:
        existing = self.get_user_by_supabase_user_id(supabase_user_id)
        if existing and existing.id != user.id:
            raise ValueError("supabase_user_id_already_bound")
        user.supabase_user_id = supabase_user_id
        self.db.flush()
        return user

    def create_user_from_supabase(self, supabase_user_id: str, email: str, full_name: str | None = None) -> User:
        user = User(
            id=f"user_{uuid4().hex[:12]}",
            supabase_user_id=supabase_user_id,
            full_name=full_name or email.split("@")[0],
            email=email,
            status="active",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def create_user_for_onboarding(self, email: str, full_name: str, phone: str | None = None) -> User:
        user = User(
            id=f"user_{uuid4().hex[:12]}",
            supabase_user_id=None,
            full_name=full_name,
            phone=phone,
            email=email,
            status="active",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def create_default_account(self, user_id: str, currency: str = "AED") -> Account:
        account = Account(
            id=uuid.uuid4(),
            user_id=user_id,
            currency=currency,
            available_balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            status="active",
        )
        self.db.add(account)
        self.db.flush()
        return account

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

    def get_beneficiary_by_hint(self, owner_user_id: str, receiver_hint: str) -> Beneficiary | None:
        normalized = receiver_hint.strip().lower()
        stmt = select(Beneficiary).where(
            Beneficiary.owner_user_id == owner_user_id,
            Beneficiary.status == "active",
        )
        rows = self.db.scalars(stmt).all()
        for row in rows:
            if row.display_name.lower() == normalized:
                return row
            if row.identifier.lower() == normalized:
                return row
            if row.id.lower() == normalized:
                return row
        return None

    def get_or_create_verified_beneficiary_for_user(
        self,
        owner_user_id: str,
        receiver_user_id: str,
        receiver_email: str,
        display_name: str,
    ) -> Beneficiary:
        stmt = select(Beneficiary).where(
            Beneficiary.owner_user_id == owner_user_id,
            Beneficiary.beneficiary_user_id == receiver_user_id,
            Beneficiary.status == "active",
        )
        existing = self.db.scalar(stmt)
        if existing:
            existing.display_name = display_name
            existing.identifier = receiver_email
            existing.is_verified = True
            self.db.flush()
            return existing

        row = Beneficiary(
            id=f"ben_{uuid4().hex[:16]}",
            owner_user_id=owner_user_id,
            beneficiary_user_id=receiver_user_id,
            display_name=display_name,
            identifier=receiver_email,
            rail_type="wallet",
            is_verified=True,
            status="active",
        )
        self.db.add(row)
        self.db.flush()
        return row

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
        session_id: str,
        auth_context_id: str,
        beneficiary_id: str,
        amount: Decimal,
        currency: str,
        payment_method_id: str,
        purpose: str,
    ) -> Transaction:
        row = Transaction(
            id=self._generate_transaction_id(),
            idempotency_key=idempotency_key,
            payer_user_id=payer_user_id,
            session_id=session_id,
            auth_context_id=auth_context_id,
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

    @staticmethod
    def _generate_transaction_id() -> str:
        try:
            uuid7_fn = getattr(uuid, "uuid7", None)
            if uuid7_fn is None:
                raise AttributeError("uuid7 not available")
            v7 = uuid7_fn()
            return f"txn_{str(v7).replace('-', '')}"
        except Exception:
            return f"txn_{uuid.uuid4().hex}"
