const path = require("node:path");
const fs = require("node:fs/promises");
const fsSync = require("node:fs");
let electron = require("electron");
try {
  // Prefer main-process conditional export when it includes ipcMain.
  const mainElectron = require("electron/main");
  if (mainElectron && typeof mainElectron.ipcMain !== "undefined") electron = mainElectron;
} catch {}
const { app, BrowserWindow, BrowserView, ipcMain, clipboard } = electron;

try {
  console.log("[scc-chatgpt-browser] main.js boot");
  console.log(
    "[scc-chatgpt-browser] env backfill:",
    String(process.env.SCC_WEBGPT_BACKFILL_AUTOSTART || ""),
    String(process.env.SCC_WEBGPT_BACKFILL_LIMIT || ""),
    String(process.env.SCC_WEBGPT_BACKFILL_SCROLL_STEPS || "")
  );
  const keys = Object.keys(electron || {}).filter((k) => k.toLowerCase().includes("ipc")).slice(0, 40);
  console.log("[scc-chatgpt-browser] electron ipc keys:", keys.join(","));
  console.log("[scc-chatgpt-browser] electron ipcMain typeof:", typeof ipcMain);
  try {
    console.log("[scc-chatgpt-browser] userData:", app.getPath("userData"));
  } catch {}
} catch {}

// Reduce Windows permission issues for Chromium cache dirs by forcing a temp cache location.
try {
  const cacheRoot = path.join(app.getPath("temp"), "scc-chatgpt-browser-cache");
  app.commandLine.appendSwitch("disk-cache-dir", cacheRoot);
  app.commandLine.appendSwitch("disable-gpu-shader-disk-cache");
} catch {}

function parseBoolEnv(name, fallback) {
  const raw = (process.env[name] || "").trim().toLowerCase();
  if (!raw) return fallback;
  if (raw === "1" || raw === "true" || raw === "yes" || raw === "y" || raw === "on") return true;
  if (raw === "0" || raw === "false" || raw === "no" || raw === "n" || raw === "off") return false;
  return fallback;
}

const DEFAULTS = {
  endpoint:
    (process.env.SCC_CHATGPT_BROWSER_DEFAULT_ENDPOINT || "").trim() ||
    "http://127.0.0.1:18788/intake/directive",
  webgpt_intake_endpoint:
    (process.env.SCC_WEBGPT_INTAKE_ENDPOINT || "").trim() ||
    "http://127.0.0.1:18788/scc/webgpt/intake",
  webgpt_export_endpoint:
    (process.env.SCC_WEBGPT_EXPORT_ENDPOINT || "").trim() ||
    "http://127.0.0.1:18788/scc/webgpt/export",
  auth_token: "",
  autosend: parseBoolEnv("SCC_CHATGPT_BROWSER_DEFAULT_AUTOSEND", false)
};

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

async function readJson(filePath) {
  try {
    const txt = await fs.readFile(filePath, "utf8");
    return JSON.parse(txt);
  } catch {
    return null;
  }
}

async function writeJson(filePath, data) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, JSON.stringify(data, null, 2), "utf8");
}

function configPath() {
  return path.join(app.getPath("userData"), "scc_chatgpt_browser_config.json");
}

async function loadSettings() {
  const cfg = (await readJson(configPath())) || {};
  return {
    endpoint: typeof cfg.endpoint === "string" && cfg.endpoint.trim() ? cfg.endpoint.trim() : DEFAULTS.endpoint,
    webgpt_intake_endpoint:
      typeof cfg.webgpt_intake_endpoint === "string" && cfg.webgpt_intake_endpoint.trim()
        ? cfg.webgpt_intake_endpoint.trim()
        : DEFAULTS.webgpt_intake_endpoint,
    webgpt_export_endpoint:
      typeof cfg.webgpt_export_endpoint === "string" && cfg.webgpt_export_endpoint.trim()
        ? cfg.webgpt_export_endpoint.trim()
        : DEFAULTS.webgpt_export_endpoint,
    auth_token: typeof cfg.auth_token === "string" ? cfg.auth_token.trim() : DEFAULTS.auth_token,
    autosend: typeof cfg.autosend === "boolean" ? cfg.autosend : DEFAULTS.autosend
  };
}

async function saveSettings(partial) {
  const cur = await loadSettings();
  const next = { ...cur, ...partial };
  await writeJson(configPath(), next);
  return next;
}

function nowIso() {
  return new Date().toISOString();
}

function buildPayload(snapshot) {
  const directives = snapshot?.directives || [];
  const pageUrl = directives[0]?.page_url || snapshot?.page_url || "";
  const capturedAt = directives[0]?.captured_at || snapshot?.captured_at || nowIso();
  return {
    source: "chatgpt_embedded_browser",
    page_url: pageUrl,
    captured_at: capturedAt,
    directives: directives.map((d) => d.parsed)
  };
}

let win = null;
let view = null;
let latestSnapshot = { directives: [], errors: [], key: "", page_url: "", captured_at: "" };
let lastAutosentKey = "";
let pendingChatReq = new Map(); // rid -> { resolve, timer }
let lastWebgptAutoKey = "";
let lastWebgptAutoAtMs = 0;
let pendingBackfillAutostart = null; // { limit, scroll_steps, scroll_delay_ms, per_conv_wait_ms } | null

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..", "..", "..");
const COMMAND_QUEUE_PATH = path.join(REPO_ROOT, "artifacts", "scc_state", "browser_commands.jsonl");
const COMMAND_ACK_PATH = path.join(REPO_ROOT, "artifacts", "scc_state", "browser_commands_ack.jsonl");
const PROCESS_STATE_PATH = path.join(REPO_ROOT, "artifacts", "scc_state", "browser_process.json");
let commandQueueOffset = 0;
const processedCommandIds = new Set();
let commandPumpBusy = false;
let lastQueueMtimeMs = 0;
let lastStateFlushAtMs = 0;
let lastKnownChatUrl = "";
let lastProcessStateFlushAtMs = 0;
let authRedirectRetryCount = 0;
let desiredHomeUrl = "";

function commandStatePath() {
  try {
    return path.join(app.getPath("userData"), "scc_browser_command_queue_state.json");
  } catch {
    return path.join(process.cwd(), ".scc_browser_command_queue_state.json");
  }
}

async function loadCommandState() {
  try {
    const p = commandStatePath();
    const raw = await fs.readFile(p, "utf8");
    const parsed = JSON.parse(raw);
    const off = Number(parsed?.offset);
    const mtime = Number(parsed?.mtime_ms);
    if (Number.isFinite(off) && off >= 0) commandQueueOffset = off;
    if (Number.isFinite(mtime) && mtime > 0) lastQueueMtimeMs = mtime;
  } catch {}
}

async function loadHomeUrl() {
  try {
    desiredHomeUrl = String(process.env.SCC_CHATGPT_BROWSER_HOME_URL || "").trim();
  } catch {
    desiredHomeUrl = "";
  }

  if (desiredHomeUrl) return desiredHomeUrl;

  try {
    const p = path.join(app.getPath("userData"), "scc_chatgpt_browser_last_url.txt");
    const raw = await fs.readFile(p, "utf8");
    const u = String(raw || "").trim();
    if (u) desiredHomeUrl = u;
  } catch {}
  return desiredHomeUrl;
}

