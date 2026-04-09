from fastapi import APIRouter, Depends

from app.api.security import require_internal_service_token
from app.services.auth_context_store import auth_context_store
from shared_lib.contracts.auth_context import RegisterAuthContextRequest, RegisterAuthContextResponse

router = APIRouter(tags=["auth-context"], dependencies=[Depends(require_internal_service_token)])


@router.post("/internal/auth-context/register", response_model=RegisterAuthContextResponse)
def register_auth_context(payload: RegisterAuthContextRequest) -> RegisterAuthContextResponse:
    record = auth_context_store.register(
        auth_context_id=payload.auth_context_id,
        user_id=payload.user_id,
        session_id=payload.session_id,
        ttl_seconds=payload.ttl_seconds,
    )
    return RegisterAuthContextResponse(
        registered=True,
        auth_context_id=record.auth_context_id,
        expires_at=record.expires_at.isoformat(),
    )
