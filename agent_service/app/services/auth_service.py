from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.request_context import get_correlation_id
from app.services.session_manager import SessionPrincipal, session_manager
from shared_lib.contracts.user import (
    UserIdentityResponse,
    UserPasswordLoginRequest,
    UserPinVerifyRequest,
    UserPinVerifyResponse,
)


class AuthService:
    async def cli_login(self, email: str, password: str) -> SessionPrincipal:
        user = await self._verify_password_login(email=email, password=password)
        return session_manager.create_session(
            internal_user_id=user.internal_user_id,
            supabase_user_id=user.supabase_user_id,
            email=user.email,
        )

    async def _verify_password_login(self, email: str, password: str) -> UserIdentityResponse:
        payload = UserPasswordLoginRequest(email=email, password=password)
        headers = {"Content-Type": "application/json"}
        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.gateway_base_url}/users/login-password",
                headers=headers,
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code in {400, 401, 404}:
                raise PermissionError("Login rejected: invalid email or password.")
            if resp.status_code >= 400:
                raise RuntimeError("Failed to verify login with gateway.")
            data = resp.json()
        return UserIdentityResponse(**data)

    async def verify_transaction_pin(self, internal_user_id: str, pin: str) -> bool:
        payload = UserPinVerifyRequest(internal_user_id=internal_user_id, pin=pin)
        headers = {"Content-Type": "application/json"}
        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.gateway_base_url}/users/verify-pin",
                headers=headers,
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code >= 400:
                raise RuntimeError("Failed to verify transaction PIN with gateway.")
            data = resp.json()
        return UserPinVerifyResponse(**data).verified


auth_service = AuthService()
