from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.services.pydantic_payment_agent import (
    PaymentExecutionInput,
    PydanticPaymentAgentService,
)
from app.services.retrieval import RetrievalService
from shared_lib.contracts.agent import AgentMessageResponse, AuthChallengeVerifyResponse
from shared_lib.core.idempotency import make_idempotency_key


@dataclass
class SessionState:
    user_id: str
    amount: Decimal | None = None
    beneficiary_id: str | None = None
    beneficiary_name: str | None = None
    payment_method_id: str | None = None
    purpose: str = ""
    auth_verified: bool = False
    auth_context_id: str | None = None
    ready_to_execute: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "amount": str(self.amount) if self.amount is not None else None,
            "beneficiary_id": self.beneficiary_id,
            "beneficiary_name": self.beneficiary_name,
            "payment_method_id": self.payment_method_id,
            "purpose": self.purpose,
            "auth_verified": self.auth_verified,
            "auth_context_id": self.auth_context_id,
            "ready_to_execute": self.ready_to_execute,
        }


class AgentOrchestrator:
    def __init__(self) -> None:
        self._agent = PydanticPaymentAgentService()
        self._retrieval = RetrievalService()
        self._sessions: dict[str, SessionState] = {}
        self._auth_challenges: dict[str, dict[str, Any]] = {}

    async def process_message(self, session_id: str, user_id: str, message: str) -> AgentMessageResponse:
        state = self._sessions.setdefault(session_id, SessionState(user_id=user_id))
        beneficiaries = await self._retrieval.get_beneficiaries(user_id)
        default_method = await self._retrieval.get_default_payment_method(user_id)
        slots = await self._agent.extract_slots(
            user_id=user_id,
            message=message,
            beneficiaries=beneficiaries,
            default_method_id=default_method,
        )
        if slots.intent != "send_money":
            return AgentMessageResponse(
                session_id=session_id,
                response="I can help with payments. Please say: pay <amount> AED to <beneficiary>.",
                next_action="ask_slot",
                state=state.to_dict(),
            )

        if slots.amount is not None:
            state.amount = slots.amount
        if slots.beneficiary_name:
            state.beneficiary_name = slots.beneficiary_name
        if slots.beneficiary_id:
            state.beneficiary_id = slots.beneficiary_id
        if slots.payment_method_id:
            state.payment_method_id = slots.payment_method_id
        if slots.purpose:
            state.purpose = slots.purpose

        if not state.payment_method_id:
            state.payment_method_id = default_method

        if state.amount is None:
            return AgentMessageResponse(
                session_id=session_id,
                response="Please provide the amount in AED.",
                next_action="ask_slot",
                state=state.to_dict(),
            )
        if state.beneficiary_id is None:
            return AgentMessageResponse(
                session_id=session_id,
                response="Beneficiary not found or not registered. Please use a verified beneficiary name.",
                next_action="ask_slot",
                state=state.to_dict(),
            )
        if state.payment_method_id is None:
            return AgentMessageResponse(
                session_id=session_id,
                response="No payment method found. Please add a payment method first.",
                next_action="failed",
                state=state.to_dict(),
            )
        if not state.auth_verified:
            return AgentMessageResponse(
                session_id=session_id,
                response="Authentication required. Start PIN verification.",
                next_action="auth_challenge",
                state=state.to_dict(),
            )

        state.ready_to_execute = True
        return AgentMessageResponse(
            session_id=session_id,
            response=(
                f"Ready to pay {state.amount} {settings.default_currency} to {state.beneficiary_name or state.beneficiary_id}. "
                "Confirm to execute."
            ),
            next_action="ready_to_execute",
            state=state.to_dict(),
        )

    def start_auth_challenge(self, session_id: str, user_id: str, preferred_type: str) -> dict[str, str]:
        challenge_id = f"chl_{uuid4().hex[:12]}"
        challenge_type = "pin" if preferred_type == "pin" else "otp"
        self._auth_challenges[challenge_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "challenge_type": challenge_type,
            "attempts": 0,
            "verified": False,
        }
        return {"challenge_id": challenge_id, "challenge_type": challenge_type}

    def verify_auth_challenge(self, challenge_id: str, user_id: str, value: str) -> AuthChallengeVerifyResponse:
        challenge = self._auth_challenges.get(challenge_id)
        if not challenge or challenge["user_id"] != user_id:
            return AuthChallengeVerifyResponse(
                challenge_id=challenge_id,
                verified=False,
                challenge_type="pin",
                next_step="locked",
                message="Invalid challenge.",
            )
        challenge["attempts"] += 1

        if challenge["challenge_type"] == "pin":
            # Prototype static PIN. Replace with hashed PIN verifier from DB.
            if value == "1234":
                challenge["verified"] = True
                self._mark_session_auth_verified(challenge["session_id"], challenge_id)
                return AuthChallengeVerifyResponse(
                    challenge_id=challenge_id,
                    verified=True,
                    challenge_type="pin",
                    next_step="proceed",
                    message="PIN verified.",
                )
            if challenge["attempts"] >= settings.max_pin_attempts:
                return AuthChallengeVerifyResponse(
                    challenge_id=challenge_id,
                    verified=False,
                    challenge_type="pin",
                    next_step="otp_fallback",
                    message="PIN failed. Switch to OTP.",
                )
            return AuthChallengeVerifyResponse(
                challenge_id=challenge_id,
                verified=False,
                challenge_type="pin",
                next_step="retry",
                message="Invalid PIN.",
            )

        if value == "000999":
            challenge["verified"] = True
            self._mark_session_auth_verified(challenge["session_id"], challenge_id)
            return AuthChallengeVerifyResponse(
                challenge_id=challenge_id,
                verified=True,
                challenge_type="otp",
                next_step="proceed",
                message="OTP verified.",
            )
        if challenge["attempts"] >= settings.max_otp_attempts:
            return AuthChallengeVerifyResponse(
                challenge_id=challenge_id,
                verified=False,
                challenge_type="otp",
                next_step="locked",
                message="OTP attempts exhausted.",
            )
        return AuthChallengeVerifyResponse(
            challenge_id=challenge_id,
            verified=False,
            challenge_type="otp",
            next_step="retry",
            message="Invalid OTP.",
        )

    def _mark_session_auth_verified(self, session_id: str, challenge_id: str) -> None:
        state = self._sessions.get(session_id)
        if not state:
            return
        state.auth_verified = True
        state.auth_context_id = challenge_id

    async def confirm_and_execute(self, session_id: str) -> AgentMessageResponse:
        state = self._sessions.get(session_id)
        if not state:
            return AgentMessageResponse(
                session_id=session_id,
                response="Session not found.",
                next_action="failed",
                state={},
            )
        if not state.ready_to_execute:
            return AgentMessageResponse(
                session_id=session_id,
                response="Session is not ready for execution.",
                next_action="ask_slot",
                state=state.to_dict(),
            )

        result = await self._agent.execute_with_tool_call(
            PaymentExecutionInput(
                payer_user_id=state.user_id,
                beneficiary_id=state.beneficiary_id or "",
                amount=state.amount or Decimal("0"),
                payment_method_id=state.payment_method_id or "",
                purpose=state.purpose,
                auth_context_id=state.auth_context_id or "",
                idempotency_key=make_idempotency_key(),
            )
        )
        state.ready_to_execute = False
        next_action = "executed" if result.status == "SUCCESS" else "failed"
        return AgentMessageResponse(
            session_id=session_id,
            response=f"Transfer {result.status}. transaction_id={result.transaction_id}",
            next_action=next_action,
            state=state.to_dict(),
        )

    def get_session_state(self, session_id: str) -> dict[str, Any]:
        state = self._sessions.get(session_id)
        return state.to_dict() if state else {}


orchestrator = AgentOrchestrator()
