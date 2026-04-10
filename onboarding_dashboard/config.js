// Deployment configuration.
// Empty string = same-origin (both frontend and API on Vercel).
// For local dev, delete this file; app.js falls back to localhost:8100.
// AGENT_API_BASE is for the separate agent service used by agent-logs.html.
// Keep it empty to disable logs page until a deployed agent URL is available.
window.__APP_CONFIG__ = {
  API_BASE: "",
  AGENT_API_BASE: "",
};
