import "https://pyscript.net/releases/2024.9.2/core.js";

const BASE_PATH = "/assets/keelie"; // change if you host elsewhere

function mountWidget() {
  const host = document.getElementById("keelie-widget");
  if (!host) return;

  host.innerHTML = `
    <div class="keelie-card">
      <div class="keelie-header">Keelie (Keel Toys)</div>
      <div class="keelie-chat" id="keelie-chat"></div>
      <div class="keelie-row">
        <input class="keelie-input" id="keelie-text" placeholder="Type a message…" />
        <button class="keelie-btn" id="keelie-send">Send</button>
      </div>
    </div>
  `;

  const chatEl = host.querySelector("#keelie-chat");
  const inputEl = host.querySelector("#keelie-text");
  const sendBtn = host.querySelector("#keelie-send");

  window.keelieAddMessage = (who, text) => {
    const div = document.createElement("div");
    div.className = "keelie-msg";
    div.innerHTML = `<span class="keelie-name">${who}:</span><pre>${text}</pre>`;
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
  };

  sendBtn.addEventListener("click", () => window.keelieSend?.());
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") window.keelieSend?.();
  });

  // Load Python logic once via PyScript
  const py = document.createElement("py-script");
  py.setAttribute("src", `${BASE_PATH}/keelie_runtime.py`);
  document.body.appendChild(py);

  window.keelieAddMessage("Keelie", "Hello! 👋 How can I help you?");
}

mountWidget();
