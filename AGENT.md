# Agent Architecture (Receiver Verification + Abortable Payments)

## 1) Recommended Design

Use a **single orchestrator agent** with **two custom tools**:

1. `verify_receiver`
2. `execute_payment`

Reason:
- Lower orchestration complexity than two-agent handoff.
- Easier to enforce hard guardrails in one state machine.
- Clear migration path to real payment APIs by swapping backend adapter only.

Two-agent setup can be added later if you want strict role separation (`verification-agent` + `execution-agent`), but it is not required for this prototype.

---

## 2) Core Principle

**No payment execution is allowed until receiver verification is complete and explicitly confirmed by sender.**

Execution order must always be:
1. Extract intent and slots.
2. Resolve and fetch receiver details from backend.
3. Show receiver details to sender and ask for confirmation.
4. Collect missing payment fields (amount/note if missing).
5. Final transaction confirmation.
6. Execute payment tool call.

---

## 3) Tool Contracts

## Tool A: `verify_receiver`

Purpose:
- Resolve receiver input (name/identifier) into beneficiary record.
- Fetch canonical receiver details from backend.

Input:
- `sender_user_id`
- `receiver_hint` (name/handle/identifier)

Output:
- `found` (bool)
- `beneficiary_id`
- `display_name`
- `masked_identifier`
- `verification_status`
- `risk_flags` (optional)

Behavior:
- If not found or not verified, agent must refuse payment execution.
- If multiple matches, ask sender to select one.

## Tool B: `execute_payment`

Purpose:
- Perform transfer through gateway endpoint after all checks pass.

Input:
- `sender_user_id`
- `beneficiary_id`
- `amount`
- `currency` (`AED`)
- `purpose_note`
- `auth_context_id`
- `idempotency_key`

Output:
- `transaction_id`
- `status`
- `timestamp`
- `failure_code` / `failure_reason` if failed

---

## 4) Conversation State Machine

States:
1. `IDLE`
2. `INTENT_PARSED`
3. `RECEIVER_VERIFIED`
4. `AWAITING_RECEIVER_CONFIRMATION`
5. `AWAITING_MISSING_FIELDS` (amount/note)
6. `AWAITING_AUTH` (PIN then OTP fallback)
7. `AWAITING_FINAL_CONFIRMATION`
8. `EXECUTING`
9. `COMPLETED`
10. `ABORTED`

Transitions:
- User says “send money to shriyash”:
  - `IDLE -> INTENT_PARSED -> RECEIVER_VERIFIED -> AWAITING_RECEIVER_CONFIRMATION`
- User confirms receiver:
  - move to `AWAITING_MISSING_FIELDS` if amount/note missing; else `AWAITING_AUTH`
- Auth success:
  - `AWAITING_AUTH -> AWAITING_FINAL_CONFIRMATION`
- User confirms final summary:
  - `AWAITING_FINAL_CONFIRMATION -> EXECUTING -> COMPLETED`
- User says “cancel”, “abort”, “stop payment” at any pre-execution state:
  - `* -> ABORTED`

---

## 5) Abort Handling

Rules:
- Abort command is valid at any point before `EXECUTING`.
- On abort:
  - clear pending payment state in session
  - do not call `execute_payment`
  - return `"Transaction aborted. No money was sent."`
  - write local agent log event `transaction_aborted`

If user aborts after receiver verification but before final confirmation, no side effects should exist except local logs.

---

## 6) Guardrails

1. Receiver confirmation guardrail:
- Must show verified receiver details before moving forward.
- Must obtain explicit user “yes” for intended receiver.

2. Final confirmation guardrail:
- Must show summary: receiver, amount AED, note.
- Must receive explicit proceed confirmation.

3. Balance privacy guardrail:
- User can only query own balance.
- Cross-account requests are denied at agent and backend.

4. Execution guardrail:
- Tool invocation is blocked unless:
  - receiver confirmed
  - amount valid
  - auth verified
  - final confirmation received

5. Idempotency guardrail:
- All execute calls require `idempotency_key`.

---

## 7) Example Flow

User: "Send money to shriyash."

Agent:
1. calls `verify_receiver(sender_user_id, "shriyash")`
2. returns details: `Shriyash`, `user_shriyash@wallet` (masked)
3. asks: "I found receiver Shriyash (user_sh****@wallet). Is this the intended receiver?"

User: "Yes."

Agent:
4. asks amount: "How much AED should I send?"

User: "2000 AED"

Agent:
5. asks optional note: "Any note to add?"

User: "Project reimbursement."

Agent:
6. auth flow (PIN -> OTP fallback if needed)
7. final summary + confirm
8. on yes, calls `execute_payment(...)`
9. returns transaction result with timestamp

Abort case:
- If user says "cancel" before step 8, agent moves to `ABORTED` and does not execute.

---

## 8) Implementation Mapping (Current Repo)

- Orchestration: `agent_service/app/domain/orchestrator.py`
- Pydantic AI extraction/execution service: `agent_service/app/services/pydantic_payment_agent.py`
- Gateway tool router: `agent_service/app/services/tool_router.py`
- Prompt policy: `agent_service/prompts/payment_agent_prompt.txt`
- Local logs: `agent_service/app/core/agent_logger.py` -> `agent_service/logs/agent.log`

To align with this architecture, add a dedicated `verify_receiver` endpoint in gateway and call it before payment readiness in orchestrator.