async function saveHomeUrl(url) {
  const u = String(url || "").trim();
  if (!u) return;
  try {
    const parsed = new URL(u);
    if (!String(parsed.hostname || "").endsWith("chatgpt.com")) return;
  } catch {
    return;
  }

  lastKnownChatUrl = u;
  try {
    const p = path.join(app.getPath("userData"), "scc_chatgpt_browser_last_url.txt");
    await fs.mkdir(path.dirname(p), { recursive: true });
    await fs.writeFile(p, u, "utf8");
  } catch {}
}

async function flushProcessState() {
  const now = Date.now();
  if (now - lastProcessStateFlushAtMs < 1500) return;
  lastProcessStateFlushAtMs = now;
  try {
      const payload = {
        pid: process.pid,
        started_at: nowIso(),
        app_dir: __dirname,
        log_path: String(process.env.SCC_BROWSER_LOG_PATH || "").trim(),
        user_data: (() => {
          try {
            return app.getPath("userData");
          } catch {
            return "";
          }
        })(),
      partition: "persist:scc-chatgpt",
      current_url: lastKnownChatUrl || "",
      command_queue_path: COMMAND_QUEUE_PATH,
      command_ack_path: COMMAND_ACK_PATH,
    };
    await fs.mkdir(path.dirname(PROCESS_STATE_PATH), { recursive: true });
    await fs.writeFile(PROCESS_STATE_PATH, JSON.stringify(payload, null, 2), "utf8");
  } catch {}
}

async function flushCommandState() {
  const now = Date.now();
  if (now - lastStateFlushAtMs < 1500) return;
  lastStateFlushAtMs = now;
  try {
    const p = commandStatePath();
    await fs.mkdir(path.dirname(p), { recursive: true });
    await fs.writeFile(p, JSON.stringify({ offset: commandQueueOffset, mtime_ms: lastQueueMtimeMs }, null, 2), "utf8");
  } catch {}
}

function getArgValue(flag) {
  const idx = process.argv.indexOf(flag);
  if (idx < 0) return null;
  const next = process.argv[idx + 1];
  if (!next || next.startsWith("--")) return null;
  return String(next);
}

function hasArg(flag) {
  return process.argv.includes(flag);
}
let backfillState = { running: false, run_id: "", total: 0, idx: 0, ok: 0, fail: 0, last_error: "" };
let backfillStopFlag = false;
let toolbarHeight = 56;

function logLine(obj) {
  try {
    const s = typeof obj === "string" ? obj : JSON.stringify(obj);
    console.log(`[scc-chatgpt-browser] ${s}`);
  } catch {
    try {
      console.log("[scc-chatgpt-browser] (log failed)");
    } catch {}
  }
}

async function appendCommandAck(payload) {
  try {
    await fs.mkdir(path.dirname(COMMAND_ACK_PATH), { recursive: true });
    await fs.appendFile(COMMAND_ACK_PATH, JSON.stringify(payload) + "\n", "utf8");
  } catch {}
}

function rememberCommandId(id) {
  if (!id) return;
  processedCommandIds.add(String(id));
  if (processedCommandIds.size <= 500) return;
  // Best-effort bound memory (drop oldest by recreating set).
  const arr = Array.from(processedCommandIds);
  processedCommandIds.clear();
  for (const v of arr.slice(-300)) processedCommandIds.add(v);
}

async function handleBrowserCommand(cmd) {
  const name = String(cmd?.cmd || "").trim();
  const args = (cmd && typeof cmd.args === "object" && cmd.args) ? cmd.args : {};
  const id = String(cmd?.id || "");

  if (!name) return;
  logLine({ event: "browser_command", id, cmd: name, args });
  const startedAt = nowIso();

  try {
    if (name === "open_url") {
      const url = String(args.url || "").trim();
      if (view && url) {
        // IMPORTANT: attach .catch() directly to avoid Electron/Node unhandled rejection warnings on ERR_ABORTED redirects.
        view.webContents.loadURL(url).catch((e) => {
          logLine({ event: "open_url_load_failed", id, url, error: String(e?.message || e) });
        });
      }
      await appendCommandAck({ id, ok: true, cmd: name, at: nowIso(), started_at: startedAt, url });
      return;
    }

    if (name === "webgpt_sync") {
      const res = await webgptSyncNow();
      await appendCommandAck({ id, ok: !!res?.ok, cmd: name, at: nowIso(), started_at: startedAt, res });
      return;
    }

    if (name === "webgpt_export") {
      const res = await webgptExportNow();
      await appendCommandAck({ id, ok: !!res?.ok, cmd: name, at: nowIso(), started_at: startedAt, res });
      return;
    }

    if (name === "webgpt_backfill_start") {
      const opts = {
        limit: Number.isFinite(Number(args.limit)) ? Number(args.limit) : 500,
        scroll_steps: Number.isFinite(Number(args.scroll_steps)) ? Number(args.scroll_steps) : 60,
        sidebar_scroll_steps: Number.isFinite(Number(args.sidebar_scroll_steps)) ? Number(args.sidebar_scroll_steps) : undefined,
        scroll_delay_ms: Number.isFinite(Number(args.scroll_delay_ms)) ? Number(args.scroll_delay_ms) : 220,
        per_conv_wait_ms: Number.isFinite(Number(args.per_conv_wait_ms)) ? Number(args.per_conv_wait_ms) : 15000,
      };
      const res = await webgptBackfillStart(opts);
      await appendCommandAck({ id, ok: !!res?.ok, cmd: name, at: nowIso(), started_at: startedAt, res });
      return;
    }

    if (name === "webgpt_backfill_stop") {
      const res = await webgptBackfillStop();
      await appendCommandAck({ id, ok: !!res?.ok, cmd: name, at: nowIso(), started_at: startedAt, res });
      return;
    }

    if (name === "webgpt_capture_memory") {
      const settings = await loadSettings();
      const cap = await capturePersonalizationMemory(20000);
      if (!cap?.ok) {
        await appendCommandAck({ id, ok: false, cmd: name, at: nowIso(), started_at: startedAt, error: cap?.error || "capture_failed" });
        return;
      }
      const intakeRes = await postJsonWithRetry(
        (process.env.SCC_WEBGPT_MEMORY_INTAKE_ENDPOINT || "").trim() || "http://127.0.0.1:18788/scc/webgpt/memory/intake",
        cap.snapshot,
        settings.auth_token,
        2
      );
      await appendCommandAck({ id, ok: !!intakeRes?.ok, cmd: name, at: nowIso(), started_at: startedAt, res: intakeRes });
      if (win) win.webContents.send("scc:webgptResult", { kind: "memory_intake", ...intakeRes });
      return;
    }

    await appendCommandAck({ id, ok: false, cmd: name, at: nowIso(), started_at: startedAt, error: "unknown_cmd" });
  } catch (e) {
    await appendCommandAck({ id, ok: false, cmd: name, at: nowIso(), started_at: startedAt, error: String(e?.message || e) });
    throw e;
  }
}

