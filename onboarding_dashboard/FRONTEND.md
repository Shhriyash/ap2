# Frontend Guide

## Overview
This frontend is a standalone onboarding dashboard for the payment agent assistant.

Scope:
- Sign-up only (no login screen in dashboard)
- Backend-connected onboarding flow
- CLI auth handoff message after signup completion

## Features
1. Interactive landing page
- Hero section with clear CTA (`Start Signup`)
- Responsive layout for desktop and mobile

2. Progressive signup wizard
- Step 1: General details (name, email, phone)
- Step 2: PIN setup
- Step 3: OTP device start + OTP verification
- Step 4: Completion summary + CLI handoff guidance

3. Backend integration
- API calls wired to onboarding endpoints:
  - `POST /onboarding/signup`
  - `POST /onboarding/users/{user_id}/pin`
  - `POST /onboarding/users/{user_id}/otp-device/start`
  - `POST /onboarding/users/{user_id}/otp-device/verify`
  - `GET /onboarding/users/{user_id}/status`

4. Separate live agent logs page
- Dedicated page for user agent session activity
- Session-based live refresh
- Start/stop/clear controls for readable monitoring

4. UX and accessibility baseline
- Visible focus states
- Proper labels and feedback messages
- Touch-friendly controls
- Reduced-motion support

## Project Files
- `onboarding_dashboard/index.html` - page structure
- `onboarding_dashboard/styles.css` - design system and responsive styling
- `onboarding_dashboard/app.js` - flow logic and backend API integration

## How to Run
From repo root:

```powershell
cd onboarding_dashboard
python -m http.server 5173
```

Open in browser:
- `http://localhost:5173`

Then set backend base URL in the dashboard UI (default shown: `http://localhost:8100`).

## Notes
- This frontend does not execute backend auth hardening phases.
- It is designed to work with backend onboarding methods already implemented separately.
