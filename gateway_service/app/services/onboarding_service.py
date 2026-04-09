from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy.orm import Session

from app.db.repository import PaymentRepository


@dataclass
class OnboardingSessionRecord:
    user_id: str
    token: str
    expires_at: datetime


@dataclass
class OtpChallengeRecord:
    user_id: str
    challenge_id: str
    code: str
    expires_at: datetime
    destination_masked: str
    verified: bool = False


class OnboardingStore:
    def __init__(self) -> None:
        self._sessions: dict[str, OnboardingSessionRecord] = {}
        self._challenges: dict[str, OtpChallengeRecord] = {}
        self._pins: dict[str, str] = {}
        self._verified_users: set[str] = set()
        self._lock = Lock()

    def create_session(self, user_id: str, ttl_minutes: int = 30) -> str:
        token = f"onb_{secrets.token_hex(16)}"
        record = OnboardingSessionRecord(
            user_id=user_id,
            token=token,
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        with self._lock:
            self._sessions[token] = record
        return token

    def validate_session(self, token: str | None, user_id: str) -> bool:
        if not token:
            return False
        with self._lock:
            record = self._sessions.get(token)
            if not record:
                return False
            if record.expires_at <= datetime.now(UTC):
                self._sessions.pop(token, None)
                return False
            return record.user_id == user_id

    def set_pin(self, user_id: str, pin: str) -> None:
        digest = hashlib.sha256(f"prototype-pin::{user_id}::{pin}".encode("utf-8")).hexdigest()
        with self._lock:
            self._pins[user_id] = digest

    def start_otp(self, user_id: str, destination: str) -> OtpChallengeRecord:
        challenge_id = f"chl_{secrets.token_hex(8)}"
        code = "000999"
        destination_masked = _mask_destination(destination)
        record = OtpChallengeRecord(
            user_id=user_id,
            challenge_id=challenge_id,
            code=code,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            destination_masked=destination_masked,
            verified=False,
        )
        with self._lock:
            self._challenges[challenge_id] = record
        return record

    def verify_otp(self, user_id: str, challenge_id: str, submitted_code: str) -> bool:
        with self._lock:
            record = self._challenges.get(challenge_id)
            if not record:
                return False
            if record.user_id != user_id:
                return False
            if record.expires_at <= datetime.now(UTC):
                self._challenges.pop(challenge_id, None)
                return False
            if submitted_code != record.code:
                return False
            record.verified = True
            self._verified_users.add(user_id)
            return True

    def is_verified(self, user_id: str) -> bool:
        with self._lock:
            return user_id in self._verified_users


class OnboardingService:
    def __init__(self, db: Session, store: OnboardingStore) -> None:
        self.db = db
        self.repo = PaymentRepository(db)
        self.store = store

    def signup(self, full_name: str, email: str, phone: str | None) -> dict:
        normalized_email = email.strip().lower()
        existing = self.repo.get_user_by_email(normalized_email)
        if existing:
            token = self.store.create_session(existing.id)
            return {
                "user_id": existing.id,
                "supabase_user_id": existing.supabase_user_id,
                "email_verification_required": True,
                "onboarding_session_token": token,
            }

        user = self.repo.create_user_for_onboarding(
            email=normalized_email,
            full_name=full_name.strip(),
            phone=phone.strip() if phone else None,
        )
        self.repo.create_default_account(user.id)
        self.db.commit()
        token = self.store.create_session(user.id)
        return {
            "user_id": user.id,
            "supabase_user_id": user.supabase_user_id,
            "email_verification_required": True,
            "onboarding_session_token": token,
        }

    def set_pin(self, user_id: str, pin: str) -> None:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        self.store.set_pin(user_id=user_id, pin=pin)

    def start_otp(self, user_id: str, destination: str) -> dict:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        challenge = self.store.start_otp(user_id=user_id, destination=destination)
        return {
            "challenge_id": challenge.challenge_id,
            "destination_masked": challenge.destination_masked,
        }

    def verify_otp(self, user_id: str, challenge_id: str, value: str) -> dict:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        verified = self.store.verify_otp(user_id=user_id, challenge_id=challenge_id, submitted_code=value)
        return {
            "verified": verified,
            "message": "OTP verified." if verified else "OTP verification failed.",
        }

    def status(self, user_id: str) -> dict:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        email_verified = bool(user.supabase_user_id) or self.store.is_verified(user_id)
        return {
            "user_id": user.id,
            "email": user.email,
            "email_verified": email_verified,
            "status": user.status,
        }


def _mask_destination(destination: str) -> str:
    value = destination.strip()
    if not value:
        return "***"
    if "@" in value:
        local, _, domain = value.partition("@")
        masked_local = local[:2] + "*" * max(1, len(local) - 2)
        return f"{masked_local}@{domain}"
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


onboarding_store = OnboardingStore()
