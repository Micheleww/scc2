const DEFAULTS = {
  endpoint: "http://localhost:8787/intake/directive",
  auth_token: "",
  autosend: false
};

async function getSettings() {
  return await chrome.storage.sync.get(DEFAULTS);
}

async function ensureDefaultsOnInstall() {
  const existing = await chrome.storage.sync.get(null);
  const updates = {};
  if (typeof existing.endpoint !== "string") updates.endpoint = DEFAULTS.endpoint;
  if (typeof existing.auth_token !== "string") updates.auth_token = DEFAULTS.auth_token;
  if (typeof existing.autosend !== "boolean") updates.autosend = DEFAULTS.autosend;
  if (Object.keys(updates).length > 0) await chrome.storage.sync.set(updates);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function postJsonWithRetry(endpoint, payload, authToken, maxRetries) {
  let lastErr = null;
  const attempts = 1 + Math.max(0, maxRetries || 0);

  for (let i = 0; i < attempts; i++) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12_000);
    try {
      const headers = { "Content-Type": "application/json" };
      if (authToken) headers.Authorization = `Bearer ${authToken}`;
      const res = await fetch(endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      clearTimeout(timeout);
      const text = await res.text().catch(() => "");
      if (res.ok) return { ok: true, status: res.status, text, attempts: i + 1 };
      lastErr = new Error(`HTTP ${res.status}${text ? `: ${text.slice(0, 500)}` : ""}`);
    } catch (e) {
      clearTimeout(timeout);
      lastErr = e instanceof Error ? e : new Error(String(e));
    }

    if (i < attempts - 1) await sleep(300 * (i + 1) + 250 * i * i);
  }

  return { ok: false, error: String(lastErr?.message || lastErr), attempts };
}

chrome.runtime.onInstalled.addListener(() => {
  ensureDefaultsOnInstall();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    if (message?.action === "SCC_GET_SETTINGS") {
      sendResponse({ ok: true, settings: await getSettings() });
      return;
    }

    if (message?.action === "SCC_POST_PAYLOAD") {
      const settings = await getSettings();
      const endpoint = settings.endpoint || DEFAULTS.endpoint;
      const authToken = settings.auth_token || "";
      const payload = message.payload;
      if (!payload || typeof payload !== "object") {
        sendResponse({ ok: false, error: "Missing payload" });
        return;
      }

      const res = await postJsonWithRetry(endpoint, payload, authToken, 2);
      sendResponse(res);
      return;
    }

    sendResponse({ ok: false, error: "Unknown action" });
  })();

  return true;
});

