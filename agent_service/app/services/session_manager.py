from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import settings


@dataclass
class SessionPrincipal:
    session_token: str
    session_id: str
    internal_user_id: str
    supabase_user_id: str
    email: str | None
    issued_at: datetime
    expires_at: datetime


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionPrincipal] = {}

    def create_session(self, internal_user_id: str, supabase_user_id: str, email: str | None) -> SessionPrincipal:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(minutes=settings.agent_session_ttl_minutes)
        principal = SessionPrincipal(
            session_token=f"sess_{uuid4().hex}",
            session_id=f"s_{uuid4().hex[:16]}",
            internal_user_id=internal_user_id,
            supabase_user_id=supabase_user_id,
            email=email,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        self._sessions[principal.session_token] = principal
        return principal

    def get_session(self, session_token: str) -> SessionPrincipal | None:
        principal = self._sessions.get(session_token)
        if not principal:
            return None
        if principal.expires_at <= datetime.now(UTC):
            self._sessions.pop(session_token, None)
            return None
        return principal

    def validate_session(self, session_token: str, session_id: str | None = None) -> SessionPrincipal | None:
        principal = self.get_session(session_token)
        if not principal:
            return None
        if session_id and principal.session_id != session_id:
            return None
        return principal


session_manager = SessionManager()
