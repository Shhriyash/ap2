const API_BASE = "http://localhost:8100";

const state = {
  currentStep: 1,
  userId: "",
  supabaseUserId: "",
  onboardingSessionToken: "",
  challengeId: "",
  email: "",
  emailVerificationRequired: null,
  otpVerified: false,
  accountConnectionStatus: "",
  accountConnectionMethod: "",
  accountConnectionLabel: "",
};

const elements = {
  signupForm: document.getElementById("signup-form"),
  pinForm: document.getElementById("pin-form"),
  otpStartForm: document.getElementById("otp-start-form"),
  otpVerifyForm: document.getElementById("otp-verify-form"),
  accountConnectForm: document.getElementById("account-connect-form"),
  connectMethod: document.getElementById("connect-method"),
  skipAccountBtn: document.getElementById("skip-account-btn"),
  refreshStatusBtn: document.getElementById("refresh-status-btn"),
  signupMessage: document.getElementById("signup-message"),
  pinMessage: document.getElementById("pin-message"),
  otpMessage: document.getElementById("otp-message"),
  accountMessage: document.getElementById("account-message"),
  finalSummary: document.getElementById("final-summary"),
  steps: [...document.querySelectorAll(".step")],
  panels: [...document.querySelectorAll(".step-panel")],
  accountGroups: [...document.querySelectorAll("[data-connect-group]")],
  accountHolderName: document.getElementById("account-holder-name"),
  billingCountry: document.getElementById("billing-country"),
  financialInstitution: document.getElementById("financial-institution"),
  bankAccountNumber: document.getElementById("bank-account-number"),
  routingCode: document.getElementById("routing-code"),
  cardNumber: document.getElementById("card-number"),
  cardExpiry: document.getElementById("card-expiry"),
  cardCvv: document.getElementById("card-cvv"),
};

const cleanBaseUrl = (rawUrl) => {
  const trimmed = (rawUrl || "").trim();
  if (!trimmed) return "";
  return trimmed.replace(/\/+$/, "");
};

const setMessage = (target, kind, text) => {
  target.className = `feedback ${kind}`;
  target.textContent = text;
};

const apiRequest = async (path, { method = "GET", payload } = {}) => {
  const base = cleanBaseUrl(API_BASE);
  if (!base) throw new Error("Service configuration is unavailable.");

  const headers = {
    "Content-Type": "application/json",
  };

  if (state.onboardingSessionToken) {
    headers["X-Onboarding-Session-Token"] = state.onboardingSessionToken;
  }

  const response = await fetch(`${base}${path}`, {
    method,
    headers,
    body: method === "GET" ? undefined : JSON.stringify(payload || {}),
  });

  const raw = await response.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    data = raw ? { raw } : {};
  }

  if (!response.ok) {
    const detail = data?.detail || data?.message || "Request failed. Please retry.";
    throw new Error(detail);
  }

  return data;
};

const getFirst = (obj, keys) => {
  for (const key of keys) {
    if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== "") {
      return obj[key];
    }
  }
  return "";
};

const computeMaxAllowedStep = () => {
  if (!state.userId) return 1;
  if (!state.otpVerified) return 3;
  if (!state.accountConnectionStatus) return 4;
  return 5;
};

const maskIdentifier = (value, keep = 4) => {
  const clean = String(value || "").replace(/\s+/g, "");
  if (clean.length <= keep) return clean;
  return `${"*".repeat(Math.max(clean.length - keep, 2))}${clean.slice(-keep)}`;
};

const setConnectionFieldsRequired = (method) => {
  const mark = (element, required) => {
    if (element) element.required = required;
  };

  mark(elements.accountHolderName, true);
  mark(elements.billingCountry, true);
  mark(elements.financialInstitution, method === "bank");
  mark(elements.bankAccountNumber, method === "bank");
  mark(elements.routingCode, method === "bank");
  mark(elements.cardNumber, method === "card");
  mark(elements.cardExpiry, method === "card");
  mark(elements.cardCvv, method === "card");
};

