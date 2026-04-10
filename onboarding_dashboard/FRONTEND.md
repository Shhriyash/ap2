# Agent2Pay Frontend Guide

## Overview
This standalone frontend serves as the interactive landing page and onboarding portal for the **Agent2Pay** AI payment assistant. It has been built with a modern, dark-premium aesthetic to showcase the application's unique features, primarily its voice-first approach and strict P2P capabilities.

**Scope:**
- Marketing landing page detailing features and benefits.
- Sign-up wizard (no login screen; login/authentication is done via CLI).
- Backend-connected onboarding flow with real API integration.
- Dedicated agent logs monitor.

## Key Interface Features

1. **Interactive Landing Page (`index.html`)**
   - **Dark Premium Aesthetic**: Glassmorphism panes, custom gradient mesh animations, floating particles.
   - **Dynamic Animations**: Scroll-reveal sections, voice command live typing demo, animated security cascade.
   - **Feature Showcases**: Visualizers for P2P interactions, natural language extraction, and security/OTP flows.
   - **Comparison Table**: Clear distinctions between Agent2Pay and traditional payment frameworks.

2. **Progressive Signup Wizard (`signup.html`)**
   - 5-step interactive process with a glassmorphic dark-theme UI.
   - Step 1: General details (name, email, phone)
   - Step 2: PIN setup
   - Step 3: OTP device start + verification
   - Step 4: Account linking (Bank/Card)
   - Step 5: Completion summary and CLI handoff guidance

3. **Backend API Integration (`app.js`)**
   - API calls wired to the backend agent gateway (`http://localhost:8100` by default):
     - `POST /onboarding/signup`
     - `POST /onboarding/users/{user_id}/pin`
     - `POST /onboarding/users/{user_id}/otp-device/start`
     - `POST /onboarding/users/{user_id}/otp-device/verify`
     - `GET /onboarding/users/{user_id}/status`

4. **Live Agent Logs Page (`agent-logs.html`)**
   - Real-time monitor for AI agent session states and extraction outputs.
   - Start/stop/clear streaming feed controls.

## Design & Accessibility

- **Design System**: Over 60+ CSS variables governing colors (Teal/Violet/Gold anchors on Deep Navy), borders, shadows, and spacing.
- **Animations**: `landing.js` drives a lightweight particle canvas, IntersectionObserver reveal logic, and typing effects.
- **Accessibility**: Support for `prefers-reduced-motion: reduce`, visible focus outlines, scalable typography, and valid aria roles.

## File Structure
- `index.html` - The scrollable marketing landing page.
- `signup.html` - The 5-step registration wizard.
- `agent-logs.html` - Live agent monitoring feed.
- `styles.css` - comprehensive utility and component design system.
- `landing.js` - UI animations, canvas backgrounds, and scroll interactions.
- `app.js` - form handling, state machine, and backend API interactions for signup.
- `agent-logs.js` - long-polling or polling loop for displaying backend agent logs.

## How to Run Locally

From the repository root:

```powershell
cd onboarding_dashboard
python -m http.server 5173
```

Open in your browser:
- `http://localhost:5173`

*Note: Ensure the Agent & Gateway Python backend services are running so the Signup API steps and Agent Logs fetch logic function correctly.*
