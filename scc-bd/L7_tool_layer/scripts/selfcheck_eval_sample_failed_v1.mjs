import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { execFileSync } from "node:child_process"

import { buildPinsFromMapV1, writePinsV1Outputs } from "../../L2_task_layer/pins/pins_builder_v1.mjs"
import { runPreflightV1, writePreflightV1Output } from "../../L13_security_layer/preflight/preflight_v1.mjs"

function writeText(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, text, "utf8")
}

function writeJson(file, obj) {
  writeText(file, JSON.stringify(obj, null, 2) + "\n")
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, ""))
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
const taskId = "eval_sample_failed_v1"
const artDir = path.join(repoRoot, "artifacts", taskId)
if (fs.existsSync(artDir)) fs.rmSync(artDir, { recursive: true, force: true })
fs.mkdirSync(path.join(artDir, "evidence"), { recursive: true })

console.log(`[selfcheck:eval_sample_failed_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:eval_sample_failed_v1] taskId=${taskId}`)

// Ensure Map is fresh
const mapBuildCmd = "npm --prefix oc-scc-local run -s map:build"
execFileSync(process.platform === "win32" ? "cmd.exe" : "sh", process.platform === "win32" ? ["/c", mapBuildCmd] : ["-lc", mapBuildCmd], {
  cwd: repoRoot,
  stdio: "inherit",
  windowsHide: true,
  timeout: 240000,
})
const mapVersionPath = path.join(repoRoot, "map", "version.json")
if (!fs.existsSync(mapVersionPath)) {
  console.error("[selfcheck:eval_sample_failed_v1] FAIL: missing map/version.json")
  process.exit(2)
}
const mapVersion = readJson(mapVersionPath)
const mapHash = String(mapVersion?.hash ?? "").trim()

const childTask = {
  title: "Eval sample failed (synthetic)",
  goal: "Synthetic strict-gate-valid FAILED task for eval replay smoke sample sets.",
  role: "factory_manager",
  // Keep required files empty so preflight passes for a role that cannot write outside artifacts/**.
  files: [],
  allowedTests: ["python -m compileall ."],
  pins: { allowed_paths: [] },
}

const pinsReq = {
  schema_version: "scc.pins_request.v1",
  task_id: taskId,
  child_task: childTask,
  signals: { keywords: ["eval", "sample"], failing_test: null, stacktrace: null },
  budgets: { max_files: 8, max_loc: 200, default_line_window: 120, max_pins_tokens: 8000 },
  map_ref: { path: "map/map.json", hash: mapHash },
}

const pinsOut = buildPinsFromMapV1({ repoRoot, request: pinsReq })
if (!pinsOut.ok) {
  console.error(`[selfcheck:eval_sample_failed_v1] FAIL: pins build failed: ${pinsOut.error}`)
  process.exit(3)
}

writePinsV1Outputs({
  repoRoot,
  taskId,
  outDir: `artifacts/${taskId}/pins`,
  pinsResult: pinsOut.result_v2 ?? undefined,
  pinsSpec: pinsOut.pins,
  detail: pinsOut.detail,
})

const rolePolicy = readJson(path.join(repoRoot, "roles", "factory_manager.json"))
const pf = runPreflightV1({ repoRoot, taskId, childTask, pinsSpec: pinsOut.pins, rolePolicy })
if (!pf.ok || !pf.preflight) {
  console.error(`[selfcheck:eval_sample_failed_v1] FAIL: preflight runner failed: ${pf.error}`)
  process.exit(4)
}
writePreflightV1Output({ repoRoot, taskId, preflight: pf.preflight })
if (!pf.preflight.pass) {
  console.error("[selfcheck:eval_sample_failed_v1] FAIL: expected preflight pass=true for this synthetic sample")
  process.exit(4)
}

writeText(path.join(artDir, "report.md"), "# eval sample failed v1\nSynthetic sample for eval replay.\n")
writeText(path.join(artDir, "patch.diff"), "\n")
writeText(path.join(artDir, "selftest.log"), "eval sample failed selfcheck\nEXIT_CODE=0\n")
writeText(
  path.join(artDir, "events.jsonl"),
  JSON.stringify(
    {
      schema_version: "scc.event.v1",
      t: new Date().toISOString(),
      event_type: "EXECUTOR_ERROR",
      task_id: taskId,
      parent_id: null,
      role: "selfcheck",
      area: "selfcheck",
      executor: "selfcheck",
      model: null,
      reason: "synthetic_failed_sample",
      details: { note: "strict gates require at least one event row" },
    },
    null,
    0,
  ) + "\n",
)

const submit = {
  schema_version: "scc.submit.v1",
  task_id: taskId,
  status: "FAILED",
  reason_code: "synthetic_failed_sample",
  changed_files: [],
  new_files: [],
  touched_files: [],
  allow_paths: { read: ["docs/WORKLOG.md"], write: ["docs/WORKLOG.md"] },
  tests: { commands: ["python -m compileall ."], passed: false, summary: "synthetic sample (failed)" },
  artifacts: {
    report_md: `artifacts/${taskId}/report.md`,
    selftest_log: `artifacts/${taskId}/selftest.log`,
    evidence_dir: `artifacts/${taskId}/evidence/`,
    patch_diff: `artifacts/${taskId}/patch.diff`,
    submit_json: `artifacts/${taskId}/submit.json`,
  },
  exit_code: 1,
  needs_input: [],
  summary: "Synthetic failed sample for eval replay smoke.",
}
writeJson(path.join(artDir, "submit.json"), submit)

const replayBundle = {
  schema_version: "scc.replay_bundle.v1",
  task_id: taskId,
  created_at: new Date().toISOString(),
  source: { job_id: null, executor: "selfcheck", model: null, job_status: "FAILED", exit_code: 1 },
  board_task_payload: {
    kind: "atomic",
    title: childTask.title,
    goal: childTask.goal,
    role: childTask.role,
    files: childTask.files,
    skills: [],
    pointers: null,
    pins: pinsOut.pins,
    pins_instance: null,
    allowedTests: childTask.allowedTests,
    allowedExecutors: ["codex"],
    allowedModels: [],
    runner: "internal",
    area: "selfcheck",
    lane: "batchlane",
    task_class_id: "selfcheck",
  },
  artifacts: {
    submit_json: `artifacts/${taskId}/submit.json`,
    preflight_json: `artifacts/${taskId}/preflight.json`,
    pins_json: `artifacts/${taskId}/pins/pins.json`,
    report_md: `artifacts/${taskId}/report.md`,
    selftest_log: `artifacts/${taskId}/selftest.log`,
    evidence_dir: `artifacts/${taskId}/evidence/`,
    patch_diff: `artifacts/${taskId}/patch.diff`,
  },
  replay: { dispatch_via: "tools/scc/ops/replay_bundle_dispatch.py" },
}
writeJson(path.join(artDir, "replay_bundle.json"), replayBundle)

try {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--strict", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 180000,
  })
} catch {
  console.error("[selfcheck:eval_sample_failed_v1] FAIL: strict run_ci_gates did not PASS")
  process.exit(5)
}

console.log("[selfcheck:eval_sample_failed_v1] OK")
