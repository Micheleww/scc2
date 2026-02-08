const DEFAULTS = {
  endpoint: "http://localhost:8787/intake/directive",
  auth_token: "",
  autosend: false
};

async function load() {
  const settings = await chrome.storage.sync.get(DEFAULTS);
  document.getElementById("endpoint").value = settings.endpoint || DEFAULTS.endpoint;
  document.getElementById("token").value = settings.auth_token || "";
  document.getElementById("autosend").checked = !!settings.autosend;
}

function setStatus(text) {
  const el = document.getElementById("status");
  el.textContent = text || "";
}

document.getElementById("saveBtn").addEventListener("click", async () => {
  setStatus("Saving…");
  const endpoint = document.getElementById("endpoint").value.trim() || DEFAULTS.endpoint;
  const auth_token = document.getElementById("token").value.trim();
  const autosend = !!document.getElementById("autosend").checked;
  await chrome.storage.sync.set({ endpoint, auth_token, autosend });
  setStatus("Saved");
  setTimeout(() => setStatus(""), 1200);
});

load();

