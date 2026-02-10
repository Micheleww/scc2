import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { execFileSync } from "node:child_process"
import { buildPinsFromMapV1 } from "../../L2_task_layer/pins/pins_builder_v1.mjs"

function mustReadJson(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
console.log(`[selfcheck:map_sqlite_v1] repoRoot=${repoRoot}`)

// 1) Ensure map outputs exist (map.json + version + sqlite).
const buildStdout = execFileSync("node", ["oc-scc-local/scripts/map_build_v1.mjs", "--repo-root", repoRoot, "--sqlite"], {
  cwd: repoRoot,
  windowsHide: true,
  timeout: 240000,
  maxBuffer: 20 * 1024 * 1024,
  encoding: "utf8",
})
const built = JSON.parse(String(buildStdout ?? "").replace(/^\uFEFF/, ""))
if (!built?.ok) {
  console.error("[selfcheck:map_sqlite_v1] FAIL: map build failed:", JSON.stringify(built, null, 2))
  process.exit(1)
}

const sqlitePath = path.join(repoRoot, "map", "map.sqlite")
if (!fs.existsSync(sqlitePath)) {
  console.error("[selfcheck:map_sqlite_v1] FAIL: missing map/map.sqlite (expected sqlite build output)")
  process.exit(2)
}

// 2) Query via sqlite backend must return results.
const qStdout = execFileSync(
  "node",
  ["oc-scc-local/scripts/map_query_v1.mjs", "--repo-root", repoRoot, "--backend", "sqlite", "--q", "gateway", "--limit", "5"],
  {
    cwd: repoRoot,
    windowsHide: true,
    timeout: 20000,
    maxBuffer: 10 * 1024 * 1024,
    encoding: "utf8",
  },
)
const q = JSON.parse(String(qStdout ?? "").replace(/^\uFEFF/, ""))
if (!q?.ok || !Array.isArray(q.results) || q.results.length === 0) {
  console.error("[selfcheck:map_sqlite_v1] FAIL: sqlite query empty:", JSON.stringify(q, null, 2))
  process.exit(3)
}

// 3) Pins builder must prefer sqlite on main path when configured.
process.env.MAP_PINS_QUERY_BACKEND = "sqlite"
process.env.MAP_PINS_QUERY_STRICT = "true"
process.env.MAP_QUERY_BACKEND = "sqlite"

const ver = mustReadJson(path.join(repoRoot, "map", "version.json"))
const hash = String(ver?.hash ?? "").trim()
if (!hash) {
  console.error("[selfcheck:map_sqlite_v1] FAIL: missing map/version.json hash")
  process.exit(4)
}

const taskId = "map_sqlite_selfcheck_v1"
const pins_request = {
  schema_version: "scc.pins_request.v1",
  task_id: taskId,
  child_task: {
    title: "Selfcheck: Map SQLite → Pins builder",
    goal: "Ensure pins builder uses sqlite backend when enabled.",
    role: "executor",
    files: ["oc-scc-local/src/gateway.mjs"],
    allowedTests: ["npm --prefix oc-scc-local run smoke"],
  },
  signals: { keywords: ["gateway", "sqlite", "pins"] },
  map_ref: { path: "map/map.json", hash },
  budgets: { max_files: 10, max_loc: 200, default_line_window: 140 },
}

const pinsBuilt = buildPinsFromMapV1({ repoRoot, request: pins_request })
if (!pinsBuilt.ok) {
  console.error("[selfcheck:map_sqlite_v1] FAIL: pins build failed:", JSON.stringify(pinsBuilt, null, 2))
  process.exit(5)
}
if (pinsBuilt?.detail?.query_backend !== "sqlite") {
  console.error("[selfcheck:map_sqlite_v1] FAIL: expected pins detail query_backend=sqlite:", JSON.stringify(pinsBuilt.detail ?? null, null, 2))
  process.exit(6)
}

console.log("[selfcheck:map_sqlite_v1] OK")
process.exitCode = 0

