import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { runPreflightV1 } from "../src/preflight_v1.mjs"

function mustReadJson(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
console.log(`[selfcheck:preflight_commands_v1] repoRoot=${repoRoot}`)

const taskId = "preflight_commands_selfcheck_v1"
const policy = mustReadJson(path.join(repoRoot, "roles", "executor.json"))

const pins = { allowed_paths: ["oc-scc-local/src"] }
const child = {
  title: "Selfcheck: preflight command validation",
  goal: "Ensure preflight validates common python -m commands and npm --prefix patterns.",
  role: "executor",
  files: ["oc-scc-local/src/gateway.mjs"],
  allowedTests: ["python -m compileall .", "python -m pytest -q", "npm --prefix oc-scc-local run smoke"],
  pins,
}

const pre = runPreflightV1({ repoRoot, taskId, childTask: child, pinsSpec: pins, rolePolicy: policy })
if (!pre.ok) {
  console.error("[selfcheck:preflight_commands_v1] run failed:", JSON.stringify(pre, null, 2))
  process.exit(2)
}
if (!pre.preflight?.pass) {
  console.error("[selfcheck:preflight_commands_v1] FAIL:", JSON.stringify(pre.preflight, null, 2))
  process.exit(3)
}

console.log("[selfcheck:preflight_commands_v1] OK")
