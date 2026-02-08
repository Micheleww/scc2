function setStatus(text, kind) {
  const el = document.getElementById("statusText");
  el.textContent = text || "";
  if (kind === "ok") el.style.color = "var(--ok)";
  else if (kind === "bad") el.style.color = "var(--danger)";
  else el.style.color = "var(--muted)";
}

function getUrl() {
  return document.getElementById("urlInput").value.trim();
}

function getSccBase() {
  const raw = (document.getElementById("endpointInput")?.value || "").trim();
  if (!raw) return "http://127.0.0.1:18788";
  try {
    const u = new URL(raw);
    return u.origin;
  } catch {
    // If user enters a bare host:port without scheme, default to http.
    try {
      const u = new URL("http://" + raw.replace(/^https?:\/\//, ""));
      return u.origin;
    } catch {
      return "http://127.0.0.1:18788";
    }
  }
}

async function init() {
  const settings = await window.scc.getSettings();
  document.getElementById("endpointInput").value = settings.endpoint || "";
  document.getElementById("webgptIntakeInput").value = settings.webgpt_intake_endpoint || "";
  document.getElementById("webgptExportInput").value = settings.webgpt_export_endpoint || "";
  document.getElementById("tokenInput").value = settings.auth_token || "";
  document.getElementById("autosendToggle").checked = !!settings.autosend;
  document.getElementById("urlInput").value = "https://chatgpt.com/";
  document.getElementById("sendBtn").disabled = true;
  document.getElementById("copyBtn").disabled = true;
  document.getElementById("webgptSyncBtn").disabled = false;
  document.getElementById("webgptExportBtn").disabled = false;
  document.getElementById("webgptBackfillBtn").disabled = false;
  document.getElementById("webgptStopBtn").disabled = true;

  document.getElementById("backBtn").addEventListener("click", () => window.scc.nav("back"));
  document.getElementById("fwdBtn").addEventListener("click", () => window.scc.nav("forward"));
  document.getElementById("reloadBtn").addEventListener("click", () => window.scc.nav("reload"));

  document.getElementById("goBtn").addEventListener("click", () => window.scc.openUrl(getUrl()));
  document.getElementById("urlInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") window.scc.openUrl(getUrl());
  });

  document.getElementById("sccConsoleBtn").addEventListener("click", () => window.scc.openUrl(getSccBase() + "/scc"));
  document.getElementById("sccExecWfBtn").addEventListener("click", () => window.scc.openUrl(getSccBase() + "/scc/executor/waterfall"));
  document.getElementById("sccAutoWfBtn").addEventListener("click", () => window.scc.openUrl(getSccBase() + "/scc/automation/waterfall"));

  document.getElementById("saveBtn").addEventListener("click", async () => {
    setStatus("Saving…");
    const endpoint = document.getElementById("endpointInput").value.trim();
    const webgpt_intake_endpoint = document.getElementById("webgptIntakeInput").value.trim();
    const webgpt_export_endpoint = document.getElementById("webgptExportInput").value.trim();
    const auth_token = document.getElementById("tokenInput").value.trim();
    const autosend = !!document.getElementById("autosendToggle").checked;
    await window.scc.setSettings({ endpoint, webgpt_intake_endpoint, webgpt_export_endpoint, auth_token, autosend });
    setStatus("Saved", "ok");
    setTimeout(() => setStatus(""), 1200);
  });

  document.getElementById("autosendToggle").addEventListener("change", async (e) => {
    await window.scc.setSettings({ autosend: !!e.target.checked });
  });

  document.getElementById("sendBtn").addEventListener("click", async () => {
    setStatus("Sending…");
    const res = await window.scc.sendNow();
    if (res?.ok) setStatus(`Sent (${res.status})`, "ok");
    else setStatus(`Send failed: ${res?.error || "Unknown error"}`, "bad");
  });

  document.getElementById("copyBtn").addEventListener("click", async () => {
    await window.scc.copyPayload();
    setStatus("Copied payload", "ok");
    setTimeout(() => setStatus(""), 1000);
  });

  document.getElementById("webgptSyncBtn").addEventListener("click", async () => {
    setStatus("WebGPT syncing…");
    const res = await window.scc.webgptSyncNow();
    if (res?.ok) setStatus(`WebGPT synced (${res.status})`, "ok");
    else setStatus(`WebGPT sync failed: ${res?.error || "Unknown error"}`, "bad");
  });

  document.getElementById("webgptExportBtn").addEventListener("click", async () => {
    setStatus("WebGPT exporting…");
    const res = await window.scc.webgptExportNow();
    if (res?.ok) setStatus(`WebGPT exported (${res.status})`, "ok");
    else setStatus(`WebGPT export failed: ${res?.error || "Unknown error"}`, "bad");
  });

  document.getElementById("webgptBackfillBtn").addEventListener("click", async () => {
    const limit = parseInt(document.getElementById("webgptBackfillLimitInput").value || "120", 10) || 120;
    const scroll_steps = parseInt(document.getElementById("webgptBackfillScrollInput").value || "30", 10) || 30;
    setStatus(`WebGPT backfill starting (limit=${limit})…`);
    document.getElementById("webgptBackfillBtn").disabled = true;
    document.getElementById("webgptStopBtn").disabled = false;
    const res = await window.scc.webgptBackfillStart({ limit, scroll_steps, scroll_delay_ms: 220, per_conv_wait_ms: 15000 });
    if (res?.ok) setStatus("WebGPT backfill running…", "ok");
    else setStatus(`WebGPT backfill start failed: ${res?.error || "Unknown error"}`, "bad");
  });

  document.getElementById("webgptStopBtn").addEventListener("click", async () => {
    setStatus("Stopping backfill…");
    const res = await window.scc.webgptBackfillStop();
    document.getElementById("webgptBackfillBtn").disabled = false;
    document.getElementById("webgptStopBtn").disabled = true;
    if (res?.ok) setStatus("Backfill stopped", "ok");
    else setStatus(`Stop failed: ${res?.error || "Unknown error"}`, "bad");
  });

  window.scc.onSnapshot((snap) => {
    const n = snap?.directives?.length || 0;
    document.getElementById("detectedText").textContent = `Detected ${n}`;
    document.getElementById("sendBtn").disabled = n === 0;
    document.getElementById("copyBtn").disabled = n === 0;
  });

  window.scc.onPostResult((res) => {
    if (res?.ok) setStatus(`${res.autosend ? "Auto-sent" : "Sent"} (${res.status})`, "ok");
    else setStatus(`${res.autosend ? "Auto-send" : "Send"} failed: ${res?.error || "Unknown error"}`, "bad");
  });

  window.scc.onWebGPTResult((res) => {
    if (res?.ok) {
      const kind = res.kind || "webgpt";
      setStatus(`${kind} OK (${res.status})`, "ok");
      if (kind === "export") {
        const t = res.text || "";
        if (t) {
          try {
            const parsed = JSON.parse(t);
            if (parsed?.doc_path) document.getElementById("webgptText").textContent = `WebGPT doc: ${parsed.doc_path}`;
          } catch {}
        }
      }
    } else {
      setStatus(`WebGPT ${res?.kind || ""} failed: ${res?.error || "Unknown error"}`, "bad");
    }
  });

  window.scc.onWebGPTBackfillProgress((evt) => {
    if (!evt) return;
    if (evt.phase === "open") {
      setStatus(`Backfill: ${evt.idx + 1}/${evt.total} opening…`, "ok");
    } else if (evt.phase === "skip") {
      setStatus(`Backfill: ${evt.idx + 1}/${evt.total} skip (${evt.error || "skip"})`, "bad");
    } else if (evt.phase === "done") {
      document.getElementById("webgptBackfillBtn").disabled = false;
      document.getElementById("webgptStopBtn").disabled = true;
      setStatus("Backfill done", "ok");
    } else if (evt.phase === "error") {
      document.getElementById("webgptBackfillBtn").disabled = false;
      document.getElementById("webgptStopBtn").disabled = true;
      setStatus(`Backfill error: ${evt.error || "unknown"}`, "bad");
    }
  });

  window.scc.onWebGPTBackfillState((st) => {
    if (!st) return;
    const t = `WebGPT backfill: running=${!!st.running} ok=${st.ok || 0} fail=${st.fail || 0} idx=${(st.idx || 0) + 1}/${st.total || 0}`;
    document.getElementById("webgptText").textContent = t;
    if (!st.running) {
      document.getElementById("webgptBackfillBtn").disabled = false;
      document.getElementById("webgptStopBtn").disabled = true;
    }
  });

  window.scc.onNavigate((evt) => {
    if (evt?.url) document.getElementById("urlInput").value = evt.url;
  });

  // Report toolbar height to main process so BrowserView can be laid out correctly (no overlap / no clipping).
  const toolbar = document.querySelector(".toolbar");
  const report = () => {
    try {
      const h = Math.max(0, Math.ceil(toolbar?.getBoundingClientRect?.().height || 0));
      if (h > 0) window.scc.setToolbarHeight(h);
    } catch {
      // ignore
    }
  };
  report();
  if (toolbar && window.ResizeObserver) {
    const ro = new ResizeObserver(() => report());
    ro.observe(toolbar);
  } else {
    window.addEventListener("resize", () => report());
  }
}

init();
