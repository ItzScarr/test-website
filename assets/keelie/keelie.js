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
    .replace(/'/g, "&#039;");
}

function linkify(s) {
  const safe = escapeHtml(s);
  return safe.replace(
    /(https?:\/\/[^\s<]+)/g,
    `<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>`
  );
}

function formatMessage(text) {
  const safe = String(text ?? "");
  // **bold**
  const bolded = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // URLs
  const withLinks = linkify(bolded);
  // newlines
  return withLinks.replace(/\n/g, "<br>");
}

function nowTime() {
  const d = new Date();
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function isMobile() {
  return window.matchMedia && window.matchMedia("(max-width: 520px)").matches;
}

function createWidget() {
  const launcher = el(`
    <button class="keelie-launcher" type="button" aria-label="Open chat">
      <span class="keelie-launcher-icon" aria-hidden="true">💬</span>
      <span class="keelie-launcher-dot" aria-hidden="true"></span>
    </button>
  `);

  const panel = el(`
    <div class="keelie-panel" role="dialog" aria-label="Keelie chat">
      <div class="keelie-header">
        <div class="keelie-title">
          <div class="keelie-title-name">Keelie</div>
          <div class="keelie-title-sub">Keel Toys assistant</div>
        </div>
        <button class="keelie-close" type="button" aria-label="Close chat">×</button>
      </div>

      <div class="keelie-body" id="keelie-body"></div>

      <div class="keelie-suggest" id="keelie-suggest" style="display:none">
        <div class="keelie-suggest-label">Suggestions</div>
        <div class="keelie-suggest-list" id="keelie-suggest-list" role="listbox"></div>
      </div>

      <div class="keelie-footer">
        <input class="keelie-input" id="keelie-input" type="text" placeholder="Ask a question…" autocomplete="off" />
        <button class="keelie-send" id="keelie-send" type="button">Send</button>
      </div>
      <div class="keelie-note">
        Please don’t share personal details (order numbers, invoices, phone, email) in chat.
      </div>
    </div>
  `);

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  const body = panel.querySelector("#keelie-body");
  const inputEl = panel.querySelector("#keelie-input");
  const sendBtn = panel.querySelector("#keelie-send");
  const closeBtn = panel.querySelector(".keelie-close");

  function scrollToBottom() {
    body.scrollTop = body.scrollHeight;
  }

  function addBubble(text, who = "bot", opts = {}) {
    const wrap = document.createElement("div");
    wrap.className = `keelie-msg keelie-msg--${who}`;

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble";
    bubble.innerHTML = formatMessage(text);

    const meta = document.createElement("div");
    meta.className = "keelie-meta";
    meta.textContent = opts.time ?? nowTime();

    wrap.appendChild(bubble);
    wrap.appendChild(meta);
    body.appendChild(wrap);

    scrollToBottom();
    return wrap;
  }

  function addTyping() {
    const wrap = document.createElement("div");
    wrap.className = "keelie-msg keelie-msg--bot";
    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble keelie-bubble--typing";
    bubble.innerHTML = `
      <span class="keelie-typing">
        <span></span><span></span><span></span>
      </span>
    `;
    wrap.appendChild(bubble);
    body.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function removeNode(node) {
    if (node && node.parentNode) node.parentNode.removeChild(node);
  }

  // ---- feedback (unchanged behaviour) ----
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

    body.appendChild(row);
    scrollToBottom();
  }

  // ---- suggestion / typeahead (OPTION B) ----
  const suggestWrap = panel.querySelector("#keelie-suggest");
  const suggestList = panel.querySelector("#keelie-suggest-list");
  const SUGGEST_ENABLED = !!(suggestWrap && suggestList);

  // Static suggestions are "what can I ask?" prompts.
  // Product-name autocomplete is built from stock_codes.xlsx via keelie_stock_loader.js.
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

  /**
   * In-memory index of products for typeahead.
   * Populated once window.keelieStockReady resolves.
   */
  let STOCK_INDEX = [];
  let STOCK_READY = false;

  function norm(s) {
    return String(s || "").toLowerCase().trim();
  }

  function buildStockIndex(rows) {
    const out = [];
    const seen = new Set();

    (rows || []).forEach((r) => {
      const name = String(r?.product_name || "").trim();
      if (!name) return;

      const key = norm(name);
      if (!key || seen.has(key)) return;
      seen.add(key);

      out.push({
        name,
        nameLower: key,
        code: String(r?.stock_code || "").trim()
      });
    });

    // Small stability improvement: keep a deterministic order.
    out.sort((a, b) => a.nameLower.localeCompare(b.nameLower));
    return out;
  }

  // Best-effort: hook into the loader promise if present.
  // (keelie_stock_loader.js sets window.keelieStockRows and window.keelieStockReady)
  try {
    const maybePromise = window.keelieStockReady;
    if (maybePromise && typeof maybePromise.then === "function") {
      maybePromise
        .then((rows) => {
          STOCK_INDEX = buildStockIndex(rows || window.keelieStockRows || []);
          STOCK_READY = true;
          // If the user is typing when stock finishes loading, refresh suggestions.
          setTimeout(() => updateSuggest(), 0);
        })
        .catch(() => {
          STOCK_READY = false;
          STOCK_INDEX = [];
        });
    } else if (Array.isArray(window.keelieStockRows)) {
      STOCK_INDEX = buildStockIndex(window.keelieStockRows);
      STOCK_READY = true;
    }
  } catch (_) {
    // ignore
  }

  function scoreTextMatch(query, candidate) {
    const q = norm(query);
    const c = norm(candidate);
    if (!q) return 0;

    // Strong signals.
    if (c === q) return 1000;
    if (c.startsWith(q)) return 800;
    const idx = c.indexOf(q);
    if (idx >= 0) return 650 - Math.min(idx, 60); // earlier occurrence = better

    // Token overlap (weak fuzzy).
    const qTokens = q.split(/\s+/).filter(Boolean);
    const cTokens = new Set(c.split(/\s+/).filter(Boolean));
    let overlap = 0;
    qTokens.forEach((t) => {
      if (cTokens.has(t)) overlap++;
    });

    return overlap > 0 ? (300 + overlap) : 0;
  }

  function extractProductQuery(rawInput) {
    const q = String(rawInput || "").trim();
    if (!q) return "";

    // If they’re already asking "stock code for ...", match on the tail.
    const m = q.match(/stock\s*code\s*(?:for|of)\s*(.+)$/i);
    if (m && m[1]) return m[1].trim();

    // Otherwise, just use their current text.
    return q;
  }

  function topProductSuggestions(rawInput, limit = 6) {
    if (!STOCK_READY || !STOCK_INDEX.length) return [];

    const q = extractProductQuery(rawInput);
    if (q.length < 2) return [];

    // Avoid running product search when user is clearly asking a non-product question.
    // (Very light heuristic: questions starting with these words are usually FAQs.)
    const qLower = norm(rawInput);
    const looksLikeFAQ =
      /^(what|where|when|how|why|do you|can you|is there|tell me)\b/.test(qLower) &&
      !/stock\s*code|sku|product/.test(qLower);

    if (looksLikeFAQ) return [];

    const ranked = STOCK_INDEX
      .map((p) => ({ p, s: scoreTextMatch(q, p.nameLower) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, limit);

    // Render as "real" autocomplete: selecting inserts an exact product name.
    return ranked.map(({ p }) => ({
      kind: "product",
      label: p.name,
      value: `What’s the stock code for ${p.name}?`
    }));
  }

  function topStaticSuggestions(rawInput, limit = 6) {
    const query = String(rawInput || "").trim();
    if (query.length < 2) return [];

    const ranked = STATIC_SUGGESTIONS
      .map((item) => ({ item, s: scoreTextMatch(query, item) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, limit)
      .map((x) => ({ kind: "static", label: x.item, value: x.item }));

    return ranked;
  }

  let activeSuggestIndex = -1;
  /** @type {{kind: "static"|"product", label: string, value: string}[]} */
  let currentSuggestItems = [];

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

    items.forEach((sugg) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "keelie-suggest-item";
      btn.textContent = sugg.label;

      btn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        inputEl.value = sugg.value;
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

    if (raw.length < 2) {
      hideSuggest();
      return;
    }

    // Prefer product autocomplete when it matches, otherwise fall back to static prompts.
    // If stock isn't ready yet, this gracefully becomes static-only.
    const product = topProductSuggestions(raw, 6);
    const statics = topStaticSuggestions(raw, 6);

    // If we have product matches, show them first, then a few static prompts if space.
    const merged = product.concat(statics).slice(0, 6);

    renderSuggest(merged);
  }

  // ---- open/close behaviour ----
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
        const next = clamp(activeSuggestIndex + 1, 0, count - 1);
        setActiveSuggest(next);
      } else if (e.key === "ArrowUp" && count > 0) {
        e.preventDefault();
        const next = clamp(activeSuggestIndex - 1, 0, count - 1);
        setActiveSuggest(next);
      } else if (e.key === "Enter") {

        if (acceptActiveSuggest()) {
          e.preventDefault();
          return;
        }
      }
    }
  });

  inputEl.addEventListener("input", () => {
    updateSuggest();
  });

  inputEl.addEventListener("blur", () => {
    setTimeout(() => {
      if (document.activeElement && suggestWrap.contains(document.activeElement)) return;
      hideSuggest();
    }, 120);
  });

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

  // Expose UI hooks for Python
  window.keelieAddBubble = (text, who = "bot") => addBubble(text, who);
  window.keelieTypingStart = () => addTyping();
  window.keelieTypingStop = (node) => removeNode(node);

  // ---- send flow ----
  async function handleSend() {
    const msg = (inputEl.value || "").trim();
    if (!msg) return;

    if (!canSend()) {
      addBubble("You’re sending messages very quickly — please wait a moment and try again.", "bot");
      setInputDisabled(true);
      setTimeout(() => setInputDisabled(false), Math.max(0, lockUntil - Date.now()));
      return;
    }

    recordSend();
    hideSuggest();

    addBubble(msg, "user");
    inputEl.value = "";
    setInputDisabled(true);

    try {
      if (typeof window.keelieSend === "function") {
        const reply = await window.keelieSend(msg);
        if (reply) {
          addBubble(reply, "bot");
          if (shouldAskFeedback(reply)) addFeedbackRow();
        }
      } else {
        addBubble(
          "The assistant isn’t ready yet. Please try again in a moment — or contact us at " + CONTACT_URL,
          "bot"
        );
      }
    } catch (err) {
      addBubble(
        "Sorry — something went wrong. Please try again, or contact us at " + CONTACT_URL,
        "bot"
      );
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

  // ---- boot ----
  addBubble("Loading assistant…", "bot", { time: "" });
  ensurePyScriptLoaded();

  waitForBrain()
    .then(() => {
      addBubble("Hi! I’m Keelie — ask me about MOQ, Keeleco, deliveries, invoices, or stock codes.", "bot");
    })
    .catch(() => {
      addBubble(
        "I couldn’t load the assistant. Please refresh, or contact us at " + CONTACT_URL,
        "bot"
      );
    });
}

// mount
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", createWidget);
} else {
  createWidget();
}
