from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.security import require_internal_service_token
from app.db.session import get_db
from app.services.user_service import UserService
from shared_lib.contracts.user import UserIdentityResponse, UserLoginResolveRequest, UserProvisionRequest

router = APIRouter(tags=["users"], dependencies=[Depends(require_internal_service_token)])


@router.get("/users/by-supabase/{supabase_user_id}", response_model=UserIdentityResponse)
def get_user_by_supabase_user_id(
    supabase_user_id: str,
    db: Session = Depends(get_db),
) -> UserIdentityResponse:
    user = UserService(db).get_by_supabase_user_id(supabase_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User mapping not found.")
    return user


@router.post("/users/provision", response_model=UserIdentityResponse)
def provision_user(
    payload: UserProvisionRequest,
    db: Session = Depends(get_db),
) -> UserIdentityResponse:
    return UserService(db).provision_from_supabase(payload)


@router.post("/users/resolve-login", response_model=UserIdentityResponse)
def resolve_login_user(
    payload: UserLoginResolveRequest,
    db: Session = Depends(get_db),
) -> UserIdentityResponse:
    user = UserService(db).resolve_login_identity(payload)
    if not user:
        raise HTTPException(status_code=404, detail="No internal user found for this email.")
    return user
