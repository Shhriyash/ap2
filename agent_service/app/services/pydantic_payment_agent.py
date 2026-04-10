from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.fallback import FallbackModel
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
    intent: Literal["send_money", "check_balance", "last_transfer", "add_beneficiary", "unknown"]
    amount: float | None = None
    receiver_name: str | None = None
    beneficiary_id: str | None = None
    beneficiary_email: str | None = None
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
        self._enabled = bool(settings.groq_api_key or settings.openrouter_api_key)
        self._tool_router = PaymentToolRouter()
        self._slot_agent: Agent[SlotExtractionDeps, IntentSlots] | None = None
        self._execution_agent: Agent[PaymentExecutionDeps, ExecutionResult] | None = None
        self._conv_agent: Agent[None, str] | None = None
        self._slot_histories: dict[str, list[ModelMessage]] = {}
        self._slot_history_max_messages = 20

        if self._enabled:
            # Provider SDKs resolve keys from environment.
            if settings.groq_api_key and not os.getenv("GROQ_API_KEY"):
                os.environ["GROQ_API_KEY"] = settings.groq_api_key
            if settings.openrouter_api_key and not os.getenv("OPENROUTER_API_KEY"):
                os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key

            instructions = _load_prompt_instructions()
            slot_model = self._build_model_with_rate_limit_fallback(
                groq_model_name=(settings.groq_slot_model or settings.groq_model).strip(),
                openrouter_model_name=(settings.openrouter_slot_model or settings.openrouter_model).strip(),
            )
            self._slot_agent = Agent(
                model=slot_model,
                deps_type=SlotExtractionDeps,
                output_type=IntentSlots,
                instructions=instructions,
                model_settings=ModelSettings(max_tokens=settings.openrouter_slot_max_tokens),
            )
            self._register_slot_tools(self._slot_agent)

            self._execution_agent = Agent(
                model=self._build_model_with_rate_limit_fallback(
                    groq_model_name=settings.groq_model.strip(),
                    openrouter_model_name=settings.openrouter_model.strip(),
                ),
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

            self._conv_agent = Agent(
                model=slot_model,
                output_type=str,
                instructions=(
                    "You are a friendly payment assistant for a mobile payment app. "
                    "Respond naturally and briefly (1-2 sentences) to the user's message. "
                    "You can transfer money, check balances, and review recent transfers. "
                    "Do not perform any actual transactions here — just respond conversationally."
                ),
                model_settings=ModelSettings(max_tokens=100),
            )

    def _build_model_with_rate_limit_fallback(self, groq_model_name: str, openrouter_model_name: str):
        groq_model = f"groq:{groq_model_name}" if settings.groq_api_key and groq_model_name else None
        openrouter_model = (
            f"openrouter:{openrouter_model_name}" if settings.openrouter_api_key and openrouter_model_name else None
        )

        if groq_model and openrouter_model:
            return FallbackModel(
                groq_model,
                openrouter_model,
                fallback_on=self._fallback_on_rate_limit,
            )
        if groq_model:
            return groq_model
        if openrouter_model:
            return openrouter_model
        raise RuntimeError("No LLM provider configured. Set GROQ_API_KEY or OPENROUTER_API_KEY.")

    @staticmethod
    def _fallback_on_rate_limit(exc: Exception) -> bool:
        if not isinstance(exc, ModelHTTPError):
            return False
        status_code = getattr(exc, "status_code", None)
        if status_code in {429, 503}:
            return True
        body_text = str(getattr(exc, "body", "")).lower()
        return any(token in body_text for token in {"rate limit", "too many requests", "quota", "invalid json schema"})

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
            amount: str,
            payment_method_id: str,
            purpose: str,
            auth_context_id: str,
            idempotency_key: str,
        ) -> dict:
            payload = PaymentTransferRequest(
                payer_user_id=payer_user_id,
                session_id=session_id,
                beneficiary_id=beneficiary_id,
                amount=Decimal(amount),
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
        session_id: str,
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
            result = await self._slot_agent.run(
                message,
                deps=deps,
                message_history=self._slot_histories.get(session_id, []),
            )
            self._slot_histories[session_id] = result.all_messages()[-self._slot_history_max_messages :]
            slots = result.output
            log_event(
                "slot_extraction_primary",
                {
                    "intent": slots.intent,
                    "has_amount": slots.amount is not None,
                    "has_receiver_name": bool(slots.receiver_name),
                },
            )
        except Exception as exc:
            last_error = exc
            slots = None
            log_event("slot_extraction_primary_error", {"error": str(exc)[:500]})

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
        try:
            run_result = await self._execution_agent.run(prompt, deps=deps)
            output = run_result.output
            if not output.executed:
                return PaymentTransferResponse(
                    transaction_id="",
                    status="FAILED",
                    message=output.message,
                    failure_code="EXECUTION_AGENT_ABORTED",
                )
        except Exception as exc:
            log_event("execution_agent_error", {"error": str(exc)[:500]})

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

    async def add_beneficiary(self, owner_user_id: str, display_name: str, email: str):
        return await self._tool_router.add_beneficiary(
            owner_user_id=owner_user_id,
            display_name=display_name,
            email=email,
        )

    async def generate_response(self, message: str) -> str:
        if not self._enabled or not self._conv_agent:
            return "Hi. I can transfer money and check your balance. What do you need?"
        try:
            result = await self._conv_agent.run(message)
            return result.output.strip() or "I can help with transfers and balance checks."
        except Exception as exc:
            log_event("conv_agent_error", {"error": str(exc)[:200]})
            return "Hi. I can transfer money and check your balance. What do you need?"

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

        amount: float | None = None
        receiver_name: str | None = None
        purpose = ""
        intent: Literal["send_money", "check_balance", "unknown"] = "unknown"

        if self._is_balance_intent(lower):
            intent = "check_balance"
        elif self._is_last_transfer_intent(lower):
            intent = "last_transfer"
        elif self._is_add_beneficiary_intent(lower):
            intent = "add_beneficiary"

        amount_match = re.search(
            r"(?<!\w)(\d+(?:\.\d{1,2})?)\s*(?:aed|dhs?|dirham|dirhams)?\b",
            lower,
            flags=re.IGNORECASE,
        )
        if amount_match:
            try:
                amount = float(amount_match.group(1))
            except Exception:
                amount = None

        to_match = re.search(r"\bto\s+([^\s,!?;:]+)", text, flags=re.IGNORECASE)
        if to_match:
            candidate = to_match.group(1).strip().strip(".,!?;:()[]{}<>\"'")
            if candidate.lower() not in {"send", "pay", "transfer", "give", "move", "money", "payment"}:
                receiver_name = candidate

        note_match = re.search(r"\bnote\s*[:\-]\s*(.+)$", text, flags=re.IGNORECASE)
        if note_match:
            purpose = note_match.group(1).strip()

        if self._is_send_intent(lower) or (receiver_name and intent == "unknown") or amount is not None:
            intent = "send_money"

        beneficiary_email: str | None = None
        if intent == "add_beneficiary":
            email_match = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)
            if email_match:
                beneficiary_email = email_match.group(0).strip().lower()
            amount = None
            purpose = ""

        if intent == "check_balance":
            amount = None
            receiver_name = None
            purpose = ""

        return IntentSlots(
            intent=intent,
            amount=amount,
            receiver_name=receiver_name,
            beneficiary_email=beneficiary_email,
            purpose=purpose,
            payment_method_id=default_method_id,
        )

    @staticmethod
    def _slots_empty(slots: IntentSlots) -> bool:
        return (
            slots.intent == "unknown"
            and slots.amount is None
            and not slots.receiver_name
            and not slots.beneficiary_id
            and not slots.target_user_id
            and not slots.target_user_name
            and not slots.purpose
        )

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

    @staticmethod
    def _is_add_beneficiary_intent(lower_message: str) -> bool:
        keywords = {
            "add contact",
            "add beneficiary",
            "add a contact",
            "add a beneficiary",
            "save contact",
            "new contact",
            "add payee",
            "new payee",
        }
        return any(token in lower_message for token in keywords)

    @staticmethod
    def _is_last_transfer_intent(lower_message: str) -> bool:
        keywords = {
            "last transfer",
            "previous transfer",
            "last payment",
            "what was the money you sent",
            "how much did i send",
            "what did i just send",
            "show last transaction",
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
