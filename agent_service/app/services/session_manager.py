from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
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
        self._store_path = self._resolve_store_path()
        self._load_sessions()

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
        self._save_sessions()
        return principal

    def get_session(self, session_token: str) -> SessionPrincipal | None:
        principal = self._sessions.get(session_token)
        if not principal:
            return None
        if principal.expires_at <= datetime.now(UTC):
            self._sessions.pop(session_token, None)
            self._save_sessions()
            return None
        return principal

    def validate_session(self, session_token: str, session_id: str | None = None) -> SessionPrincipal | None:
        principal = self.get_session(session_token)
        if not principal:
            return None
        if session_id and principal.session_id != session_id:
            return None
        return principal

    def _resolve_store_path(self) -> Path:
        if settings.agent_session_store_path.strip():
            return Path(settings.agent_session_store_path).expanduser().resolve()
        return (Path(__file__).resolve().parents[2] / "logs" / "session_store.json").resolve()

    def _load_sessions(self) -> None:
        if not self._store_path.exists():
            return
        try:
            raw = self._store_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            return

        now = datetime.now(UTC)
        for item in data:
            try:
                principal = SessionPrincipal(
                    session_token=item["session_token"],
                    session_id=item["session_id"],
                    internal_user_id=item["internal_user_id"],
                    supabase_user_id=item.get("supabase_user_id", ""),
                    email=item.get("email"),
                    issued_at=datetime.fromisoformat(item["issued_at"]),
                    expires_at=datetime.fromisoformat(item["expires_at"]),
                )
            except Exception:
                continue
            if principal.expires_at > now:
                self._sessions[principal.session_token] = principal

    def _save_sessions(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "session_token": principal.session_token,
                "session_id": principal.session_id,
                "internal_user_id": principal.internal_user_id,
                "supabase_user_id": principal.supabase_user_id,
                "email": principal.email,
                "issued_at": principal.issued_at.isoformat(),
                "expires_at": principal.expires_at.isoformat(),
            }
            for principal in self._sessions.values()
        ]
        self._store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


session_manager = SessionManager()
