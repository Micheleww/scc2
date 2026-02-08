const $ = sel => document.querySelector(sel)
const esc = s => String(s ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")

function fmtMs(ms) {
  const n = Number(ms)
  if (!Number.isFinite(n) || n < 0) return "-"
  if (n < 1000) return `${Math.floor(n)}ms`
  if (n < 60_000) return `${Math.floor(n / 1000)}s`
  if (n < 3_600_000) return `${Math.floor(n / 60_000)}m`
  return `${Math.floor(n / 3_600_000)}h`
}

function pill(text, cls) {
  return `<span class="pill ${cls ?? ""}">${esc(text)}</span>`
}

function statusPill(s) {
  const v = String(s ?? "").toLowerCase()
  if (["done", "pass", "ok"].includes(v)) return pill(s, "good")
  if (["failed", "fail", "error", "dlq"].includes(v)) return pill(s, "bad")
  if (["running", "queued", "in_progress", "needs_split"].includes(v)) return pill(s, "warn")
  return pill(s, "")
}

function setText(id, val) {
  const el = document.getElementById(id)
  if (el) el.textContent = String(val ?? "-")
}

function setHtml(id, html) {
  const el = document.getElementById(id)
  if (el) el.innerHTML = html
}

function wireTabs() {
  const tabs = Array.from(document.querySelectorAll(".tab"))
  for (const t of tabs) {
    t.addEventListener("click", () => {
      for (const x of tabs) x.classList.remove("active")
      t.classList.add("active")
      const name = t.getAttribute("data-tab")
      for (const body of Array.from(document.querySelectorAll(".tabBody"))) body.classList.remove("active")
      const el = document.getElementById(`tab_${name}`)
      if (el) el.classList.add("active")
    })
  }
}

async function fetchJson(url) {
  const r = await fetch(url, { cache: "no-store" })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

function renderTasks(tasks) {
  const rows = (tasks ?? []).map(t => {
    const id = esc(t.id ?? "")
    const title = esc(t.title ?? "").slice(0, 140)
    const kind = esc(t.kind ?? "")
    const status = statusPill(t.status ?? "")
    const lane = esc(t.lane ?? "")
    const role = esc(t.role ?? "")
    const cls = esc(t.task_class_id ?? t.task_class_candidate ?? "")
    const updated = t.updatedAt ? new Date(t.updatedAt).toLocaleString() : "-"
    return `<tr>
      <td class="mono">${id}</td>
      <td>${kind}</td>
      <td>${status}</td>
      <td>${esc(lane)}</td>
      <td>${esc(role)}</td>
      <td class="mono">${cls}</td>
      <td>${title}</td>
      <td class="mono">${esc(updated)}</td>
    </tr>`
  })
  setHtml("tasksBody", rows.join("") || `<tr><td colspan="8" class="muted">No tasks</td></tr>`)
}

function renderWorkers(workers, jobsById) {
  const now = Date.now()
  const rows = (workers ?? []).map(w => {
    const id = esc(w.id ?? "")
    const name = esc(w.name ?? "")
    const executors = esc((w.executors ?? []).join(","))
    const models = esc((w.models ?? []).slice(0, 6).join(","))
    const lastSeen = typeof w.lastSeen === "number" ? fmtMs(now - w.lastSeen) : "-"
    const runningJobId = w.runningJobId ? esc(w.runningJobId) : ""
    const job = runningJobId ? jobsById.get(runningJobId) : null
    const jobSummary = job ? `${esc(job.executor ?? "")}/${esc(job.model_effective ?? job.model ?? "")} ${esc(job.taskType ?? "")}` : "-"
    const lease = job && typeof job.leaseUntil === "number" ? fmtMs(job.leaseUntil - now) : "-"
    return `<tr>
      <td><div class="mono">${id}</div><div class="muted">${name}</div></td>
      <td>${executors}</td>
      <td class="mono">${models}</td>
      <td class="mono">${lastSeen}</td>
      <td><div class="mono">${runningJobId || "-"}</div><div class="muted">${esc(jobSummary)}</div></td>
      <td class="mono">${lease}</td>
    </tr>`
  })
  setHtml("workersBody", rows.join("") || `<tr><td colspan="6" class="muted">No workers</td></tr>`)
}

function renderEvents(events) {
  const rows = (events ?? []).map(e => {
    const t = esc(e.t ?? "")
    const type = esc(e.event_type ?? e.type ?? "")
    const task = esc(e.task_id ?? "")
    const cls = esc(e.task_class ?? "")
    const executor = esc(e.executor ?? "")
    const model = esc(e.model ?? "")
    const exit = e.exit_code != null ? esc(e.exit_code) : ""
    const notes = esc(e.notes ?? e.reason ?? "")
    return `<tr>
      <td class="mono">${t}</td>
      <td>${statusPill(type)}</td>
      <td class="mono">${task}</td>
      <td class="mono">${cls}</td>
      <td>${executor}</td>
      <td class="mono">${model}</td>
      <td class="mono">${exit}</td>
      <td>${notes}</td>
    </tr>`
  })
  setHtml("eventsBody", rows.join("") || `<tr><td colspan="8" class="muted">No events</td></tr>`)
}

function summarizeObj(obj) {
  if (!obj || typeof obj !== "object") return "-"
  const parts = []
  for (const [k, v] of Object.entries(obj)) parts.push(`${k}=${v}`)
  return parts.join(" ")
}

async function refresh() {
  const snap = await fetchJson("/sccdev/api/v1/snapshot?tasks=200&events=120&jobs=200")
  setText("lastUpdated", `Last updated: ${new Date().toLocaleTimeString()}`)
  setText("repoRoot", snap.repoRoot ?? "-")
  setText("degradation", snap.factory?.degradation?.action?.action ?? snap.factory?.degradation?.action ?? "-")
  setText("stopBleeding", String(snap.factory?.repo_health?.stop_the_bleeding ?? "-"))
  setText("wipLimits", summarizeObj(snap.factory?.wip?.limits))
  setText("wipEffective", summarizeObj(snap.factory?.wip?.effective_limits))
  setText("wipRunning", summarizeObj(snap.factory?.wip?.running?.by_lane))

  setText("boardCounts", summarizeObj(snap.board?.counts))
  setText("jobCounts", summarizeObj(snap.executor?.jobs?.byStatus))
  setText("workerCounts", summarizeObj(snap.executor?.workers?.byExecutorActive))

  setText("codexDefault", snap.models?.codexDefault ?? "-")
  setText("codexPreferred", (snap.models?.codexPreferred ?? []).join(",") || "-")
  setText("routerStats", snap.models?.routerStatsSummary ?? "-")

  renderTasks(snap.board?.tasks ?? [])

  const jobsById = new Map((snap.executor?.jobs?.items ?? []).map(j => [String(j.id), j]))
  renderWorkers(snap.executor?.workers?.items ?? [], jobsById)
  renderEvents(snap.events?.items ?? [])
}

function boot() {
  wireTabs()
  $("#btnRefresh")?.addEventListener("click", () => refresh().catch(console.error))
  refresh().catch(console.error)
  setInterval(() => refresh().catch(() => {}), 2500)
}

boot()

