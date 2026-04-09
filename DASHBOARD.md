# Payment Agent Assistant Onboarding Dashboard Plan

## 1. Objective
- Build a separate onboarding dashboard where users can:
  - Register general details.
  - Set up a secure PIN.
  - Register and verify OTP device/channel.
- Dashboard scope is **sign-up only** (no sign-in/login screen in dashboard).
- User authentication before interacting with agent happens on **CLI**, not in dashboard.
- CLI authentication uses Supabase default email auth and checks user existence in Supabase-backed user records.
- Keep onboarding implementation isolated from existing `agent_service` orchestration.
- Ensure frontend is fully wired to backend endpoints with clear request/response contracts.

## 2. Separation Strategy (Critical)
- Do not modify `agent_service` flow for MVP onboarding.
- Add onboarding only under gateway + a new standalone frontend app.
- Keep auth responsibility split:
  - Dashboard: registration/sign-up only.
  - CLI: authentication gate before agent usage.
  - Backend: Supabase auth integration + user existence check.
- Proposed new areas:
  - `gateway_service/app/api/routes/onboarding.py`
  - `gateway_service/app/api/routes/cli_auth.py` (or equivalent auth route if backend agent adds it)
  - `gateway_service/app/services/onboarding_service.py`
  - `gateway_service/app/services/supabase_auth_service.py`
  - `gateway_service/app/db/models_onboarding.py` (or extend existing models module cleanly)
  - `gateway_service/migrations/sql/002_onboarding_auth.sql`
  - `shared_lib/shared_lib/contracts/onboarding.py`
  - `onboarding_dashboard/` (new React frontend project)

## 3. Backend API Design (Endpoints frontend will call)
| Step | Endpoint | Method | Purpose |
|---|---|---|---|
| 1 | `/onboarding/signup` | `POST` | Register user, create/link Supabase auth user by email, return onboarding context |
| 2 | `/onboarding/users/{user_id}/pin` | `POST` | Set/replace PIN (hashed server-side) |
| 3 | `/onboarding/users/{user_id}/otp-device/start` | `POST` | Register device/channel and issue OTP challenge |
| 4 | `/onboarding/users/{user_id}/otp-device/verify` | `POST` | Verify OTP and mark device as verified |
| 5 | `/onboarding/users/{user_id}/status` | `GET` | Fetch onboarding + email verification status for completion UI |

### CLI Authentication Endpoints (not called by dashboard)
- Backend auth layer should expose or support a CLI flow that:
  - Verifies Supabase email authentication.
  - Validates mapped user exists and is active.
  - Blocks agent access if not authenticated/verified.
- Dashboard only needs to display post-signup guidance: "Authenticate on CLI using the same registered email."

## 4. Data Model Plan
- `users` (reuse existing table, extend for Supabase mapping):
  - `id` (internal app user id)
  - `email` (normalized, unique)
  - `supabase_user_id` (UUID/string, unique)
  - `email_verified` (boolean)
  - `registration_source` (default `dashboard`)
  - timestamps (`created_at`, `updated_at`)
- `user_security`
  - `user_id` (FK)
  - `pin_hash`
  - `pin_updated_at`
  - `failed_pin_attempts`
  - `lock_until`
- `user_otp_devices`
  - `id`
  - `user_id`
  - `channel` (`sms`/`email`)
  - `destination_masked`
  - `destination_encrypted` (or tokenized)
  - `is_verified`
  - `is_primary`
  - `created_at`
- `otp_challenges`
  - `id`
  - `user_id`
  - `device_id`
  - `otp_hash`
  - `expires_at`
  - `attempts`
  - `status`

## 5. Frontend UX Plan (Interactive Dashboard)
- Build a 4-step wizard:
  - Step 1: General details (includes email used for Supabase auth).
  - Step 2: PIN setup with strength/rule hints.
  - Step 3: OTP device registration and OTP verification.
  - Step 4: Completion (show signup success + CLI authentication instructions).
- UX requirements:
  - Real-time validation.
  - Inline error states and retry actions.
  - Progress indicator with completed/active steps.
  - Disabled-next until each step is valid.
  - Success screen with `user_id`, `email`, `email_verification_status`, and "next step in CLI".
  - No login/sign-in UI in dashboard (explicitly out of scope).

## 6. Frontend-Backend Integration Rules
- Use typed API client layer (`axios`/`fetch` wrapper + TS interfaces).
- Handle all API errors with structured messages (`4xx` validation, `409` conflict, `429` throttling).
- Persist wizard state in memory + optional `sessionStorage`.
- Add loading states for each submit action.
- Add CORS config in gateway for dashboard origin.
- Expect signup payload/response contract to include:
  - request: `email`, `full_name`, optional profile fields.
  - response: `user_id`, `supabase_user_id`, `email_verification_required`, `onboarding_session_token`.
- Frontend should be resilient to async email verification:
  - Read `/onboarding/users/{user_id}/status` for current verification state.
  - Show clear pending state if email verification is incomplete.
- Do not store or handle Supabase service credentials in frontend.

## 7. Security & Compliance Baseline
- Hash PIN using Argon2/Bcrypt (never store raw PIN).
- OTP must be one-time, short TTL, attempt-limited.
- Mask destination in API responses.
- Add rate limiting on OTP start/verify and PIN attempts.
- Normalize email and enforce unique registration on normalized email.
- Backend-only Supabase service role usage (never exposed to frontend).
- Require verified email before marking user as fully onboarded for agent access.
- Bind OTP challenge to `user_id + device_id + challenge_id` to prevent replay across users/devices.
- Invalidate previous active OTP challenge when a new OTP is issued for the same device.
- Prevent account enumeration with generic error messages (for unknown phone/email/user).
- Validate and normalize input server-side (phone in E.164, email lowercase/trimmed).
- Encrypt sensitive PII at rest (OTP destination raw value) and keep masked values for display.
- Keep secrets out of code (`PIN_PEPPER`, OTP signing key, encryption key via env/secret manager).
- Add minimal retention policy for OTP artifacts (e.g., delete/expire challenge records quickly).
- Add correlation IDs and security event trails for every onboarding API call.
- Audit log events:
  - user_registered
  - pin_set
  - otp_device_started
  - otp_device_verified
  - otp_verify_failed
  - user_locked
  - otp_challenge_expired

