from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from app.core.agent_logger import log_event
from app.core.config import settings
from app.services.tool_router import PaymentToolRouter
from shared_lib.contracts.payment import PaymentTransferRequest, PaymentTransferResponse
from shared_lib.contracts.payment import VerifyReceiverResponse


@dataclass
class SlotExtractionDeps:
    user_id: str
    beneficiaries: list[dict]
    default_method_id: str | None


@dataclass
class PaymentExecutionDeps:
    tool_router: PaymentToolRouter


class IntentSlots(BaseModel):
    intent: Literal["send_money", "check_balance", "unknown"]
    amount: Decimal | None = None
    receiver_hint: str | None = None
    beneficiary_id: str | None = None
    target_user_id: str | None = None
    target_user_name: str | None = None
    purpose: str = ""
    payment_method_id: str | None = None


class ExecutionResult(BaseModel):
    executed: bool
    message: str
    transaction_id: str | None = None
    status: str | None = None


class PaymentExecutionInput(BaseModel):
    payer_user_id: str
    session_id: str
    beneficiary_id: str
    amount: Decimal = Field(..., gt=Decimal("0"))
    payment_method_id: str
    purpose: str = ""
    auth_context_id: str
    idempotency_key: str


class PydanticPaymentAgentService:
    def __init__(self) -> None:
        self._enabled = bool(settings.openrouter_api_key)
        self._tool_router = PaymentToolRouter()
        self._slot_agent: Agent[SlotExtractionDeps, IntentSlots] | None = None
        self._slot_agent_fallback: Agent[SlotExtractionDeps, IntentSlots] | None = None
        self._execution_agent: Agent[PaymentExecutionDeps, ExecutionResult] | None = None

        if self._enabled:
            # pydantic-ai OpenRouter provider expects OPENROUTER_API_KEY in environment.
            if not os.getenv("OPENROUTER_API_KEY"):
                os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key
            instructions = _load_prompt_instructions()
            slot_model = (settings.openrouter_slot_model or settings.openrouter_model).strip()
            self._slot_agent = Agent(
                model=f"openrouter:{slot_model}",
                deps_type=SlotExtractionDeps,
                output_type=IntentSlots,
                instructions=instructions,
                model_settings=ModelSettings(max_tokens=settings.openrouter_slot_max_tokens),
            )
            self._register_slot_tools(self._slot_agent)

            primary_model = settings.openrouter_model.strip()
            if primary_model and primary_model != slot_model:
                self._slot_agent_fallback = Agent(
                    model=f"openrouter:{primary_model}",
                    deps_type=SlotExtractionDeps,
                    output_type=IntentSlots,
                    instructions=instructions,
                    model_settings=ModelSettings(max_tokens=settings.openrouter_slot_max_tokens),
                )
                self._register_slot_tools(self._slot_agent_fallback)

            self._execution_agent = Agent(
                model=f"openrouter:{settings.openrouter_model}",
                deps_type=PaymentExecutionDeps,
                output_type=ExecutionResult,
                instructions=(
                    "You are a payment execution agent. "
                    "Call the pay_money tool exactly once with provided validated payload. "
                    "Then return executed=true and include transaction details."
                ),
                model_settings=ModelSettings(max_tokens=settings.openrouter_execution_max_tokens),
            )
            self._register_execution_tools()

    def _register_slot_tools(self, slot_agent: Agent[SlotExtractionDeps, IntentSlots]) -> None:
        @slot_agent.tool
        def match_beneficiary(ctx: RunContext[SlotExtractionDeps], beneficiary_name: str) -> str | None:
            for row in ctx.deps.beneficiaries:
                if not row.get("verified"):
                    continue
                if row.get("name", "").lower() == beneficiary_name.lower():
                    return row.get("beneficiary_id")
            return None

    def _register_execution_tools(self) -> None:
        assert self._execution_agent is not None

        @self._execution_agent.tool
        async def pay_money(
            ctx: RunContext[PaymentExecutionDeps],
            payer_user_id: str,
            session_id: str,
            beneficiary_id: str,
            amount: Decimal,
            payment_method_id: str,
            purpose: str,
            auth_context_id: str,
            idempotency_key: str,
        ) -> dict:
            payload = PaymentTransferRequest(
                payer_user_id=payer_user_id,
                session_id=session_id,
                beneficiary_id=beneficiary_id,
                amount=amount,
                currency="AED",
                payment_method_id=payment_method_id,
                purpose=purpose,
                auth_context_id=auth_context_id,
                idempotency_key=idempotency_key,
            )
            result = await ctx.deps.tool_router.transfer(payload)
            return result.model_dump(mode="json")

    async def extract_slots(
        self,
        user_id: str,
        message: str,
        beneficiaries: list[dict],
        default_method_id: str | None,
    ) -> IntentSlots:
        if not self._enabled or not self._slot_agent:
            return self._fallback_slot_extraction(message, beneficiaries, default_method_id)

        deps = SlotExtractionDeps(
            user_id=user_id,
            beneficiaries=beneficiaries,
            default_method_id=default_method_id,
        )

        last_error: Exception | None = None
        try:
            result = await self._slot_agent.run(message, deps=deps)
            slots = result.output
            log_event(
                "slot_extraction_primary",
                {
                    "intent": slots.intent,
                    "has_amount": slots.amount is not None,
                    "has_receiver_hint": bool(slots.receiver_hint),
                },
            )
        except Exception as exc:
            last_error = exc
            slots = None
            log_event("slot_extraction_primary_error", {"error": str(exc)[:500]})

        if (slots is None or self._slots_empty(slots)) and self._slot_agent_fallback is not None:
            try:
                retry_result = await self._slot_agent_fallback.run(message, deps=deps)
                slots = retry_result.output
                last_error = None
                log_event(
                    "slot_extraction_fallback",
                    {
                        "intent": slots.intent,
                        "has_amount": slots.amount is not None,
                        "has_receiver_hint": bool(slots.receiver_hint),
                    },
                )
            except Exception as exc:
                last_error = exc
                log_event("slot_extraction_fallback_error", {"error": str(exc)[:500]})

        if slots is None:
            if last_error:
                log_event("slot_extraction_return_unknown", {"reason": "all_models_failed"})
                return self._fallback_slot_extraction(message, beneficiaries, default_method_id)
            log_event("slot_extraction_return_unknown", {"reason": "no_slots_output"})
            return self._fallback_slot_extraction(message, beneficiaries, default_method_id)

        if self._slots_empty(slots):
            log_event("slot_extraction_return_unknown", {"reason": "empty_slots"})
            return self._fallback_slot_extraction(message, beneficiaries, default_method_id)

        if slots.payment_method_id is None:
            slots.payment_method_id = default_method_id
        return slots

    async def execute_with_tool_call(self, payload: PaymentExecutionInput) -> PaymentTransferResponse:
        if not self._enabled or not self._execution_agent:
            return await self._tool_router.transfer(
                PaymentTransferRequest(
                    payer_user_id=payload.payer_user_id,
                    session_id=payload.session_id,
                    beneficiary_id=payload.beneficiary_id,
                    amount=payload.amount,
                    currency="AED",
                    payment_method_id=payload.payment_method_id,
                    purpose=payload.purpose,
                    auth_context_id=payload.auth_context_id,
                    idempotency_key=payload.idempotency_key,
                )
            )

        deps = PaymentExecutionDeps(tool_router=self._tool_router)
        prompt = (
            "Execute payment using this validated payload:\n"
            f"{payload.model_dump_json(indent=2)}\n"
            "Do not change values."
        )
        run_result = await self._execution_agent.run(prompt, deps=deps)
        output = run_result.output
        if not output.executed:
            return PaymentTransferResponse(
                transaction_id="",
                status="FAILED",
                message=output.message,
                failure_code="EXECUTION_AGENT_ABORTED",
            )

        # Tool output is returned through model narration, so fetch directly as reliable fallback.
        return await self._tool_router.transfer(
            PaymentTransferRequest(
                payer_user_id=payload.payer_user_id,
                session_id=payload.session_id,
                beneficiary_id=payload.beneficiary_id,
                amount=payload.amount,
                currency="AED",
                payment_method_id=payload.payment_method_id,
                purpose=payload.purpose,
                auth_context_id=payload.auth_context_id,
                idempotency_key=payload.idempotency_key,
            )
        )

    async def get_balance(self, requestor_user_id: str, target_user_id: str):
        return await self._tool_router.get_balance(requestor_user_id=requestor_user_id, target_user_id=target_user_id)

    async def verify_receiver(self, sender_user_id: str, receiver_hint: str) -> VerifyReceiverResponse:
        return await self._tool_router.verify_receiver(sender_user_id=sender_user_id, receiver_hint=receiver_hint)

    async def register_auth_context(self, auth_context_id: str, user_id: str, session_id: str) -> None:
        await self._tool_router.register_auth_context(
            auth_context_id=auth_context_id,
            user_id=user_id,
            session_id=session_id,
        )

    def _fallback_slot_extraction(
        self,
        message: str,
        beneficiaries: list[dict],
        default_method_id: str | None,
    ) -> IntentSlots:
        text = message.strip()
        lower = text.lower()

        amount: Decimal | None = None
        receiver_hint: str | None = None
        purpose = ""
        intent: Literal["send_money", "check_balance", "unknown"] = "unknown"

        if self._is_balance_intent(lower):
            intent = "check_balance"

        email_match = re.search(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", text)
        if email_match:
            receiver_hint = self._sanitize_receiver_hint(email_match.group(1))

        amount_match = re.search(
            r"(?<!\w)(\d+(?:\.\d{1,2})?)\s*(?:aed|dhs?|dirham|dirhams)?\b",
            lower,
            flags=re.IGNORECASE,
        )
        if amount_match:
            try:
                amount = Decimal(amount_match.group(1))
            except Exception:
                amount = None

        if not receiver_hint:
            to_match = re.search(r"\bto\s+([^\s,!?;:]+)", text, flags=re.IGNORECASE)
            if to_match:
                receiver_hint = self._sanitize_receiver_hint(to_match.group(1))

        note_match = re.search(r"\bnote\s*[:\-]\s*(.+)$", text, flags=re.IGNORECASE)
        if note_match:
            purpose = note_match.group(1).strip()

        if self._is_send_intent(lower) or receiver_hint or amount is not None:
            intent = "send_money"

        if intent == "check_balance":
            amount = None
            receiver_hint = None
            purpose = ""

        return IntentSlots(
            intent=intent,
            amount=amount,
            receiver_hint=receiver_hint,
            purpose=purpose,
            payment_method_id=default_method_id,
        )

    @staticmethod
    def _slots_empty(slots: IntentSlots) -> bool:
        return (
            slots.intent == "unknown"
            and slots.amount is None
            and not slots.receiver_hint
            and not slots.beneficiary_id
            and not slots.target_user_id
            and not slots.target_user_name
            and not slots.purpose
        )

    @staticmethod
    def _sanitize_receiver_hint(value: str) -> str:
        return value.strip().strip(".,!?;:()[]{}<>\"'").lower()

    @staticmethod
    def _is_send_intent(lower_message: str) -> bool:
        keywords = {
            "send",
            "pay",
            "transfer",
            "remit",
            "give",
            "move money",
            "send money",
            "make payment",
        }
        return any(token in lower_message for token in keywords)

    @staticmethod
    def _is_balance_intent(lower_message: str) -> bool:
        keywords = {
            "balance",
            "available balance",
            "how much do i have",
            "funds left",
            "wallet amount",
            "account balance",
        }
        return any(token in lower_message for token in keywords)


def _load_prompt_instructions() -> str:
    try:
        prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "payment_agent_prompt.txt"
        with prompt_path.open("r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return (
            "Detect intent send_money/check_balance and extract slots. "
            "Enforce no cross-account balance disclosure."
        )
