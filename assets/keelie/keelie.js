import "https://pyscript.net/releases/2024.9.2/core.js";

const BASE_PATH = "assets/keelie";

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
  // Escape first (security), then allow limited formatting
  let safe = escapeHtml(text);

  // Bold: **text**
  safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Newlines -> <br>
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
    <div class="keelie-panel" role="dialog" aria-label="Keelie chat">
      <div class="keelie-header">
        <div class="keelie-badge">K</div>
        <div class="keelie-title">
          <strong>Keelie</strong>
          <span>Keel Toys assistant</span>
        </div>
        <button class="keelie-close" aria-label="Close chat">✕</button>
      </div>

      <div class="keelie-chat" id="keelie-chat"></div>

      <div class="keelie-footer">
        <div class="keelie-row">
          <input class="keelie-input" id="keelie-text" placeholder="Type a message…" autocomplete="off" />
          <button class="keelie-send" id="keelie-send">Send</button>
        </div>
        <div class="keelie-typing" id="keelie-typing" style="display:none;">Keelie is typing…</div>
      </div>
    </div>
  `);

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  const chatEl = panel.querySelector("#keelie-chat");
  const inputEl = panel.querySelector("#keelie-text");
  const sendBtn = panel.querySelector("#keelie-send");
  const closeBtn = panel.querySelector(".keelie-close");
  const typingEl = panel.querySelector("#keelie-typing");

  // ==============================
  // Chat bubble rendering
  // ==============================
  function addBubble(who, text) {
    const div = document.createElement("div");
    div.className = `keelie-msg ${who === "You" ? "you" : "bot"}`;

    const bubble = document.createElement("div");
    bubble.className = "keelie-bubble";

    // ✅ Render limited formatting
    bubble.innerHTML = formatKeelie(text);

    div.appendChild(bubble);
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  // expose UI helpers to Python
  window.keelieAddBubble = addBubble;
  window.keelieSetTyping = (on) => { typingEl.style.display = on ? "block" : "none"; };
  window.keelieGetInput = () => inputEl.value || "";
  window.keelieClearInput = () => { inputEl.value = ""; };

  function openPanel(){ panel.classList.add("is-open"); inputEl.focus(); }
  function closePanel(){ panel.classList.remove("is-open"); }

  launcher.addEventListener("click", () => {
    panel.classList.contains("is-open") ? closePanel() : openPanel();
  });
  closeBtn.addEventListener("click", closePanel);

  async function doSend(){
    if (typeof window.keelieSend !== "function") {
      addBubble("Keelie", "I’m still loading… try again in a moment.");
      return;
    }
    await window.keelieSend();
  }

  sendBtn.addEventListener("click", doSend);
  inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter") doSend(); });

  // load python runtime
  const py = document.createElement("py-script");
  py.setAttribute("src", `${BASE_PATH}/keelie_runtime.py`);
  document.body.appendChild(py);

  // greeting
  addBubble("Keelie", "Hello! 👋 I’m Keelie. How can I help you today?");
}

mountWidget();
