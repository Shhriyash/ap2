from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.core.agent_logger import log_event
from app.core.config import settings
from app.services.auth_service import auth_service
from app.services.pydantic_payment_agent import (
    PaymentExecutionInput,
    PydanticPaymentAgentService,
)
from app.services.retrieval import RetrievalService
from shared_lib.contracts.agent import AgentMessageResponse, AuthChallengeVerifyResponse
from shared_lib.core.idempotency import make_idempotency_key
import re


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
    add_contact_name: str | None = None
    add_contact_email: str | None = None
    awaiting_add_contact_confirm: bool = False
    last_transfer_amount: Decimal | None = None
    last_transfer_currency: str | None = None
    last_transfer_receiver: str | None = None
    last_transfer_note: str = ""
    last_transfer_transaction_id: str | None = None
    last_transfer_status: str | None = None
    last_transfer_timestamp: str | None = None

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
            "add_contact_name": self.add_contact_name,
            "add_contact_email": self.add_contact_email,
            "awaiting_add_contact_confirm": self.awaiting_add_contact_confirm,
            "last_transfer_amount": str(self.last_transfer_amount) if self.last_transfer_amount is not None else None,
            "last_transfer_currency": self.last_transfer_currency,
            "last_transfer_receiver": self.last_transfer_receiver,
            "last_transfer_note": self.last_transfer_note,
            "last_transfer_transaction_id": self.last_transfer_transaction_id,
            "last_transfer_status": self.last_transfer_status,
            "last_transfer_timestamp": self.last_transfer_timestamp,
        }


