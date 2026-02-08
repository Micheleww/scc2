import fs from "node:fs"
import path from "node:path"
import { execFileSync } from "node:child_process"
import { computeMapHash, loadMapV1, queryMapV1 } from "./map_v1.mjs"

function normPosixRel(p) {
  const s = String(p ?? "").trim().replaceAll("\\", "/").replace(/^\.\/+/, "")
  if (!s) return null
  if (s.includes("..")) return null
  if (s.startsWith("/")) return null
  if (/^[a-zA-Z]:\//.test(s)) return null
  return s
}

function fileExists(repoRoot, rel) {
  try {
    const abs = path.join(repoRoot, rel)
    return fs.existsSync(abs) && fs.statSync(abs).isFile()
  } catch {
    return false
  }
}

function stableUniq(list) {
  const out = []
  const seen = new Set()
  for (const v of list) {
    const s = String(v ?? "")
    if (!s) continue
    if (seen.has(s)) continue
    seen.add(s)
    out.push(s)
  }
  return out
}

function extractKeywordTokens(text, { max = 24 } = {}) {
  const s = String(text ?? "")
  const out = []
  const seen = new Set()
  const re = /[A-Za-z_][A-Za-z0-9_./-]{2,}/g
  let m
  while ((m = re.exec(s))) {
    const t = String(m[0] ?? "").trim()
    if (!t) continue
    const lower = t.toLowerCase()
    if (seen.has(lower)) continue
    seen.add(lower)
    out.push(t)
    if (out.length >= max) break
  }
  out.sort((a, b) => a.localeCompare(b))
  return out
}

function inferQueries({ child_task, signals }) {
  const q = []
  const title = String(child_task?.title ?? "")
  const goal = String(child_task?.goal ?? "")
  q.push(...extractKeywordTokens(`${title}\n${goal}`, { max: 40 }))

  const files = Array.isArray(child_task?.files) ? child_task.files : []
  for (const f0 of files) {
    const f = normPosixRel(f0)
    if (!f) continue
    q.push(f)
    q.push(path.posix.basename(f))
    const dir = path.posix.dirname(f)
    if (dir && dir !== ".") q.push(dir)
  }

  const tests = Array.isArray(child_task?.allowedTests) ? child_task.allowedTests : []
  for (const c0 of tests) {
    const c = String(c0 ?? "").trim()
    if (!c) continue
    q.push(...extractKeywordTokens(c, { max: 18 }))
  }

  const sig = signals && typeof signals === "object" ? signals : {}
  const failing = typeof sig.failing_test === "string" ? sig.failing_test : null
  if (failing) q.push(...extractKeywordTokens(failing, { max: 12 }))
  const keywords = Array.isArray(sig.keywords) ? sig.keywords : []
  for (const kw of keywords) q.push(...extractKeywordTokens(String(kw ?? ""), { max: 6 }))
  const stack = typeof sig.stacktrace === "string" ? sig.stacktrace : null
  if (stack) q.push(...extractKeywordTokens(stack, { max: 18 }))

  return stableUniq(q.filter(Boolean)).slice(0, 80)
}

function pickCandidatesFromQueries({ map, queries, perQueryLimit = 12, maxCandidates = 80 }) {
  const scored = []
  const kindBoost = (k) => {
    if (k === "key_symbol") return 3.0
    if (k === "entry_point") return 2.0
    if (k === "test_entry") return 1.8
    if (k === "config") return 1.2
    if (k === "module") return 0.6
    return 1.0
  }
  for (const q of queries) {
    const out = queryMapV1({ map, q, limit: perQueryLimit })
    if (!out?.ok) continue
    for (const r of Array.isArray(out.results) ? out.results : []) {
      const p = r?.path ? normPosixRel(r.path) : null
      if (!p) continue
      const base = Number(r.score ?? 0)
      const score = base * kindBoost(String(r.kind ?? ""))
      scored.push({
        score,
        kind: String(r.kind ?? ""),
        id: String(r.id ?? ""),
        path: p,
        symbol: r.symbol ? String(r.symbol) : null,
        line: Number.isFinite(Number(r.line)) ? Number(r.line) : null,
      })
      if (scored.length >= maxCandidates * 4) break
    }
  }
  scored.sort((a, b) => {
    const ds = Number(b.score ?? 0) - Number(a.score ?? 0)
    if (ds !== 0) return ds
    const ak = String(a.kind).localeCompare(String(b.kind))
    if (ak !== 0) return ak
    const ap = String(a.path).localeCompare(String(b.path))
    if (ap !== 0) return ap
    return String(a.id).localeCompare(String(b.id))
  })
  return scored.slice(0, Math.max(1, maxCandidates))
}

function querySqliteBatch({ repoRoot, dbPathRel = "map/map.sqlite", queries, perQueryLimit, maxCandidates }) {
  const root = path.resolve(repoRoot || process.cwd())
  const dbAbs = path.resolve(root, dbPathRel)
  if (!fs.existsSync(dbAbs)) return { ok: false, error: "missing_sqlite", db: dbPathRel }

  const req = {
    queries: Array.isArray(queries) ? queries.map((x) => String(x ?? "")).filter(Boolean) : [],
  }
  const raw = JSON.stringify(req)
  try {
    const stdout = execFileSync(
      "python",
      [
        "tools/scc/map/map_query_sqlite_batch_v1.py",
        "--repo-root",
        root,
        "--db",
        dbPathRel,
        "--limit-per-query",
        String(perQueryLimit ?? 12),
        "--max-results",
        String(maxCandidates ?? 120),
      ],
      { cwd: root, input: raw, encoding: "utf8", windowsHide: true, timeout: 60000, maxBuffer: 10 * 1024 * 1024 },
    )
    const out = JSON.parse(String(stdout ?? "").replace(/^\uFEFF/, ""))
    if (!out || typeof out !== "object" || out.ok !== true) return { ok: false, error: "sqlite_query_bad_output" }
    return { ok: true, results: Array.isArray(out.results) ? out.results : [] }
  } catch (e) {
    return { ok: false, error: "sqlite_query_failed", message: String(e?.message ?? e) }
  }
}

function expandWindow(line, { defaultWindow }) {
  const ln = Math.max(1, Number(line ?? 1))
  const w = Math.max(20, Math.min(800, Math.floor(Number(defaultWindow ?? 120))))
  const half = Math.floor(w / 2)
  return [Math.max(1, ln - half), ln + half]
}

function addWindow(lineWindows, file, win) {
  const f = String(file)
  if (!f) return
  const w = Array.isArray(win) ? win : null
  if (!w || w.length !== 2) return
  const s = Math.max(1, Math.floor(Number(w[0] ?? 1)))
  const e = Math.max(s, Math.floor(Number(w[1] ?? s)))
  const arr = lineWindows[f] ?? []
  const key = `${s}:${e}`
  if (arr.some((x) => Array.isArray(x) && `${x[0]}:${x[1]}` === key)) return
  arr.push([s, e])
  arr.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]))
  lineWindows[f] = arr.slice(0, 8)
}

