from typing import Literal

from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=3)
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
    preferred_type: Literal["pin", "otp"] = "pin"


class AuthChallengeVerifyRequest(BaseModel):
    challenge_id: str
    value: str = Field(..., min_length=1)


class CliLoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6, max_length=120)


class CliLoginResponse(BaseModel):
    session_token: str
    session_id: str
    internal_user_id: str
    supabase_user_id: str


class AuthChallengeVerifyResponse(BaseModel):
    challenge_id: str
    verified: bool
    challenge_type: Literal["pin", "otp"]
    next_step: Literal["retry", "otp_fallback", "proceed", "locked"]
    message: str
