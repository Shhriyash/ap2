from fastapi import Header, HTTPException

from app.core.config import settings


def require_internal_service_token(x_internal_service_token: str | None = Header(default=None)) -> None:
    expected = settings.internal_service_token.strip()
    if not expected:
        return
    if x_internal_service_token != expected:
        raise HTTPException(status_code=401, detail="Invalid internal service token.")
