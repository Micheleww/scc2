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
const taskId = "events_migrate_selfcheck_v1"
const artDir = path.join(repoRoot, "artifacts", taskId)
if (fs.existsSync(artDir)) fs.rmSync(artDir, { recursive: true, force: true })
fs.mkdirSync(path.join(artDir, "evidence"), { recursive: true })

// Ensure map is up to date for map/ssot_map gates.
const mapBuildCmd = process.platform === "win32" ? "npm --prefix oc-scc-local run map:build" : "npm --prefix oc-scc-local run map:build"
execFileSync(process.platform === "win32" ? "cmd.exe" : "sh", process.platform === "win32" ? ["/c", mapBuildCmd] : ["-lc", mapBuildCmd], {
  cwd: repoRoot,
  stdio: "inherit",
  windowsHide: true,
  timeout: 240000,
})

writeText(path.join(artDir, "report.md"), "# events migration selfcheck\n")
writeText(path.join(artDir, "patch.diff"), "\n")
writeText(path.join(artDir, "selftest.log"), "events migration selfcheck\nEXIT_CODE=0\n")

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

console.log(`[selfcheck:events_migrate_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:events_migrate_v1] taskId=${taskId}`)

// 1) Generate all required artifacts deterministically (non-strict).
try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 180000,
  })
} catch {
  console.error("[selfcheck:events_migrate_v1] FAIL: expected non-strict run_ci_gates to PASS")
  process.exit(1)
}

const eventsPath = path.join(artDir, "events.jsonl")
if (!fs.existsSync(eventsPath)) {
  console.error("[selfcheck:events_migrate_v1] FAIL: expected events.jsonl to exist after non-strict gates")
  process.exit(2)
}

// 2) Simulate legacy artifacts: remove events.jsonl, strict should fail.
fs.rmSync(eventsPath, { force: true })
let strictFailed = false
try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--strict", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 180000,
  })
} catch {
  strictFailed = true
}
if (!strictFailed) {
  console.error("[selfcheck:events_migrate_v1] FAIL: expected strict run_ci_gates to FAIL without events.jsonl")
  process.exit(3)
}

// 3) Run migration tool to backfill events.jsonl, strict should PASS now.
try {
  execFileSync("python", ["tools/scc/ops/backfill_events_v1.py", "--repo-root", repoRoot, "--task-id", taskId], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 60000,
  })
} catch {
  console.error("[selfcheck:events_migrate_v1] FAIL: backfill_events_v1.py failed")
  process.exit(4)
}
if (!fs.existsSync(eventsPath)) {
  console.error("[selfcheck:events_migrate_v1] FAIL: expected events.jsonl after migration tool")
  process.exit(5)
}

try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--strict", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 180000,
  })
} catch {
  console.error("[selfcheck:events_migrate_v1] FAIL: expected strict run_ci_gates to PASS after events backfill")
  process.exit(6)
}

console.log("[selfcheck:events_migrate_v1] OK")
process.exitCode = 0

