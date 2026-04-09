from __future__ import annotations

from typing import Any


class RetrievalService:
    # Prototype retrieval store. Replace with DB queries/cache in next phase.
    _beneficiaries: dict[str, list[dict[str, Any]]] = {
        "user_x": [
            {"beneficiary_id": "ben_y", "name": "y", "verified": True},
            {"beneficiary_id": "ben_z", "name": "z", "verified": True},
        ]
    }

    _methods: dict[str, list[dict[str, Any]]] = {
        "user_x": [{"payment_method_id": "pm_wallet_user_x", "is_default": True}]
    }

    async def get_beneficiaries(self, user_id: str) -> list[dict[str, Any]]:
        return self._beneficiaries.get(user_id, [])

    async def get_default_payment_method(self, user_id: str) -> str | None:
        methods = self._methods.get(user_id, [])
        for method in methods:
            if method.get("is_default"):
                return method["payment_method_id"]
        return methods[0]["payment_method_id"] if methods else None
