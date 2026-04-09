from typing import Literal

from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=3)
    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    channel: Literal["text", "voice"] = "text"


class AgentMessageResponse(BaseModel):
    session_id: str
    response: str
    next_action: Literal[
        "ask_slot",
        "auth_challenge",
        "ready_to_execute",
        "executed",
        "failed",
    ]
    state: dict


class AuthChallengeStartRequest(BaseModel):
    session_id: str
    user_id: str
    preferred_type: Literal["pin", "otp"] = "pin"


class AuthChallengeVerifyRequest(BaseModel):
    challenge_id: str
    user_id: str
    value: str = Field(..., min_length=1)


class AuthChallengeVerifyResponse(BaseModel):
    challenge_id: str
    verified: bool
    challenge_type: Literal["pin", "otp"]
    next_step: Literal["retry", "otp_fallback", "proceed", "locked"]
    message: str