const updateConnectionMethodView = () => {
  const method = String(elements.connectMethod?.value || "bank");
  elements.accountGroups.forEach((group) => {
    const type = group.dataset.connectGroup;
    const isVisible = type === "shared" || type === method;
    group.hidden = !isVisible;
  });
  setConnectionFieldsRequired(method);
};

const goToStep = (stepNumber) => {
  const allowedStep = computeMaxAllowedStep();
  const nextStep = Math.min(stepNumber, allowedStep);
  state.currentStep = nextStep;
  elements.steps.forEach((stepBtn) => {
    const step = Number(stepBtn.dataset.step);
    const isCurrent = step === nextStep;
    stepBtn.classList.toggle("is-active", isCurrent);
    stepBtn.setAttribute("aria-selected", isCurrent ? "true" : "false");
    stepBtn.disabled = step > allowedStep;
  });

  elements.panels.forEach((panel) => {
    const isCurrent = panel.id === `step-${nextStep}`;
    panel.classList.toggle("is-visible", isCurrent);
    panel.hidden = !isCurrent;
  });
};

const handleSignup = async (event) => {
  event.preventDefault();
  const formData = new FormData(elements.signupForm);
  const password = String(formData.get("password") || "").trim();
  const confirmPassword = String(formData.get("confirm_password") || "").trim();
  const payload = {
    full_name: String(formData.get("full_name") || "").trim(),
    email: String(formData.get("email") || "").trim().toLowerCase(),
    password,
    phone: String(formData.get("phone") || "").trim(),
  };

  if (!payload.full_name || !payload.email || !payload.password) {
    setMessage(elements.signupMessage, "error", "Full name, email, and password are required.");
    return;
  }

  if (payload.password.length < 6) {
    setMessage(elements.signupMessage, "error", "Password must be at least 6 characters.");
    return;
  }

  if (password !== confirmPassword) {
    setMessage(elements.signupMessage, "error", "Password and confirm password do not match.");
    return;
  }

  try {
    setMessage(elements.signupMessage, "warn", "Creating signup...");
    const data = await apiRequest("/onboarding/signup", { method: "POST", payload });

    state.userId = getFirst(data, ["user_id", "id"]);
    state.supabaseUserId = getFirst(data, ["supabase_user_id"]);
    state.onboardingSessionToken = getFirst(data, ["onboarding_session_token", "session_token"]);
    state.emailVerificationRequired = Boolean(data.email_verification_required);
    state.email = payload.email;
    state.challengeId = "";
    state.otpVerified = false;
    state.accountConnectionStatus = "";
    state.accountConnectionMethod = "";
    state.accountConnectionLabel = "";

    if (!state.userId) {
      throw new Error("Signup response did not include user_id.");
    }

    setMessage(elements.signupMessage, "ok", `Signup created for user_id: ${state.userId}`);
    goToStep(2);
  } catch (error) {
    setMessage(elements.signupMessage, "error", error.message || "Failed to create signup.");
  }
};

const handlePinSetup = async (event) => {
  event.preventDefault();

  if (!state.userId) {
    setMessage(elements.pinMessage, "error", "Complete step 1 before setting PIN.");
    goToStep(1);
    return;
  }

  const formData = new FormData(elements.pinForm);
  const pin = String(formData.get("pin") || "").trim();
  const confirmPin = String(formData.get("confirm_pin") || "").trim();

  if (!/^\d{4,8}$/.test(pin)) {
    setMessage(elements.pinMessage, "error", "PIN must be 4 to 8 digits.");
    return;
  }

  if (pin !== confirmPin) {
    setMessage(elements.pinMessage, "error", "PIN and confirm PIN do not match.");
    return;
  }

  try {
    setMessage(elements.pinMessage, "warn", "Saving PIN...");
    await apiRequest(`/onboarding/users/${encodeURIComponent(state.userId)}/pin`, {
      method: "POST",
      payload: { pin },
    });

    setMessage(elements.pinMessage, "ok", "PIN saved successfully.");
    goToStep(3);
  } catch (error) {
    setMessage(elements.pinMessage, "error", error.message || "Failed to save PIN.");
  }
};

