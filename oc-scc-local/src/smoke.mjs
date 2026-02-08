import process from "node:process"
import { URL } from "node:url"

const base = new URL(process.env.GATEWAY_BASE ?? "http://127.0.0.1:18788")

async function check(path) {
  const url = new URL(path, base)
  const start = Date.now()
  try {
    const res = await fetch(url)
    const ms = Date.now() - start
    return { path, ok: res.ok, status: res.status, ms }
  } catch (e) {
    const ms = Date.now() - start
    return { path, ok: false, status: 0, ms, error: String(e?.message ?? e) }
  }
}

const targets = [
  "/health",
  "/status",
  "/prompts/registry",
  "/desktop",
  "/mcp/health",
  "/opencode/global/health",
]

const results = await Promise.all(targets.map(check))
for (const r of results) {
  console.log(`${r.ok ? "OK" : "NO"} ${String(r.status).padStart(3, " ")} ${String(r.ms).padStart(4, " ")}ms  ${r.path}`)
  if (r.error) console.log(`    ${r.error}`)
}

const failed = results.some((r) => !r.ok && r.path !== "/desktop" && r.path !== "/mcp/health" && r.path !== "/opencode/global/health")
process.exitCode = failed ? 1 : 0
