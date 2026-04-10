from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.request_context import get_correlation_id


class RetrievalService:
    @property
    def _internal_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return headers

    async def get_beneficiaries(self, user_id: str) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
                resp = await client.get(
                    f"{settings.gateway_base_url}/accounts/{user_id}/beneficiaries",
                    headers=self._internal_headers,
                )
                resp.raise_for_status()
                data = resp.json()
            return [
                {
                    "beneficiary_id": item["beneficiary_id"],
                    "name": item["display_name"],
                    "masked_identifier": item["masked_identifier"],
                    "verified": item["is_verified"],
                }
                for item in data.get("beneficiaries", [])
            ]
        except Exception:
            return []

    async def get_default_payment_method(self, user_id: str) -> str | None:
        return f"pm_wallet_{user_id}"