export function buildPinsFromMapV1({ repoRoot, request, budgets = null } = {}) {
  const root = path.resolve(repoRoot || process.cwd())
  const req = request && typeof request === "object" ? request : null
  if (!req) return { ok: false, error: "missing_request" }
  const taskId = String(req.task_id ?? "").trim()
  if (!taskId) return { ok: false, error: "missing_task_id" }
  const child = req.child_task && typeof req.child_task === "object" ? req.child_task : null
  if (!child) return { ok: false, error: "missing_child_task" }

  const mapRef = req.map_ref && typeof req.map_ref === "object" ? req.map_ref : null
  const mapPathRel = mapRef?.path ? String(mapRef.path) : "map/map.json"
  const mapHashDeclared = mapRef?.hash ? String(mapRef.hash) : null

  let mapLoaded
  try {
    mapLoaded = loadMapV1({ repoRoot: root, mapPath: mapPathRel })
  } catch (e) {
    return { ok: false, error: "map_load_failed", message: String(e?.message ?? e), map_path: mapPathRel }
  }
  const map = mapLoaded?.data
  if (!map || typeof map !== "object") return { ok: false, error: "map_invalid", map_path: mapPathRel }
  const mapHash = computeMapHash(map)
  if (mapHashDeclared && mapHashDeclared !== mapHash) {
    return {
      ok: false,
      error: "map_hash_mismatch",
      expected: mapHashDeclared,
      got: mapHash,
      hint: "Map is out of date; rebuild map/map.json + map/version.json, then retry.",
    }
  }

  const sig = req.signals && typeof req.signals === "object" ? req.signals : {}
  const cfg = budgets && typeof budgets === "object" ? budgets : req.budgets && typeof req.budgets === "object" ? req.budgets : {}
  const maxFiles = Math.max(1, Math.min(60, Math.floor(Number(cfg.max_files ?? cfg.maxFiles ?? 20) || 20)))
  const maxLoc = Math.max(60, Math.min(2000, Math.floor(Number(cfg.max_loc ?? cfg.maxLoc ?? 240) || 240)))
  const defaultWindow = Math.max(40, Math.min(600, Math.floor(Number(cfg.default_line_window ?? cfg.defaultLineWindow ?? 140) || 140)))

  const requiredFilesRaw = Array.isArray(child.files) ? child.files : []
  const requiredFiles = stableUniq(requiredFilesRaw.map(normPosixRel).filter(Boolean))

  const missingOnDisk = requiredFiles.filter((f) => !fileExists(root, f))
  if (missingOnDisk.length) {
    return { ok: false, error: "required_files_missing", missing_files: missingOnDisk.slice(0, 20) }
  }

  const queries = inferQueries({ child_task: child, signals: sig })
  const preferSqlite = String(process.env.MAP_PINS_QUERY_BACKEND ?? "").toLowerCase() === "sqlite" || String(process.env.MAP_QUERY_BACKEND ?? "").toLowerCase() === "sqlite"
  const sqliteStrictMode = (() => {
    const v = String(process.env.MAP_PINS_QUERY_STRICT ?? "auto").toLowerCase()
    if (v === "auto") return preferSqlite
    return v === "1" || v === "true" || v === "yes" || v === "on"
  })()
  const sqliteAvailable = fs.existsSync(path.join(root, "map", "map.sqlite"))
  if (preferSqlite && !sqliteAvailable && sqliteStrictMode) {
    return {
      ok: false,
      error: "sqlite_required_missing",
      message:
        "MAP_PINS_QUERY_BACKEND=sqlite but map/map.sqlite is missing. Rebuild map with sqlite (e.g. `npm --prefix oc-scc-local run map:build`) and retry.",
    }
  }
  let queryBackendUsed = "json"
  let candidates = []
  if (preferSqlite && sqliteAvailable) {
    const q = querySqliteBatch({ repoRoot: root, dbPathRel: "map/map.sqlite", queries, perQueryLimit: 12, maxCandidates: 120 })
    if (q.ok) {
      candidates = Array.isArray(q.results) ? q.results : []
      queryBackendUsed = "sqlite"
    } else if (sqliteStrictMode) {
      return { ok: false, error: "sqlite_query_failed", details: q }
    }
  }
  if (!candidates.length) {
    candidates = pickCandidatesFromQueries({ map, queries, perQueryLimit: 12, maxCandidates: 120 })
  }

  const allowedPaths = []
  const lineWindows = {}
  const symbols = []
  const pathReasons = new Map()

  const recordReason = (file, why) => {
    if (!file) return
    const cur = pathReasons.get(file) ?? []
    if (why && !cur.includes(why)) {
      cur.push(why)
      pathReasons.set(file, cur)
    }
  }

  const addFile = (f, why) => {
    const file = normPosixRel(f)
    if (!file) return false
    if (!fileExists(root, file)) return false
    recordReason(file, why)
    if (allowedPaths.includes(file)) return true
    if (allowedPaths.length >= maxFiles) return false
    allowedPaths.push(file)
    addWindow(lineWindows, file, [1, defaultWindow])
    return true
  }

  for (const f of requiredFiles) addFile(f, "required:child_task.files")

  for (const c of candidates) {
    if (allowedPaths.length >= maxFiles) break
    addFile(c.path, `map:${c.kind}`)
    if (c.kind === "key_symbol" && c.symbol) {
      symbols.push(c.symbol)
      if (Number.isFinite(c.line)) addWindow(lineWindows, c.path, expandWindow(c.line, { defaultWindow }))
    }
  }

  const allowedFinal = stableUniq(allowedPaths).slice(0, maxFiles)
  allowedFinal.sort((a, b) => a.localeCompare(b))
  const symFinal = stableUniq(symbols).slice(0, 64)
  symFinal.sort((a, b) => a.localeCompare(b))

  if (!allowedFinal.length) return { ok: false, error: "no_candidates" }

  // Ensure line_windows only references allowed paths.
  const windowsFinal = {}
  for (const f of allowedFinal) {
    const wins = Array.isArray(lineWindows[f]) ? lineWindows[f] : []
    windowsFinal[f] = wins.length ? wins : [[1, defaultWindow]]
  }

  const pins = {
    allowed_paths: allowedFinal,
    forbidden_paths: [".git", "node_modules", "dist", "build", "coverage", "artifacts", "_tmp"],
    symbols: symFinal,
    line_windows: windowsFinal,
    max_files: Math.max(1, Math.min(100, allowedFinal.length)),
    max_loc: maxLoc,
    ssot_assumptions: [],
  }

  const recommended_queries = queries.slice(0, 12)
  const preflight_expectation = {
    required: true,
    notes: "Pins are map-derived. Preflight should ensure: (1) child_task.files ⊆ pins.allowed_paths, (2) allowedTests validate, (3) role policy write scope is satisfied.",
    map_hash: mapHash,
  }

  const result = {
    schema_version: "scc.pins_result.v1",
    task_id: taskId,
    pins,
    recommended_queries,
    preflight_expectation,
  }

  const detail = {
    schema_version: "scc.pins_detail.v1",
    task_id: taskId,
    map_ref: { path: mapPathRel, hash: mapHash },
    query_backend: queryBackendUsed,
    sqlite: { preferred: preferSqlite, strict: sqliteStrictMode, available: sqliteAvailable, db: "map/map.sqlite" },
    budgets: { max_files: maxFiles, max_loc: maxLoc, default_line_window: defaultWindow },
    required_files: requiredFiles,
    queries,
    candidates: candidates.slice(0, 60),
    file_reasons: Object.fromEntries(
      allowedFinal.map((f) => [f, (pathReasons.get(f) ?? []).slice(0, 6)])
    ),
  }

  // Pins v2 (audited pins): each pin must carry reason + read_only/write_intent for auditable gates.
  const requiredSet = new Set(Array.isArray(detail.required_files) ? detail.required_files.map((x) => String(x)) : [])
  const symbolsByFile = new Map()
  try {
    for (const c of Array.isArray(detail.candidates) ? detail.candidates : []) {
      if (!c || typeof c !== "object") continue
      if (String(c.kind ?? "") !== "key_symbol") continue
      const p = normPosixRel(c.path)
      const sym = c.symbol ? String(c.symbol) : null
      if (!p || !sym) continue
      const arr = symbolsByFile.get(p) ?? []
      if (!arr.includes(sym)) arr.push(sym)
      symbolsByFile.set(p, arr)
    }
  } catch {
    // ignore
  }

  const pinItems = allowedFinal.map((file) => {
    const reasons = detail?.file_reasons && typeof detail.file_reasons === "object" ? detail.file_reasons[file] : null
    const reasonText = Array.isArray(reasons) && reasons.length ? reasons.join("; ") : "map-derived candidate"
    const write_intent = requiredSet.has(file)
    const read_only = !write_intent
    const line_windows = Array.isArray(windowsFinal[file]) ? windowsFinal[file] : [[1, defaultWindow]]
    const fileSyms = symbolsByFile.get(file) ?? []
    return {
      path: file,
      reason: reasonText,
      read_only,
      write_intent,
      symbols: stableUniq(fileSyms).slice(0, 24),
      line_windows,
    }
  })

  const pins_v2 = {
    items: pinItems,
    allowed_paths: pins.allowed_paths,
    forbidden_paths: pins.forbidden_paths,
    symbols: pins.symbols,
    line_windows: pins.line_windows,
    max_files: pins.max_files,
    max_loc: pins.max_loc,
    ssot_assumptions: pins.ssot_assumptions,
  }

  const result_v2 = {
    schema_version: "scc.pins_result.v2",
    task_id: taskId,
    pins: pins_v2,
    recommended_queries,
    preflight_expectation,
  }

  return { ok: true, result, result_v2, pins, pins_v2, detail }
}

