from sqlalchemy.orm import Session

from app.db.repository import PaymentRepository
from shared_lib.contracts.user import UserIdentityResponse, UserLoginResolveRequest, UserProvisionRequest


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
