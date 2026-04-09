# Backend Architecture (Prototype)

## 1) Services

The backend is split into two FastAPI services:

1. Agent Service (`agent_service`)
- Handles CLI login, session control, intent flow, slot filling, auth challenge flow, and orchestration.
- Calls gateway through internal tool router.

2. Gateway Service (`gateway_service`)
- Owns user mapping, receiver verification, balance, payment execution, ledger writes, and transaction status.
- Enforces internal-service token on sensitive routes.

Shared contracts are in `shared_lib`.

---

## 2) Security Model (Current Prototype)

1. User login
- User logs in through CLI using Supabase email/password.
- Agent validates Supabase credentials and token using Supabase Auth API.

2. Session principal
- Agent issues a server-side session token and session id.
- Sender identity for all operations is derived from this session principal only.

3. Internal backend trust
- Agent includes `X-Internal-Service-Token` for gateway calls.
- Gateway validates this token on internal/sensitive endpoints.

4. Transfer integrity
- Receiver must be verified and explicitly confirmed.
- PIN/OTP challenge required.
- Auth context is registered in gateway and consumed once during transfer.

5. Privacy guardrail
- Balance endpoint only allows `requestor_user_id == target_user_id`.

---

## 3) Unified Environment

Single env file: `.env.agent`  
Contains:
- Agent settings
- Gateway settings
- Supabase auth settings
- Supabase Postgres DSN (`SUPABASE_DATABASE_URL`)
- Internal service token

`.env.gateway` is removed.

---

## 4) Main Endpoints

## Agent Service (`http://localhost:8000`)

1. `POST /auth/cli/login`
- Input: Supabase email/password.
- Output: `session_token`, `session_id`, internal user mapping.
- Purpose: mandatory login before chat.

2. `POST /agent/message`
- Auth: `Authorization: Bearer <session_token>`.
- Input: `session_id`, `message`, `channel`.
- Purpose: run conversation turn, collect slots, verify receiver, ask confirmations.

3. `POST /auth/challenge/start`
- Auth required.
- Input: `session_id`, `preferred_type`.
- Purpose: start PIN or OTP challenge.

4. `POST /auth/challenge/verify`
- Auth required.
- Input: `challenge_id`, `value`.
- Purpose: verify PIN/OTP and bind auth context in session.

5. `POST /agent/confirm`
- Auth required.
- Input: `session_id`, `confirmed`.
- Purpose: final execution confirm or abort.

6. `GET /agent/session/{session_id}`
- Auth required.
- Purpose: view current conversation/session state.

## Gateway Service (`http://localhost:8100`)

Sensitive routes require `X-Internal-Service-Token`.

1. `POST /users/provision`
- Ensure internal user row exists for Supabase user id.
- Creates default AED account on first provision.

2. `GET /users/by-supabase/{supabase_user_id}`
- Fetch mapped internal user identity.

3. `POST /receivers/verify`
- Resolve receiver hint for sender.
- Returns masked receiver identity and verification status.

4. `GET /accounts/{target_user_id}/balance?requestor_user_id=...`
- Returns own balance only.

5. `POST /internal/auth-context/register`
- Registers one-time auth context (`auth_context_id`, `user_id`, `session_id`).

6. `POST /payments/transfer`
- Validates idempotency and auth-context consume.
- Executes debit/credit + ledger updates.
- Returns transaction id and timestamp.

7. `POST /payments/validate`
- Pre-check path for transfer validation.

8. `GET /payments/{transaction_id}`
- Fetch transaction status.

9. `POST /payments/refund`
10. `POST /payments/reverse`
- Simulated lifecycle operations.

---

## 5) Data Flow

## A. Login and Session Establishment

1. CLI -> Agent `/auth/cli/login`
2. Agent -> Supabase Auth APIs (password grant + token user check)
3. Agent -> Gateway `/users/provision`
4. Agent stores in-memory session principal and returns session token/id

## B. Payment Flow

1. CLI -> Agent `/agent/message` (with session token)
2. Agent extracts intent/slots
3. Agent -> Gateway `/receivers/verify`
4. Agent asks receiver confirmation
5. Agent collects amount/note
6. Agent handles PIN/OTP
7. Agent -> Gateway `/internal/auth-context/register`
8. CLI -> Agent `/agent/confirm`
9. Agent -> Gateway `/payments/transfer`
10. Gateway writes transactions + ledger and returns receipt data
11. Agent returns final response

## C. Balance Flow

1. CLI -> Agent `/agent/message`
2. Agent enforces own-balance policy
3. Agent -> Gateway `/accounts/{id}/balance` with `requestor_user_id`
4. Gateway enforces ownership and returns balance

---

## 6) Transaction and Replay Rules

1. Transaction ID:
- Generated server-side in gateway repository.
- Uses UUIDv7 when available, UUIDv4 fallback.

2. Idempotency:
- `idempotency_key` unique in transactions.
- Replay returns original transaction response.
- Replay does not consume auth context again.

---

## 7) Logging and Traceability

1. Agent:
- Local file logs at `agent_service/logs/agent.log`
- Includes correlation id.

2. Gateway:
- Local file logs at `gateway_service/logs/gateway.log`
- Includes correlation id.

3. Correlation propagation:
- Agent middleware sets or accepts `X-Correlation-ID`.
- Agent forwards correlation id to gateway.
- Gateway logs with same id for cross-service tracing.

---

## 8) Stack

- Python 3.11+
- FastAPI + Uvicorn
- Pydantic v2 + pydantic-settings
- pydantic-ai (OpenRouter model path optional)
- SQLAlchemy 2.x
- Psycopg (PostgreSQL driver)
- Supabase Auth (email/password)
- Supabase Postgres (via DSN)
- Local file logging for audit/debug