export function writePinsV1Outputs({ repoRoot, taskId, outDir, pinsResult, pinsSpec, detail } = {}) {
  const root = path.resolve(repoRoot || process.cwd())
  const id = String(taskId ?? "").trim()
  if (!id) return { ok: false, error: "missing_task_id" }
  const base = path.resolve(root, outDir || path.join("artifacts", id, "pins"))
  fs.mkdirSync(base, { recursive: true })
  const pinsPath = path.join(base, "pins.json")
  const pinsSpecPath = path.join(base, "pins_spec.json")
  const detailPath = path.join(base, "pins_detail.json")
  const pinsMdPath = path.join(base, "pins.md")

  const spec = (pinsSpec && typeof pinsSpec === "object" ? pinsSpec : null) ??
    (pinsResult && typeof pinsResult === "object" && pinsResult.pins && typeof pinsResult.pins === "object" ? pinsResult.pins : null) ??
    {}
  const result =
    pinsResult && typeof pinsResult === "object"
      ? pinsResult
      : { schema_version: "scc.pins_result.v1", task_id: id, pins: spec }

  fs.writeFileSync(pinsPath, JSON.stringify(result, null, 2) + "\n", "utf8")
  fs.writeFileSync(pinsSpecPath, JSON.stringify(spec ?? {}, null, 2) + "\n", "utf8")
  if (detail) fs.writeFileSync(detailPath, JSON.stringify(detail, null, 2) + "\n", "utf8")
  try {
    const allowed = Array.isArray(spec?.allowed_paths) ? spec.allowed_paths : []
    const lineWins = spec?.line_windows && typeof spec.line_windows === "object" ? spec.line_windows : {}
    const reasons = detail?.file_reasons && typeof detail.file_reasons === "object" ? detail.file_reasons : {}
    const rows = allowed.map((p) => {
      const wins = Array.isArray(lineWins[p]) ? lineWins[p].map((w) => Array.isArray(w) ? `${w[0]}-${w[1]}` : "").filter(Boolean) : []
      const reasonList = Array.isArray(reasons[p]) ? reasons[p] : []
      const winText = wins.length ? wins.join(", ") : "-"
      const reasonText = reasonList.length ? reasonList.join("; ") : "-"
      return `| \`${p}\` | ${winText} | ${reasonText} |`
    })
    const md = [
      "# pins",
      "",
      "| path | line_windows | reasons |",
      "| --- | --- | --- |",
      ...rows,
      "",
      `max_files: ${spec?.max_files ?? ""}`,
      `max_loc: ${spec?.max_loc ?? ""}`,
    ]
    fs.writeFileSync(pinsMdPath, md.join("\n") + "\n", "utf8")
  } catch {
    // best-effort; ignore write errors
  }
  return { ok: true, pinsPath, pinsSpecPath, detailPath, outDir: base }
}
