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
        <!-- Autosuggest overlay (positioned via CSS) -->
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

  const chatEl = panel.querySelector("#keelie-chat");
  const inputEl = panel.querySelector("#keelie-text");
  const sendBtn = panel.querySelector("#keelie-send");
  const closeBtn = panel.querySelector(".keelie-close");

  // ==============================
  // FLIP animation helpers (smooth reflow)
  // ==============================
  function flipAnimate(mutator) {
    const items = Array.from(chatEl.querySelectorAll(".keelie-msg"));
    const first = new Map(items.map((el) => [el, el.getBoundingClientRect().top]));

    mutator();

    const items2 = Array.from(chatEl.querySelectorAll(".keelie-msg"));
    const last = new Map(items2.map((el) => [el, el.getBoundingClientRect().top]));

    items2.forEach((el) => {
      const dy = (first.get(el) ?? last.get(el)) - last.get(el);
      if (!dy) return;
      el.style.transform = `translateY(${dy}px)`;
      el.style.transition = "transform 0s";
      requestAnimationFrame(() => {
        el.style.transition = "";
        el.style.transform = "";
      });
    });
  }

  function removeBubbleSmooth(row) {
    if (!row || !row.parentNode) return;
    row.classList.add("is-leaving");
    // match CSS transition duration (~220ms)
    setTimeout(() => {
      if (!row.parentNode) return;
      flipAnimate(() => row.remove());
    }, 230);
  }

  // ==============================
  // Chat bubbles (animated)
  // ==============================
  function addBubble(who, text) {
    const row = document.createElement("div");
    row.className = `keelie-msg ${who === "You" ? "you" : "bot"} is-entering`;

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble";
    bubble.innerHTML = formatKeelie(text);

    row.appendChild(bubble);

    flipAnimate(() => {
      chatEl.appendChild(row);
    });

    requestAnimationFrame(() => {
      row.classList.remove("is-entering");
    });

    chatEl.scrollTop = chatEl.scrollHeight;
    return row;
  }

  // Expose to Python runtime
  window.keelieAddBubble = addBubble;
  window.keelieGetInput = () => inputEl.value || "";
  window.keelieClearInput = () => {
    inputEl.value = "";
  };

  // ==============================
  // Inline status bubble (used by Python if needed)
  // ==============================
  let statusRow = null;

  function showStatus(text) {
    if (statusRow) removeBubbleSmooth(statusRow);
    statusRow = addBubble("Keelie", text);
    // make it look like a status bubble via CSS class if you have it
    statusRow.classList.add("keelie-status-msg");
    const bubble = statusRow.querySelector(".keelie-bubble");
    if (bubble) bubble.classList.add("keelie-status-bubble");
  }

  function clearStatus() {
    if (statusRow) removeBubbleSmooth(statusRow);
    statusRow = null;
  }

  window.keelieShowStatus = showStatus;
  window.keelieClearStatus = clearStatus;

  // ==============================
  // Autosuggest (overlay; click sends)
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
    qTokens.forEach((t) => {
      if (iTokens.has(t)) overlap++;
    });

    return overlap > 0 ? 40 + overlap : 0;
  }

  // Hoisted => never "not defined"
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

  function acceptActiveSuggestAndSend() {
    if (!SUGGEST_ENABLED) return false;
    if (activeSuggestIndex < 0) return false;

    const chosen = currentSuggestItems[activeSuggestIndex];
    if (!chosen) return false;

    inputEl.value = chosen;
    hideSuggest();

    // Guaranteed send path
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

      // Use pointerdown so it works on mobile + doesn't blur input
      btn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        e.stopPropagation();

        inputEl.value = text;
        hideSuggest();

        // Guaranteed send path
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
    if (query.length < 2) {
      hideSuggest();
      return;
    }

    const ranked = SUGGESTIONS
      .map((item) => ({ item, s: scoreSuggestion(query, item) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 6)
      .map((x) => x.item);

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

  // Escape closes suggest first, then panel
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!panel.classList.contains("is-open")) return;

    if (panel.classList.contains("is-suggesting")) {
      hideSuggest();
      return;
    }
    closePanel();
  });

  // Click-away inside panel hides suggestions
  document.addEventListener("pointerdown", (e) => {
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

  async function doSend() {
    hideSuggest();

    if (!pythonReady || typeof window.keelieSend !== "function") {
      addBubble("Keelie", "I’m still loading… please try again in a moment.");
      return;
    }
    await window.keelieSend();
  }

  sendBtn.addEventListener("click", doSend);

  inputEl.addEventListener("input", () => updateSuggest());

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
        e.preventDefault();
        if (acceptActiveSuggestAndSend()) return;
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
  const loadingRow = addBubble("Keelie", "Loading assistant…");

  // ✅ Fade away after 3 seconds + smooth reflow
  setTimeout(() => {
    removeBubbleSmooth(loadingRow);
  }, 3000);

  const py = document.createElement("py-script");
  // bump this ?v= if you change python file
  py.setAttribute("src", `${BASE_PATH}/keelie_runtime.py?v=7`);
  document.body.appendChild(py);

  const failTimer = setTimeout(() => {
    if (!pythonReady) {
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
