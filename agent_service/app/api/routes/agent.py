from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.orchestrator import orchestrator
from app.services.auth_service import auth_service
from app.services.session_manager import SessionPrincipal, session_manager
from shared_lib.contracts.agent import (
    AgentMessageRequest,
    AgentMessageResponse,
    AuthChallengeStartRequest,
    AuthChallengeVerifyRequest,
    AuthChallengeVerifyResponse,
    CliLoginRequest,
    CliLoginResponse,
)

router = APIRouter(tags=["agent"])
security = HTTPBearer(auto_error=False)


class ConfirmRequest(BaseModel):
    session_id: str
    confirmed: bool


def _get_principal(credentials: HTTPAuthorizationCredentials = Depends(security)) -> SessionPrincipal:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing session token.")
    principal = session_manager.get_session(credentials.credentials)
    if not principal:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    return principal


@router.post("/auth/cli/login", response_model=CliLoginResponse)
async def cli_login(payload: CliLoginRequest) -> CliLoginResponse:
    try:
        principal = await auth_service.cli_login(email=payload.email, pin=payload.pin)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return CliLoginResponse(
        session_token=principal.session_token,
        session_id=principal.session_id,
        internal_user_id=principal.internal_user_id,
        supabase_user_id=principal.supabase_user_id,
    )


@router.post("/agent/message", response_model=AgentMessageResponse)
async def agent_message(
    payload: AgentMessageRequest,
    principal: SessionPrincipal = Depends(_get_principal),
) -> AgentMessageResponse:
    if payload.session_id != principal.session_id:
        raise HTTPException(status_code=403, detail="Session id does not match authenticated principal.")
    return await orchestrator.process_message(payload.session_id, principal.internal_user_id, payload.message)


@router.post("/auth/challenge/start")
async def auth_challenge_start(
    payload: AuthChallengeStartRequest,
    principal: SessionPrincipal = Depends(_get_principal),
) -> dict[str, str]:
    if payload.session_id != principal.session_id:
        raise HTTPException(status_code=403, detail="Session id does not match authenticated principal.")
    return orchestrator.start_auth_challenge(payload.session_id, principal.internal_user_id, payload.preferred_type)


@router.post("/auth/challenge/verify", response_model=AuthChallengeVerifyResponse)
async def auth_challenge_verify(
    payload: AuthChallengeVerifyRequest,
    principal: SessionPrincipal = Depends(_get_principal),
) -> AuthChallengeVerifyResponse:
    return await orchestrator.verify_auth_challenge(payload.challenge_id, principal.internal_user_id, payload.value)


@router.post("/agent/confirm", response_model=AgentMessageResponse)
async def confirm_execution(
    payload: ConfirmRequest,
    principal: SessionPrincipal = Depends(_get_principal),
) -> AgentMessageResponse:
    if payload.session_id != principal.session_id:
        raise HTTPException(status_code=403, detail="Session id does not match authenticated principal.")
    if not payload.confirmed:
        state = orchestrator.abort_transaction(payload.session_id)
        return AgentMessageResponse(
            session_id=payload.session_id,
            response="Execution cancelled. No money was sent.",
            next_action="ask_slot",
            state=state,
        )
    return await orchestrator.confirm_and_execute(payload.session_id)


@router.get("/agent/session/{session_id}")
async def get_session(
    session_id: str,
    principal: SessionPrincipal = Depends(_get_principal),
) -> dict:
    if session_id != principal.session_id:
        raise HTTPException(status_code=403, detail="Session id does not match authenticated principal.")
    return orchestrator.get_session_state(session_id)
