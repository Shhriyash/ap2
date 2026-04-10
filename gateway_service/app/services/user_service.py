import hashlib

from sqlalchemy.orm import Session

from app.db.repository import PaymentRepository
from shared_lib.contracts.user import (
    UserIdentityResponse,
    UserLoginResolveRequest,
    UserPasswordLoginRequest,
    UserPinLoginRequest,
    UserPinVerifyRequest,
    UserProvisionRequest,
)


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PaymentRepository(db)

    def get_by_supabase_user_id(self, supabase_user_id: str) -> UserIdentityResponse | None:
        user = self.repo.get_user_by_supabase_user_id(supabase_user_id)
        if not user:
            return None
        return UserIdentityResponse(
            internal_user_id=user.id,
            supabase_user_id=user.supabase_user_id or "",
            email=user.email,
            full_name=user.full_name,
            status=user.status,
        )

    def resolve_login_identity(self, payload: UserLoginResolveRequest) -> UserIdentityResponse | None:
        user = self.repo.get_user_by_email(payload.email)
        if not user:
            return None

        try:
            self.repo.bind_supabase_user_id(user, payload.supabase_user_id)
        except ValueError:
            return None

        self.db.commit()
        return UserIdentityResponse(
            internal_user_id=user.id,
            supabase_user_id=user.supabase_user_id or "",
            email=user.email,
            full_name=user.full_name,
            status=user.status,
        )

    def verify_pin_login(self, payload: UserPinLoginRequest) -> UserIdentityResponse | None:
        user = self.repo.get_user_by_email(payload.email)
        if not user or user.status != "active":
            return None
        if not user.pin_hash:
            return None
        if user.pin_hash != self._hash_pin(user.id, payload.pin):
            return None
        return UserIdentityResponse(
            internal_user_id=user.id,
            supabase_user_id=user.supabase_user_id or "",
            email=user.email,
            full_name=user.full_name,
            status=user.status,
        )

    def verify_password_login(self, payload: UserPasswordLoginRequest) -> UserIdentityResponse | None:
        user = self.repo.get_user_by_email(payload.email)
        if not user or user.status != "active":
            return None
        if not user.password_hash:
            return None
        if user.password_hash != self._hash_password(user.id, payload.password):
            return None
        return UserIdentityResponse(
            internal_user_id=user.id,
            supabase_user_id=user.supabase_user_id or "",
            email=user.email,
            full_name=user.full_name,
            status=user.status,
        )

    def verify_pin_for_user(self, payload: UserPinVerifyRequest) -> bool:
        user = self.repo.get_user_by_id(payload.internal_user_id)
        if not user or user.status != "active":
            return False
        if not user.pin_hash:
            return False
        return user.pin_hash == self._hash_pin(user.id, payload.pin)

    def set_user_password(self, user_id: str, password: str) -> None:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        user.password_hash = self._hash_password(user_id, password)
        self.db.flush()

    def set_user_pin(self, user_id: str, pin: str) -> None:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise LookupError("User not found.")
        user.pin_hash = self._hash_pin(user_id, pin)
        self.db.flush()

    @staticmethod
    def _hash_pin(user_id: str, pin: str) -> str:
        return hashlib.sha256(f"pin::{user_id}::{pin}".encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_password(user_id: str, password: str) -> str:
        return hashlib.sha256(f"pwd::{user_id}::{password}".encode("utf-8")).hexdigest()

    def provision_from_supabase(self, payload: UserProvisionRequest) -> UserIdentityResponse:
        existing = self.repo.get_user_by_supabase_user_id(payload.supabase_user_id)
        if existing:
            return UserIdentityResponse(
                internal_user_id=existing.id,
                supabase_user_id=existing.supabase_user_id or "",
                email=existing.email,
                full_name=existing.full_name,
                status=existing.status,
            )

        user = self.repo.create_user_from_supabase(
            supabase_user_id=payload.supabase_user_id,
            email=payload.email,
            full_name=payload.full_name,
        )
        self.repo.create_default_account(user_id=user.id)
        self.db.commit()
        return UserIdentityResponse(
            internal_user_id=user.id,
            supabase_user_id=user.supabase_user_id or "",
            email=user.email,
            full_name=user.full_name,
            status=user.status,
        )
