from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.request_context import get_correlation_id
from app.services.session_manager import SessionPrincipal, session_manager
from shared_lib.contracts.user import UserIdentityResponse, UserLoginResolveRequest


@dataclass
class SupabaseAuthResult:
    access_token: str
    supabase_user_id: str
    email: str | None


class AuthService:
    async def cli_login(self, email: str, password: str) -> SessionPrincipal:
        supabase_auth = await self._authenticate_with_supabase(email=email, password=password)
        await self._validate_access_token(supabase_auth.access_token)
        user = await self._ensure_internal_user(
            supabase_user_id=supabase_auth.supabase_user_id,
            email=supabase_auth.email or email,
        )
        return session_manager.create_session(
            internal_user_id=user.internal_user_id,
            supabase_user_id=user.supabase_user_id,
            email=user.email,
        )

    async def _authenticate_with_supabase(self, email: str, password: str) -> SupabaseAuthResult:
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise RuntimeError("Supabase settings missing. Configure SUPABASE_URL and SUPABASE_ANON_KEY.")
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        }
        payload = {"email": email, "password": password}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password",
                headers=headers,
                json=payload,
            )
            if resp.status_code >= 400:
                raise PermissionError("Supabase authentication failed.")
            body = resp.json()
        user = body.get("user") or {}
        supabase_user_id = user.get("id")
        if not supabase_user_id:
            raise PermissionError("Supabase authentication failed: missing user id.")
        return SupabaseAuthResult(
            access_token=body["access_token"],
            supabase_user_id=supabase_user_id,
            email=user.get("email"),
        )

    async def _validate_access_token(self, access_token: str) -> None:
        headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers=headers,
            )
            if resp.status_code >= 400:
                raise PermissionError("Supabase token validation failed.")

    async def _ensure_internal_user(self, supabase_user_id: str, email: str) -> UserIdentityResponse:
        payload = UserLoginResolveRequest(supabase_user_id=supabase_user_id, email=email)
        headers = {"Content-Type": "application/json"}
        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.gateway_base_url}/users/resolve-login",
                headers=headers,
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code == 404:
                raise PermissionError("Login rejected: email is not onboarded in internal users table.")
            if resp.status_code >= 400:
                raise RuntimeError("Failed to resolve internal user mapping.")
            data = resp.json()
        return UserIdentityResponse(**data)


auth_service = AuthService()
