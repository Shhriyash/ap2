from __future__ import annotations

from typing import Any


class RetrievalService:
    async def get_beneficiaries(self, user_id: str) -> list[dict[str, Any]]:
        # Beneficiary verification is DB-backed in gateway /receivers/verify.
        return []

    async def get_default_payment_method(self, user_id: str) -> str | None:
        return f"pm_wallet_{user_id}"

    async def resolve_user_name(self, name: str) -> str | None:
        return None
