from fastapi import APIRouter
from pydantic import BaseModel

from app.domain.orchestrator import orchestrator
from shared_lib.contracts.agent import (
    AgentMessageRequest,
    AgentMessageResponse,
    AuthChallengeStartRequest,
    AuthChallengeVerifyRequest,
    AuthChallengeVerifyResponse,
)

router = APIRouter(tags=["agent"])


class ConfirmRequest(BaseModel):
    session_id: str
    confirmed: bool


@router.post("/agent/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest) -> AgentMessageResponse:
    return await orchestrator.process_message(payload.session_id, payload.user_id, payload.message)


@router.post("/auth/challenge/start")
async def auth_challenge_start(payload: AuthChallengeStartRequest) -> dict[str, str]:
    return orchestrator.start_auth_challenge(payload.session_id, payload.user_id, payload.preferred_type)


@router.post("/auth/challenge/verify", response_model=AuthChallengeVerifyResponse)
async def auth_challenge_verify(payload: AuthChallengeVerifyRequest) -> AuthChallengeVerifyResponse:
    return orchestrator.verify_auth_challenge(payload.challenge_id, payload.user_id, payload.value)


@router.post("/agent/confirm", response_model=AgentMessageResponse)
async def confirm_execution(payload: ConfirmRequest) -> AgentMessageResponse:
    if not payload.confirmed:
        return AgentMessageResponse(
            session_id=payload.session_id,
            response="Execution cancelled.",
            next_action="ask_slot",
            state=orchestrator.get_session_state(payload.session_id),
        )
    return await orchestrator.confirm_and_execute(payload.session_id)


@router.get("/agent/session/{session_id}")
async def get_session(session_id: str) -> dict:
    return orchestrator.get_session_state(session_id)
