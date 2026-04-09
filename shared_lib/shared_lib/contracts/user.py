from pydantic import BaseModel, Field


class UserProvisionRequest(BaseModel):
    supabase_user_id: str = Field(..., min_length=3)
    email: str = Field(..., min_length=3)
    full_name: str | None = None


class UserLoginResolveRequest(BaseModel):
    supabase_user_id: str = Field(..., min_length=3)
    email: str = Field(..., min_length=3)


class UserPinLoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    pin: str = Field(..., min_length=4, max_length=8)


class UserPinVerifyRequest(BaseModel):
    internal_user_id: str = Field(..., min_length=3)
    pin: str = Field(..., min_length=4, max_length=8)


class UserPinVerifyResponse(BaseModel):
    verified: bool


class UserIdentityResponse(BaseModel):
    internal_user_id: str
    supabase_user_id: str
    email: str | None = None
    full_name: str | None = None
    status: str
