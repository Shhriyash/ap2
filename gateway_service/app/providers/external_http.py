from __future__ import annotations

from decimal import Decimal

import httpx

from app.core.config import settings
from app.providers.base import PaymentProvider
from shared_lib.contracts.payment import (
    PaymentTransferRequest,
    PaymentTransferResponse,
    PaymentValidateRequest,
    PaymentValidateResponse,
    RefundRequest,
    ReversalRequest,
    TransactionStatusResponse,
)


class ExternalHttpPaymentProvider(PaymentProvider):
    """
    Adapter for replacing the dummy backend with a real payment processor API.
    Keep gateway endpoints and shared contracts unchanged; only this adapter evolves.
    """

    def __init__(self) -> None:
        self._base_url = settings.external_payment_base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.external_payment_api_key}",
            "Content-Type": "application/json",
        }
        self._timeout = settings.external_payment_timeout_seconds

    def validate(self, payload: PaymentValidateRequest) -> PaymentValidateResponse:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base_url}/validate",
                headers=self._headers,
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code >= 400:
                return PaymentValidateResponse(valid=False, reason="external_validate_failed")
            body = resp.json()
        return PaymentValidateResponse(valid=bool(body.get("valid")), reason=body.get("reason"))

    def transfer(self, payload: PaymentTransferRequest) -> PaymentTransferResponse:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base_url}/transfer",
                headers=self._headers,
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code >= 400:
                return PaymentTransferResponse(
                    transaction_id="",
                    status="FAILED",
                    message="External transfer failed.",
                    failure_code="EXTERNAL_TRANSFER_FAILED",
                )
            body = resp.json()
        return PaymentTransferResponse(**body)

    def get_status(self, transaction_id: str) -> TransactionStatusResponse:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(
                f"{self._base_url}/payments/{transaction_id}",
                headers=self._headers,
            )
            if resp.status_code >= 400:
                return TransactionStatusResponse(
                    transaction_id=transaction_id,
                    status="FAILED",
                    amount=Decimal("0"),
                    currency="AED",
                    payer_user_id="",
                    beneficiary_id="",
                    failure_code="NOT_FOUND",
                    failure_reason="External status lookup failed.",
                )
            body = resp.json()
        return TransactionStatusResponse(**body)

    def refund(self, payload: RefundRequest) -> PaymentTransferResponse:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base_url}/refund",
                headers=self._headers,
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code >= 400:
                return PaymentTransferResponse(
                    transaction_id=payload.transaction_id,
                    status="FAILED",
                    message="External refund failed.",
                    failure_code="EXTERNAL_REFUND_FAILED",
                )
            body = resp.json()
        return PaymentTransferResponse(**body)

    def reverse(self, payload: ReversalRequest) -> PaymentTransferResponse:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base_url}/reverse",
                headers=self._headers,
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code >= 400:
                return PaymentTransferResponse(
                    transaction_id=payload.transaction_id,
                    status="FAILED",
                    message="External reversal failed.",
                    failure_code="EXTERNAL_REVERSAL_FAILED",
                )
            body = resp.json()
        return PaymentTransferResponse(**body)
