# AI Agent Payments Prototype Scaffold

This repository contains a split-service prototype for an AI voice/text payment agent:

- `agent_service`: `pydantic-ai` orchestration, retrieval/slot flow, tool execution.
- `gateway_service`: payment gateway simulation with pluggable provider adapters.
- `shared_lib`: reusable contracts/utilities shared by both services.

Designed for future backend replacement:

- Keep Agent + API contracts stable.
- Switch gateway provider from `dummy` to `external` with env change and adapter updates.
- Keep your custom payment tool interface unchanged while swapping provider internals.

## Quick Start

1. Copy env templates:
   - `Copy-Item .env.agent.example .env.agent`
   - `Copy-Item .env.gateway.example .env.gateway`
2. Bootstrap environments:
   - `powershell -ExecutionPolicy Bypass -File .\\scripts\\bootstrap.ps1`
3. Run gateway:
   - `powershell -ExecutionPolicy Bypass -File .\\scripts\\run_gateway.ps1`
4. Run agent:
   - `powershell -ExecutionPolicy Bypass -File .\\scripts\\run_agent.ps1`

## Services

- Agent API: `http://localhost:8000`
  - `POST /agent/message`
  - `POST /auth/challenge/start`
  - `POST /auth/challenge/verify`
- Gateway API: `http://localhost:8100`
  - `POST /payments/validate`
  - `POST /payments/transfer`
  - `POST /payments/refund`
  - `POST /payments/reverse`
  - `GET /payments/{transaction_id}`

## Notes

- Currency is fixed to `AED`.
- Beneficiary pre-registration is mandatory for transfer.
- PIN-first with OTP fallback is scaffolded in the agent flow.
- Database migrations are in `gateway_service/migrations/sql`.
- `pydantic-ai` uses OpenRouter when `OPENROUTER_API_KEY` is set; otherwise deterministic fallback parsing is used.
