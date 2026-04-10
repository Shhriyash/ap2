# RUNBOOK: New User Setup (GitHub -> Running Stack)

## 0) Scope and Exemptions
This runbook is for first-time setup on a new machine.

Exemptions for this runbook:
- Do **not** create a new Supabase project.
- Do **not** generate new API keys.
- Use team-provided values and paste them when instructed.

## 1) Prerequisites
Install these before starting:
- Git
- Python 3.11+
- Windows PowerShell
- Access to a reachable Postgres/Supabase database URL

Check versions:

```powershell
git --version
python --version
```

## 2) Clone from GitHub
Run in PowerShell:

```powershell
git clone <YOUR_GITHUB_REPO_URL>
cd ap2
```

## 3) Create Environment File
Create `.env.agent` from template:

```powershell
Copy-Item .env.agent.example .env.agent
```

Open `.env.agent` and fill values **now**.

Required entries to paste now:

| Key | What to enter | Source |
|---|---|---|
| `SUPABASE_URL` | Existing project URL | Team-provided |
| `SUPABASE_ANON_KEY` | Existing anon key | Team-provided |
| `INTERNAL_SERVICE_TOKEN` | Shared internal token string | Team-provided |
| `SUPABASE_DATABASE_URL` | Existing DB DSN | Team-provided |

Recommended entries to paste now:

| Key | What to enter | Source |
|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | Existing service role key | Team-provided |
| `GROQ_API_KEY` | Existing Groq key | Team-provided |
| `OPENROUTER_API_KEY` | Existing OpenRouter key | Team-provided |
| `GROQ_API_KEY2` | Groq key for FastRTC STT/TTS helpers | Team-provided |
| `DEEPGRAM_API_KEY` | Deepgram key for primary TTS | Team-provided |

Keep defaults unless your team says otherwise:
- `AGENT_HOST=0.0.0.0`
- `AGENT_PORT=8000`
- `GATEWAY_HOST=0.0.0.0`
- `GATEWAY_PORT=8100`

## 4) Install Dependencies (requirements.txt)
### Option A (recommended): one command bootstrap

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

This creates:
- `.venv-agent`
- `.venv-gateway`

### Option B (manual install by requirements file)

```powershell
python -m venv .venv-agent
python -m venv .venv-gateway

Push-Location .\agent_service
..\.venv-agent\Scripts\pip.exe install --upgrade pip
..\.venv-agent\Scripts\pip.exe install -r .\requirements.txt
Pop-Location

Push-Location .\gateway_service
..\.venv-gateway\Scripts\pip.exe install --upgrade pip
..\.venv-gateway\Scripts\pip.exe install -r .\requirements.txt
Pop-Location
```

What gets installed:
- `agent_service/requirements.txt` includes FastAPI, Uvicorn, pydantic-settings, httpx, `pydantic-ai-slim[openrouter,groq]`, and editable `shared_lib`.
- `gateway_service/requirements.txt` includes FastAPI, Uvicorn, pydantic-settings, SQLAlchemy, psycopg, httpx, and editable `shared_lib`.

## 5) Initialize Prototype DB (Supabase)
Run once after dependency setup:

```powershell
.\.venv-gateway\Scripts\python.exe .\gateway_service\scripts\init_supabase_dummy_db.py --reset
```

Optional: set all users to `5000 AED` after initialization:

```powershell
.\.venv-gateway\Scripts\python.exe .\gateway_service\scripts\init_supabase_dummy_db.py --reset --set-all-balance --balance-amount 5000
```

Notes:
- New users created via signup/provisioning get default `500.00 AED`.
- Existing helper script still works:

```powershell
.\.venv-gateway\Scripts\python.exe .\gateway_service\scripts\set_all_balances.py --amount 5000
```

## 6) Start Services
### Option A (recommended): start both services together

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_stack.ps1
```

### Option B: start in two terminals
Terminal 1:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_gateway.ps1
```

Terminal 2:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_agent.ps1
```

## 7) Verify Services Are Up
Run from repo root:

```powershell
Invoke-RestMethod http://localhost:8100/health
Invoke-RestMethod http://localhost:8000/health
```

Expected: both return `status: ok`.

## 8) CLI Login (Required Before Agent Chat)
Run:

```powershell
python .\scripts\cli_login.py --agent-url http://localhost:8000
```

When prompted, enter:
- `Email:` -> your registered user email
- `Password:` -> your signup password

This writes `.agent_session.json` and starts interactive chat.
PIN is used later only for payment confirmation/auth challenge.

## 9) Voice CLI (STT -> agent -> TTS)
Run voice mode after services are up:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_voice_cli.ps1
```

Direct command:

```powershell
.\.venv-agent\Scripts\python.exe .\scripts\cli_voice.py --agent-url http://localhost:8000
```

Voice policy in this flow:
- No voice interaction before CLI login is successful.
- PIN entry during payment verification is typed-only (never voice-captured).
- STT uses Groq Whisper; TTS uses Deepgram with Groq fallback.

## 10) Run Frontend (Landing + Signup + Agent Logs)
In a new terminal:

```powershell
python -m http.server 5173 --directory onboarding_dashboard
```

Open browser:
- `http://localhost:5173`

Pages:
- Landing: `/index.html`
- Signup: `/signup.html`
- Agent Logs: `/agent-logs.html`

## 11) Stop Services
From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_stack.ps1
```

## 12) Quick Troubleshooting
If ports are stuck (`10048` bind error), run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_stack.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_stack.ps1
```

If `.env.agent` is missing, recreate it:

```powershell
Copy-Item .env.agent.example .env.agent
```

If venv missing, rerun bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 -Recreate
```
