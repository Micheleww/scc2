const { ipcRenderer } = require("electron");

const PREFIXES = [
  { type: "SCC_DIRECTIVE_JSON", prefix: "SCC_DIRECTIVE_JSON:" },
  { type: "SCC_APPROVAL_JSON", prefix: "SCC_APPROVAL_JSON:" },
  { type: "SCC_STATUS_REQUEST_JSON", prefix: "SCC_STATUS_REQUEST_JSON:" }
];

let lastKey = "";
let scheduled = null;

function nowIso() {
  return new Date().toISOString();
}

function stableTextFromNode(node) {
  if (!node) return "";
  const txt = node.innerText || node.textContent || "";
  return String(txt).replace(/\r\n/g, "\n").trim();
}

function findLatestAssistantNode() {
  const byRole = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
  if (byRole.length > 0) return byRole[byRole.length - 1];

  const main = document.querySelector("main") || document.body;
  const articles = Array.from(main.querySelectorAll("article"));
  if (articles.length === 0) return null;

  const filtered = articles.filter((a) => !a.querySelector('[data-message-author-role="user"]'));
  return (filtered.length ? filtered : articles)[(filtered.length ? filtered : articles).length - 1];
}

function captureJson(text, startIndex) {
  let i = startIndex;
  while (i < text.length && /\s/.test(text[i])) i++;
  if (i >= text.length) return { ok: false, error: "Missing JSON after prefix" };
  const first = text[i];
  if (first !== "{" && first !== "[") return { ok: false, error: `Expected '{' or '[' but got '${first}'` };

  const stack = [first];
  let inString = false;
  let escape = false;

  for (let j = i + 1; j < text.length; j++) {
    const ch = text[j];
    if (inString) {
      if (escape) {
        escape = false;
        continue;
      }
      if (ch === "\\\\") {
        escape = true;
        continue;
      }
      if (ch === '"') {
        inString = false;
        continue;
      }
      continue;
    }

    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "{" || ch === "[") {
      stack.push(ch);
      continue;
    }
    if (ch === "}" || ch === "]") {
      const top = stack[stack.length - 1];
      const match = (top === "{" && ch === "}") || (top === "[" && ch === "]");
      if (!match) return { ok: false, error: "Mismatched JSON brackets" };
      stack.pop();
      if (stack.length === 0) {
        const raw = text.slice(i, j + 1);
        return { ok: true, raw, endIndex: j + 1 };
      }
      continue;
    }
  }

  return { ok: false, error: "Unterminated JSON block" };
}

function extractDirectivesFromText(text, pageUrl) {
  const directives = [];
  const errors = [];
  const capturedAt = nowIso();
  const prefixSet = new Map(PREFIXES.map((p) => [p.prefix, p.type]));
  const re = /(^|\n)[ \t]*(SCC_DIRECTIVE_JSON:|SCC_APPROVAL_JSON:|SCC_STATUS_REQUEST_JSON:)/g;

  let m;
  while ((m = re.exec(text))) {
    const prefix = m[2];
    const type = prefixSet.get(prefix) || prefix.replace(/:$/, "");
    const start = re.lastIndex;
    const cap = captureJson(text, start);
    if (!cap.ok) {
      errors.push({ type, error: cap.error });
      continue;
    }
    try {
      const parsed = JSON.parse(cap.raw);
      directives.push({
        type,
        parsed,
        raw: cap.raw,
        captured_at: capturedAt,
        page_url: pageUrl
      });
      re.lastIndex = cap.endIndex;
    } catch (e) {
      errors.push({ type, error: `JSON.parse failed: ${String(e?.message || e)}` });
      re.lastIndex = cap.endIndex;
    }
  }

  return { directives, errors, capturedAt };
}

function computeKey(pageUrl, assistantText) {
  const head = assistantText.slice(0, 240);
  return `${pageUrl}::${assistantText.length}::${head}`;
}

function computeSnapshot() {
  const node = findLatestAssistantNode();
  const pageUrl = location.href;
  const assistantText = stableTextFromNode(node);
  const key = computeKey(pageUrl, assistantText);

  if (!assistantText) {
    return { directives: [], errors: [], key, page_url: pageUrl, captured_at: nowIso() };
  }

  const extracted = extractDirectivesFromText(assistantText, pageUrl);
  return {
    directives: extracted.directives,
    errors: extracted.errors,
    key,
    page_url: pageUrl,
    captured_at: extracted.capturedAt
  };
}

