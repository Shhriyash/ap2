from pydantic import BaseModel, Field


class UserProvisionRequest(BaseModel):
    supabase_user_id: str = Field(..., min_length=3)
    email: str = Field(..., min_length=3)
    full_name: str | None = None


class UserLoginResolveRequest(BaseModel):
    supabase_user_id: str = Field(..., min_length=3)
    email: str = Field(..., min_length=3)


class UserIdentityResponse(BaseModel):
    internal_user_id: str
    supabase_user_id: str
    email: str | None = None
    full_name: str | None = None
    status: str
