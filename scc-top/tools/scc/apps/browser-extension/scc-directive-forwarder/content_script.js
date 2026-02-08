const PREFIXES = [
  { type: "SCC_DIRECTIVE_JSON", prefix: "SCC_DIRECTIVE_JSON:" },
  { type: "SCC_APPROVAL_JSON", prefix: "SCC_APPROVAL_JSON:" },
  { type: "SCC_STATUS_REQUEST_JSON", prefix: "SCC_STATUS_REQUEST_JSON:" }
];

let lastSnapshot = { directives: [], errors: [], key: "" };
let lastAutosentKey = "";
let autosendEnabled = false;
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

  return { directives, errors };
}

async function loadAutosend() {
  const stored = await chrome.storage.sync.get({ autosend: false });
  autosendEnabled = !!stored.autosend;
}

function computeKey(pageUrl, assistantText) {
  const head = assistantText.slice(0, 240);
  return `${pageUrl}::${assistantText.length}::${head}`;
}

function renderToast(message, kind) {
  try {
    const id = "scc-forwarder-toast";
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement("div");
      el.id = id;
      el.style.position = "fixed";
      el.style.right = "12px";
      el.style.bottom = "12px";
      el.style.zIndex = "2147483647";
      el.style.maxWidth = "420px";
      el.style.padding = "10px 12px";
      el.style.borderRadius = "12px";
      el.style.font = "12px/1.35 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif";
      el.style.boxShadow = "0 12px 30px rgba(0,0,0,0.35)";
      el.style.border = "1px solid rgba(255,255,255,0.14)";
      el.style.background = "rgba(17, 24, 39, 0.92)";
      el.style.color = "rgba(255,255,255,0.92)";
      document.documentElement.appendChild(el);
    }
    el.textContent = message;
    el.style.borderColor = kind === "bad" ? "rgba(255, 107, 107, 0.8)" : "rgba(46, 204, 113, 0.7)";
    clearTimeout(el._sccTimer);
    el._sccTimer = setTimeout(() => el.remove(), 2800);
  } catch {
    // ignore
  }
}

async function computeSnapshot() {
  const node = findLatestAssistantNode();
  const pageUrl = location.href;
  const assistantText = stableTextFromNode(node);
  const key = computeKey(pageUrl, assistantText);

  if (!assistantText) return { directives: [], errors: [], key };

  const extracted = extractDirectivesFromText(assistantText, pageUrl);
  return { ...extracted, key };
}

async function maybeAutosend(snapshot) {
  if (!autosendEnabled) return;
  if (snapshot.directives.length === 0) return;
  if (snapshot.key === lastAutosentKey) return;

  lastAutosentKey = snapshot.key;
  const payload = {
    source: "chatgpt_extension",
    page_url: snapshot.directives[0]?.page_url || location.href,
    captured_at: snapshot.directives[0]?.captured_at || nowIso(),
    directives: snapshot.directives.map((d) => d.parsed)
  };

  const res = await chrome.runtime.sendMessage({ action: "SCC_POST_PAYLOAD", payload });
  if (res?.ok) renderToast(`SCC auto-sent (${res.status})`, "ok");
  else renderToast(`SCC auto-send failed: ${res?.error || "Unknown error"}`, "bad");
}

async function refreshSnapshot() {
  const snapshot = await computeSnapshot();
  lastSnapshot = snapshot;
  await maybeAutosend(snapshot);
}

function scheduleRefresh() {
  if (scheduled) return;
  scheduled = setTimeout(async () => {
    scheduled = null;
    await refreshSnapshot();
  }, 600);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.action === "SCC_GET_LATEST_DIRECTIVES") {
    sendResponse({
      ok: true,
      directives: lastSnapshot.directives,
      errors: lastSnapshot.errors
    });
    return;
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") return;
  if (Object.prototype.hasOwnProperty.call(changes, "autosend")) {
    autosendEnabled = !!changes.autosend.newValue;
  }
});

(async () => {
  await loadAutosend();
  lastSnapshot = await computeSnapshot();
  lastAutosentKey = lastSnapshot.key;

  const mo = new MutationObserver(() => scheduleRefresh());
  mo.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
})();
