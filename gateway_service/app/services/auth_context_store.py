from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock


@dataclass
class AuthContextRecord:
    auth_context_id: str
    user_id: str
    session_id: str
    expires_at: datetime
    consumed: bool = False


class AuthContextStore:
    def __init__(self) -> None:
        self._records: dict[str, AuthContextRecord] = {}
        self._lock = Lock()

    def register(self, auth_context_id: str, user_id: str, session_id: str, ttl_seconds: int) -> AuthContextRecord:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._lock:
            existing = self._records.get(auth_context_id)
            if existing and existing.expires_at > now:
                return existing
            record = AuthContextRecord(
                auth_context_id=auth_context_id,
                user_id=user_id,
                session_id=session_id,
                expires_at=expires_at,
                consumed=False,
            )
            self._records[auth_context_id] = record
            return record

    def consume(self, auth_context_id: str, user_id: str, session_id: str) -> bool:
        now = datetime.now(UTC)
        with self._lock:
            record = self._records.get(auth_context_id)
            if not record:
                return False
            if record.expires_at <= now:
                self._records.pop(auth_context_id, None)
                return False
            if record.consumed:
                return False
            if record.user_id != user_id or record.session_id != session_id:
                return False
            record.consumed = True
            return True


auth_context_store = AuthContextStore()
