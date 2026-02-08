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
const taskId = "ci_gates_strict_selfcheck_v1"
const artDir = path.join(repoRoot, "artifacts", taskId)
if (fs.existsSync(artDir)) fs.rmSync(artDir, { recursive: true, force: true })
fs.mkdirSync(path.join(artDir, "evidence"), { recursive: true })

// Ensure map is up to date for ssot_map gate.
const mapBuildCmd = process.platform === "win32" ? 'npm --prefix oc-scc-local run map:build' : 'npm --prefix oc-scc-local run map:build'
execFileSync(process.platform === "win32" ? "cmd.exe" : "sh", process.platform === "win32" ? ["/c", mapBuildCmd] : ["-lc", mapBuildCmd], {
  cwd: repoRoot,
  stdio: "inherit",
  windowsHide: true,
  timeout: 240000,
})

writeText(path.join(artDir, "report.md"), "# ci gates strict selfcheck\n")
writeText(path.join(artDir, "patch.diff"), "\n")
writeText(path.join(artDir, "selftest.log"), "ci gates strict selfcheck\nEXIT_CODE=0\n")

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

console.log(`[selfcheck:ci_gates_strict_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:ci_gates_strict_v1] taskId=${taskId}`)

// 1) Strict mode should fail-closed when artifacts are missing.
let strictFailed = false
try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--strict", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    // Suppress expected FAIL output to keep selfcheck logs signal-rich.
    stdio: "pipe",
    windowsHide: true,
    timeout: 180000,
  })
} catch {
  strictFailed = true
}
if (!strictFailed) {
  console.error("[selfcheck:ci_gates_strict_v1] FAIL: expected --strict to fail when required artifacts are missing")
  process.exit(1)
}

// 2) Non-strict mode should deterministically backfill and PASS.
try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 180000,
  })
} catch {
  console.error("[selfcheck:ci_gates_strict_v1] FAIL: expected non-strict run_ci_gates to PASS with deterministic backfill")
  process.exit(1)
}

const mustExist = [
  path.join(artDir, "contracts_backfill.json"),
  path.join(artDir, "preflight.json"),
  path.join(artDir, "pins", "pins.json"),
  path.join(artDir, "replay_bundle.json"),
  path.join(artDir, "verdict.json"),
]
for (const f of mustExist) {
  if (!fs.existsSync(f)) {
    console.error(`[selfcheck:ci_gates_strict_v1] FAIL: missing ${path.relative(repoRoot, f).replaceAll("\\", "/")}`)
    process.exit(2)
  }
}

console.log("[selfcheck:ci_gates_strict_v1] OK")
