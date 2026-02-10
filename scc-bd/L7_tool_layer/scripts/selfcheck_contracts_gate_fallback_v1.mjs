import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { execFileSync } from "node:child_process"

function writeText(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, text, "utf8")
}

function writeJson(file, obj) {
  writeText(file, JSON.stringify(obj, null, 2) + "\n")
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
const taskId = "contracts_gate_selfcheck_v1"
const artDir = path.join(repoRoot, "artifacts", taskId)
fs.mkdirSync(path.join(artDir, "evidence"), { recursive: true })

// Ensure map is up to date for ssot_map gate.
try {
  const mapBuildCmd = process.platform === "win32" ? "npm --prefix oc-scc-local run map:build" : "npm --prefix oc-scc-local run map:build"
  execFileSync(process.platform === "win32" ? "cmd.exe" : "sh", process.platform === "win32" ? ["/c", mapBuildCmd] : ["-lc", mapBuildCmd], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 240000,
  })
} catch {
  // best-effort
}

writeText(path.join(artDir, "report.md"), "# contracts gate selfcheck\n")
writeText(path.join(artDir, "patch.diff"), "\n")
writeText(path.join(artDir, "selftest.log"), "contracts gate selfcheck\nEXIT_CODE=0\n")

const submit = {
  schema_version: "scc.submit.v1",
  task_id: taskId,
  status: "DONE",
  changed_files: [],
  new_files: [],
  touched_files: [],
  allow_paths: { read: ["**"], write: ["**"] },
  tests: { commands: ["python -m compileall ."], passed: true, summary: "selfcheck" },
  artifacts: {
    report_md: `artifacts/${taskId}/report.md`,
    selftest_log: `artifacts/${taskId}/selftest.log`,
    evidence_dir: `artifacts/${taskId}/evidence/`,
    patch_diff: `artifacts/${taskId}/patch.diff`,
    submit_json: `artifacts/${taskId}/submit.json`,
  },
  exit_code: 0,
  needs_input: [],
}
writeJson(path.join(artDir, "submit.json"), submit)

// Intentionally do NOT create:
// - artifacts/<task_id>/preflight.json
// - artifacts/<task_id>/pins/pins.json
// - artifacts/<task_id>/replay_bundle.json
// contracts gate should fail-closed unless run_ci_gates can deterministically backfill them.

console.log(`[selfcheck:contracts_gate_fallback_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:contracts_gate_fallback_v1] taskId=${taskId}`)

try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 180000,
  })
} catch (e) {
  console.error("[selfcheck:contracts_gate_fallback_v1] FAIL: run_ci_gates returned non-zero")
  process.exit(1)
}

const mustExist = [
  path.join(artDir, "preflight.json"),
  path.join(artDir, "pins", "pins.json"),
  path.join(artDir, "replay_bundle.json"),
  path.join(artDir, "verdict.json"),
]
for (const f of mustExist) {
  if (!fs.existsSync(f)) {
    console.error(`[selfcheck:contracts_gate_fallback_v1] FAIL: missing ${path.relative(repoRoot, f).replaceAll("\\", "/")}`)
    process.exit(2)
  }
}

console.log("[selfcheck:contracts_gate_fallback_v1] OK")
