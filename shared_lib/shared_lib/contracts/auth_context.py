from pydantic import BaseModel, Field


class RegisterAuthContextRequest(BaseModel):
    auth_context_id: str = Field(..., min_length=3)
    user_id: str = Field(..., min_length=3)
    session_id: str = Field(..., min_length=3)
    ttl_seconds: int = Field(default=300, ge=30, le=900)


class RegisterAuthContextResponse(BaseModel):
    registered: bool
    auth_context_id: str
    expires_at: str
