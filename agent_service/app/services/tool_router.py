from __future__ import annotations

import httpx

from app.core.config import settings
from shared_lib.contracts.payment import PaymentTransferRequest, PaymentTransferResponse


class PaymentToolRouter:
    async def transfer(self, payload: PaymentTransferRequest) -> PaymentTransferResponse:
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.gateway_base_url}/payments/transfer",
                json=payload.model_dump(mode="json"),
            )
            resp.raise_for_status()
            data = resp.json()
        return PaymentTransferResponse(**data)