async function pumpCommandQueue() {
  if (commandPumpBusy) return;
  commandPumpBusy = true;
  try {
    if (!fsSync.existsSync(COMMAND_QUEUE_PATH)) return;
    const stat = fsSync.statSync(COMMAND_QUEUE_PATH);
    if (!stat.isFile()) return;
    lastQueueMtimeMs = Number(stat.mtimeMs || 0) || lastQueueMtimeMs;
    const size = stat.size || 0;
    if (size <= commandQueueOffset) return;

    const fd = fsSync.openSync(COMMAND_QUEUE_PATH, "r");
    try {
      const buf = Buffer.allocUnsafe(Math.min(1024 * 256, size - commandQueueOffset));
      const bytesRead = fsSync.readSync(fd, buf, 0, buf.length, commandQueueOffset);
      if (bytesRead <= 0) return;
      commandQueueOffset += bytesRead;
      await flushCommandState();
      const chunk = buf.subarray(0, bytesRead).toString("utf8");
      const lines = chunk.split(/\r?\n/).filter(Boolean);
      for (const line of lines) {
        let parsed = null;
        try { parsed = JSON.parse(line); } catch { parsed = null; }
        if (!parsed || typeof parsed !== "object") continue;
        const id = String(parsed.id || "");
        if (id && processedCommandIds.has(id)) continue;
        rememberCommandId(id);
        try {
          await handleBrowserCommand(parsed);
        } catch (e) {
          logLine({ event: "browser_command_error", id, error: String(e?.message || e) });
        }
      }
    } finally {
      try { fsSync.closeSync(fd); } catch {}
    }
  } catch (e) {
    logLine({ event: "command_queue_pump_error", error: String(e?.message || e) });
  } finally {
    commandPumpBusy = false;
  }
}

function layout() {
  if (!win || !view) return;
  const bounds = win.getContentBounds();
  const th = Math.max(40, Math.min(180, Number(toolbarHeight) || 56));
  view.setBounds({ x: 0, y: th, width: bounds.width, height: Math.max(0, bounds.height - th) });
}

async function maybeAutosend() {
  const settings = await loadSettings();
  if (!settings.autosend) return;
  if (!latestSnapshot?.directives?.length) return;
  if (latestSnapshot.key && latestSnapshot.key === lastAutosentKey) return;

  lastAutosentKey = latestSnapshot.key || nowIso();
  const payload = buildPayload(latestSnapshot);
  const res = await postJsonWithRetry(settings.endpoint, payload, settings.auth_token, 2);
  if (win) win.webContents.send("scc:postResult", { autosend: true, ...res });
}

async function sendNow() {
  const settings = await loadSettings();
  const payload = buildPayload(latestSnapshot);
  const res = await postJsonWithRetry(settings.endpoint, payload, settings.auth_token, 2);
  if (win) win.webContents.send("scc:postResult", { autosend: false, ...res });
  return res;
}

async function requestChatArchiveSnapshot(timeoutMs = 4000) {
  if (!view) return { ok: false, error: "no_view" };
  const rid = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  return await new Promise((resolve) => {
    const timer = setTimeout(() => {
      pendingChatReq.delete(rid);
      resolve({ ok: false, error: "snapshot_timeout" });
    }, Math.max(250, timeoutMs));
    pendingChatReq.set(rid, { resolve, timer });
    try {
      view.webContents.send("scc:requestChatArchiveSnapshot", { rid });
    } catch (e) {
      clearTimeout(timer);
      pendingChatReq.delete(rid);
      resolve({ ok: false, error: String(e?.message || e) });
    }
  });
}

async function waitForWebGPTReady(timeoutMs = 20000) {
  if (!view) return { ok: false, error: "no_view" };
  const deadline = Date.now() + Math.max(1500, timeoutMs);
  const js = `(() => {
    const main = document.querySelector('main') || document.body;
    const url = String(location.href || '');
    const path = String(location.pathname || '');
    const counts = {
      role_nodes: document.querySelectorAll('[data-message-author-role]').length,
      conversation_turn: main.querySelectorAll('[data-testid=\"conversation-turn\"]').length,
      message_testid: main.querySelectorAll('[data-testid=\"message\"]').length,
      articles: main.querySelectorAll('article').length,
      markdown: main.querySelectorAll('.markdown').length,
    };
    return { url, path, counts };
  })();`;

  let last = null;
  while (Date.now() < deadline) {
    try {
      last = await view.webContents.executeJavaScript(js, true);
    } catch {
      last = null;
    }
    const path = String(last?.path || "");
    const counts = last?.counts || {};
    const roleN = Number(counts.role_nodes || 0);
    const convN = Number(counts.conversation_turn || 0);
    const msgN = Number(counts.message_testid || 0);
    if (path.startsWith("/auth/")) return { ok: false, error: "auth_redirect", debug: last };
    if (roleN > 0 || convN > 0 || msgN > 0) return { ok: true, debug: last };
    await sleep(750);
  }
  return { ok: false, error: "wait_timeout", debug: last };
}

