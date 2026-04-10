# AI Agent Payments Prototype Scaffold

This repo is a split-service prototype for an AI payment assistant:

- `agent_service`: conversation orchestration, slot extraction, receiver verification flow, and payment execution control.
- `gateway_service`: payment/balance backend (dummy processor for prototype).
- `shared_lib`: shared Pydantic contracts and common utilities used by both services.

## Documentation

- [Agent architecture and flow details](./AGENT.md)
- [Backend architecture, endpoint and data flow](./BACKEND.md)
- [Brutal security analysis and risky query catalog](./BRUTAL_SECURITY_ANALYSIS.md)
- [Auth hardening phased plan and progress](./PROTOTYPE_AUTH_HARDENING_PLAN.md)

## Technology Stack

- Language: `Python 3.11+`
- API framework: `FastAPI`
- ASGI server: `Uvicorn`
- Config: `pydantic-settings` with unified `.env.agent` (agent + gateway sections)
- Data contracts and validation: `Pydantic v2`
- Agent runtime: `pydantic-ai-slim[openrouter,groq]` (Groq primary, OpenRouter fallback)
- HTTP client: `httpx`
- Database ORM: `SQLAlchemy 2.x`
- PostgreSQL driver: `psycopg[binary]`
- Database: `PostgreSQL` (local, Supabase, or managed Postgres)
- Packaging for shared code: local editable package `shared_lib` (`-e ../shared_lib`)
- Local dev automation: PowerShell scripts in `scripts/`

## Runtime Modes

- Agent parsing mode:
  - with `GROQ_API_KEY`: Groq LLM-assisted parsing/tool orchestration
  - with both `GROQ_API_KEY` and `OPENROUTER_API_KEY`: OpenRouter fallback on Groq rate-limit errors
  - without either key: deterministic fallback slot extraction

## Codebase Structure

```text
ap2/
|-- README.md
|-- AGENT.md
|-- .env.agent.example
|-- scripts/
|   |-- bootstrap.ps1
|   |-- run_agent.ps1
|   `-- run_gateway.ps1
|-- agent_service/
|   |-- requirements.txt
|   |-- prompts/payment_agent_prompt.txt
|   `-- app/
|       |-- main.py
|       |-- api/routes/
|       |   |-- agent.py
|       |   `-- health.py
|       |-- domain/orchestrator.py
|       |-- services/
|       |   |-- pydantic_payment_agent.py
|       |   |-- retrieval.py
|       |   `-- tool_router.py
|       `-- core/
|           |-- config.py
|           `-- agent_logger.py
|-- gateway_service/
|   |-- requirements.txt
|   |-- migrations/sql/001_init.sql
|   |-- scripts/bootstrap_dummy_data.py
|   `-- app/
|       |-- main.py
|       |-- api/routes/
|       |   |-- payments.py
|       |   `-- health.py
|       |-- db/
|       |   |-- models.py
|       |   |-- repository.py
|       |   `-- session.py
|       |-- providers/
|       |   |-- base.py
|       |   `-- dummy.py
|       `-- services/payment_service.py
`-- shared_lib/
    |-- pyproject.toml
    `-- shared_lib/
        |-- contracts/
        |   |-- agent.py
        |   `-- payment.py
        `-- core/
            |-- errors.py
            `-- idempotency.py
```

## New User Installation

All commands below assume you are running from the repo root.

### 1) Prerequisites

- `Git`
- `Python 3.11+` available as `python`
- `PowerShell` (`pwsh` or Windows PowerShell)
- A reachable PostgreSQL database

### 2) Clone

```powershell
git clone <your-repository-url>
cd ap2
```

### 3) Create env files

```powershell
Copy-Item .env.agent.example .env.agent
```

Required edits:

- In `.env.agent`, set `SUPABASE_DATABASE_URL` to your Supabase Postgres DSN.
- Keep one `INTERNAL_SERVICE_TOKEN` value in `.env.agent` (used by both services).

Optional edits:

- In `.env.agent`, set `GROQ_API_KEY` (recommended primary) and optionally `OPENROUTER_API_KEY` for fallback.
- For voice mode, set `GROQ_API_KEY2` (or reuse `GROQ_API_KEY`) and `DEEPGRAM_API_KEY`.

### 4) Install all dependencies

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

This creates:

- `.venv-agent`
- `.venv-gateway`

### 5) Seed initial dummy data

```powershell
.\.venv-gateway\Scripts\python.exe .\gateway_service\scripts\bootstrap_dummy_data.py --reset
```

This seeds users, accounts, and verified beneficiaries for local transfer tests.

Standalone Supabase initializer (schema + seed, from any working directory):

```powershell
.\.venv-gateway\Scripts\python.exe .\gateway_service\scripts\init_supabase_dummy_db.py --reset
```

Optional: set every active user AED balance to 5000 after seeding:

```powershell
.\.venv-gateway\Scripts\python.exe .\gateway_service\scripts\init_supabase_dummy_db.py --reset --set-all-balance --balance-amount 5000
```

### 6) Start services

Terminal 1:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_gateway.ps1
```

Terminal 2:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_agent.ps1
```

Or start both with one command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_stack.ps1
```

`run_stack.ps1` now performs a pre-clean automatically (stale PID file + listeners on agent/gateway ports) to avoid Windows bind errors like `WinError 10048`.

Stop both service windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_stack.ps1
```

### 7) Authenticate in CLI (required before chat)

```powershell
python .\scripts\cli_login.py --agent-url http://localhost:8000
```

This writes `.agent_session.json` with:
- `session_token`
- `session_id`
- authenticated internal user mapping

### 8) Voice CLI (STT -> Agent -> TTS)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_voice_cli.ps1
```

Direct command:

```powershell
.\.venv-agent\Scripts\python.exe .\scripts\cli_voice.py --agent-url http://localhost:8000
```

Voice mode constraints:
- Voice starts only after typed email+password login succeeds.
- PIN is always entered manually via secure typed prompt during transaction verification.
- Voice resumes automatically after PIN verification.
- Voice pipeline uses Groq Whisper STT, Deepgram TTS primary, and Groq TTS fallback.

### 9) Verify health

```powershell
Invoke-RestMethod http://localhost:8100/health
Invoke-RestMethod http://localhost:8000/health
```

Expected response contains `status: ok` for both services.

## API Surface

- Agent (`http://localhost:8000`)
  - `POST /auth/cli/login`
  - `POST /agent/message`
  - `POST /agent/confirm`
  - `GET /agent/session/{session_id}`
  - `POST /auth/challenge/start`
  - `POST /auth/challenge/verify`
- Gateway (`http://localhost:8100`)
  - `GET /users/by-supabase/{supabase_user_id}`
  - `POST /users/provision`
  - `POST /payments/validate`
  - `POST /receivers/verify`
  - `POST /payments/transfer`
  - `POST /payments/refund`
  - `POST /payments/reverse`
  - `GET /payments/{transaction_id}`
  - `GET /accounts/{target_user_id}/balance?requestor_user_id=<user_id>`

## Notes

- Currency is fixed to `AED`.
- New signups/provisioned users get default `500.00 AED` opening balance.
- Receiver is verified by email against active users, then sender confirms before transfer.
- Receiver confirmation is required before payment execution.
- Agent logs are written to `agent_service/logs/agent.log`.
- Protected agent endpoints require `Authorization: Bearer <session_token>` from CLI login.
- Gateway service routes are backend-internal and require `X-Internal-Service-Token`.
