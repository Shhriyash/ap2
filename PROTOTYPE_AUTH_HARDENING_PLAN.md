# Prototype Auth + Transaction Hardening Plan

## 1) Confirmed Direction

This plan adopts your decisions:

1. User registers with Supabase auth (email-based).
2. User must authenticate in CLI before any agent interaction.
3. On successful login, user existence is validated against app DB records.
4. Session stores authenticated user identity and injects it into tool calls.
5. Sender identity must come from authenticated session context, not from free-form LLM output.
6. Every payment creates a transaction ID tied to sender/receiver and full metadata.

---

## 2) Target Prototype Flow

1. CLI starts and asks user to login.
2. CLI performs Supabase email auth.
3. CLI receives Supabase access token and user id (`supabase_user_id`).
4. Agent service verifies token and maps `supabase_user_id` to internal app user record.
5. Agent session is created with server-owned principal:
   - `session_id`
   - `internal_user_id`
   - `supabase_user_id`
   - `auth_time`
6. User chats with agent.
7. Orchestrator always uses session principal as sender in tool payload.
8. Receiver is verified.
9. PIN/OTP challenge is completed.
10. Payment executes and transaction is written with unique transaction ID.

---

## 3) Identity and Authorization Model (Prototype-Safe)

## Identity source of truth
- Supabase auth user id (`supabase_user_id`) is the external identity.
- Internal `users` table has a row linked to `supabase_user_id`.

## Mandatory checks
- Reject chat requests without valid session token.
- Reject if `supabase_user_id` has no mapped internal user row.
- Never accept sender id from client payload when executing payment.
- Derive sender id from server session only.

## Session contract
- Session state stores principal once at login.
- Payment and balance tools read sender from session context automatically.
- User cannot override this through prompt text.

---

## 4) Transaction ID Strategy

Use two identifiers:

1. `transaction_id` (business id, shown to user)
- Example: `txn_20260410_01JABC...` (ULID/UUIDv7 preferred).
- Unique per payment attempt.

2. `idempotency_key` (request replay protection)
- Unique key per client execution intent.
- If same key is replayed, return original result.

Store both in `transactions` table with:
- `payer_user_id`
- `beneficiary_id`
- `amount`, `currency`
- `status`, `failure_code`, `failure_reason`
- `created_at`, `updated_at`

---

## 5) What Is Still Important for Prototype (After Auth + Txn IDs)

Priority P0 (must-have before broader testing):

1. Token validation at agent boundary
- Verify Supabase JWT signature/expiry.
- Reject expired or invalid token.

2. Session-bound sender enforcement
- Remove sender fields from public API payloads where possible.
- Build sender in backend from session principal.

3. Auth challenge integrity
- `auth_context_id` must be one-time, short-lived, and session-bound.
- Gateway must verify it, not only agent.

4. API misuse controls
- Rate limit on login, auth verify, transfer endpoints.
- Basic lockout/cooldown after repeated failed PIN/OTP attempts.

5. Consistent audit trail
- Keep agent logs local (as required).
- Ensure gateway transaction logs include request correlation id.

Priority P1 (strongly recommended in prototype):

6. Persistent session store
- Move session state from in-memory to Redis/Postgres table.

7. Signed service-to-service calls
- Agent->Gateway include signed internal token or mTLS.

8. Input normalization and strict validation
- Normalize names/identifiers.
- Strict allowlist for tool payload fields.

9. Security test corpus
- Include prompt-injection and policy-bypass test messages.

Priority P2 (next prototype iteration):

10. Basic fraud heuristics
- Velocity checks, unusual amount check, repeated failure behavior.

11. Observability
- Metrics for transfer success/failure, auth failure rate, latency.

12. Recovery behavior
- Retry policy for transient gateway errors.
- Idempotent safe retries only.

---

## 6) Minimal Schema Additions

1. `users`
- Add `supabase_user_id` (unique, indexed).

2. `agent_sessions` (or equivalent)
- `session_id`, `internal_user_id`, `supabase_user_id`, `created_at`, `expires_at`, `status`.

3. `auth_challenges`
- `challenge_id`, `session_id`, `user_id`, `type`, `status`, `attempt_count`, `expires_at`, `used_at`.

4. `transactions`
- Ensure unique `transaction_id` and unique `idempotency_key`.

---

## 7) Implementation Phases

## Phase 1: CLI Auth + Session Principal
1. Add CLI login command using Supabase email auth.
2. Add agent login endpoint to validate Supabase token and create session.
3. Return session token/id for subsequent chat calls.

