from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

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
        self._execution_agent: Agent[PaymentExecutionDeps, ExecutionResult] | None = None

        if self._enabled:
            instructions = _load_prompt_instructions()
            self._slot_agent = Agent(
                model=f"openrouter:{settings.openrouter_model}",
                deps_type=SlotExtractionDeps,
                output_type=IntentSlots,
                instructions=instructions,
            )
            self._register_slot_tools()

            self._execution_agent = Agent(
                model=f"openrouter:{settings.openrouter_model}",
                deps_type=PaymentExecutionDeps,
                output_type=ExecutionResult,
                instructions=(
                    "You are a payment execution agent. "
                    "Call the pay_money tool exactly once with provided validated payload. "
                    "Then return executed=true and include transaction details."
                ),
            )
            self._register_execution_tools()

    def _register_slot_tools(self) -> None:
        assert self._slot_agent is not None

        @self._slot_agent.tool
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
        result = await self._slot_agent.run(message, deps=deps)
        slots = result.output
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
        lower = message.lower().strip()
        amount: Decimal | None = None
        receiver_hint = None
        beneficiary_id = None

        amt_match = re.search(r"\b(\d+(?:\.\d{1,2})?)\b(?:\s*aed)?", lower)
        if amt_match:
            try:
                amount = Decimal(amt_match.group(1))
            except Exception:
                amount = None

        email_match = re.search(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", lower)
        if email_match:
            receiver_hint = email_match.group(0)

        recipient_patterns = [
            r"\bto\s+([a-zA-Z][\w.-]*)",
            r"\bfor\s+([a-zA-Z][\w.-]*)",
            r"\binto\s+([a-zA-Z][\w.-]*)",
            r"\bpay\s+([a-zA-Z][\w.-]*)",
            r"\bsend\s+(?:money\s+)?(?:\d+(?:\.\d{1,2})?\s*(?:aed)?\s+)?to\s+([a-zA-Z][\w.-]*)",
            r"\btransfer\s+(?:\d+(?:\.\d{1,2})?\s*(?:aed)?\s+)?to\s+([a-zA-Z][\w.-]*)",
        ]
        if receiver_hint is None:
            for pattern in recipient_patterns:
                m = re.search(pattern, lower)
                if m:
                    receiver_hint = m.group(1)
                    break

        target_user_name = None
        if "balance" in lower and "of " in lower:
            target_user_name = lower.split("of ", 1)[1].split()[0]
        elif "balance for " in lower:
            target_user_name = lower.split("balance for ", 1)[1].split()[0]
        if receiver_hint:
            for row in beneficiaries:
                if row.get("name", "").lower() == receiver_hint and row.get("verified"):
                    beneficiary_id = row.get("beneficiary_id")
                    break
        return IntentSlots(
            intent=_detect_intent(lower),
            amount=amount,
            receiver_hint=receiver_hint,
            beneficiary_id=beneficiary_id,
            target_user_name=target_user_name,
            payment_method_id=default_method_id,
        )


def _detect_intent(lower_text: str) -> str:
    balance_markers = {
        "balance",
        "current balance",
        "available balance",
        "how much do i have",
        "funds left",
        "wallet balance",
    }
    payment_markers = {
        "pay",
        "send",
        "transfer",
        "remit",
        "settle",
        "give",
        "move",
        "wire",
    }

    if any(marker in lower_text for marker in balance_markers):
        return "check_balance"
    if any(marker in lower_text for marker in payment_markers):
        return "send_money"
    return "unknown"


def _load_prompt_instructions() -> str:
    try:
        with open("prompts/payment_agent_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return (
            "Detect intent send_money/check_balance and extract slots. "
            "Enforce no cross-account balance disclosure."
        )