function scheduleRefresh() {
  if (scheduled) return;
  scheduled = setTimeout(() => {
    scheduled = null;
    try {
      const snapshot = computeSnapshot();
      if (snapshot.key !== lastKey) {
        lastKey = snapshot.key;
        ipcRenderer.send("scc:directives", snapshot);
      }
    } catch {
      // ignore
    }
  }, 650);
}

function start() {
  try {
    const snapshot = computeSnapshot();
    lastKey = snapshot.key;
    ipcRenderer.send("scc:directives", snapshot);
  } catch {
    // ignore
  }

  const mo = new MutationObserver(() => scheduleRefresh());
  mo.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
}

window.addEventListener("DOMContentLoaded", () => start());

// WebGPT capture (visible DOM only): extract current conversation messages for local archiving.
function getConversationId() {
  const m = location.pathname.match(/^\\/c\\/([^\\/]+)/);
  return m ? m[1] : null;
}

function getConversationTitle() {
  const t = document.title || "";
  return t.replace(" | ChatGPT", "").trim() || null;
}

function extractVisibleMessages() {
  const nodes = Array.from(document.querySelectorAll("[data-message-author-role]"));
  const messages = [];
  for (const node of nodes) {
    const roleAttr = (node.getAttribute("data-message-author-role") || "assistant").toLowerCase();
    const role = roleAttr === "user" ? "user" : roleAttr === "assistant" ? "assistant" : "assistant";

    const codeBlocks = Array.from(node.querySelectorAll("pre code")).map((c) => (c.innerText || "").trim()).filter(Boolean);
    const md = node.querySelector(".markdown, [data-testid='conversation-turn'] .markdown");
    const text = (md ? md.innerText : node.innerText || "").trim();

    const msgId = node.getAttribute("data-message-id") || node.id || null;
    const content_json = codeBlocks.length ? { code_blocks: codeBlocks } : null;

    messages.push({
      message_id: msgId,
      role,
      created_at: null,
      content_text: text,
      content_json
    });
  }
  return messages;
}

function computeChatArchiveSnapshot() {
  const conversation_id = getConversationId();
  const title = getConversationTitle();
  if (!conversation_id) return { ok: false, error: "not_on_conversation_page" };
  const messages = extractVisibleMessages().filter((m) => m.content_text && m.content_text.trim());
  return {
    ok: true,
    conversation_id,
    title,
    source: "webgpt_embedded_browser",
    page_url: location.href,
    captured_at: nowIso(),
    messages
  };
}

ipcRenderer.on("scc:requestChatArchiveSnapshot", (_evt, req) => {
  const rid = req && typeof req.rid === "string" ? req.rid : "";
  try {
    const snap = computeChatArchiveSnapshot();
    ipcRenderer.send("scc:chatArchiveSnapshot", { rid, snapshot: snap });
  } catch (e) {
    ipcRenderer.send("scc:chatArchiveSnapshot", { rid, snapshot: { ok: false, error: String(e?.message || e) } });
  }
});

// WebGPT backfill (best-effort): iterate sidebar conversations, open each, scroll to load, capture, forward snapshots.
let __backfillStop = false;

function parseBoolEnv(name, fallback) {
  const raw = String(process.env[name] || "").trim().toLowerCase();
  if (!raw) return fallback;
  if (raw === "1" || raw === "true" || raw === "yes" || raw === "y" || raw === "on") return true;
  if (raw === "0" || raw === "false" || raw === "no" || raw === "n" || raw === "off") return false;
  return fallback;
}

function parseIntEnv(name, fallback) {
  const raw = String(process.env[name] || "").trim();
  if (!raw) return fallback;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? n : fallback;
}

