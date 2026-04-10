from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TransactionStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    REFUNDED = "REFUNDED"
    REVERSED = "REVERSED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    supabase_user_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)
    pin_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    held_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    beneficiary_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120))
    identifier: Mapped[str] = mapped_column(String(120))
    rail_type: Mapped[str] = mapped_column(String(30), default="wallet")
    is_verified: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_transactions_idempotency_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    auth_context_id: Mapped[str] = mapped_column(String(64), index=True)
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    payment_method_id: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"),
        default=TransactionStatus.PENDING,
    )
    failure_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OnboardingSession(Base):
    __tablename__ = "onboarding_sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    challenge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    code: Mapped[str] = mapped_column(String(10))
    destination_masked: Mapped[str] = mapped_column(String(200))
    verified: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
