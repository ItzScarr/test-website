// File: assets/keelie/keelie.js
import "https://pyscript.net/releases/2024.9.2/core.js";

const BASE_PATH = "assets/keelie";
const CONTACT_URL = "https://www.keeltoys.com/contact-us/";

// ------------------------------
// DOM helper
// ------------------------------
function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
// ==============================
// Privacy guard (pre-send)
// ==============================
function looksLikePersonalInfo(text) {
  if (!text) return false;

  // Email
  if (/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(text)) return true;

  // Phone (loose)
  if (/(?:(?:\+|00)\s?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d[\d\s-]{7,}\d/.test(text))
    return true;

  // Order / invoice refs (only if long digits + cue word)
  if (/\b(order|invoice|account|ref|reference|tracking|awb|consignment)\b/i.test(text)
      && /\b\d{6,}\b/.test(text))
    return true;

  return false;
}

function showPrivacyWarning() {
  window.keelieAddBubble(
    "Keelie",
    "For your privacy, please don’t share personal or account details here "
    + "(like email addresses, phone numbers, or order/invoice references).\n\n"
    + "Our customer service team can help securely via the Contact page."
  );
}


// ------------------------------
// Formatting helpers
// ------------------------------
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\'/g, "&#039;");
}
function linkify(safeHtmlText) {
  // Converts http(s) URLs into clickable links.
  // Input MUST already be escaped (so we’re not injecting user HTML).
  const urlRe = /\bhttps?:\/\/[^\s<]+/gi;

  return safeHtmlText.replace(urlRe, (url) => {
    // Trim common trailing punctuation that often follows URLs in sentences
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

  // ✅ clickable links (after escaping)
  safe = linkify(safe);

  // **bold**
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<span class="keelie-bold">$1</span>');

  // newlines
  safe = safe.replace(/\n/g, "<br>");

  return safe;
}


// Professional greeting HTML
function greetingHtml() {
  return `
    <div class="keelie-greet">
      <div class="keelie-greet-title">Hi — I’m <strong>Keelie</strong> 👋</div>
      <div class="keelie-greet-sub">I can help with orders, products, and stock codes.</div>

      <ul class="keelie-greet-list">
        <li><strong>Minimum order values</strong> (e.g. “minimum order value”)</li>
        <li><strong>Stock codes / SKUs</strong> (e.g. “stock code for Polar Bear Plush 20cm”)</li>
        <li><strong>Keeleco®</strong> sustainability & recycled materials</li>
        <li><strong>Delivery & tracking</strong> (e.g. “where is my order?”)</li>
        <li><strong>Invoices</strong> (e.g. “download an invoice”)</li>
      </ul>

      <div class="keelie-greet-footer">Start typing below — suggestions appear as you type.</div>
    </div>
  `;
}

function mountWidget() {
  // ------------------------------
  // UI
  // ------------------------------
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

        <a class="keelie-contact" href="${CONTACT_URL}" target="_blank" rel="noopener noreferrer">
          Contact
        </a>

        <button class="keelie-close" aria-label="Close chat">✕</button>
      </div>

      <div class="keelie-chat" id="keelie-chat"></div>

      <div class="keelie-footer">
        <!-- Autosuggest overlay (CSS positions it above input, overlapping chat) -->
        <div class="keelie-suggest" id="keelie-suggest" style="display:none;">
          <div class="keelie-suggest-list" id="keelie-suggest-list"></div>
        </div>

        <div class="keelie-row">
          <input class="keelie-input" id="keelie-text" placeholder="Type a message…" autocomplete="off" />
          <button class="keelie-send" id="keelie-send">Send</button>
        </div>

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

  // ------------------------------
  // FLIP animation helpers (smooth reflow)
  // ------------------------------
  function flipAnimate(mutator) {
    const items = Array.from(chatEl.querySelectorAll(".keelie-msg"));
    const first = new Map(items.map((n) => [n, n.getBoundingClientRect().top]));

    mutator();

    const items2 = Array.from(chatEl.querySelectorAll(".keelie-msg"));
    const last = new Map(items2.map((n) => [n, n.getBoundingClientRect().top]));

    items2.forEach((n) => {
      const dy = (first.get(n) ?? last.get(n)) - last.get(n);
      if (!dy) return;
      n.style.transform = `translateY(${dy}px)`;
      n.style.transition = "transform 0s";
      requestAnimationFrame(() => {
        n.style.transition = "";
        n.style.transform = "";
      });
    });
  }

  function removeBubbleSmooth(row) {
    if (!row || !row.parentNode) return;
    row.classList.add("is-leaving");
    setTimeout(() => {
      if (!row.parentNode) return;
      flipAnimate(() => row.remove());
    }, 230); // matches CSS ~220ms
  }

  // ------------------------------
  // Bubble creation (animated)
  // ------------------------------
  function appendBubbleNode(row) {
    flipAnimate(() => {
      chatEl.appendChild(row);
    });

    requestAnimationFrame(() => row.classList.remove("is-entering"));

    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function addBubble(who, text) {
    const row = document.createElement("div");
    row.className = `keelie-msg ${who === "You" ? "you" : "bot"} is-entering`;

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble";
    bubble.innerHTML = formatKeelie(text);

    row.appendChild(bubble);
    appendBubbleNode(row);
    return row;
  }

  // Expose to Python
  window.keelieAddBubble = addBubble;
  window.keelieGetInput = () => inputEl.value || "";
  window.keelieClearInput = () => { inputEl.value = ""; };

  // Status bubble hooks (optional for python)
  let statusRow = null;

  function showStatus(text) {
    if (statusRow) removeBubbleSmooth(statusRow);
    statusRow = addBubble("Keelie", text);
    statusRow.classList.add("keelie-status-msg");
    const b = statusRow.querySelector(".keelie-bubble");
    if (b) b.classList.add("keelie-status-bubble");
  }

  function clearStatus() {
    if (statusRow) removeBubbleSmooth(statusRow);
    statusRow = null;
  }

  window.keelieShowStatus = showStatus;
  window.keelieClearStatus = clearStatus;

  // ------------------------------
  // Autosuggest (overlay, click-to-send)
  // ------------------------------
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

  function norm(s) { return String(s || "").toLowerCase().trim(); }

  function scoreSuggestion(query, item) {
    const q = norm(query);
    const it = norm(item);
    if (!q) return 0;
    if (it.startsWith(q)) return 100;
    if (it.includes(q)) return 70;

    const qTokens = new Set(q.split(/\s+/).filter(Boolean));
    const iTokens = new Set(it.split(/\s+/).filter(Boolean));
    let overlap = 0;
    qTokens.forEach((t) => { if (iTokens.has(t)) overlap++; });
    return overlap > 0 ? (40 + overlap) : 0;
  }

  // function declaration => hoisted (never "not defined")
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
    children.forEach((node, i) => {
      node.classList.toggle("is-active", i === activeSuggestIndex);
    });
  }

  function acceptHighlightedAndSend() {
    if (!SUGGEST_ENABLED) return false;
    if (activeSuggestIndex < 0) return false;

    const chosen = currentSuggestItems[activeSuggestIndex];
    if (!chosen) return false;

    inputEl.value = chosen;
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

    items.forEach((text) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "keelie-suggest-item";
      btn.textContent = text;

      // pointerdown = reliable + avoids blur
      btn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        inputEl.value = text;
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

  // ------------------------------
  // Panel open/close
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
    clearStatus();
    if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
  }

  launcher.addEventListener("click", () => {
    panel.classList.contains("is-open") ? closePanel() : openPanel();
  });
  closeBtn.addEventListener("click", closePanel);

  // Escape: hide suggest first, then close panel
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!panel.classList.contains("is-open")) return;

    if (panel.classList.contains("is-suggesting")) {
      hideSuggest();
      return;
    }
    closePanel();
  });

  // click-away hides suggestions
  document.addEventListener("pointerdown", (e) => {
    if (!SUGGEST_ENABLED) return;
    if (!panel.contains(e.target)) return;
    if (e.target === inputEl) return;
    if (suggestWrap.contains(e.target)) return;
    hideSuggest();
  });

  // ------------------------------
  // Send flow
  // ------------------------------
  let pythonReady = false;

  async function doSend() {
    hideSuggest();

    const msg = (inputEl.value || "").trim();
    if (!msg) return;

    // 🔐 Privacy prevention — stop before sending
    if (looksLikePersonalInfo(msg)) {
      inputEl.value = "";
      showPrivacyWarning();
      return;
    }

    if (!pythonReady || typeof window.keelieSend !== "function") {
      addBubble("Keelie", "I’m still loading… please try again in a moment.");
      return;
    }

    await window.keelieSend();
  }

  sendBtn.addEventListener("click", doSend);

  inputEl.addEventListener("input", () => updateSuggest());

  inputEl.addEventListener("keydown", (e) => {
    // suggestions open: arrows + enter accept/send
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
        if (acceptHighlightedAndSend()) return;
        doSend();
        return;
      }
    }

    if (e.key === "Enter") {
      e.preventDefault();
      doSend();
    }
  });

  // ------------------------------
  // Boot + Python runtime
  // ------------------------------
  const loadingRow = addBubble("Keelie", "Loading assistant…");

  // fade away after 3 seconds + smooth reflow
  setTimeout(() => removeBubbleSmooth(loadingRow), 3000);

  const py = document.createElement("py-script");
  py.setAttribute("src", `${BASE_PATH}/keelie_runtime.py?v=7`); // bump if you edit python
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

      // Add a rich greeting bubble (more professional than plain text)
      const row = document.createElement("div");
      row.className = "keelie-msg bot is-entering";

      const bubble = document.createElement("div");
      bubble.className = "keelie-bubble keelie-bubble-greeting";
      bubble.innerHTML = greetingHtml();

      row.appendChild(bubble);
      appendBubbleNode(row);
    }
  }, 250);
}

mountWidget();
