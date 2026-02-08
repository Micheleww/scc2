import { execFileSync } from "node:child_process"
import path from "node:path"
import process from "node:process"

import { writeTraceV1 } from "./lib/trace_v1.mjs"

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
const taskId = "orchestrator_selfcheck_v1"
const child = "contracts/examples/child_task.runtime_noop.example.json"

console.log(`[selfcheck:orchestrator_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:orchestrator_v1] taskId=${taskId}`)

try {
  execFileSync(
    "python",
    ["tools/scc/runtime/orchestrator_v1.py", "--child", child, "--task-id", taskId, "--executor", "noop", "--snapshot", "--enforce-wip"],
    { cwd: repoRoot, stdio: "inherit", windowsHide: true, timeout: 600000 },
  )
} catch {
  console.error("[selfcheck:orchestrator_v1] FAIL: orchestrator_v1 failed")
  process.exit(1)
}

try {
  writeTraceV1({ repoRoot, taskId, routing: { executor: "noop", model: null, model_effective: null } })
} catch {
  console.error("[selfcheck:orchestrator_v1] FAIL: trace.json write failed")
  process.exit(2)
}

try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--strict", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 240000,
  })
} catch {
  console.error("[selfcheck:orchestrator_v1] FAIL: strict gates did not PASS")
  process.exit(3)
}

console.log("[selfcheck:orchestrator_v1] OK")
