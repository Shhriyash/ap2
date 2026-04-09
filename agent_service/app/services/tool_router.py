from __future__ import annotations

from decimal import Decimal

import httpx

from app.core.config import settings
from app.core.request_context import get_correlation_id
from shared_lib.contracts.auth_context import RegisterAuthContextRequest, RegisterAuthContextResponse
from shared_lib.contracts.payment import BalanceResponse
from shared_lib.contracts.payment import PaymentTransferRequest, PaymentTransferResponse
from shared_lib.contracts.payment import VerifyReceiverRequest, VerifyReceiverResponse


class PaymentToolRouter:
    @property
    def _internal_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return headers

    async def transfer(self, payload: PaymentTransferRequest) -> PaymentTransferResponse:
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.gateway_base_url}/payments/transfer",
                headers=self._internal_headers,
                json=payload.model_dump(mode="json"),
            )
            resp.raise_for_status()
            data = resp.json()
        return PaymentTransferResponse(**data)

    async def get_balance(self, requestor_user_id: str, target_user_id: str) -> BalanceResponse:
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.get(
                f"{settings.gateway_base_url}/accounts/{target_user_id}/balance",
                headers=self._internal_headers,
                params={"requestor_user_id": requestor_user_id},
            )
            resp.raise_for_status()
            data = resp.json()
        return BalanceResponse(
            user_id=data["user_id"],
            currency=data["currency"],
            available_balance=Decimal(str(data["available_balance"])),
        )

    async def verify_receiver(self, sender_user_id: str, receiver_hint: str) -> VerifyReceiverResponse:
        payload = VerifyReceiverRequest(sender_user_id=sender_user_id, receiver_hint=receiver_hint)
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.gateway_base_url}/receivers/verify",
                headers=self._internal_headers,
                json=payload.model_dump(mode="json"),
            )
            resp.raise_for_status()
            data = resp.json()
        return VerifyReceiverResponse(**data)

    async def register_auth_context(
        self,
        auth_context_id: str,
        user_id: str,
        session_id: str,
        ttl_seconds: int = 300,
    ) -> RegisterAuthContextResponse:
        payload = RegisterAuthContextRequest(
            auth_context_id=auth_context_id,
            user_id=user_id,
            session_id=session_id,
            ttl_seconds=ttl_seconds,
        )
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.gateway_base_url}/internal/auth-context/register",
                headers=self._internal_headers,
                json=payload.model_dump(mode="json"),
            )
            resp.raise_for_status()
            data = resp.json()
        return RegisterAuthContextResponse(**data)
