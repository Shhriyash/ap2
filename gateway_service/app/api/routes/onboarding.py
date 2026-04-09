from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.onboarding_service import OnboardingService, onboarding_store

router = APIRouter(tags=["onboarding"])


class SignupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=6, max_length=120)
    phone: str | None = Field(default=None, max_length=30)


class SignupResponse(BaseModel):
    user_id: str
    supabase_user_id: str | None = None
    email_verification_required: bool = True
    onboarding_session_token: str


class PinRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8)


class OtpStartRequest(BaseModel):
    channel: str = "email"
    destination: str = Field(..., min_length=3, max_length=200)


class OtpStartResponse(BaseModel):
    challenge_id: str
    destination_masked: str


class OtpVerifyRequest(BaseModel):
    challenge_id: str = Field(..., min_length=3)
    value: str | None = None
    otp: str | None = None


class OtpVerifyResponse(BaseModel):
    verified: bool
    message: str


class OnboardingStatusResponse(BaseModel):
    user_id: str
    email: str | None = None
    email_verified: bool
    status: str


def _require_onboarding_session(token: str | None, user_id: str) -> None:
    if not onboarding_store.validate_session(token=token, user_id=user_id):
        raise HTTPException(status_code=401, detail="Invalid or expired onboarding session token.")


@router.post("/onboarding/signup", response_model=SignupResponse)
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
) -> SignupResponse:
    try:
        data = OnboardingService(db, onboarding_store).signup(
            full_name=payload.full_name,
            email=payload.email,
            phone=payload.phone,
            password=payload.password,
        )
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SignupResponse(**data)


@router.post("/onboarding/users/{user_id}/pin")
def set_pin(
    user_id: str,
    payload: PinRequest,
    db: Session = Depends(get_db),
    x_onboarding_session_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if not payload.pin.isdigit():
        raise HTTPException(status_code=422, detail="PIN must be numeric.")
    _require_onboarding_session(x_onboarding_session_token, user_id)
    try:
        OnboardingService(db, onboarding_store).set_pin(user_id=user_id, pin=payload.pin)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"saved": True}


@router.post("/onboarding/users/{user_id}/otp-device/start", response_model=OtpStartResponse)
def start_otp(
    user_id: str,
    payload: OtpStartRequest,
    db: Session = Depends(get_db),
    x_onboarding_session_token: str | None = Header(default=None),
) -> OtpStartResponse:
    _require_onboarding_session(x_onboarding_session_token, user_id)
    try:
        data = OnboardingService(db, onboarding_store).start_otp(user_id=user_id, destination=payload.destination)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OtpStartResponse(**data)


@router.post("/onboarding/users/{user_id}/otp-device/verify", response_model=OtpVerifyResponse)
def verify_otp(
    user_id: str,
    payload: OtpVerifyRequest,
    db: Session = Depends(get_db),
    x_onboarding_session_token: str | None = Header(default=None),
) -> OtpVerifyResponse:
    _require_onboarding_session(x_onboarding_session_token, user_id)
    submitted_value = payload.value or payload.otp
    if not submitted_value:
        raise HTTPException(status_code=422, detail="Missing OTP value.")
    try:
        data = OnboardingService(db, onboarding_store).verify_otp(
            user_id=user_id,
            challenge_id=payload.challenge_id,
            value=submitted_value,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OtpVerifyResponse(**data)


@router.get("/onboarding/users/{user_id}/status", response_model=OnboardingStatusResponse)
def onboarding_status(
    user_id: str,
    db: Session = Depends(get_db),
    x_onboarding_session_token: str | None = Header(default=None),
) -> OnboardingStatusResponse:
    _require_onboarding_session(x_onboarding_session_token, user_id)
    try:
        data = OnboardingService(db, onboarding_store).status(user_id=user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OnboardingStatusResponse(**data)