## 8. Implementation Phases
1. **Phase A: Contracts + Schema**
   - Add `onboarding` pydantic contracts in shared lib.
   - Add migration `002_onboarding_auth.sql`.
   - Add DB model mappings and repository methods.
   - Add `supabase_user_id` and `email_verified` support in user model.
2. **Phase B: Backend APIs**
   - Implement onboarding routes + service layer.
   - Add validation, hashing, OTP challenge generation/verification.
   - Integrate Supabase email auth user creation/linking in signup endpoint.
   - Implement/align CLI auth gate that checks Supabase-authenticated user existence before agent interaction.
   - Add unit tests for service logic and route tests for all endpoint paths.
3. **Phase C: Dashboard Frontend**
   - Scaffold `onboarding_dashboard` (React + TS).
   - Build sign-up-only 4-step wizard UI and API integration.
   - Add form validation and error UX.
   - Add completion state for CLI auth handoff and email verification pending.
4. **Phase D: Hardening**
   - Add CORS, request logging, rate limits, retry-safe behavior.
   - Add end-to-end tests for full registration flow.
5. **Phase E: Optional Agent Integration (post-MVP)**
   - Replace static PIN/OTP in `agent_service` with gateway-backed verification endpoints.
   - Keep this behind a feature flag to avoid breaking current flows.
6. **Phase F: Prototype Operability**
   - Add metrics + lightweight dashboards for onboarding funnel and error rates.
   - Add support/admin endpoints for safe retries and unlock flows.
   - Add synthetic smoke script for CI/local (`register -> pin -> otp start -> verify`).

## 9. Testing Plan
- Backend:
  - Unit tests for PIN/OTP logic.
  - Supabase integration tests (mocked client + one integration smoke against test project if available).
  - API contract tests for request/response and failure paths.
- Frontend:
  - Component tests for each sign-up step and completion guidance state.
  - E2E test for complete onboarding happy path + OTP failure/retry + email verification pending state.
- Integration:
  - Full flow test: signup -> set PIN -> start OTP -> verify OTP -> status fetch -> CLI auth success precondition check.

## 10. Definition of Done
- User can complete onboarding from UI without manual DB changes.
- All sign-up endpoints are live and called by frontend.
- PIN stored hashed, OTP verified with expiry/attempt controls.
- Dashboard exposes sign-up only; no login page/path in UI.
- Backend enforces CLI authentication precondition (Supabase email auth + user existence check) before agent interaction.
- Tests pass for backend API + frontend wizard + E2E flow.
- P0 security controls and P0 operability controls (below) are implemented.

## 11. Missing Registration Security Features (Prototype View)
### P0 (must-have now)
- Add brute-force controls:
  - Per-user and per-IP throttling for signup, PIN set, OTP start, OTP verify.
  - Temporary lockouts after repeated PIN/OTP failures.
- Add anti-replay controls:
  - OTP challenge can be verified only once.
  - Expired or consumed challenge returns deterministic failure.
- Add step integrity:
  - Issue short-lived onboarding session token after registration.
  - Require this token for PIN and OTP setup endpoints.
- Add identity integrity:
  - Ensure one active app user record per normalized email.
  - Ensure `users.supabase_user_id` mapping is unique and immutable after link.
- Add response hardening:
  - No sensitive details in error messages.
  - No raw PIN/OTP/PII in logs.
- Add secure defaults:
  - Security headers (`X-Content-Type-Options`, `X-Frame-Options`, strict `Referrer-Policy`).
  - Strict CORS allowlist for dashboard origin.

### P1 (next prototype increment)
- Add CAPTCHA/human-check on repeated OTP start attempts.
- Add device binding metadata (device name, platform, last seen, risk score placeholder).
- Add account recovery baseline for lost OTP device (manual reset with audit trail).
- Add PIN rotation policy and block previously used recent PIN hashes.
- Add privacy controls:
  - Configurable retention windows for onboarding PII and security logs.
  - Soft-delete and cleanup jobs.

## 12. Additional Features To Enhance Operability (Prototype View)
### P0 (must-have now)
- Structured logging:
  - JSON logs with `request_id`, `user_id`, `endpoint`, `latency_ms`, `result`.
- Metrics:
  - `onboarding_start_total`
  - `onboarding_completed_total`
  - `otp_start_total`
  - `otp_verify_success_total`
  - `otp_verify_failure_total`
  - `pin_set_failure_total`
- Operational visibility:
  - Basic `/health` + `/ready` checks include DB connectivity.
  - Simple funnel report endpoint for daily conversion and drop-off.
- Idempotency:
  - Idempotency key support on registration and OTP start endpoints.
  - Safe retry semantics in frontend API client.

### P1 (next prototype increment)
- Admin/support tooling:
  - Search onboarding status by `user_id`.
  - Trigger OTP resend with cooldown guard.
  - Unlock user after manual verification.
- Notification abstraction:
  - OTP provider adapter with dummy and real implementations.
  - Dead-letter capture for failed OTP sends.
- Release safety:
  - Feature flags for OTP channels and strictness knobs.
  - Canary mode toggle for new verification logic.
