// File: assets/keelie/keelie.js
import "https://pyscript.net/releases/2024.9.2/core.js";

const BASE_PATH = "assets/keelie";
const CONTACT_URL = "https://www.keeltoys.com/contact-us/";

// ==============================
// Element helper
// ==============================
function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// ==============================
// Safe formatting helpers
// ==============================
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\'/g, "&#039;");
}


function linkify(safeHtmlText) {
  // Convert http(s) URLs into clickable links.
  // Input MUST already be escaped.
  const urlRe = /\bhttps?:\/\/[^\s<]+/gi;

  return safeHtmlText.replace(urlRe, (url) => {
    // Trim common trailing punctuation
    const trimmed = url.replace(/[)\].,!?;:]+$/g, "");
    const trailing = url.slice(trimmed.length);

    return (
      `<a href="${trimmed}" target="_blank" rel="noopener noreferrer">${trimmed}</a>` +
      trailing
    );
  });
}


function formatKeelie(text) {
  let safe = escapeHtml(text);

  // clickable links
  safe = linkify(safe);

  // **bold**
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<span class="keelie-bold">$1</span>');

  // newlines
  safe = safe.replace(/\n/g, "<br>");

  return safe;
}

function mountWidget() {
  const launcher = el(`
    <button class="keelie-launcher" aria-label="Open chat">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M7 8h10M7 12h6M21 12c0 4.418-4.03 8-9 8a10.6 10.6 0 0 1-3.29-.52L3 21l1.64-4.1A7.37 7.37 0 0 1 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8Z"
          stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
  `);

  // NOTE: autosuggest container is ABOVE input row (in-flow, no overlap)
  const panel = el(`
    <div class="keelie-panel" role="dialog" aria-label="Keelie chat" aria-modal="true">
      <div class="keelie-header">
        <div class="keelie-badge">K</div>
        <div class="keelie-title">
          <strong>Keelie</strong>
          <span>Keel Toys assistant</span>
        </div>

        <a class="keelie-contact" href="${CONTACT_URL}" target="_blank" rel="noopener noreferrer">
          Contact
        </a>

        <button class="keelie-close" aria-label="Close chat">✕</button>
      </div>

      <div class="keelie-chat" id="keelie-chat"></div>

      <div class="keelie-footer">
        <div class="keelie-suggest" id="keelie-suggest" style="display:none;">
          <div class="keelie-suggest-list" id="keelie-suggest-list"></div>
        </div>

        <div class="keelie-row">
          <input class="keelie-input" id="keelie-text" placeholder="Type a message…" autocomplete="off" />
          <button class="keelie-send" id="keelie-send">Send</button>
        </div>

        <div class="keelie-status" id="keelie-thinking" style="display:none;">Keelie is thinking…</div>
        <div class="keelie-status" id="keelie-typing" style="display:none;">Keelie is typing…</div>

        <div class="keelie-privacy">
          This assistant runs in your browser. Messages aren’t sent to a server.
        </div>
      </div>
    </div>
  `);

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  // Pulse the launcher once shortly after load (subtle attention cue)
  setTimeout(() => launcher.classList.add("keelie-pulse"), 600);
  setTimeout(() => launcher.classList.remove("keelie-pulse"), 2200);


  const chatEl = panel.querySelector("#keelie-chat");
  const inputEl = panel.querySelector("#keelie-text");
  const sendBtn = panel.querySelector("#keelie-send");
  const closeBtn = panel.querySelector(".keelie-close");

  // Status lines exist for fallback; Python also uses inline status bubbles via window.keelieShowStatus
  const thinkingEl = panel.querySelector("#keelie-thinking");
  const typingEl = panel.querySelector("#keelie-typing");

  // ==============================
  // Chat bubbles
  // ==============================
    // ==============================
  // Feedback buttons (👍/👎)
  // - Shown on fallback AND key “high-value” answers
  // - Never shown on the initial onboarding/help panel
  // - Never shown until the user has actually sent a message
  // ==============================
  const FALLBACK_TRIGGER_RE = /I[’']m not able to help with that just now\./i;

  const FEEDBACK_TRIGGERS = [
    // Stock codes / SKU answers
    /\bstock\s*code\b/i,
    /\bsku\b/i,

    // Minimum order values
    /\bminimum\s+order\b/i,
    /\bminimum\s+order\s+values\b/i,
    /\b£\s*\d+/i,

    // Invoices
    /\binvoice\b/i,
    /Invoice\s+History/i,

    // Delivery / tracking
    /\btracking\b/i,
    /\border\s+confirmation\s+email\b/i,
    /\bdelivery\b/i,

    // Keeleco / sustainability
    /\bkeeleco\b/i,
    /\brecycled\b/i,

    // Production / where made
    /\bproduced\b/i,
    /\bmanufactur/i
  ];

  function isOnboardingPanel(text) {
    const t = String(text || "");
    // Covers variants like: "I can help with..." or "I can help you with things like..."
    return /\bI\s+can\s+help\b/i.test(t) && /\bWhat\s+would\s+you\s+like\s+to\s+ask\?\b/i.test(t);
  }

  function shouldOfferFeedback(who, text) {
    if (who !== "Keelie") return false;
    if (!userHasMessaged) return false;

    const t = String(text || "");
    if (isOnboardingPanel(t)) return false;

    if (FALLBACK_TRIGGER_RE.test(t)) return true;
    return FEEDBACK_TRIGGERS.some(rx => rx.test(t));
  }

  function attachFeedback(bubbleEl, originalText) {
  if (!bubbleEl || bubbleEl.querySelector(".keelie-feedback")) return;

  const row = document.createElement("div");
  row.className = "keelie-feedback";

  const label = document.createElement("span");
  label.className = "keelie-feedback-label";
  label.textContent = "Helpful?";

  const yesBtn = document.createElement("button");
  yesBtn.type = "button";
  yesBtn.setAttribute("aria-label", "This was helpful");
  yesBtn.textContent = "👍";

  const noBtn = document.createElement("button");
  noBtn.type = "button";
  noBtn.setAttribute("aria-label", "This was not helpful");
  noBtn.textContent = "👎";

  row.appendChild(label);
  row.appendChild(yesBtn);
  row.appendChild(noBtn);
  bubbleEl.appendChild(row);

  const acknowledge = (helpful) => {
    yesBtn.disabled = true;
    noBtn.disabled = true;
    row.innerHTML = helpful
      ? '<span class="keelie-feedback-thanks">Thanks!</span>'
      : '<span class="keelie-feedback-thanks">Thanks — noted.</span>';

    // Optional: store locally (no server)
    try {
      const key = "keelie_feedback";
      const data = JSON.parse(localStorage.getItem(key)) || {
        helpful: 0,
        notHelpful: 0
      };

      if (helpful) data.helpful += 1;
      else data.notHelpful += 1;

      localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
      // ignore
    }
  };

  yesBtn.addEventListener("click", () => acknowledge(true));
  noBtn.addEventListener("click", () => acknowledge(false));
}


function addBubble(who, text) {
    const row = document.createElement("div");
    row.className = `keelie-msg ${who === "You" ? "you" : "bot"}`;

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble";
    bubble.innerHTML = formatKeelie(text);

    row.appendChild(bubble);
    // Offer quick feedback on fallback + key answers
    if (shouldOfferFeedback(who, text)) {
      attachFeedback(bubble, text);
    }
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  // Expose to Python runtime
  window.keelieAddBubble = addBubble;
  window.keelieGetInput = () => inputEl.value || "";
  window.keelieClearInput = () => { inputEl.value = ""; };

  // Inline status bubble (used by Python)
  let statusBubble = null;

  function showStatus(text) {
    clearStatus();
    const row = document.createElement("div");
    row.className = "keelie-msg bot keelie-status-msg";

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble keelie-status-bubble";
    bubble.innerHTML = `${escapeHtml(String(text).replace(/…+$/g, ""))}<span class="keelie-dots" aria-hidden="true"><span></span><span></span><span></span></span>`;

    row.appendChild(bubble);
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;

    statusBubble = row;
  }

  function clearStatus() {
    if (statusBubble && statusBubble.parentNode) statusBubble.parentNode.removeChild(statusBubble);
    statusBubble = null;
  }

  window.keelieShowStatus = showStatus;
  window.keelieClearStatus = clearStatus;

  // ==============================
  // Autosuggest (professional + safe)
  // - shows only after 2+ chars
  // - click suggestion: fills input + sends (via sendBtn.click())
  // ==============================
  const suggestWrap = panel.querySelector("#keelie-suggest");
  const suggestList = panel.querySelector("#keelie-suggest-list");
  const SUGGEST_ENABLED = !!(suggestWrap && suggestList);

  const SUGGESTIONS = [
    "What’s the minimum order value?",
    "What’s the minimum value?",
    "What is your MOQ?",
    "Where are your toys produced?",
    "Tell me about Keeleco and recycled materials",
    "What’s the stock code for Polar Bear Plush 20cm?",
    "How do I find a stock code / SKU?",
    "Where is my order?",
    "How do I track my order?",
    "How do I download an invoice?",
    "What are your opening hours?",
    "How do I contact customer service?"
  ];

  let activeSuggestIndex = -1;
  let currentSuggestItems = [];

  function norm(s) {
    return String(s || "").toLowerCase().trim();
  }

  function scoreSuggestion(query, item) {
    const q = norm(query);
    const it = norm(item);
    if (!q) return 0;

    if (it.startsWith(q)) return 100;
    if (it.includes(q)) return 70;

    const qTokens = new Set(q.split(/\s+/).filter(Boolean));
    const iTokens = new Set(it.split(/\s+/).filter(Boolean));
    let overlap = 0;
    qTokens.forEach(t => { if (iTokens.has(t)) overlap++; });

    return overlap > 0 ? (40 + overlap) : 0;
  }

  // Function declaration (hoisted) so it can never be "not defined"
  function hideSuggest() {
    if (!SUGGEST_ENABLED) return;
    suggestWrap.style.display = "none";
    suggestList.innerHTML = "";
    activeSuggestIndex = -1;
    currentSuggestItems = [];
    panel.classList.remove("is-suggesting");
  }

  function setActiveSuggest(nextIndex) {
    if (!SUGGEST_ENABLED) return;
    const children = Array.from(suggestList.children);
    if (!children.length) return;

    activeSuggestIndex = nextIndex;
    children.forEach((el, i) => {
      if (i === activeSuggestIndex) el.classList.add("is-active");
      else el.classList.remove("is-active");
    });
  }

  function acceptActiveSuggest() {
    if (!SUGGEST_ENABLED) return false;
    if (activeSuggestIndex < 0) return false;

    const chosen = currentSuggestItems[activeSuggestIndex];
    if (!chosen) return false;

    inputEl.value = chosen;
    hideSuggest();

    // ✅ Guaranteed send: click the actual Send button
    setTimeout(() => sendBtn.click(), 0);
    return true;
  }

  function renderSuggest(items) {
    if (!SUGGEST_ENABLED) return;

    currentSuggestItems = items;
    activeSuggestIndex = -1;

    if (!items.length) {
      hideSuggest();
      return;
    }

    suggestList.innerHTML = "";

    items.forEach((text) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "keelie-suggest-item";
      btn.textContent = text;

      // pointerdown is the most reliable across devices;
      // preventDefault stops input blur issues.
      btn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        inputEl.value = text;
        hideSuggest();

        // ✅ Guaranteed send: click Send button
        setTimeout(() => sendBtn.click(), 0);
      });

      suggestList.appendChild(btn);
    });

    suggestWrap.style.display = "block";
    panel.classList.add("is-suggesting");
  }

  function updateSuggest() {
    if (!SUGGEST_ENABLED) return;

    const query = (inputEl.value || "").trim();

    // Only show after 2+ chars
    if (query.length < 2) {
      hideSuggest();
      return;
    }

    const ranked = SUGGESTIONS
      .map(item => ({ item, s: scoreSuggestion(query, item) }))
      .filter(x => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 6)
      .map(x => x.item);

    renderSuggest(ranked);
  }

  // ==============================
  // Panel open/close
  // ==============================
  let lastFocused = null;

  function openPanel() {
    lastFocused = document.activeElement;
    panel.classList.add("is-open");
    inputEl.focus();
  }

  function closePanel() {
    panel.classList.remove("is-open");
    hideSuggest();
    clearStatus();
    if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
  }

  launcher.addEventListener("click", () => {
    panel.classList.contains("is-open") ? closePanel() : openPanel();
  });

  closeBtn.addEventListener("click", closePanel);

  // Escape: close suggest first, then close panel
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!panel.classList.contains("is-open")) return;

    if (panel.classList.contains("is-suggesting")) {
      hideSuggest();
      return;
    }
    closePanel();
  });

  // Click-away inside panel hides suggestions (not panel)
  document.addEventListener("click", (e) => {
    if (!SUGGEST_ENABLED) return;
    if (!panel.contains(e.target)) return;
    if (e.target === inputEl) return;
    if (suggestWrap.contains(e.target)) return;
    hideSuggest();
  });

  // ==============================
  // Send flow
  // ==============================
  let pythonReady = false;
  let userHasMessaged = false; // set true after the first user send

  // ==============================
  // Anti-spam rate limit
  // - If a user sends too many messages quickly, apply a cooldown
  // ==============================
  const RATE_WINDOW_MS = 8000;   // look back 8 seconds
  const RATE_MAX_SENDS = 4;      // allow up to 4 sends in that window
  const COOLDOWN_MS = 10000;     // lock input for 10 seconds if exceeded

  let recentSends = [];          // timestamps (ms)
  let cooldownUntil = 0;

  function inCooldown() {
    return Date.now() < cooldownUntil;
  }

  function startCooldown() {
    cooldownUntil = Date.now() + COOLDOWN_MS;

    // Disable input + send button during cooldown
    inputEl.disabled = true;
    sendBtn.disabled = true;

    // Brief feedback (keep it short)
    addBubble("Keelie", "Please slow down a little — you can send another message in a few seconds.");

    setTimeout(() => {
      if (!inCooldown()) {
        inputEl.disabled = false;
        sendBtn.disabled = false;
        inputEl.focus();
      }
    }, COOLDOWN_MS);
  }

  function registerSendOrCooldown() {
    const now = Date.now();

    if (now < cooldownUntil) return false;

    // Keep only sends within the window
    recentSends = recentSends.filter(t => now - t <= RATE_WINDOW_MS);

    // Too many sends -> cooldown
    if (recentSends.length >= RATE_MAX_SENDS) {
      startCooldown();
      return false;
    }

    recentSends.push(now);
    return true;
  }


  async function doSend() {
    hideSuggest();

    const msg = (inputEl.value || "").trim();
    if (!msg) return;
    userHasMessaged = true;

    // ✅ Anti-spam gate
    if (!registerSendOrCooldown()) return;

    if (!pythonReady || typeof window.keelieSend !== "function") {
      addBubble("Keelie", "I’m still loading… please try again in a moment.");
      return;
    }
    await window.keelieSend();
  }

  sendBtn.addEventListener("click", doSend);

  inputEl.addEventListener("input", () => updateSuggest());

  inputEl.addEventListener("keydown", (e) => {
    // If suggestions are open, allow navigation + Enter to accept (and send)
    if (SUGGEST_ENABLED && suggestWrap.style.display !== "none") {
      const max = currentSuggestItems.length - 1;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = activeSuggestIndex < max ? activeSuggestIndex + 1 : 0;
        setActiveSuggest(next);
        return;
      }

      if (e.key === "ArrowUp") {
        e.preventDefault();
        const next = activeSuggestIndex > 0 ? activeSuggestIndex - 1 : max;
        setActiveSuggest(next);
        return;
      }

      if (e.key === "Enter") {
        // Accept highlighted suggestion -> sends automatically
        if (acceptActiveSuggest()) return;
        // Otherwise send typed text
        e.preventDefault();
        doSend();
        return;
      }
    }

    if (e.key === "Enter") {
      e.preventDefault();
      doSend();
    }
  });

  // ==============================
  // Boot + Python runtime
  // ==============================
  showStatus("Loading assistant…");

  const py = document.createElement("py-script");
  // bump this ?v= if you change python file
  py.setAttribute("src", `${BASE_PATH}/keelie_runtime.py?v=12`);
  document.body.appendChild(py);

  const failTimer = setTimeout(() => {
    if (!pythonReady) {
      clearStatus();
      addBubble(
        "Keelie",
        "Sorry — the assistant didn’t load properly.\n\nYou can contact our team here:\n" + CONTACT_URL
      );
    }
  }, 10000);

  const readyCheck = setInterval(() => {
    if (typeof window.keelieSend === "function") {
      pythonReady = true;
      clearTimeout(failTimer);
      clearInterval(readyCheck);

      clearStatus();

      addBubble(
        "Keelie",
        "Hello! 👋 I’m Keelie — the Keel Toys assistant.\n\n"
        + "I can help you with things like:\n"
        + "• **Minimum order values** (e.g. *What’s the minimum order value?*)\n"
        + "• **Stock codes / SKUs** (e.g. *What’s the stock code for Polar Bear Plush 20cm?*)\n"
        + "• **Keeleco® recycled materials & sustainability**\n"
        + "• **Where our toys are made**\n"
        + "• **Delivery & order questions** (e.g. *Where is my order?*)\n"
        + "• **Invoices** (e.g. *How do I download an invoice?*)\n\n"
        + "What would you like to ask?"
      );
    }
  }, 250);
}
mountWidget();