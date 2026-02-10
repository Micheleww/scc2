import path from "node:path"
import process from "node:process"
import fs from "node:fs"
import { execFileSync } from "node:child_process"
import { loadMapV1, queryMapV1 } from "../../L17_ontology_layer/map_v1/map_v1.mjs"

function parseArgs(argv) {
  const out = { repoRoot: null, mapPath: null, q: null, limit: 20, backend: null }
  for (let i = 2; i < argv.length; i += 1) {
    const a = String(argv[i] ?? "")
    const next = argv[i + 1]
    if (a === "--repo-root") {
      out.repoRoot = String(next ?? "")
      i += 1
      continue
    }
    if (a === "--map") {
      out.mapPath = String(next ?? "")
      i += 1
      continue
    }
    if (a === "--q" || a === "-q") {
      out.q = String(next ?? "")
      i += 1
      continue
    }
    if (a === "--limit") {
      out.limit = Number(next ?? out.limit)
      i += 1
      continue
    }
    if (a === "--backend") {
      out.backend = String(next ?? "")
      i += 1
      continue
    }
  }
  return out
}

const args = parseArgs(process.argv)
const repoRoot = path.resolve(args.repoRoot || process.env.SCC_REPO_ROOT || path.join(process.cwd(), ".."))
const backend = String(args.backend ?? process.env.MAP_QUERY_BACKEND ?? "").toLowerCase()
const wantSqlite = backend === "sqlite"
const strict = (() => {
  const v = String(process.env.MAP_QUERY_STRICT ?? "auto").toLowerCase()
  if (v === "auto") return wantSqlite
  return v === "1" || v === "true" || v === "yes" || v === "on"
})()
const sqlitePath = path.join(repoRoot, "map", "map.sqlite")
if (wantSqlite && !fs.existsSync(sqlitePath) && strict) {
  console.error(JSON.stringify({ ok: false, error: "missing_sqlite", db: "map/map.sqlite", hint: "Rebuild map with sqlite (npm --prefix oc-scc-local run map:build)" }, null, 2))
  process.exit(2)
}
if (wantSqlite && fs.existsSync(sqlitePath)) {
  const q = String(args.q ?? "")
  const limit = Number.isFinite(args.limit) ? args.limit : 20
  const stdout = execFileSync(
    "python",
    ["tools/scc/map/map_query_sqlite_v1.py", "--repo-root", repoRoot, "--db", "map/map.sqlite", "--q", q, "--limit", String(limit)],
    { cwd: repoRoot, windowsHide: true, timeout: 20000, maxBuffer: 10 * 1024 * 1024, encoding: "utf8" },
  )
  process.stdout.write(String(stdout ?? ""))
  process.exit(0)
}

const loaded = loadMapV1({ repoRoot, mapPath: args.mapPath || "map/map.json" })
const out = queryMapV1({ map: loaded.data, q: args.q ?? "", limit: args.limit })
if (!out.ok) {
  console.error(JSON.stringify(out, null, 2))
  process.exitCode = 2
} else {
  console.log(JSON.stringify(out, null, 2))
  process.exitCode = 0
}
