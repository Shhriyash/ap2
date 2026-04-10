# Onboarding Dashboard (Frontend-Only Prototype)

## Scope
- This module is **frontend only** and kept separate from existing agent internals.
- Dashboard supports **sign-up only**.
- Dashboard does **not** include sign-in/login.
- Agent access is gated outside dashboard: user must authenticate via CLI using the same email identity.

## Current Implementation (Progressive)
1. Interactive landing page
- Hero section with clear scope and CTA.
- Animated reveal sections, responsive layout, and accessibility-first structure.

2. Signup wizard (step by step)
- Step 1: General details + email signup.
- Step 2: PIN setup.
- Step 3: OTP device start + OTP verification.
- Step 4: Account connection (bank account or debit card) with skip option.
- Step 5: Completion summary + CLI handoff guidance.

3. Backend wiring
- Live API request logging panel.
- Configurable backend base URL from UI.
- Typed payload handling and guarded error states.

## Backend Endpoints Wired In Frontend
- `POST /onboarding/signup`
- `POST /onboarding/users/{user_id}/pin`
- `POST /onboarding/users/{user_id}/otp-device/start`
- `POST /onboarding/users/{user_id}/otp-device/verify`
- `GET /onboarding/users/{user_id}/status`

## Supabase + CLI Auth Assumption
- Frontend assumes backend handles Supabase email user creation/mapping during signup.
- Frontend completion message instructs user to authenticate in CLI before using agent features.
- Frontend does not manage Supabase secrets or service-role credentials.

## Important Note on Backend Auth Hardening Plan
- Use the prototype auth hardening plan as **reference only** for understanding expected backend behavior.
- This frontend does not execute backend hardening phases or backend rollout plans.

## Files
- `index.html` - landing page + signup wizard structure.
- `styles.css` - visual system, responsive behavior, motion, accessibility states.
- `app.js` - progressive flow logic and backend endpoint integration.

## Run Locally
From repo root:

```powershell
python -m http.server 5173 --directory onboarding_dashboard
```

Open:
- `http://localhost:5173`

Then set backend base URL in the dashboard UI (default: `http://localhost:8100`).

## Deploy On Vercel
This repository already includes `vercel.json` with frontend rewrites and API routing.

After deployment:
- Landing page: `/`
- Signup page: `/signup`
- Agent logs page: `/agent-logs`

Runtime config is controlled in `onboarding_dashboard/config.js`:
- `API_BASE: ""` means same-origin API calls (works with Vercel rewrite to `/api/index.py`).
- `AGENT_API_BASE` must point to a deployed `agent_service` URL if you want live logs.
- If `AGENT_API_BASE` is left empty, the logs page is intentionally disabled in production.