async function runBackfill(opts) {
  __backfillStop = false;
  const run_id = (opts && typeof opts.run_id === "string" && opts.run_id) || nowIso();
  const limit = opts && typeof opts.limit !== "undefined" ? opts.limit : 200;
  const scroll_steps = opts && typeof opts.scroll_steps !== "undefined" ? opts.scroll_steps : 30;
  const scroll_delay_ms = opts && typeof opts.scroll_delay_ms !== "undefined" ? opts.scroll_delay_ms : 220;
  const per_conv_wait_ms = opts && typeof opts.per_conv_wait_ms !== "undefined" ? opts.per_conv_wait_ms : 15000;

  const urls = listConversationUrls(limit);
  ipcRenderer.send("scc:backfillProgress", { run_id, phase: "discovered", total: urls.length });
  if (!urls.length) {
    ipcRenderer.send("scc:backfillProgress", { run_id, phase: "error", error: "no_conversations_found (maybe not logged in?)" });
    return;
  }

  for (let idx = 0; idx < urls.length; idx++) {
    if (__backfillStop) {
      ipcRenderer.send("scc:backfillProgress", { run_id, phase: "stopped", idx, total: urls.length });
      return;
    }
    const url = urls[idx];
    ipcRenderer.send("scc:backfillProgress", { run_id, phase: "open", idx, total: urls.length, url });
    try {
      location.assign(url);
    } catch {
      window.location.href = url;
    }
    const cid = await waitForConversationPage(per_conv_wait_ms);
    if (!cid) {
      ipcRenderer.send("scc:backfillProgress", { run_id, phase: "skip", idx, total: urls.length, url, error: "timeout_wait_conversation" });
      continue;
    }
    await scrollLoadOlderMessages(scroll_steps, scroll_delay_ms);
    const snap = computeChatArchiveSnapshot();
    ipcRenderer.send("scc:backfillSnapshot", { run_id, idx, total: urls.length, snapshot: snap });
    await new Promise((r) => setTimeout(r, 250));
  }

  ipcRenderer.send("scc:backfillProgress", { run_id, phase: "done", total: urls.length });
}

function listConversationUrls(limit) {
  const max = Math.max(1, Math.min(2000, Number(limit) || 200));
  const anchors = Array.from(document.querySelectorAll('a[href^="/c/"]'));
  const urls = [];
  const seen = new Set();
  for (const a of anchors) {
    const href = (a.getAttribute("href") || "").trim();
    if (!href.startsWith("/c/")) continue;
    const u = new URL(href, location.origin).toString();
    if (seen.has(u)) continue;
    seen.add(u);
    urls.push(u);
    if (urls.length >= max) break;
  }
  return urls;
}

async function waitForConversationPage(timeoutMs) {
  const deadline = Date.now() + Math.max(1000, timeoutMs || 12000);
  while (Date.now() < deadline) {
    const cid = getConversationId();
    if (cid) return cid;
    await new Promise((r) => setTimeout(r, 250));
  }
  return null;
}

async function scrollLoadOlderMessages(steps, delayMs) {
  const n = Math.max(0, Math.min(250, Number(steps) || 0));
  const d = Math.max(60, Math.min(1500, Number(delayMs) || 200));
  const target = document.querySelector("main") || document.scrollingElement || document.documentElement;
  for (let i = 0; i < n; i++) {
    if (__backfillStop) return;
    try {
      target.scrollTop = 0;
      window.scrollTo(0, 0);
    } catch {}
    await new Promise((r) => setTimeout(r, d));
  }
}

ipcRenderer.on("scc:backfillStop", () => {
  __backfillStop = true;
});

ipcRenderer.on("scc:backfillStart", async (_evt, opts) => {
  try {
    await runBackfill(opts || {});
  } catch (e) {
    ipcRenderer.send("scc:backfillProgress", { run_id: nowIso(), phase: "error", error: String(e?.message || e) });
  }
});

// Autostart (hands-free): if env is true, start after load with configured defaults.
window.addEventListener("DOMContentLoaded", () => {
  // Preload health ping (for debugging capture automation).
  setTimeout(() => {
    try {
      const urls = (() => {
        try {
          return listConversationUrls(12);
        } catch {
          return [];
        }
      })();
      let envAutostart = null;
      let envLimit = null;
      let envScroll = null;
      try {
        envAutostart = String(process.env.SCC_WEBGPT_BACKFILL_AUTOSTART || "");
        envLimit = String(process.env.SCC_WEBGPT_BACKFILL_LIMIT || "");
        envScroll = String(process.env.SCC_WEBGPT_BACKFILL_SCROLL_STEPS || "");
      } catch {}
      ipcRenderer.send("scc:preloadHello", {
        url: String(location.href || ""),
        has_conversation_id: !!getConversationId(),
        discovered_urls: urls.length,
        sample_url: urls[0] || "",
        env_autostart: envAutostart,
        env_limit: envLimit,
        env_scroll_steps: envScroll
      });
    } catch {
      // ignore
    }
  }, 1200);

  const autostart = parseBoolEnv("SCC_WEBGPT_BACKFILL_AUTOSTART", false);
  if (!autostart) return;
  const limit = parseIntEnv("SCC_WEBGPT_BACKFILL_LIMIT", 120);
  const scroll_steps = parseIntEnv("SCC_WEBGPT_BACKFILL_SCROLL_STEPS", 30);
  setTimeout(() => {
    runBackfill({ limit, scroll_steps, scroll_delay_ms: 220, per_conv_wait_ms: 15000 }).catch(() => {});
  }, 1200);
});