async function captureCurrentConversation(timeoutMs = 15000) {
  if (!view) return { ok: false, error: "no_view" };
  // Give ChatGPT time to hydrate DOM; avoid false negatives right after navigation.
  const ready = await waitForWebGPTReady(Math.min(20000, Math.max(2500, timeoutMs)));
  if (!ready?.ok) {
    return { ok: true, snapshot: { ok: false, error: ready?.error || "not_ready", debug: ready?.debug } };
  }
  const js = `(() => {
    function safeSlice(s, n) {
      const t = String(s || '');
      return t.length > n ? (t.slice(0, n) + '…') : t;
    }
    function djb2(str) {
      let h = 5381;
      for (let i = 0; i < str.length; i++) h = ((h << 5) + h) + str.charCodeAt(i);
      return (h >>> 0).toString(16);
    }
    const m = location.pathname.match(/^\\/c\\/([^\\/]+)/);
    const fallbackId = 'url_' + djb2(String(location.href||''));
    const conversation_id = m ? m[1] : fallbackId;
    const title = (document.title || '').replace(' | ChatGPT','').trim() || null;

    const main = document.querySelector('main') || document.body;
    const counts = {
      role_nodes: document.querySelectorAll('[data-message-author-role]').length,
      conversation_turn: main.querySelectorAll('[data-testid=\"conversation-turn\"]').length,
      message_testid: main.querySelectorAll('[data-testid=\"message\"]').length,
      articles: main.querySelectorAll('article').length,
      markdown: main.querySelectorAll('.markdown').length,
    };

    let nodes = Array.from(main.querySelectorAll('[data-message-author-role]'));
    let mode = 'role_nodes';
    if (!nodes.length) {
      nodes = Array.from(main.querySelectorAll('[data-testid=\"conversation-turn\"]'));
      mode = 'conversation_turn';
    }
    if (!nodes.length) {
      nodes = Array.from(main.querySelectorAll('[data-testid=\"message\"]'));
      mode = 'message_testid';
    }
    if (!nodes.length) {
      nodes = Array.from(main.querySelectorAll('article'));
      mode = 'article_nodes';
    }

    const messages = [];
    for (const node of nodes) {
      let role = 'assistant';
      const roleNode =
        (node.getAttribute && node.getAttribute('data-message-author-role') ? node : null) ||
        (node.querySelector ? node.querySelector('[data-message-author-role]') : null);
      const roleAttr = roleNode && roleNode.getAttribute ? (roleNode.getAttribute('data-message-author-role') || '') : '';
      if (String(roleAttr).toLowerCase() === 'user') role = 'user';
      if (String(roleAttr).toLowerCase() === 'assistant') role = 'assistant';
      if (!roleAttr && node.querySelector && node.querySelector('[data-message-author-role=\"user\"]')) role = 'user';

      const codeBlocks = Array.from(node.querySelectorAll('pre code')).map((c)=> (c.innerText||'').trim()).filter(Boolean);
      const md =
        node.querySelector?.('[data-message-author-role] .markdown, .markdown, [data-testid=\"conversation-turn\"] .markdown') ||
        null;
      const text = (md ? md.innerText : node.innerText || '').trim();
      const msgId = (node.getAttribute && node.getAttribute('data-message-id')) ? (node.getAttribute('data-message-id') || null) : (node.id || null);
      const content_json = codeBlocks.length ? { code_blocks: codeBlocks } : null;
      messages.push({ message_id: msgId, role, created_at: null, content_text: text, content_json });
    }
    const filtered = messages.filter((m)=> m.content_text && m.content_text.trim());
    return {
      ok: filtered.length > 0,
      conversation_id,
      title,
      source: 'webgpt_embedded_browser',
      page_url: String(location.href||''),
      captured_at: new Date().toISOString(),
      messages: filtered,
      debug: {
        mode,
        counts,
        node_count: nodes.length,
        message_count: filtered.length,
        title_preview: safeSlice(title || '', 120),
        url_preview: safeSlice(String(location.href || ''), 220),
      }
    };
  })();`;
  try {
    const p = Promise.race([
      view.webContents.executeJavaScript(js, true),
      new Promise((_, rej) => setTimeout(() => rej(new Error("capture_timeout")), Math.max(1000, timeoutMs))),
    ]);
    const snapshot = await p;
    return { ok: true, snapshot };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}

async function capturePersonalizationMemory(timeoutMs = 20000) {
  if (!view) return { ok: false, error: "no_view" };
  const js = `(() => {
    function norm(s) { return String(s || '').replace(/\\r\\n/g, '\\n').trim(); }
    const page_url = String(location.href || '');
    const captured_at = new Date().toISOString();

    // Try to find the memory dialog by title (CN/EN) and extract list-like lines.
    const body = document.body || document.documentElement;
    const fullText = norm(body ? (body.innerText || body.textContent || '') : '');

    // Heuristic: keep only the section around "保存的记忆" / "Saved memories" if present.
    const markers = ['保存的记忆', 'Saved memories', '记忆', 'Memory'];
    let start = 0;
    for (const m of markers) {
      const idx = fullText.indexOf(m);
      if (idx >= 0) { start = Math.max(0, idx - 200); break; }
    }
    const sliced = fullText.slice(start, start + 20000);

    const lines = sliced.split('\\n').map((l) => l.trim()).filter(Boolean);
    // Drop obvious UI chrome lines.
    const drop = new Set(['ChatGPT', '保存的记忆', 'Saved memories', '搜索记忆', 'Search memories', '了解更多', 'Learn more']);
    const items = lines.filter((l) => l.length >= 6 && l.length <= 600 && !drop.has(l));

    return {
      ok: true,
      page_url,
      captured_at,
      items: items.slice(0, 2000),
      text: sliced,
    };
  })();`;

  try {
    const p = Promise.race([
      view.webContents.executeJavaScript(js, true),
      new Promise((_, rej) => setTimeout(() => rej(new Error("capture_timeout")), Math.max(1000, timeoutMs))),
    ]);
    const snapshot = await p;
    return { ok: true, snapshot };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}

async function webgptSyncNow() {
  const settings = await loadSettings();

  // Prefer main-process capture (no preload dependence).
  const cap = await captureCurrentConversation(15000);
  if (!cap?.ok) return cap;
  const snapshot = cap.snapshot;
  logLine({ event: "webgpt_sync_capture", ok: !!snapshot?.ok, debug: snapshot?.debug, url: snapshot?.page_url });
  if (!snapshot?.ok) return { ok: false, error: snapshot?.error || "no_messages_found", debug: snapshot?.debug };
  const res = await postJsonWithRetry(settings.webgpt_intake_endpoint, snapshot, settings.auth_token, 2);
  if (win) win.webContents.send("scc:webgptResult", { kind: "intake", snapshot, ...res });
  return { ...res, conversation_id: snapshot.conversation_id };
}

async function webgptExportNow() {
  const settings = await loadSettings();

  const cap = await captureCurrentConversation(15000);
  if (!cap?.ok) return cap;
  const snapshot = cap.snapshot;
  logLine({ event: "webgpt_export_capture", ok: !!snapshot?.ok, debug: snapshot?.debug, url: snapshot?.page_url });
  if (!snapshot?.ok) return { ok: false, error: snapshot?.error || "no_messages_found", debug: snapshot?.debug };
  const payload = { conversation_id: snapshot.conversation_id };
  const res = await postJsonWithRetry(settings.webgpt_export_endpoint, payload, settings.auth_token, 2);
  if (win) win.webContents.send("scc:webgptResult", { kind: "export", snapshot, ...res });
  return res;
}

async function maybeAutoWebGPT(url) {
  const enabled = parseBoolEnv("SCC_WEBGPT_AUTOSYNC", true);
  if (!enabled) return;
  if (!url || typeof url !== "string") return;

  let u = null;
  try {
    u = new URL(url);
  } catch {
    return;
  }

  if (!String(u.hostname || "").endsWith("chatgpt.com")) return;
  if (!String(u.pathname || "").startsWith("/c/")) return;

  const key = `${u.origin}${u.pathname}`;
  const now = Date.now();
  if (key === lastWebgptAutoKey && now - lastWebgptAutoAtMs < 25_000) return;
  lastWebgptAutoKey = key;
  lastWebgptAutoAtMs = now;
  logLine({ event: "webgpt_autosync_trigger", url });

  const delayMs = Math.max(600, Math.min(12_000, parseInt(String(process.env.SCC_WEBGPT_AUTOSYNC_DELAY_MS || "2200"), 10) || 2200));
  setTimeout(async () => {
    try {
      const intake = await webgptSyncNow();
      if (!intake?.ok) return;
      const doExport = parseBoolEnv("SCC_WEBGPT_AUTOSYNC_EXPORT", true);
      const cid = intake?.conversation_id;
      if (!doExport || !cid) return;
      const settings = await loadSettings();
      const exportRes = await postJsonWithRetry(settings.webgpt_export_endpoint, { conversation_id: cid }, settings.auth_token, 2);
      if (win) win.webContents.send("scc:webgptResult", { kind: "auto_export", conversation_id: cid, ...exportRes });
    } catch (e) {
      logLine({ event: "webgpt_autosync_error", error: String(e?.message || e), url });
    }
  }, delayMs);
}

async function maybeAutostartBackfill(url) {
  if (!pendingBackfillAutostart) return;
  if (!url || typeof url !== "string") return;
  let u = null;
  try {
    u = new URL(url);
  } catch {
    return;
  }
  if (!String(u.hostname || "").endsWith("chatgpt.com")) return;
  if (String(u.pathname || "").startsWith("/auth/")) return;

  const opts = pendingBackfillAutostart;
  pendingBackfillAutostart = null;
  logLine({ event: "webgpt_backfill_autostart", url, opts: { limit: opts.limit, scroll_steps: opts.scroll_steps } });
  await sleep(1200);
  await webgptBackfillStart(opts);
}

async function webgptBackfillStart(opts) {
  if (!view) return { ok: false, error: "no_view" };
  if (backfillState.running) return { ok: true, already_running: true, state: backfillState };
  const run_id = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  backfillState = { running: true, run_id, total: 0, idx: 0, ok: 0, fail: 0, last_error: "" };
  backfillStopFlag = false;

  async function loadUrlWithRetry(url, maxAttempts = 3) {
    let lastErr = null;
    for (let i = 0; i < Math.max(1, maxAttempts); i++) {
      try {
        await view.webContents.loadURL(url);
        return { ok: true, attempts: i + 1 };
      } catch (e) {
        lastErr = e instanceof Error ? e : new Error(String(e));
        const msg = String(lastErr?.message || lastErr);
        // ChatGPT redirects/hydration can surface ERR_ABORTED even when a new URL is already loaded.
        if (msg.includes("ERR_ABORTED")) {
          try {
            const cur = String(view.webContents.getURL() || "");
            if (cur && cur !== "about:blank") return { ok: true, attempts: i + 1, aborted: true, current_url: cur };
          } catch {}
        }
        await sleep(350 * (i + 1) + 200 * i * i);
      }
    }
    return { ok: false, error: String(lastErr?.message || lastErr) };
  }

  async function captureWithRetry(timeoutMs = 20000, maxAttempts = 2) {
    let last = null;
    for (let i = 0; i < Math.max(1, maxAttempts); i++) {
      const cap = await captureCurrentConversation(timeoutMs);
      last = cap?.snapshot || { ok: false, error: cap?.error || "capture_failed" };
      if (last?.ok) return { ok: true, snapshot: last, attempts: i + 1 };
      if (String(last?.error || "").includes("auth_redirect")) break;
      await sleep(900 * (i + 1));
    }
    return { ok: false, snapshot: last, attempts: Math.max(1, maxAttempts) };
  }
  try {
    logLine({ event: "backfill_start_main_execjs", run_id, opts: opts || {} });
    if (win) win.webContents.send("scc:webgptBackfillState", backfillState);

    // Fire-and-forget loop (do not block IPC).
    (async () => {
      const limit = Math.max(1, Math.min(2000, Number(opts?.limit) || 120));
      const scrollSteps = Math.max(0, Math.min(250, Number(opts?.scroll_steps) || 30));
      const scrollDelayMs = Math.max(60, Math.min(1500, Number(opts?.scroll_delay_ms) || 220));
      const sidebarScanSteps = Math.max(10, Math.min(600, Number(opts?.sidebar_scroll_steps) || Math.max(30, scrollSteps * 3)));

      const listJs = `(() => new Promise((resolve) => {
        function isScrollable(el) {
          try {
            if (!el) return false;
            const sh = el.scrollHeight || 0;
            const ch = el.clientHeight || 0;
            return sh > ch + 50;
          } catch { return false; }
        }

        function findSidebarScrollContainer() {
          const candidates = [];
          const nav = document.querySelector('nav');
          if (nav) candidates.push(nav);
          const aside = document.querySelector('aside');
          if (aside) candidates.push(aside);
          candidates.push(...Array.from(document.querySelectorAll('nav, aside, [role=\"navigation\"], [aria-label*=\"history\" i], [aria-label*=\"chat\" i]')));
          candidates.push(...Array.from(document.querySelectorAll('div')).filter((d) => {
            try {
              const cs = getComputedStyle(d);
              return (cs.overflowY === 'auto' || cs.overflowY === 'scroll') && (d.clientHeight || 0) > 220;
            } catch { return false; }
          }));

          let best = null;
          let bestScore = 0;
          for (const el of candidates) {
            if (!isScrollable(el)) continue;
            const score = (el.scrollHeight || 0) - (el.clientHeight || 0);
            if (score > bestScore) {
              best = el;
              bestScore = score;
            }
          }
          return best;
        }

        function collectUrls(limit) {
          const anchors = Array.from(document.querySelectorAll('a[href^=\"/c/\"], a[href*=\"/c/\"]'));
          const seen = new Set();
          const out = [];
          for (const a of anchors) {
            const href = (a.getAttribute('href') || '').trim();
            if (!href.includes('/c/')) continue;
            const u = new URL(href, location.origin).toString();
            if (seen.has(u)) continue;
            seen.add(u);
            out.push(u);
            if (out.length >= limit) break;
          }
          return out;
        }

        const limit = ${limit};
        const steps = ${sidebarScanSteps};
        const delay = ${scrollDelayMs};
        const sidebar = findSidebarScrollContainer();

        let i = 0;
        const tick = () => {
          try {
            const urls = collectUrls(limit);
            if (urls.length >= limit || i >= steps || !sidebar) {
              if (urls.length === 0) urls.push(String(location.href || ''));
              return resolve(urls);
            }
            // Scroll sidebar down to force ChatGPT to hydrate/load more items.
            try { sidebar.scrollTop = (sidebar.scrollTop || 0) + Math.max(320, Math.floor(sidebar.clientHeight * 0.9)); } catch {}
          } catch {}
          i++;
          setTimeout(tick, delay);
        };
        tick();
      }))();`;

      let urls = [];
      try {
        // Retry a few times because ChatGPT sidebar is often hydrated async.
        for (let attempt = 0; attempt < 20; attempt++) {
          urls = (await view.webContents.executeJavaScript(listJs, true)) || [];
          if (Array.isArray(urls) && urls.length > 0) break;
          await new Promise((r) => setTimeout(r, 1000));
        }
      } catch (e) {
        urls = [];
        backfillState.last_error = String(e?.message || e);
      }

      if (!Array.isArray(urls) || urls.length === 0) {
        backfillState.running = false;
        backfillState.total = 0;
        backfillState.last_error = backfillState.last_error || "no_conversations_found (sidebar selector mismatch?)";
        if (win) win.webContents.send("scc:webgptBackfillProgress", { run_id, phase: "error", error: backfillState.last_error });
        if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
        logLine({ event: "backfill_error", error: backfillState.last_error });
        return;
      }

      backfillState.total = urls.length;
      if (win) win.webContents.send("scc:webgptBackfillProgress", { run_id, phase: "discovered", total: urls.length });
      if (win) win.webContents.send("scc:webgptBackfillState", backfillState);

      const captureJs = `(() => {
        function safeSlice(s, n) {
          const t = String(s || '');
          return t.length > n ? (t.slice(0, n) + '…') : t;
        }
        function djb2(str) {
          let h = 5381;
          for (let i = 0; i < str.length; i++) h = ((h << 5) + h) + str.charCodeAt(i);
          return (h >>> 0).toString(16);
        }
        const m = location.pathname.match(/^\\/c\\/([^\\/]+)/);
        const fallbackId = 'url_' + djb2(String(location.href||''));
        const conversation_id = m ? m[1] : fallbackId;
        const title = (document.title || '').replace(' | ChatGPT','').trim() || null;

        const main = document.querySelector('main') || document.body;
        const counts = {
          role_nodes: document.querySelectorAll('[data-message-author-role]').length,
          conversation_turn: main.querySelectorAll('[data-testid=\"conversation-turn\"]').length,
          message_testid: main.querySelectorAll('[data-testid=\"message\"]').length,
          articles: main.querySelectorAll('article').length,
          markdown: main.querySelectorAll('.markdown').length,
        };

        let nodes = Array.from(main.querySelectorAll('[data-message-author-role]'));
        let mode = 'role_nodes';
        if (!nodes.length) {
          nodes = Array.from(main.querySelectorAll('[data-testid=\"conversation-turn\"]'));
          mode = 'conversation_turn';
        }
        if (!nodes.length) {
          nodes = Array.from(main.querySelectorAll('[data-testid=\"message\"]'));
          mode = 'message_testid';
        }
        if (!nodes.length) {
          nodes = Array.from(main.querySelectorAll('article'));
          mode = 'article_nodes';
        }
        const messages = [];
        for (const node of nodes) {
          let role = 'assistant';
          const roleNode =
            (node.getAttribute && node.getAttribute('data-message-author-role') ? node : null) ||
            (node.querySelector ? node.querySelector('[data-message-author-role]') : null);
          const roleAttr = roleNode && roleNode.getAttribute ? (roleNode.getAttribute('data-message-author-role') || '') : '';
          if (String(roleAttr).toLowerCase() === 'user') role = 'user';
          if (String(roleAttr).toLowerCase() === 'assistant') role = 'assistant';
          if (!roleAttr && node.querySelector && node.querySelector('[data-message-author-role=\"user\"]')) role = 'user';
          const codeBlocks = Array.from(node.querySelectorAll('pre code')).map((c)=> (c.innerText||'').trim()).filter(Boolean);
          const md =
            node.querySelector?.('[data-message-author-role] .markdown, .markdown, [data-testid=\"conversation-turn\"] .markdown') ||
            null;
          const text = (md ? md.innerText : node.innerText || '').trim();
          const msgId = node.getAttribute('data-message-id') || node.id || null;
          const content_json = codeBlocks.length ? { code_blocks: codeBlocks } : null;
          messages.push({ message_id: msgId, role, created_at: null, content_text: text, content_json });
        }
        const filtered = messages.filter((m)=> m.content_text && m.content_text.trim());
        return {
          ok: filtered.length > 0,
          conversation_id,
          title,
          source: 'webgpt_embedded_browser',
          page_url: String(location.href||''),
          captured_at: new Date().toISOString(),
          messages: filtered,
          debug: {
            mode,
            counts,
            node_count: nodes.length,
            message_count: filtered.length,
            title_preview: safeSlice(title || '', 120),
            url_preview: safeSlice(String(location.href || ''), 220),
          }
        };
      })();`;

      const scrollJs = `(() => new Promise((resolve) => {
        const steps = ${scrollSteps};
        const delay = ${scrollDelayMs};
        let i = 0;
        function tick() {
          // ChatGPT loads older messages when scrolling up. Nudge towards top repeatedly.
          try {
            const el = document.scrollingElement || document.documentElement || document.body;
            if (el && typeof el.scrollTop === 'number') el.scrollTop = Math.max(0, el.scrollTop - Math.max(480, Math.floor((window.innerHeight || 800) * 0.8)));
          } catch {}
          i++;
          if (i >= steps) return resolve(true);
          setTimeout(tick, delay);
        }
        tick();
      }))();`;

      for (let idx = 0; idx < urls.length; idx++) {
        if (backfillStopFlag) {
          backfillState.running = false;
          if (win) win.webContents.send("scc:webgptBackfillProgress", { run_id, phase: "stopped", idx, total: urls.length });
          if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
          logLine({ event: "backfill_stopped", idx });
          return;
        }

        const url = urls[idx];
        backfillState.idx = idx;
        if (win) win.webContents.send("scc:webgptBackfillProgress", { run_id, phase: "open", idx, total: urls.length, url });
        if (win) win.webContents.send("scc:webgptBackfillState", backfillState);

        const loadRes = await loadUrlWithRetry(url, 3);
        if (!loadRes?.ok) {
          backfillState.fail += 1;
          backfillState.last_error = `loadURL_failed: ${String(loadRes?.error || "unknown")}`;
          if (win) win.webContents.send("scc:webgptBackfillProgress", { run_id, phase: "skip", idx, total: urls.length, url, error: backfillState.last_error });
          continue;
        }

        try {
          await view.webContents.executeJavaScript(scrollJs, true);
        } catch {}

        const capRes = await captureWithRetry(22000, 2);
        const snapshot = capRes?.snapshot || { ok: false, error: "snapshot_failed" };

        if (!snapshot || snapshot.ok !== true) {
          backfillState.fail += 1;
          backfillState.last_error = snapshot?.error || "snapshot_failed";
          logLine({ event: "backfill_snapshot_failed", url, snapshot });
          if (win) win.webContents.send("scc:webgptResult", { kind: "backfill_snapshot", ok: false, error: backfillState.last_error, url });
          continue;
        }
        if (snapshot?.debug) logLine({ event: "backfill_snapshot_debug", cid: snapshot.conversation_id, debug: snapshot.debug, url });

        const settings = await loadSettings();
        const intakeRes = await postJsonWithRetry(settings.webgpt_intake_endpoint, snapshot, settings.auth_token, 2);
        if (intakeRes?.ok) backfillState.ok += 1;
        else {
          backfillState.fail += 1;
          backfillState.last_error = intakeRes?.error || "intake_failed";
        }
        if (win) win.webContents.send("scc:webgptResult", { kind: "backfill_intake", cid: snapshot.conversation_id, ...intakeRes });

        if (intakeRes?.ok) {
          const exportRes = await postJsonWithRetry(settings.webgpt_export_endpoint, { conversation_id: snapshot.conversation_id }, settings.auth_token, 2);
          if (win) win.webContents.send("scc:webgptResult", { kind: "backfill_export", cid: snapshot.conversation_id, ...exportRes });
        }

        if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
      }

      backfillState.running = false;
      if (win) win.webContents.send("scc:webgptBackfillProgress", { run_id, phase: "done", total: urls.length });
      if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
      logLine({ event: "backfill_done", ok: backfillState.ok, fail: backfillState.fail, total: urls.length });
    })().catch((e) => {
      backfillState.running = false;
      backfillState.last_error = String(e?.message || e);
      if (win) win.webContents.send("scc:webgptBackfillProgress", { run_id, phase: "error", error: backfillState.last_error });
      if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
      logLine({ event: "backfill_fatal", error: backfillState.last_error });
    });

    return { ok: true, started: true, run_id, state: backfillState };
  } catch (e) {
    backfillState.running = false;
    backfillState.last_error = String(e?.message || e);
    if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
    return { ok: false, error: backfillState.last_error };
  }
}

async function webgptBackfillStop() {
  if (!view) return { ok: false, error: "no_view" };
  if (!backfillState.running) return { ok: true, already_stopped: true, state: backfillState };
  backfillStopFlag = true;
  backfillState.running = false;
  if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
  return { ok: true, stopped: true, state: backfillState };
}

async function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 900,
    backgroundColor: "#0b0f19",
    webPreferences: {
      preload: path.join(__dirname, "preload_ui.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  win.setMenuBarVisibility(false);
  win.setAutoHideMenuBar(true);
  win.removeMenu();

  win.on("resize", layout);
  win.on("maximize", layout);
  win.on("unmaximize", layout);
  win.on("closed", () => {
    win = null;
    view = null;
  });

  await win.loadFile(path.join(__dirname, "index.html"));

  view = new BrowserView({
    webPreferences: {
      preload: path.join(__dirname, "preload_chatgpt.js"),
      contextIsolation: true,
      nodeIntegration: false,
      // NOTE: sandbox=true disables Node APIs in preload, breaking ipc-based DOM capture automation.
      // We keep nodeIntegration=false and contextIsolation=true to limit exposure to the page.
      sandbox: false,
      partition: "persist:scc-chatgpt"
    }
  });

  win.setBrowserView(view);
  layout();

  view.webContents.on("did-navigate", (_e, url) => {
    if (win) win.webContents.send("scc:navigate", { url });
    logLine({ event: "navigate", url });
    if (url) {
      saveHomeUrl(url).catch(() => {});
      flushProcessState().catch(() => {});
    }
    maybeAutoWebGPT(url).catch(() => {});
    maybeAutostartBackfill(url).catch(() => {});

    // If we unexpectedly land on /auth/login but we have a desired home conversation, retry once.
    try {
      const u = new URL(String(url || ""));
      if (String(u.pathname || "").startsWith("/auth/") && desiredHomeUrl && authRedirectRetryCount < 2) {
        authRedirectRetryCount += 1;
        setTimeout(() => {
          if (view) view.webContents.loadURL(desiredHomeUrl).catch(() => {});
        }, 1600);
      }
    } catch {}
  });
  view.webContents.on("did-navigate-in-page", (_e, url) => {
    if (win) win.webContents.send("scc:navigate", { url });
    logLine({ event: "navigate_in_page", url });
    if (url) {
      saveHomeUrl(url).catch(() => {});
      flushProcessState().catch(() => {});
    }
    maybeAutoWebGPT(url).catch(() => {});
    maybeAutostartBackfill(url).catch(() => {});
  });
  view.webContents.on("did-finish-load", () => {
    try {
      const url = view.webContents.getURL();
      if (url) {
        saveHomeUrl(url).catch(() => {});
        flushProcessState().catch(() => {});
      }
      maybeAutoWebGPT(url).catch(() => {});
      maybeAutostartBackfill(url).catch(() => {});
    } catch {}
  });

  // Optional autostart WebGPT backfill: set intent BEFORE initial navigation so we don't miss load events.
  try {
    const raw = String(process.env.SCC_WEBGPT_BACKFILL_AUTOSTART || "").trim().toLowerCase();
    const autostart = raw === "1" || raw === "true" || raw === "yes" || raw === "y" || raw === "on";
    if (autostart) {
      const limit = parseInt(String(process.env.SCC_WEBGPT_BACKFILL_LIMIT || "120"), 10) || 120;
      const scroll_steps = parseInt(String(process.env.SCC_WEBGPT_BACKFILL_SCROLL_STEPS || "30"), 10) || 30;
      pendingBackfillAutostart = { limit, scroll_steps, scroll_delay_ms: 220, per_conv_wait_ms: 15000 };
    }
  } catch {}

  // Prefer explicit boot url, then saved "home url" (last visited), then ChatGPT home.
  const bootUrl =
    (process.env.SCC_CHATGPT_BROWSER_BOOT_URL || "").trim() ||
    (await loadHomeUrl()) ||
    "https://chatgpt.com/";
  // Avoid unhandled rejections if navigation is aborted by redirects.
  await view.webContents.loadURL(bootUrl).catch((e) => {
    logLine({ event: "boot_load_failed", url: bootUrl, error: String(e?.message || e) });
  });

  // Kick once post-load (in case did-finish-load already fired before we set intent).
  try {
    await maybeAutostartBackfill(view.webContents.getURL());
  } catch {}

}

ipcMain.on("scc:uiHeight", (_evt, height) => {
  const h = Number(height);
  if (!Number.isFinite(h) || h <= 0) return;
  toolbarHeight = Math.max(40, Math.min(240, Math.floor(h)));
  layout();
});

ipcMain.handle("scc:getSettings", async () => {
  return await loadSettings();
});

ipcMain.handle("scc:setSettings", async (_evt, partial) => {
  if (!partial || typeof partial !== "object") return await loadSettings();
  const safe = {};
  if (typeof partial.endpoint === "string") safe.endpoint = partial.endpoint;
  if (typeof partial.webgpt_intake_endpoint === "string") safe.webgpt_intake_endpoint = partial.webgpt_intake_endpoint;
  if (typeof partial.webgpt_export_endpoint === "string") safe.webgpt_export_endpoint = partial.webgpt_export_endpoint;
  if (typeof partial.auth_token === "string") safe.auth_token = partial.auth_token;
  if (typeof partial.autosend === "boolean") safe.autosend = partial.autosend;
  const next = await saveSettings(safe);
  return next;
});

ipcMain.handle("scc:sendNow", async () => {
  return await sendNow();
});

ipcMain.handle("scc:copyPayload", async () => {
  const payload = buildPayload(latestSnapshot);
  clipboard.writeText(JSON.stringify(payload, null, 2));
  return { ok: true };
});

ipcMain.handle("scc:webgptSyncNow", async () => {
  return await webgptSyncNow();
});

ipcMain.handle("scc:webgptExportNow", async () => {
  return await webgptExportNow();
});

ipcMain.handle("scc:webgptBackfillStart", async (_evt, opts) => {
  return await webgptBackfillStart(opts);
});

ipcMain.handle("scc:webgptBackfillStop", async () => {
  return await webgptBackfillStop();
});

ipcMain.on("scc:navigate", (_evt, action) => {
  if (!view) return;
  if (action === "back" && view.webContents.canGoBack()) view.webContents.goBack();
  if (action === "forward" && view.webContents.canGoForward()) view.webContents.goForward();
  if (action === "reload") view.webContents.reload();
});

ipcMain.on("scc:openUrl", (_evt, url) => {
  if (!view) return;
  if (typeof url !== "string" || !url.trim()) return;
  const next = url.trim();
  view.webContents.loadURL(next).catch(() => {});
});

ipcMain.on("scc:directives", async (_evt, snapshot) => {
  if (!snapshot || typeof snapshot !== "object") return;
  latestSnapshot = snapshot;
  if (win) win.webContents.send("scc:snapshot", latestSnapshot);
  if (!lastAutosentKey && typeof latestSnapshot.key === "string" && latestSnapshot.key) {
    lastAutosentKey = latestSnapshot.key;
    return;
  }
  await maybeAutosend();
});

ipcMain.on("scc:preloadHello", (_evt, payload) => {
  logLine({ event: "preload_hello", payload: payload || {} });
});

ipcMain.on("scc:chatArchiveSnapshot", (_evt, payload) => {
  const rid = payload && typeof payload.rid === "string" ? payload.rid : "";
  if (!rid) return;
  const pending = pendingChatReq.get(rid);
  if (!pending) return;
  pendingChatReq.delete(rid);
  try {
    clearTimeout(pending.timer);
  } catch {}
  pending.resolve({ ok: true, snapshot: payload.snapshot });
});

ipcMain.on("scc:backfillProgress", (_evt, payload) => {
  if (!payload || typeof payload !== "object") return;
  const run_id = typeof payload.run_id === "string" ? payload.run_id : "";
  if (!run_id || run_id !== backfillState.run_id) return;
  logLine({ event: "backfill_progress", payload });
  if (typeof payload.total === "number" && Number.isFinite(payload.total)) backfillState.total = payload.total;
  if (typeof payload.idx === "number" && Number.isFinite(payload.idx)) backfillState.idx = payload.idx;
  if (typeof payload.error === "string") backfillState.last_error = payload.error;
  if (payload.phase === "done" || payload.phase === "stopped" || payload.phase === "error") backfillState.running = false;
  if (win) win.webContents.send("scc:webgptBackfillProgress", payload);
  if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
});

ipcMain.on("scc:backfillSnapshot", async (_evt, payload) => {
  if (!payload || typeof payload !== "object") return;
  const run_id = typeof payload.run_id === "string" ? payload.run_id : "";
  if (!run_id || run_id !== backfillState.run_id) return;
  logLine({ event: "backfill_snapshot_received", idx: payload.idx, total: payload.total });

  const snapshot = payload.snapshot;
  if (!snapshot || typeof snapshot !== "object" || snapshot.ok !== true) {
    backfillState.fail += 1;
    backfillState.last_error = snapshot?.error || "snapshot_failed";
    if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
    return;
  }

  const settings = await loadSettings();
  const intakeRes = await postJsonWithRetry(settings.webgpt_intake_endpoint, snapshot, settings.auth_token, 2);
  if (intakeRes?.ok) backfillState.ok += 1;
  else {
    backfillState.fail += 1;
    backfillState.last_error = intakeRes?.error || "intake_failed";
  }
  logLine({ event: "backfill_intake_result", ok: !!intakeRes?.ok, status: intakeRes?.status, error: intakeRes?.error });
  if (win) win.webContents.send("scc:webgptResult", { kind: "backfill_intake", cid: snapshot.conversation_id, ...intakeRes });

  // Auto-export after successful intake (best-effort).
  if (intakeRes?.ok) {
    const exportRes = await postJsonWithRetry(
      settings.webgpt_export_endpoint,
      { conversation_id: snapshot.conversation_id },
      settings.auth_token,
      2
    );
    logLine({ event: "backfill_export_result", ok: !!exportRes?.ok, status: exportRes?.status, error: exportRes?.error });
    if (win) win.webContents.send("scc:webgptResult", { kind: "backfill_export", cid: snapshot.conversation_id, ...exportRes });
  }

  if (win) win.webContents.send("scc:webgptBackfillState", backfillState);
});

app.whenReady().then(async () => {
  // Ensure there is exactly one long-lived browser instance to keep login state stable.
  try {
    const got = app.requestSingleInstanceLock();
    if (!got) {
      try {
        app.quit();
      } catch {}
      return;
    }
  } catch {}

  // Start command queue pump to allow server-side control without restarting this process.
  try {
    await loadCommandState();
    setInterval(() => {
      pumpCommandQueue().catch(() => {});
    }, 900);
  } catch {}

  try {
    // Persist liveness so the server can detect an already-open logged-in window across restarts.
    setInterval(() => {
      flushProcessState().catch(() => {});
    }, 2000);
    flushProcessState().catch(() => {});
  } catch {}

  // "Capture once" mode: reuse persisted session (partition "persist:scc-chatgpt") and run a deterministic capture for CI/debug.
  if (hasArg("--webgpt-capture-once")) {
    try {
      const url =
        getArgValue("--url") ||
        String(process.env.SCC_WEBGPT_CAPTURE_URL || "").trim() ||
        "https://chatgpt.com/";
      const doIntake = hasArg("--intake") || String(process.env.SCC_WEBGPT_CAPTURE_INTAKE || "").trim() === "1";
      const doExport = hasArg("--export") || String(process.env.SCC_WEBGPT_CAPTURE_EXPORT || "").trim() === "1";

      const w = new BrowserWindow({
        width: 900,
        height: 740,
        show: false,
      });
      const v = new BrowserView({
        webPreferences: {
          preload: path.join(__dirname, "preload_chatgpt.js"),
          contextIsolation: true,
          nodeIntegration: false,
          sandbox: false,
          partition: "persist:scc-chatgpt",
        }
      });
      w.setBrowserView(v);
      v.setBounds({ x: 0, y: 0, width: 900, height: 740 });
      await v.webContents.loadURL(url);
      await sleep(3500);

      win = w;
      view = v;
      const settings = await loadSettings();
      const cap = await captureCurrentConversation(20000);
      const snapshot = cap?.snapshot;
      logLine({ event: "webgpt_capture_once", ok: !!snapshot?.ok, url: snapshot?.page_url, debug: snapshot?.debug });

      const outDir = path.join(process.cwd(), "artifacts", "webgpt");
      await fs.mkdir(outDir, { recursive: true });
      const outPath = path.join(outDir, `capture_once_${Date.now()}.json`);
      await fs.writeFile(outPath, JSON.stringify({ cap, snapshot }, null, 2), "utf8");
      logLine({ event: "webgpt_capture_once_written", path: outPath });

      if (doIntake && snapshot?.ok) {
        const intakeRes = await postJsonWithRetry(settings.webgpt_intake_endpoint, snapshot, settings.auth_token, 2);
        logLine({ event: "webgpt_capture_once_intake", ...intakeRes });
      }
      if (doExport && snapshot?.ok) {
        const exportRes = await postJsonWithRetry(
          settings.webgpt_export_endpoint,
          { conversation_id: snapshot.conversation_id },
          settings.auth_token,
          2
        );
        logLine({ event: "webgpt_capture_once_export", ...exportRes });
      }
    } catch (e) {
      logLine({ event: "webgpt_capture_once_error", error: String(e?.message || e) });
      try {
        process.exitCode = 2;
      } catch {}
    } finally {
      setTimeout(() => app.quit(), 1500);
    }
    return;
  }

  await createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", async () => {
  if (BrowserWindow.getAllWindows().length === 0) await createWindow();
});
