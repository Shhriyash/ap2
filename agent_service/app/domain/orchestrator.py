from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.core.agent_logger import log_event
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
    beneficiary_masked_identifier: str | None = None
    payment_method_id: str | None = None
    purpose: str = ""
    note_collected: bool = False
    receiver_confirmed: bool = False
    awaiting_receiver_confirmation: bool = False
    awaiting_note: bool = False
    auth_verified: bool = False
    auth_context_id: str | None = None
    ready_to_execute: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "amount": str(self.amount) if self.amount is not None else None,
            "beneficiary_id": self.beneficiary_id,
            "beneficiary_name": self.beneficiary_name,
            "beneficiary_masked_identifier": self.beneficiary_masked_identifier,
            "payment_method_id": self.payment_method_id,
            "purpose": self.purpose,
            "note_collected": self.note_collected,
            "receiver_confirmed": self.receiver_confirmed,
            "awaiting_receiver_confirmation": self.awaiting_receiver_confirmation,
            "awaiting_note": self.awaiting_note,
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
        log_event("agent_message_received", {"session_id": session_id, "user_id": user_id, "message": message})
        state = self._sessions.setdefault(session_id, SessionState(user_id=user_id))
        lower = message.strip().lower()

        if self._is_abort_command(lower):
            self._reset_payment_state(state)
            log_event("transaction_aborted", {"session_id": session_id, "user_id": user_id})
            return AgentMessageResponse(
                session_id=session_id,
                response="Transaction aborted. No money was sent.",
                next_action="failed",
                state=state.to_dict(),
            )

        if state.awaiting_receiver_confirmation:
            if self._is_yes(lower):
                state.receiver_confirmed = True
                state.awaiting_receiver_confirmation = False
                log_event(
                    "receiver_confirmed",
                    {"session_id": session_id, "user_id": user_id, "beneficiary_id": state.beneficiary_id},
                )
            elif self._is_no(lower):
                self._clear_receiver(state)
                return AgentMessageResponse(
                    session_id=session_id,
                    response="Receiver not confirmed. Please provide the receiver name again.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )
            else:
                return AgentMessageResponse(
                    session_id=session_id,
                    response="Please confirm receiver with yes or no.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )

        if state.awaiting_note:
            if lower in {"no", "no note", "none", "skip"}:
                state.purpose = ""
            else:
                state.purpose = message.strip()
            state.awaiting_note = False
            state.note_collected = True

        beneficiaries = await self._retrieval.get_beneficiaries(user_id)
        default_method = await self._retrieval.get_default_payment_method(user_id)
        slots = None
        if not state.receiver_confirmed or state.amount is None or state.awaiting_note:
            slots = await self._agent.extract_slots(
                user_id=user_id,
                message=message,
                beneficiaries=beneficiaries,
                default_method_id=default_method,
            )

        if slots and slots.intent == "check_balance":
            target_user_id = user_id
            if slots.target_user_id:
                target_user_id = slots.target_user_id
            elif slots.target_user_name:
                named_target = slots.target_user_name.strip().lower()
                if named_target not in {"me", "my", "mine", "myself"}:
                    target_user_id = f"named:{named_target}"

            if target_user_id != user_id:
                log_event(
                    "guardrail_balance_denied",
                    {"session_id": session_id, "user_id": user_id, "target_user_id": target_user_id},
                )
                return AgentMessageResponse(
                    session_id=session_id,
                    response="I can only share your own balance. Please ask for your current balance.",
                    next_action="failed",
                    state=state.to_dict(),
                )

            balance = await self._agent.get_balance(requestor_user_id=user_id, target_user_id=user_id)
            log_event(
                "balance_returned",
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "available_balance": str(balance.available_balance),
                    "currency": balance.currency,
                },
            )
            return AgentMessageResponse(
                session_id=session_id,
                response=f"Your current balance is {balance.available_balance} {balance.currency}.",
                next_action="executed",
                state=state.to_dict(),
            )

        if (
            not state.receiver_confirmed
            and slots
            and slots.intent != "send_money"
            and slots.amount is None
            and not slots.receiver_hint
            and not slots.beneficiary_id
            and state.amount is None
            and not state.beneficiary_name
            and not state.beneficiary_id
        ):
            return AgentMessageResponse(
                session_id=session_id,
                response="I can help with payments. Please say: send <amount> AED to <receiver email>.",
                next_action="ask_slot",
                state=state.to_dict(),
            )

        if slots:
            if slots.amount is not None:
                state.amount = slots.amount
            if slots.receiver_hint:
                state.beneficiary_name = slots.receiver_hint
            if slots.beneficiary_id:
                state.beneficiary_id = slots.beneficiary_id
            if slots.payment_method_id:
                state.payment_method_id = slots.payment_method_id
            if slots.purpose:
                state.purpose = slots.purpose
                state.note_collected = True

        if not state.payment_method_id:
            state.payment_method_id = default_method

        if not state.receiver_confirmed:
            receiver_hint = state.beneficiary_name or state.beneficiary_id
            if not receiver_hint:
                return AgentMessageResponse(
                    session_id=session_id,
                    response="Please provide the receiver email.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )

            verify = await self._agent.verify_receiver(sender_user_id=user_id, receiver_hint=receiver_hint)
            if not verify.found:
                self._clear_receiver(state)
                return AgentMessageResponse(
                    session_id=session_id,
                    response="Receiver email was not found as an active user. Please provide a valid email.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )
            if verify.verification_status != "verified":
                self._clear_receiver(state)
                return AgentMessageResponse(
                    session_id=session_id,
                    response="This receiver is not verified. Payment cannot proceed.",
                    next_action="failed",
                    state=state.to_dict(),
                )

            state.beneficiary_id = verify.beneficiary_id
            state.beneficiary_name = verify.display_name
            state.beneficiary_masked_identifier = verify.masked_identifier
            state.awaiting_receiver_confirmation = True
            log_event(
                "receiver_verified",
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "beneficiary_id": state.beneficiary_id,
                    "beneficiary_name": state.beneficiary_name,
                },
            )
            return AgentMessageResponse(
                session_id=session_id,
                response=(
                    f"I found receiver {state.beneficiary_name} ({state.beneficiary_masked_identifier}). "
                    "Is this the intended receiver? (yes/no)"
                ),
                next_action="ask_slot",
                state=state.to_dict(),
            )

        if state.amount is None:
            return AgentMessageResponse(
                session_id=session_id,
                response="Please provide the amount in AED.",
                next_action="ask_slot",
                state=state.to_dict(),
            )
        if not state.note_collected and not state.awaiting_note:
            state.awaiting_note = True
            return AgentMessageResponse(
                session_id=session_id,
                response="Any additional note? Reply with note text or say no note.",
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
        log_event(
            "payment_ready_to_confirm",
            {
                "session_id": session_id,
                "user_id": user_id,
                "beneficiary_id": state.beneficiary_id,
                "amount": str(state.amount),
            },
        )
        return AgentMessageResponse(
            session_id=session_id,
            response=(
                f"Ready to pay {state.amount} {settings.default_currency} to {state.beneficiary_name or state.beneficiary_id}. "
                f"Note: {state.purpose or '(none)'} . Confirm to execute."
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
        if not state.receiver_confirmed or not state.beneficiary_id:
            return AgentMessageResponse(
                session_id=session_id,
                response="Receiver confirmation is required before execution.",
                next_action="ask_slot",
                state=state.to_dict(),
            )
        if not state.auth_context_id:
            return AgentMessageResponse(
                session_id=session_id,
                response="Authentication context missing. Please complete PIN/OTP verification.",
                next_action="auth_challenge",
                state=state.to_dict(),
            )

        try:
            await self._agent.register_auth_context(
                auth_context_id=state.auth_context_id,
                user_id=state.user_id,
                session_id=session_id,
            )
        except Exception:
            return AgentMessageResponse(
                session_id=session_id,
                response="Could not validate authentication context with gateway. Please retry auth.",
                next_action="auth_challenge",
                state=state.to_dict(),
            )

        result = await self._agent.execute_with_tool_call(
            PaymentExecutionInput(
                payer_user_id=state.user_id,
                session_id=session_id,
                beneficiary_id=state.beneficiary_id or "",
                amount=state.amount or Decimal("0"),
                payment_method_id=state.payment_method_id or "",
                purpose=state.purpose,
                auth_context_id=state.auth_context_id or "",
                idempotency_key=make_idempotency_key(),
            )
        )
        balance_text = ""
        if result.status == "SUCCESS":
            try:
                balance = await self._agent.get_balance(requestor_user_id=state.user_id, target_user_id=state.user_id)
                balance_text = f" Available balance: {balance.available_balance} {balance.currency}."
            except Exception:
                balance_text = ""
        self._reset_payment_state(state)
        log_event(
            "payment_execution_result",
            {
                "session_id": session_id,
                "user_id": state.user_id,
                "status": result.status,
                "transaction_id": result.transaction_id,
            },
        )
        next_action = "executed" if result.status == "SUCCESS" else "failed"
        return AgentMessageResponse(
            session_id=session_id,
            response=(
                f"Transfer {result.status}. transaction_id={result.transaction_id}. "
                f"timestamp={result.timestamp or 'n/a'}.{balance_text}"
            ),
            next_action=next_action,
            state=state.to_dict(),
        )

    def abort_transaction(self, session_id: str) -> dict[str, Any]:
        state = self._sessions.get(session_id)
        if not state:
            return {}
        self._reset_payment_state(state)
        log_event("transaction_aborted", {"session_id": session_id, "user_id": state.user_id})
        return state.to_dict()

    @staticmethod
    def _is_abort_command(lower_message: str) -> bool:
        return lower_message in {"abort", "cancel", "stop", "stop payment", "cancel payment"}

    @staticmethod
    def _is_yes(lower_message: str) -> bool:
        return lower_message in {"yes", "y", "confirm", "correct"}

    @staticmethod
    def _is_no(lower_message: str) -> bool:
        return lower_message in {"no", "n", "wrong", "change"}

    @staticmethod
    def _clear_receiver(state: SessionState) -> None:
        state.beneficiary_id = None
        state.beneficiary_name = None
        state.beneficiary_masked_identifier = None
        state.receiver_confirmed = False
        state.awaiting_receiver_confirmation = False
        state.ready_to_execute = False

    def _reset_payment_state(self, state: SessionState) -> None:
        state.amount = None
        state.purpose = ""
        state.note_collected = False
        state.awaiting_note = False
        state.auth_verified = False
        state.auth_context_id = None
        self._clear_receiver(state)

    def get_session_state(self, session_id: str) -> dict[str, Any]:
        state = self._sessions.get(session_id)
        return state.to_dict() if state else {}


orchestrator = AgentOrchestrator()
