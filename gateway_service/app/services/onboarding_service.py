from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import OnboardingSession, OtpChallenge
from app.db.repository import PaymentRepository


class OnboardingStore:
    """DB-backed onboarding state (sessions, OTP challenges, verification)."""

    def create_session(self, db: Session, user_id: str, ttl_minutes: int = 30) -> str:
        token = f"onb_{secrets.token_hex(16)}"
        record = OnboardingSession(
            token=token,
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        db.add(record)
        db.flush()
        return token

    def validate_session(self, db: Session, token: str | None, user_id: str) -> bool:
        if not token:
            return False
        record = db.get(OnboardingSession, token)
        if not record:
            return False
        if record.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
            db.delete(record)
            db.flush()
            return False
        return record.user_id == user_id

    def start_otp(self, db: Session, user_id: str, destination: str) -> dict:
        challenge_id = f"chl_{secrets.token_hex(8)}"
        code = "000999"
        masked = _mask_destination(destination)
        record = OtpChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            code=code,
            destination_masked=masked,
            verified=False,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db.add(record)
        db.flush()
        return {"challenge_id": challenge_id, "destination_masked": masked}

    def verify_otp(self, db: Session, user_id: str, challenge_id: str, submitted_code: str) -> bool:
        record = db.get(OtpChallenge, challenge_id)
        if not record:
            return False
        if record.user_id != user_id:
            return False
        if record.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
            db.delete(record)
            db.flush()
            return False
        if submitted_code != record.code:
            return False
        record.verified = True
        db.flush()
        return True

    def is_verified(self, db: Session, user_id: str) -> bool:
        challenge = (
            db.query(OtpChallenge)
            .filter(OtpChallenge.user_id == user_id, OtpChallenge.verified.is_(True))
            .first()
        )
        return challenge is not None


onboarding_store = OnboardingStore()


class OnboardingService:
    def __init__(self, db: Session, store: OnboardingStore) -> None:
        self.db = db
        self.repo = PaymentRepository(db)
        self.store = store

    def signup(self, full_name: str, email: str, phone: str | None, password: str) -> dict:
        normalized_email = email.strip().lower()
        from app.services.user_service import UserService

        user_service = UserService(self.db)
        existing = self.repo.get_user_by_email(normalized_email)
        if existing:
            if existing.password_hash:
                expected = user_service._hash_password(existing.id, password)
                if existing.password_hash != expected:
                    raise PermissionError("Email is already registered with a different password.")
            else:
                user_service.set_user_password(user_id=existing.id, password=password)
                self.db.commit()

            token = self.store.create_session(self.db, existing.id)
            self.db.commit()
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
        user_service.set_user_password(user_id=user.id, password=password)
        token = self.store.create_session(self.db, user.id)
        self.db.commit()
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
        pin_digest = hashlib.sha256(f"prototype-pin::{user_id}::{pin}".encode("utf-8")).hexdigest()
        # Store pin hash directly on user row — no in-memory state needed
        from app.services.user_service import UserService

        UserService(self.db).set_user_pin(user_id=user_id, pin=pin)
        self.db.commit()

    def start_otp(self, user_id: str, destination: str) -> dict:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        data = self.store.start_otp(self.db, user_id=user_id, destination=destination)
        self.db.commit()
        return data

    def verify_otp(self, user_id: str, challenge_id: str, value: str) -> dict:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        verified = self.store.verify_otp(self.db, user_id=user_id, challenge_id=challenge_id, submitted_code=value)
        self.db.commit()
        return {
            "verified": verified,
            "message": "OTP verified." if verified else "OTP verification failed.",
        }

    def status(self, user_id: str) -> dict:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        email_verified = self.store.is_verified(self.db, user_id)
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
