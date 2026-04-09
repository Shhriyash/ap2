from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from app.core.config import settings
from app.services.tool_router import PaymentToolRouter
from shared_lib.contracts.payment import PaymentTransferRequest, PaymentTransferResponse


@dataclass
class SlotExtractionDeps:
    user_id: str
    beneficiaries: list[dict]
    default_method_id: str | None


@dataclass
class PaymentExecutionDeps:
    tool_router: PaymentToolRouter


class IntentSlots(BaseModel):
    intent: Literal["send_money", "unknown"]
    amount: Decimal | None = None
    beneficiary_name: str | None = None
    beneficiary_id: str | None = None
    purpose: str = ""
    payment_method_id: str | None = None


class ExecutionResult(BaseModel):
    executed: bool
    message: str
    transaction_id: str | None = None
    status: str | None = None


class PaymentExecutionInput(BaseModel):
    payer_user_id: str
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
            self._slot_agent = Agent(
                model=f"openrouter:{settings.openrouter_model}",
                deps_type=SlotExtractionDeps,
                output_type=IntentSlots,
                instructions=(
                    "Extract payment intent from user text. "
                    "If intent is payment, fill amount, beneficiary_name, optional purpose. "
                    "Use match_beneficiary tool when beneficiary_name is present."
                ),
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
            beneficiary_id: str,
            amount: Decimal,
            payment_method_id: str,
            purpose: str,
            auth_context_id: str,
            idempotency_key: str,
        ) -> dict:
            payload = PaymentTransferRequest(
                payer_user_id=payer_user_id,
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
                beneficiary_id=payload.beneficiary_id,
                amount=payload.amount,
                currency="AED",
                payment_method_id=payload.payment_method_id,
                purpose=payload.purpose,
                auth_context_id=payload.auth_context_id,
                idempotency_key=payload.idempotency_key,
            )
        )

    def _fallback_slot_extraction(
        self,
        message: str,
        beneficiaries: list[dict],
        default_method_id: str | None,
    ) -> IntentSlots:
        lower = message.lower()
        amount: Decimal | None = None
        beneficiary_name = None
        beneficiary_id = None
        tokens = lower.split()
        for token in tokens:
            try:
                amount = Decimal(token)
                break
            except Exception:
                continue
        if " to " in lower:
            beneficiary_name = lower.split(" to ", 1)[1].split()[0]
        if beneficiary_name:
            for row in beneficiaries:
                if row.get("name", "").lower() == beneficiary_name and row.get("verified"):
                    beneficiary_id = row.get("beneficiary_id")
                    break
        return IntentSlots(
            intent="send_money" if "pay" in lower else "unknown",
            amount=amount,
            beneficiary_name=beneficiary_name,
            beneficiary_id=beneficiary_id,
            payment_method_id=default_method_id,
        )