## Phase 2: Sender Binding + Execution Integrity
1. Remove client-supplied sender from payment execution path.
2. Inject sender from session in orchestrator.
3. Enforce one-time `auth_context_id` validation in gateway.

## Phase 3: Transaction and Replay Safety
1. Generate `transaction_id` with ULID/UUIDv7.
2. Enforce idempotency key uniqueness and replay response behavior.
3. Add correlation id across agent and gateway logs.

## Phase 4: Prototype Security Baseline
1. Add rate limiting and lockout controls.
2. Add persistent session store.
3. Add adversarial query regression tests.

---

## 8) Done Criteria for This Prototype Milestone

- User cannot call payment/balance endpoints without valid authenticated session.
- Sender identity cannot be overridden via prompt or API payload.
- Every transfer has stable transaction id and idempotency behavior.
- Receiver verification, user confirmation, and PIN/OTP gates are enforced.
- Abort/cancel works and guarantees no transfer side effect.

---

## 9) Phase Progress Log

## Phase 1 Status: Completed (2026-04-10)

Implemented:
1. CLI login workflow:
- Added `scripts/cli_login.py` for email/password login to agent backend.

2. Agent login endpoint and session token issuance:
- Added `POST /auth/cli/login` in agent service.
- Creates server-owned session principal (`session_token`, `session_id`, `internal_user_id`).

3. Session-bound authenticated agent routes:
- `POST /agent/message`
- `POST /auth/challenge/start`
- `POST /auth/challenge/verify`
- `POST /agent/confirm`
- `GET /agent/session/{session_id}`
- All now require `Authorization: Bearer <session_token>`.

4. Internal user mapping and provisioning in gateway:
- Added `GET /users/by-supabase/{supabase_user_id}`.
- Added `POST /users/provision` (idempotent).
- User provisioning also creates default AED account.

5. Schema and seed updates:
- Added `supabase_user_id` mapping field to users model and seed script behavior.

Phase 1 open caveat:
- Supabase token validation currently uses Supabase user endpoint validation call.
- Full local JWT signature verification and session persistence are planned in later phases.

## Phase 2 Status: Completed (2026-04-10)

Implemented:
1. Sender-binding in execution path:
- Agent transfer path no longer accepts sender identity from public chat payload.
- Sender identity is taken from authenticated session principal and injected server-side.

2. Payment payload session binding:
- `session_id` is now included in transfer payload contract and sent to gateway.

3. Gateway auth-context integrity enforcement:
- Added internal endpoint `POST /internal/auth-context/register`.
- Agent registers verified auth context before execution.
- Gateway requires valid one-time, non-expired auth context on transfer (`consume` semantics).

4. Internal service trust token:
- Added `INTERNAL_SERVICE_TOKEN` config to both agent and gateway.
- Gateway sensitive routes (`payments`, `users`, `auth-context`) require `X-Internal-Service-Token`.
- Agent sends this token on all gateway calls.

5. Minimal contract hardening:
- Removed `user_id` from public agent message/auth challenge request contracts.
- Prevents caller-driven sender override in API payload.

Phase 2 open caveat:
- Auth-context store is in-memory in gateway and not yet durable/shared across instances.
- Internal token is static shared secret (acceptable for prototype, not final).

## Phase 3 Status: Completed (2026-04-10)

Implemented:
1. Transaction ID generation upgraded:
- Transaction IDs now use UUIDv7 when available with fallback to UUIDv4.
- IDs are generated server-side in gateway repository (`txn_<uuid>`).

2. Idempotency replay behavior hardened:
- Gateway transfer path first checks idempotency key.
- Replay now returns the original transaction result directly without consuming auth context again.
- Prevents accidental second-factor consumption on replays.

3. Correlation ID propagation and logging:
- Agent middleware sets/propagates `X-Correlation-ID`.
- Agent forwards the same correlation ID to gateway on internal calls.
- Gateway middleware propagates and logs same correlation ID.
- Agent and gateway now log request-level events with shared correlation IDs.

4. Config simplification:
- Removed unused `OPENROUTER_BASE_URL`.
- Removed external payment mode and related env keys.
- Unified environment remains in `.env.agent`; `.env.gateway` removed.

Phase 3 open caveat:
- Gateway transaction replay currently maps non-transfer statuses to failed replay response for transfer endpoint.
- Correlation IDs are file-log based; no centralized tracing backend yet.
