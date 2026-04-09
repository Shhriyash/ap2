# Prototype Plan: Payment + Balance Agent with Account Guardrails

## Goal
Ship a safe prototype where authenticated users can:
- Send AED payments to pre-registered beneficiaries.
- Ask for their own current balance.
- Never access another user's account data.

## Scope (Current)
- Intent support: `send_money`, `check_balance`.
- Slot filling for payment: recipient, amount, note.
- Confirmation before tool execution.
- PIN-first auth with OTP fallback.
- Local file logs for agent actions (no DB logging for agent events).
- Supabase/Postgres-compatible schema and seed script for dummy users.

## Guardrails
1. Balance isolation:
- Requestor can only query `requestor_user_id == target_user_id`.
- Agent blocks cross-user balance asks before tool call.
- Gateway enforces same rule server-side.

2. Payment constraints:
- Only verified beneficiaries can receive money.
- Currency fixed to AED.
- No execution before explicit user confirmation.
- Idempotency key used for transfer calls.

3. Data minimization:
- Agent responses include only needed outcome fields.
- No exposure of other users' balances or account metadata.

## Implemented Components
- Prompt file for LLM behavior and guardrails:
  - `agent_service/prompts/payment_agent_prompt.txt`
- Dummy DB bootstrap script:
  - `gateway_service/scripts/bootstrap_dummy_data.py`
- Payment + balance contracts:
  - `shared_lib/shared_lib/contracts/payment.py`
- Balance endpoint with ownership guardrail:
  - `GET /accounts/{target_user_id}/balance?requestor_user_id=<user_id>`
- Agent local logs:
  - `agent_service/logs/agent.log`

## Execution Flow (Payment)
1. User message parsed for payment intent and slots.
2. Missing slots requested one-by-one (amount, note).
3. Auth challenge completed (PIN then OTP fallback).
4. Agent confirms transfer details.
5. Custom tool calls gateway transfer endpoint.
6. Gateway updates sender/receiver balances and ledger.
7. Agent returns transaction result.

## Execution Flow (Balance)
1. User asks current balance.
2. Agent resolves target user from query; defaults to current user.
3. If target != current user, deny request.
4. If valid, call balance endpoint and return own balance.

## Next Steps
1. Replace in-memory retrieval with DB-backed lookups in agent service.
2. Add session auth token propagation instead of raw user_id params.
3. Add structured error taxonomy and user-safe messages.
4. Add tests for:
- cross-user balance denial
- slot-filling prompts
- payment confirmation gating
- idempotent transfer replay
