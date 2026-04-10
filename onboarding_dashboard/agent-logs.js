const AGENT_API_BASE = String(window.__APP_CONFIG__?.AGENT_API_BASE ?? "")
  .trim()
  .replace(/\/+$/, "");

const elements = {
  logsForm: document.getElementById("logs-form"),
  sessionId: document.getElementById("session-id"),
  userId: document.getElementById("user-id"),
  startBtn: document.getElementById("start-logs"),
  stopBtn: document.getElementById("stop-logs"),
  clearBtn: document.getElementById("clear-logs"),
  logsFeed: document.getElementById("logs-feed"),
  logsStatus: document.getElementById("logs-status"),
};

const state = {
  timer: null,
  activeSessionId: "",
  activeUserId: "",
  lastSnapshot: "",
};

const setStatus = (kind, text) => {
  elements.logsStatus.className = `feedback logs-status ${kind}`;
  elements.logsStatus.textContent = text;
};

const renderEntry = (title, payload) => {
  const item = document.createElement("li");
  const ts = new Date().toLocaleTimeString();
  item.innerHTML = `<span class="logs-time">${ts}</span><strong>${title}</strong><pre>${JSON.stringify(payload, null, 2)}</pre>`;
  elements.logsFeed.prepend(item);
};

const fetchSessionState = async () => {
  if (!state.activeSessionId) return;

  try {
    const response = await fetch(
      `${AGENT_API_BASE}/agent/session/${encodeURIComponent(state.activeSessionId)}`,
      {
        method: "GET",
      }
    );

    if (!response.ok) {
      throw new Error("Unable to fetch session.");
    }

    const data = await response.json();
    const snapshot = JSON.stringify(data || {});

    if (snapshot !== state.lastSnapshot) {
      state.lastSnapshot = snapshot;
      renderEntry(`Session ${state.activeSessionId} updated`, data || {});
      setStatus("ok", "Live logs active.");
      return;
    }

    setStatus("warn", "Watching for new updates...");
  } catch {
    setStatus("error", "Unable to refresh logs right now.");
  }
};

const stopPolling = () => {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
};

const startPolling = async () => {
  stopPolling();
  state.lastSnapshot = "";

  await fetchSessionState();
  state.timer = setInterval(fetchSessionState, 5000);
};

const bindRevealAnimations = () => {
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
        }
      }
    },
    { threshold: 0.2 }
  );

  for (const el of document.querySelectorAll(".reveal")) {
    observer.observe(el);
  }
};

const init = () => {
  if (!AGENT_API_BASE) {
    elements.startBtn.disabled = true;
    setStatus(
      "warn",
      "Live logs are disabled until AGENT_API_BASE is configured in config.js."
    );
    bindRevealAnimations();
    return;
  }

  elements.logsForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const sessionId = elements.sessionId.value.trim();
    const userId = elements.userId.value.trim();
    if (!sessionId) {
      setStatus("error", "Session ID is required.");
      return;
    }

    state.activeSessionId = sessionId;
    state.activeUserId = userId;
    setStatus("warn", "Starting live logs...");
    await startPolling();
  });

  elements.stopBtn.addEventListener("click", () => {
    stopPolling();
    setStatus("warn", "Live logs stopped.");
  });

  elements.clearBtn.addEventListener("click", () => {
    elements.logsFeed.innerHTML = "";
    setStatus("warn", "Log entries cleared.");
  });

  bindRevealAnimations();
  setStatus("warn", "Enter a session id to begin live logging.");
};

init();
