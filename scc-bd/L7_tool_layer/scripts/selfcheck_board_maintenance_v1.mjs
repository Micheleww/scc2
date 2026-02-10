import process from "node:process"

const base = process.env.SCC_BASE_URL ?? "http://127.0.0.1:18788"

async function getJson(path) {
  const r = await fetch(`${base}${path}`)
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`)
  return await r.json()
}

async function postJson(path, body) {
  const r = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body ?? {}),
  })
  const j = await r.json().catch(() => null)
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status} ${JSON.stringify(j)?.slice?.(0, 200) ?? ""}`)
  return j
}

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERT_FAIL: ${msg}`)
}

console.log(`[selfcheck:board_maintenance_v1] base=${base}`)
await getJson("/health")

const before = await getJson("/board")
const out = await postJson("/board/maintenance", { dryRun: true, keepHours: 1, keepLastFailed: 5, keepLastDone: 2, dlqAfterAttempts: 2 })
assert(out && out.ok === true, "maintenance.ok != true")
assert(out.report && out.report.schema_version === "scc.board_maintenance_report.v1", "missing report schema")
assert(out.report.counts && typeof out.report.counts.before === "number", "missing counts.before")
assert(out.report.counts.before === before.counts.total, "counts.before mismatch")

console.log("[selfcheck:board_maintenance_v1] OK")

