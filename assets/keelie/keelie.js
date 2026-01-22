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
    .replace(/'/g, "&#039;");
}

function formatKeelie(text) {
  let safe = escapeHtml(text);

  // Bold: **text**
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<span class="keelie-bold">$1</span>');

  // Newlines
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

  const panel = el(`
    <div class="keelie-panel" role="dialog" aria-label="Keelie chat" aria-modal="true">
      <div class="keelie-header">
        <div class="keelie-badge">K</div>
        <div class="keelie-title">
          <strong>Keelie</strong>
          <span>Keel Toys assistant</span>
        </div>

        <a class="keelie-contact" href="${CONTACT_URL}" target="_blank" rel="noopener noreferrer" aria-label="Contact Keel Toys">
          Contact
        </a>

        <button class="keelie-close" aria-label="Close chat">✕</button>
      </div>

      <div class="keelie-chat" id="keelie-chat"></div>

      <div class="keelie-footer">
        <div class="keelie-row">
          <input class="keelie-input" id="keelie-text" placeholder="Type a message…" autocomplete="off" />
          <button class="keelie-send" id="keelie-send">Send</button>
        </div>

        <!-- ✅ Auto-suggest -->
        <div class="keelie-suggest" id="keelie-suggest" style="display:none;">
          <div class="keelie-suggest-list" id="keelie-suggest-list"></div>
        </div>
        <div class="keelie-suggest-hint" id="keelie-suggest-hint" style="display:none;">
          Tip: use ↑/↓ then Enter (Esc to close)
        </div>

        <!-- ✅ Two-stage status indicators -->
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

  const chatEl = panel.querySelector("#keelie-chat");
  const inputEl = panel.querySelector("#keelie-text");
  const sendBtn = panel.querySelector("#keelie-send");
  const closeBtn = panel.querySelector(".keelie-close");
  const thinkingEl = panel.querySelector("#keelie-thinking");
  const typingEl = panel.querySelector("#keelie-typing");

  function addBubble(who, text) {
    const row = document.createElement("div");
    row.className = `keelie-msg ${who === "You" ? "you" : "bot"}`;

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble";
    bubble.innerHTML = formatKeelie(text);

    row.appendChild(bubble);
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  // Expose to Python
  window.keelieAddBubble = addBubble;

  // ==============================
  // Inline status bubbles
  // ==============================
  let statusBubble = null;

  function showStatus(text) {
    removeStatus();

    const row = document.createElement("div");
    row.className = "keelie-msg bot keelie-status-msg";

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble keelie-status-bubble";
    bubble.textContent = text;

    row.appendChild(bubble);
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;

    statusBubble = row;
  }

  function removeStatus() {
    if (statusBubble && statusBubble.parentNode) {
      statusBubble.parentNode.removeChild(statusBubble);
    }
    statusBubble = null;
  }

  // Expose to Python
  window.keelieShowStatus = showStatus;
  window.keelieClearStatus = removeStatus;

  window.keelieGetInput = () => inputEl.value || "";
  window.keelieClearInput = () => { inputEl.value = ""; };

  // ==============================
  // Auto-suggest (safe; cannot crash widget)
  // ==============================
  const suggestWrap = panel.querySelector("#keelie-suggest");
  const suggestList = panel.querySelector("#keelie-suggest-list");
  const suggestHint = panel.querySelector("#keelie-suggest-hint");
  const SUGGEST_ENABLED = !!(suggestWrap && suggestList && suggestHint);

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

    btn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      inputEl.value = text;
      inputEl.focus();
      hideSuggest();
    });

    suggestList.appendChild(btn);
  });

  suggestWrap.style.display = "block";
  panel.classList.add("is-suggesting");
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
    inputEl.focus();
    hideSuggest();
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

      // mousedown avoids input blur
      btn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        inputEl.value = text;
        inputEl.focus();
        hideSuggest();
      });

      suggestList.appendChild(btn);
    });

    suggestWrap.style.display = "block";
    suggestHint.style.display = "block";
  }

  // force=true shows top suggestions even if input is empty/short
  function updateSuggest(force = false) {
    if (!SUGGEST_ENABLED) return;

    const query = (inputEl.value || "").trim();

    if (query.length < 2 && !force) {
      hideSuggest();
      return;
    }

    const ranked = SUGGESTIONS
      .map(item => ({
        item,
        s: query.length < 2 ? 1 : scoreSuggestion(query, item)
      }))
      .filter(x => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 6)
      .map(x => x.item);

    renderSuggest(ranked);
  }

  // ==============================
  // Open/close
  // ==============================
  let lastFocused = null;

  function openPanel() {
    lastFocused = document.activeElement;
    panel.classList.add("is-open");
    inputEl.focus();
  }

  function closePanel() {
    panel.classList.remove("is-open");

    // Clear inline status bubble
    if (typeof window.keelieClearStatus === "function") {
      window.keelieClearStatus();
    }

    // Hide suggestions when closing
    hideSuggest();

    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
  }

  launcher.addEventListener("click", () => {
    panel.classList.contains("is-open") ? closePanel() : openPanel();
  });
  closeBtn.addEventListener("click", closePanel);

  // Esc-to-close (and hide suggestions)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panel.classList.contains("is-open")) {
      hideSuggest();
      closePanel();
    }
  });

  // ==============================
  // Loading state + fallback
  // ==============================
  let pythonReady = false;

  function showLoading() { addBubble("Keelie", "Loading assistant…"); }
  function showFailed() {
    addBubble(
      "Keelie",
      "Sorry — the assistant didn’t load properly.\n\nYou can contact our team here:\n" + CONTACT_URL
    );
  }

  const failTimer = setTimeout(() => {
    if (!pythonReady) showFailed();
  }, 10000);

  async function doSend() {
    // Always hide suggestions on send
    hideSuggest();

    if (!pythonReady || typeof window.keelieSend !== "function") {
      addBubble("Keelie", "I’m still loading… please try again in a moment.");
      return;
    }
    await window.keelieSend();
  }

  sendBtn.addEventListener("click", doSend);

  // Autosuggest listeners
  inputEl.addEventListener("focus", () => updateSuggest(false));
  inputEl.addEventListener("input", () => updateSuggest(false));

  inputEl.addEventListener("keydown", (e) => {
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
        // accept suggestion first if highlighted
        if (acceptActiveSuggest()) return;
        doSend();
        return;
      }

      if (e.key === "Escape") {
        hideSuggest();
        return;
      }
    }

    if (e.key === "Enter") doSend();
  });

  // click-away inside the panel hides suggestions
  document.addEventListener("click", (e) => {
    if (!SUGGEST_ENABLED) return;
    if (!panel.contains(e.target)) return;
    if (e.target === inputEl) return;
    if (suggestWrap.contains(e.target)) return;
    hideSuggest();
  });

  // ==============================
  // Start python
  // ==============================
  showLoading();
  const py = document.createElement("py-script");

  // Cache-bust Python runtime too
  py.setAttribute("src", `${BASE_PATH}/keelie_runtime.py?v=8`);

  document.body.appendChild(py);

  const readyCheck = setInterval(() => {
    if (typeof window.keelieSend === "function") {
      pythonReady = true;
      clearTimeout(failTimer);
      clearInterval(readyCheck);

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