const handleOtpStart = async (event) => {
  event.preventDefault();

  if (!state.userId) {
    setMessage(elements.otpMessage, "error", "Complete steps 1 and 2 before OTP setup.");
    return;
  }

  const formData = new FormData(elements.otpStartForm);
  const channel = String(formData.get("channel") || "email");
  const destination = String(formData.get("destination") || "").trim();

  if (!destination) {
    setMessage(elements.otpMessage, "error", "Destination is required for OTP.");
    return;
  }

  try {
    setMessage(elements.otpMessage, "warn", "Sending OTP...");
    const data = await apiRequest(`/onboarding/users/${encodeURIComponent(state.userId)}/otp-device/start`, {
      method: "POST",
      payload: { channel, destination },
    });

    state.challengeId = getFirst(data, ["challenge_id", "otp_challenge_id"]);
    state.otpVerified = false;
    const masked = getFirst(data, ["destination_masked", "masked_destination"]);
    setMessage(
      elements.otpMessage,
      "ok",
      `OTP sent${masked ? ` to ${masked}` : ""}. Enter code to verify.`
    );
  } catch (error) {
    setMessage(elements.otpMessage, "error", error.message || "Failed to start OTP challenge.");
  }
};

const handleOtpVerify = async (event) => {
  event.preventDefault();

  if (!state.userId) {
    setMessage(elements.otpMessage, "error", "Complete previous steps first.");
    return;
  }

  const formData = new FormData(elements.otpVerifyForm);
  const otpCode = String(formData.get("otp_code") || "").trim();

  if (!otpCode) {
    setMessage(elements.otpMessage, "error", "OTP code is required.");
    return;
  }

  try {
    setMessage(elements.otpMessage, "warn", "Verifying OTP...");
    const payload = {
      challenge_id: state.challengeId || undefined,
      otp: otpCode,
      value: otpCode,
    };

    const data = await apiRequest(`/onboarding/users/${encodeURIComponent(state.userId)}/otp-device/verify`, {
      method: "POST",
      payload,
    });

    const verifiedFlag = data.verified === undefined ? true : Boolean(data.verified);
    if (!verifiedFlag) {
      throw new Error(data.message || "OTP verification failed.");
    }

    state.otpVerified = true;
    setMessage(elements.otpMessage, "ok", "OTP verified. Finalizing signup.");
    goToStep(4);
  } catch (error) {
    setMessage(elements.otpMessage, "error", error.message || "OTP verification failed.");
  }
};

const handleAccountConnect = async (event) => {
  event.preventDefault();

  if (!state.userId || !state.otpVerified) {
    setMessage(elements.accountMessage, "error", "Complete verification before connecting an account.");
    goToStep(3);
    return;
  }

  const formData = new FormData(elements.accountConnectForm);
  const method = String(formData.get("connect_method") || "bank");
  const holderName = String(formData.get("account_holder_name") || "").trim();
  const billingCountry = String(formData.get("billing_country") || "").trim();
  const bankName = String(formData.get("bank_name") || "").trim();
  const bankAccountNumber = String(formData.get("bank_account_number") || "").replace(/\s+/g, "");
  const routingCode = String(formData.get("routing_code") || "").trim().toUpperCase();
  const cardNumber = String(formData.get("card_number") || "").replace(/\D/g, "");
  const cardExpiry = String(formData.get("card_expiry") || "").trim();
  const cardCvv = String(formData.get("card_cvv") || "").trim();

  if (holderName.length < 2) {
    setMessage(elements.accountMessage, "error", "Account holder name is required.");
    return;
  }

  if (!billingCountry) {
    setMessage(elements.accountMessage, "error", "Billing country is required.");
    return;
  }

  if (method === "bank") {
    if (!bankName || bankName.length < 2) {
      setMessage(elements.accountMessage, "error", "Bank name is required.");
      return;
    }
    if (!/^[A-Za-z0-9]{8,34}$/.test(bankAccountNumber)) {
      setMessage(elements.accountMessage, "error", "Enter a valid account number or IBAN.");
      return;
    }
    if (!/^[A-Za-z0-9]{6,12}$/.test(routingCode)) {
      setMessage(elements.accountMessage, "error", "Enter a valid routing or SWIFT code.");
      return;
    }

    state.accountConnectionLabel = `${bankName} · ${maskIdentifier(bankAccountNumber)}`;
  } else {
    if (!/^\d{12,19}$/.test(cardNumber)) {
      setMessage(elements.accountMessage, "error", "Card number must be 12 to 19 digits.");
      return;
    }
    if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(cardExpiry)) {
      setMessage(elements.accountMessage, "error", "Expiry must be in MM/YY format.");
      return;
    }
    if (!/^\d{3,4}$/.test(cardCvv)) {
      setMessage(elements.accountMessage, "error", "CVV must be 3 or 4 digits.");
      return;
    }

    state.accountConnectionLabel = `Card · ${maskIdentifier(cardNumber)}`;
  }

  state.accountConnectionStatus = "connected";
  state.accountConnectionMethod = method;

  setMessage(elements.accountMessage, "ok", "Account linked successfully.");
  goToStep(5);
  await refreshFinalStatus();
};

