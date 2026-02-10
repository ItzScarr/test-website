import "https://pyscript.net/releases/2024.9.2/core.js";

const BASE_PATH = "assets/keelie";
const CONTACT_URL = "https://www.keeltoys.com/contact-us/";

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\\\'/g, "&#039;");
}

function linkify(safeHtmlText) {
  const urlRe = /\bhttps?:\/\/[^\s<]+/gi;
  return safeHtmlText.replace(urlRe, (url) => {
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
  safe = linkify(safe);
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<span class="keelie-bold">$1</span>');
  safe = safe.replace(/\n/g, "<br>");
  return safe;
}

function mountWidget() {
  const launcher = el(`
    <button class="keelie-launcher" aria-label="Open chat">
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
        <path fill="currentColor" d="M20 2H4a2 2 0 0 0-2 2v15.586A1.5 1.5 0 0 0 4.56 20.66L7.2 18H20a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2Zm0 14H6.38l-2.38 2.4V4h16v12Z"/>
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

        <div class="keelie-disclaimer">
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

  function addBubble(who, text) {
    const row = document.createElement("div");
    row.className = `keelie-msg ${who === "You" ? "user" : "bot"}`;

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble";
    bubble.innerHTML = formatKeelie(text);

    row.appendChild(bubble);
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  window.keelieAddBubble = addBubble;
  window.keelieGetInput = () => inputEl.value || "";
  window.keelieClearInput = () => {
    inputEl.value = "";
  };

  let statusBubble = null;

  function showStatus(text) {
    clearStatus();
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

  function clearStatus() {
    if (statusBubble && statusBubble.parentNode) {
      statusBubble.parentNode.removeChild(statusBubble);
    }
    statusBubble = null;
  }

  window.keelieShowStatus = showStatus;
  window.keelieClearStatus = clearStatus;

  // --- Helpful feedback row (kept) ---
  function addFeedbackRow() {
    const row = document.createElement("div");
    row.className = "keelie-feedback";
    row.innerHTML = `
      <span class="keelie-feedback-label">Helpful?</span>
      <button type="button" class="keelie-feedback-btn" data-v="up" aria-label="Helpful">👍</button>
      <button type="button" class="keelie-feedback-btn" data-v="down" aria-label="Not helpful">👎</button>
    `;

    row.addEventListener("click", (e) => {
      const btn = e.target.closest(".keelie-feedback-btn");
      if (!btn) return;
      const v = btn.getAttribute("data-v");

      const key = "keelieFeedbackCounts";
      const raw = localStorage.getItem(key);
      const obj = raw ? JSON.parse(raw) : { up: 0, down: 0 };
      if (v === "up") obj.up++;
      if (v === "down") obj.down++;
      localStorage.setItem(key, JSON.stringify(obj));

      row.innerHTML = `<span class="keelie-feedback-label">Thanks!</span>`;
    });

    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function shouldAskFeedback(text) {
    const t = String(text || "").toLowerCase();
    return (
      t.includes("stock code") ||
      t.includes("sku") ||
      t.includes("minimum order") ||
      t.includes("moq") ||
      t.includes("invoice") ||
      t.includes("track") ||
      t.includes("delivery")
    );
  }

  // ------------------------------
  // Suggestions: Option B Autocomplete
  // ------------------------------

  const suggestWrap = panel.querySelector("#keelie-suggest");
  const suggestList = panel.querySelector("#keelie-suggest-list");
  const SUGGEST_ENABLED = !!(suggestWrap && suggestList);

  const STATIC_SUGGESTIONS = [
    "What’s the minimum order value?",
    "What’s the minimum value?",
    "What is your MOQ?",
    "Where are your toys produced?",
    "Tell me about Keeleco and recycled materials",
    "How do I find a stock code / SKU?",
    "Where is my order?",
    "How do I track my order?",
    "How do I download an invoice?",
    "What are your opening hours?",
    "How do I contact customer service?"
  ];

  let activeSuggestIndex = -1;
  /** @type {{label:string,value:string,kind:"static"|"product"}[]} */
  let currentSuggestItems = [];

  function norm(s) {
    return String(s || "").toLowerCase().trim();
  }

  function scoreSuggestion(query, item) {
    const q = norm(query);
    const it = norm(item);
    if (!q) return 0;

    if (it === q) return 120;
    if (it.startsWith(q)) return 100;
    if (it.includes(q)) return 70;

    const qTokens = new Set(q.split(/\s+/).filter(Boolean));
    const iTokens = new Set(it.split(/\s+/).filter(Boolean));
    let overlap = 0;
    qTokens.forEach((t) => {
      if (iTokens.has(t)) overlap++;
    });

    return overlap > 0 ? (40 + overlap) : 0;
  }

  // --- Stock-backed product autocomplete ---
  let STOCK_INDEX = [];
  let STOCK_READY = false;

  function buildStockIndex(rows) {
    const out = [];
    const seen = new Set();
    (rows || []).forEach((r) => {
      const name = String(r?.product_name || "").trim();
      if (!name) return;
      const key = norm(name);
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push({ name, nameLower: key });
    });
    out.sort((a, b) => a.nameLower.localeCompare(b.nameLower));
    return out;
  }

  function initStockIndex() {
    try {
      const p = window.keelieStockReady;
      if (p && typeof p.then === "function") {
        p.then((rows) => {
          STOCK_INDEX = buildStockIndex(rows || window.keelieStockRows || []);
          STOCK_READY = STOCK_INDEX.length > 0;
          setTimeout(() => updateSuggest(), 0);
        }).catch(() => {
          STOCK_READY = false;
          STOCK_INDEX = [];
        });
        return;
      }
      if (Array.isArray(window.keelieStockRows)) {
        STOCK_INDEX = buildStockIndex(window.keelieStockRows);
        STOCK_READY = STOCK_INDEX.length > 0;
      }
    } catch (_) {
      STOCK_READY = false;
      STOCK_INDEX = [];
    }
  }

  initStockIndex();

  function extractProductQuery(rawInput) {
    const q = String(rawInput || "").trim();
    if (!q) return "";
    const m = q.match(/stock\s*code\s*(?:for|of)\s*(.+)$/i);
    if (m && m[1]) return m[1].trim();
    const m2 = q.match(/sku\s*(?:for|of)\s*(.+)$/i);
    if (m2 && m2[1]) return m2[1].trim();
    return q;
  }

  function shouldShowProductSuggest(rawInput) {
    const t = norm(rawInput);
    if (/\b(stock\s*code|sku|product\s*code|item\s*code)\b/i.test(t)) return true;
    if (/^(what|where|when|how|why|do you|can you|is there|tell me)\b/i.test(t)) return false;
    return true;
  }

  function topProductSuggestions(rawInput, limit = 6) {
    if (!STOCK_READY || !STOCK_INDEX.length) return [];
    if (!shouldShowProductSuggest(rawInput)) return [];

    const q = extractProductQuery(rawInput);
    if (q.length < 2) return [];

    return STOCK_INDEX
      .map((p) => ({ p, s: scoreSuggestion(q, p.nameLower) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, limit)
      .map((x) => ({
        kind: "product",
        label: x.p.name,
        value: `What’s the stock code for ${x.p.name}?`
      }));
  }

  function topStaticSuggestions(rawInput, limit = 6) {
    const query = (rawInput || "").trim();
    if (query.length < 2) return [];

    return STATIC_SUGGESTIONS
      .map((item) => ({ item, s: scoreSuggestion(query, item) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, limit)
      .map((x) => ({ kind: "static", label: x.item, value: x.item }));
  }

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

    inputEl.value = chosen.value;
    hideSuggest();

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

    items.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "keelie-suggest-item";
      btn.textContent = item.label;

      btn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        inputEl.value = item.value;
        hideSuggest();
        setTimeout(() => sendBtn.click(), 0);
      });

      suggestList.appendChild(btn);
    });

    suggestWrap.style.display = "block";
    panel.classList.add("is-suggesting");
  }

  function updateSuggest() {
    if (!SUGGEST_ENABLED) return;

    const raw = (inputEl.value || "").trim();

    // Only show suggestions while typing.
    if (raw.length < 2) {
      hideSuggest();
      return;
    }

    const products = topProductSuggestions(raw, 6);
    const items = (products.length ? products : topStaticSuggestions(raw, 6)).slice(0, 6);
    renderSuggest(items);
  }

  // ------------------------------
  // Open / close behaviour + keyboard
  // ------------------------------

  let lastFocused = null;

  function openPanel() {
    lastFocused = document.activeElement;
    panel.classList.add("is-open");
    inputEl.focus();
  }

  function closePanel() {
    panel.classList.remove("is-open");
    hideSuggest();
    if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
  }

  launcher.addEventListener("click", () => {
    if (panel.classList.contains("is-open")) closePanel();
    else openPanel();
  });

  closeBtn.addEventListener("click", closePanel);

  document.addEventListener("keydown", (e) => {
    if (!panel.classList.contains("is-open")) return;

    if (e.key === "Escape") {
      e.preventDefault();
      closePanel();
      return;
    }

    if (!SUGGEST_ENABLED) return;

    if (panel.classList.contains("is-suggesting")) {
      const count = currentSuggestItems.length;

      if (e.key === "ArrowDown" && count > 0) {
        e.preventDefault();
        const next = Math.min(activeSuggestIndex + 1, count - 1);
        setActiveSuggest(next);
      } else if (e.key === "ArrowUp" && count > 0) {
        e.preventDefault();
        const next = Math.max(activeSuggestIndex - 1, 0);
        setActiveSuggest(next);
      } else if (e.key === "Enter") {
        if (acceptActiveSuggest()) {
          e.preventDefault();
          return;
        }
      }
    }
  });

  inputEl.addEventListener("input", () => updateSuggest());

  inputEl.addEventListener("blur", () => {
    setTimeout(() => {
      if (document.activeElement && suggestWrap.contains(document.activeElement)) return;
      hideSuggest();
    }, 120);
  });

  // ------------------------------
  // Sending + rate limiting (kept)
  // ------------------------------

  const SEND_WINDOW_MS = 8000;
  const SEND_MAX_IN_WINDOW = 4;
  let sendTimestamps = [];
  let lockUntil = 0;

  function canSend() {
    const now = Date.now();
    if (now < lockUntil) return false;

    sendTimestamps = sendTimestamps.filter((t) => now - t < SEND_WINDOW_MS);
    if (sendTimestamps.length >= SEND_MAX_IN_WINDOW) {
      lockUntil = now + 2500;
      return false;
    }
    return true;
  }

  function recordSend() {
    sendTimestamps.push(Date.now());
  }

  function setInputDisabled(disabled) {
    inputEl.disabled = disabled;
    sendBtn.disabled = disabled;
    panel.classList.toggle("is-busy", !!disabled);
  }

  function ensurePyScriptLoaded() {
    if (document.querySelector('py-script[src*="keelie_runtime.py"]')) return;
    const py = document.createElement("py-script");
    py.setAttribute("src", `${BASE_PATH}/keelie_runtime.py`);
    document.body.appendChild(py);
  }

  function waitForBrain(timeoutMs = 10000) {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      const tick = () => {
        if (typeof window.keelieSend === "function") return resolve(true);
        if (Date.now() - start > timeoutMs) return reject(new Error("timeout"));
        setTimeout(tick, 120);
      };
      tick();
    });
  }

  async function handleSend() {
    const msg = (inputEl.value || "").trim();
    if (!msg) return;

    if (!canSend()) {
      addBubble("Keelie", "You’re sending messages very quickly — please wait a moment and try again.");
      setInputDisabled(true);
      setTimeout(() => setInputDisabled(false), Math.max(0, lockUntil - Date.now()));
      return;
    }

    recordSend();
    hideSuggest();

    // NOTE: Python reads from window.keelieGetInput().
    // Keep the input value until Python reads it.
    addBubble("You", msg);

    setInputDisabled(true);

    try {
      if (typeof window.keelieSend === "function") {
        await window.keelieSend();
      } else {
        addBubble(
          "Keelie",
          "The assistant isn’t ready yet. Please try again in a moment — or contact us at " + CONTACT_URL
        );
      }
    } catch (_) {
      addBubble("Keelie", "Sorry — something went wrong. Please try again, or contact us at " + CONTACT_URL);
    } finally {
      setInputDisabled(false);
      inputEl.focus();
    }
  }

  sendBtn.addEventListener("click", handleSend);

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  });

  // Boot
  addBubble("Keelie", "Loading assistant…");
  ensurePyScriptLoaded();

  waitForBrain()
    .then(() => {
      addBubble(
        "Keelie",
        "Hi! I’m Keelie — ask me about MOQ, Keeleco, deliveries, invoices, or stock codes (e.g. *What’s the stock code for [product name]?*)."
      );
    })
    .catch(() => {
      addBubble("Keelie", "I couldn’t load the assistant. Please refresh, or contact us at " + CONTACT_URL);
    });

  // Add feedback after bot messages (kept)
  const origAddBubble = window.keelieAddBubble;
  window.keelieAddBubble = (who, text) => {
    origAddBubble(who, text);
    if (who === "Keelie" && shouldAskFeedback(text)) addFeedbackRow();
  };
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountWidget);
} else {
  mountWidget();
}