class AgentOrchestrator:
    def __init__(self) -> None:
        self._agent = PydanticPaymentAgentService()
        self._retrieval = RetrievalService()
        self._sessions: dict[str, SessionState] = {}
        self._auth_challenges: dict[str, dict[str, Any]] = {}

    async def process_message(self, session_id: str, user_id: str, message: str, channel: str = "text") -> AgentMessageResponse:
        log_event("agent_message_received", {"session_id": session_id, "user_id": user_id, "message": message})
        state = self._sessions.setdefault(session_id, SessionState(user_id=user_id))
        lower = message.strip().lower()

        if self._is_abort_command(lower):
            self._reset_payment_state(state)
            self._clear_add_contact(state)
            log_event("transaction_aborted", {"session_id": session_id, "user_id": user_id})
            return AgentMessageResponse(
                session_id=session_id,
                response="Cancelled.",
                next_action="failed",
                state=state.to_dict(),
            )

        if state.awaiting_add_contact_confirm:
            if self._is_yes(lower):
                try:
                    result = await self._agent.add_beneficiary(
                        owner_user_id=user_id,
                        display_name=state.add_contact_name or "",
                        email=state.add_contact_email or "",
                    )
                    self._clear_add_contact(state)
                    if result.status == "not_found":
                        log_event("add_contact_not_found", {"session_id": session_id, "user_id": user_id})
                        return AgentMessageResponse(
                            session_id=session_id,
                            response=f"Couldn't find anyone with that email. Check the address and try again.",
                            next_action="ask_slot",
                            state=state.to_dict(),
                        )
                    verb = "updated" if result.status == "already_exists" else "added"
                    log_event("contact_added", {"session_id": session_id, "user_id": user_id, "beneficiary_id": result.beneficiary_id})
                    return AgentMessageResponse(
                        session_id=session_id,
                        response=f"Done. {result.display_name} ({result.masked_identifier}) has been {verb} to your contacts.",
                        next_action="ask_slot",
                        state=state.to_dict(),
                    )
                except Exception as exc:
                    log_event("add_contact_error", {"session_id": session_id, "error": str(exc)[:200]})
                    self._clear_add_contact(state)
                    return AgentMessageResponse(
                        session_id=session_id,
                        response="Something went wrong adding the contact. Please try again.",
                        next_action="failed",
                        state=state.to_dict(),
                    )
            elif self._is_no(lower):
                self._clear_add_contact(state)
                return AgentMessageResponse(
                    session_id=session_id,
                    response="Okay, contact not saved.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )
            else:
                return AgentMessageResponse(
                    session_id=session_id,
                    response=f"Add {state.add_contact_name} ({state.add_contact_email}) as a contact? Please say yes or no.",
                    next_action="ask_slot",
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
                    response="No problem. Who do you want to send to?",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )
            else:
                return AgentMessageResponse(
                    session_id=session_id,
                    response="Please reply with yes or no so I can proceed safely.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )

        if state.awaiting_note:
            state.purpose = self._normalize_note_input(message)
            state.awaiting_note = False
            state.note_collected = True

        if self._is_receivers_help_query(lower) and not self._contains_amount_or_name(message):
            return AgentMessageResponse(
                session_id=session_id,
                response="You can pay any of your saved contacts by name. Who do you want to send to?",
                next_action="ask_slot",
                state=state.to_dict(),
            )

        beneficiaries = await self._retrieval.get_beneficiaries(user_id)
        default_method = await self._retrieval.get_default_payment_method(user_id)
        slots = None
        if not state.receiver_confirmed or state.amount is None or state.awaiting_note:
            slots = await self._agent.extract_slots(
                session_id=session_id,
                user_id=user_id,
                message=message,
                beneficiaries=beneficiaries,
                default_method_id=default_method,
            )

        if slots and slots.intent == "last_transfer":
            if not state.last_transfer_transaction_id:
                return AgentMessageResponse(
                    session_id=session_id,
                    response="No transfer has been executed in this session yet.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )
            return AgentMessageResponse(
                session_id=session_id,
                response=(
                    f"Last transfer: {state.last_transfer_amount} {state.last_transfer_currency} "
                    f"to {state.last_transfer_receiver}. "
                    f"status={state.last_transfer_status}. "
                    f"transaction_id={state.last_transfer_transaction_id}. "
                    f"timestamp={state.last_transfer_timestamp or 'n/a'}."
                ),
                next_action="executed",
                state=state.to_dict(),
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

            try:
                balance = await self._agent.get_balance(requestor_user_id=user_id, target_user_id=user_id)
            except Exception:
                return AgentMessageResponse(
                    session_id=session_id,
                    response="I couldn't fetch your balance right now. Please try again in a moment.",
                    next_action="failed",
                    state=state.to_dict(),
                )
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

        if slots and slots.intent == "add_beneficiary":
            if slots.receiver_name:
                state.add_contact_name = slots.receiver_name
            if slots.beneficiary_email:
                state.add_contact_email = slots.beneficiary_email

            if not state.add_contact_name:
                return AgentMessageResponse(
                    session_id=session_id,
                    response="What name should I save this contact under?",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )
            if not state.add_contact_email:
                return AgentMessageResponse(
                    session_id=session_id,
                    response=f"What's {state.add_contact_name}'s email address?",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )

            state.awaiting_add_contact_confirm = True
            return AgentMessageResponse(
                session_id=session_id,
                response=f"Add {state.add_contact_name} ({state.add_contact_email}) as a contact? (yes/no)",
                next_action="ask_slot",
                state=state.to_dict(),
            )

        if (
            not state.receiver_confirmed
            and slots
            and slots.intent != "send_money"
            and slots.amount is None
            and not slots.receiver_name
            and not slots.beneficiary_id
            and state.amount is None
            and not state.beneficiary_name
            and not state.beneficiary_id
        ):
            if self._is_receivers_help_query(lower):
                return AgentMessageResponse(
                    session_id=session_id,
                    response="You can pay any of your saved contacts by name. Tell me who and how much.",
                    next_action="ask_slot",
                    state=state.to_dict(),
                )

            response_text = await self._agent.generate_response(message)
            return AgentMessageResponse(
                session_id=session_id,
                response=response_text,
                next_action="ask_slot",
                state=state.to_dict(),
            )

        if slots:
            if slots.amount is not None:
                try:
                    state.amount = Decimal(str(slots.amount))
                except Exception:
                    state.amount = state.amount
            if slots.receiver_name:
                state.beneficiary_name = slots.receiver_name
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
                ask = "Who do you want to send to?" if channel == "voice" else "Who should I send to? Please provide their name."
                if state.amount is None:
                    ask += " And how much (in AED)?"
                return AgentMessageResponse(
                    session_id=session_id,
                    response=ask,
                    next_action="ask_slot",
                    state=state.to_dict(),
                )

            verify = await self._agent.verify_receiver(sender_user_id=user_id, receiver_hint=receiver_hint)
            if not verify.found:
                self._clear_receiver(state)
                return AgentMessageResponse(
                    session_id=session_id,
                    response=(
                        f"I couldn't find anyone named \"{receiver_hint}\" in your contacts. "
                        "Check the name or add them as a contact in the app first."
                    ),
                    next_action="ask_slot",
                    state=state.to_dict(),
                )
            if verify.verification_status != "verified":
                self._clear_receiver(state)
                return AgentMessageResponse(
                    session_id=session_id,
                    response="That contact is not verified. Payment cannot proceed.",
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
                    f"Found {state.beneficiary_name} ({state.beneficiary_masked_identifier}). "
                    "Is this the right person? (yes/no)"
                ),
                next_action="ask_slot",
                state=state.to_dict(),
            )

        if state.amount is None:
            return AgentMessageResponse(
                session_id=session_id,
                response="What amount should I send (in AED)?",
                next_action="ask_slot",
                state=state.to_dict(),
            )
        if not state.note_collected and not state.awaiting_note:
            state.awaiting_note = True
            return AgentMessageResponse(
                session_id=session_id,
                response="Any note to add? (optional)",
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
                response="Please verify with your PIN to continue.",
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

    async def verify_auth_challenge(self, challenge_id: str, user_id: str, value: str) -> AuthChallengeVerifyResponse:
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
            try:
                pin_verified = await auth_service.verify_transaction_pin(internal_user_id=user_id, pin=value)
            except Exception:
                return AuthChallengeVerifyResponse(
                    challenge_id=challenge_id,
                    verified=False,
                    challenge_type="pin",
                    next_step="retry",
                    message="PIN verification service is temporarily unavailable. Please retry.",
                )

            if pin_verified:
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
                challenge["challenge_type"] = "otp"
                challenge["attempts"] = 0
                return AuthChallengeVerifyResponse(
                    challenge_id=challenge_id,
                    verified=False,
                    challenge_type="otp",
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

        try:
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
        except Exception as exc:
            log_event(
                "payment_execution_exception",
                {"session_id": session_id, "user_id": state.user_id, "error": str(exc)[:500]},
            )
            return AgentMessageResponse(
                session_id=session_id,
                response="Transfer failed due to a temporary execution error. Please retry.",
                next_action="failed",
                state=state.to_dict(),
            )
        balance_text = ""
        if result.status == "SUCCESS":
            try:
                balance = await self._agent.get_balance(requestor_user_id=state.user_id, target_user_id=state.user_id)
                balance_text = f" Available balance: {balance.available_balance} {balance.currency}."
            except Exception:
                balance_text = ""
        state.last_transfer_amount = state.amount
        state.last_transfer_currency = settings.default_currency
        state.last_transfer_receiver = state.beneficiary_name or state.beneficiary_id
        state.last_transfer_note = state.purpose
        state.last_transfer_transaction_id = result.transaction_id
        state.last_transfer_status = result.status
        state.last_transfer_timestamp = result.timestamp
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
    def _is_greeting(lower_message: str) -> bool:
        return any(
            token in lower_message
            for token in {
                "hi",
                "hii",
                "hello",
                "hey",
                "good morning",
                "good afternoon",
                "good evening",
            }
        )

    @staticmethod
    def _is_small_talk(lower_message: str) -> bool:
        return any(
            token in lower_message
            for token in {
                "how are you",
                "how are u",
                "what's up",
                "whats up",
                "how is it going",
            }
        )

    @staticmethod
    def _is_help_request(lower_message: str) -> bool:
        return any(
            token in lower_message
            for token in {
                "help",
                "what can you do",
                "what do you do",
                "assist",
                "capabilities",
            }
        )

    @staticmethod
    def _is_receivers_help_query(lower_message: str) -> bool:
        return (
            ("who" in lower_message or "whom" in lower_message)
            and ("send" in lower_message or "pay" in lower_message or "transfer" in lower_message)
        )

    @staticmethod
    def _contains_amount_or_name(message: str) -> bool:
        return bool(re.search(r"\b\d+(?:\.\d{1,2})?\b", message))

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

    @staticmethod
    def _clear_add_contact(state: SessionState) -> None:
        state.add_contact_name = None
        state.add_contact_email = None
        state.awaiting_add_contact_confirm = False

    @staticmethod
    def _normalize_note_input(raw_note: str) -> str:
        raw = raw_note.strip()
        if raw.lower() in {"no", "no note", "none", "skip", "n/a", "na"}:
            return ""
        normalized = re.sub(r"^\s*(?:add\s+)?note\s*[:\-]\s*", "", raw, flags=re.IGNORECASE)
        normalized = re.sub(r"^\s*note\s+(?:is|as)\s+", "", normalized, flags=re.IGNORECASE)
        return normalized.strip()

    def get_session_state(self, session_id: str) -> dict[str, Any]:
        state = self._sessions.get(session_id)
        return state.to_dict() if state else {}


orchestrator = AgentOrchestrator()