const handleSkipAccountConnection = async () => {
  if (!state.userId || !state.otpVerified) {
    setMessage(elements.accountMessage, "error", "Complete verification before continuing.");
    goToStep(3);
    return;
  }

  state.accountConnectionStatus = "skipped";
  state.accountConnectionMethod = "";
  state.accountConnectionLabel = "";

  setMessage(elements.accountMessage, "warn", "Account connection skipped. You can add it later.");
  goToStep(5);
  await refreshFinalStatus();
};

const refreshFinalStatus = async () => {
  if (!state.userId) {
    elements.finalSummary.textContent = "No user created yet.";
    return;
  }

  try {
    const status = await apiRequest(`/onboarding/users/${encodeURIComponent(state.userId)}/status`, {
      method: "GET",
    });
    const verificationState = status?.email_verified === true || status?.verified === true ? "Verified" : "Pending";
    const accountLine =
      state.accountConnectionStatus === "connected"
        ? `${state.accountConnectionMethod === "card" ? "Debit card" : "Bank account"} linked (${state.accountConnectionLabel})`
        : "Not connected";

    elements.finalSummary.innerHTML = `
      <strong>Signup complete.</strong><br/>
      User: ${state.userId}<br/>
      Email: ${state.email}<br/>
      Verification: ${verificationState}<br/>
      Account connection: ${accountLine}<br/>
      Next: Continue to CLI authentication with this same email.
    `;
  } catch (error) {
    elements.finalSummary.textContent = "Unable to refresh status right now. Please try again.";
  }
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
    {
      threshold: 0.2,
    }
  );

  for (const el of document.querySelectorAll(".reveal")) {
    observer.observe(el);
  }
};

const init = () => {
  elements.signupForm.addEventListener("submit", handleSignup);
  elements.pinForm.addEventListener("submit", handlePinSetup);
  elements.otpStartForm.addEventListener("submit", handleOtpStart);
  elements.otpVerifyForm.addEventListener("submit", handleOtpVerify);
  elements.accountConnectForm.addEventListener("submit", handleAccountConnect);
  elements.skipAccountBtn.addEventListener("click", handleSkipAccountConnection);
  elements.connectMethod.addEventListener("change", updateConnectionMethodView);
  elements.refreshStatusBtn.addEventListener("click", refreshFinalStatus);

  elements.steps.forEach((stepBtn) => {
    stepBtn.addEventListener("click", () => {
      const requested = Number(stepBtn.dataset.step);
      const maxAllowed = computeMaxAllowedStep();
      goToStep(Math.min(requested, maxAllowed));
    });
  });

  bindRevealAnimations();
  updateConnectionMethodView();
  goToStep(1);
};

init();
