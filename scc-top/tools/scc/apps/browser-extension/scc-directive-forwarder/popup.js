const DEFAULTS = {
  endpoint: "http://localhost:8787/intake/directive",
  auth_token: "",
  autosend: false
};

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function getSettings() {
  return await chrome.storage.sync.get(DEFAULTS);
}

function setStatus(kind, text) {
  const dot = document.getElementById("statusDot");
  const label = document.getElementById("statusText");
  dot.classList.remove("ok", "bad");
  if (kind === "ok") dot.classList.add("ok");
  if (kind === "bad") dot.classList.add("bad");
  label.textContent = text;
}

function showError(message) {
  const el = document.getElementById("errorText");
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = message;
}

function buildPayload(directives) {
  const nowIso = new Date().toISOString();
  const pageUrl = directives[0]?.page_url || "";
  const capturedAt = directives[0]?.captured_at || nowIso;
  return {
    source: "chatgpt_extension",
    page_url: pageUrl,
    captured_at: capturedAt,
    directives: directives.map((d) => d.parsed)
  };
}

async function refresh() {
  showError("");
  setStatus("", "Detecting…");

  const settings = await getSettings();
  document.getElementById("endpointText").textContent = settings.endpoint;
  document.getElementById("autosendToggle").checked = !!settings.autosend;

  const tab = await getActiveTab();
  if (!tab?.id || !tab.url?.startsWith("https://chatgpt.com/")) {
    setStatus("bad", "Open chatgpt.com");
    document.getElementById("sendBtn").disabled = true;
    document.getElementById("copyBtn").disabled = true;
    return { directives: [] };
  }

  let resp;
  try {
    resp = await chrome.tabs.sendMessage(tab.id, { action: "SCC_GET_LATEST_DIRECTIVES" });
  } catch (e) {
    setStatus("bad", "No content script");
    showError(String(e?.message || e));
    document.getElementById("sendBtn").disabled = true;
    document.getElementById("copyBtn").disabled = true;
    return { directives: [] };
  }

  const directives = resp?.directives || [];
  const errors = resp?.errors || [];

  if (directives.length > 0) setStatus("ok", `Detected ${directives.length}`);
  else setStatus("", "Detected 0");

  if (errors.length > 0) showError(errors.map((x) => `${x.type}: ${x.error}`).join("\n"));

  document.getElementById("sendBtn").disabled = directives.length === 0;
  document.getElementById("copyBtn").disabled = directives.length === 0;

  return { directives };
}

document.getElementById("optionsLink").addEventListener("click", async (e) => {
  e.preventDefault();
  await chrome.runtime.openOptionsPage();
});

document.getElementById("autosendToggle").addEventListener("change", async (e) => {
  await chrome.storage.sync.set({ autosend: !!e.target.checked });
});

document.getElementById("copyBtn").addEventListener("click", async () => {
  const { directives } = await refresh();
  const payload = buildPayload(directives);
  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  setStatus("ok", "Copied payload");
});

document.getElementById("sendBtn").addEventListener("click", async () => {
  const { directives } = await refresh();
  const payload = buildPayload(directives);

  setStatus("", "Sending…");
  showError("");
  const resp = await chrome.runtime.sendMessage({ action: "SCC_POST_PAYLOAD", payload });
  if (resp?.ok) setStatus("ok", `Sent (${resp.status})`);
  else {
    setStatus("bad", "Send failed");
    showError(resp?.error || "Unknown error");
  }
});

refresh();

