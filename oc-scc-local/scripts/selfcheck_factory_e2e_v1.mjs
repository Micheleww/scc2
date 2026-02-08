import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { execFileSync } from "node:child_process"

import { buildPinsFromMapV1, writePinsV1Outputs } from "../src/pins_builder_v1.mjs"
import { runPreflightV1, writePreflightV1Output } from "../src/preflight_v1.mjs"
import { writeTraceV1 } from "./lib/trace_v1.mjs"

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
const taskId = "factory_e2e_selfcheck_v1"
const artDir = path.join(repoRoot, "artifacts", taskId)
if (fs.existsSync(artDir)) fs.rmSync(artDir, { recursive: true, force: true })
fs.mkdirSync(path.join(artDir, "evidence"), { recursive: true })

console.log(`[selfcheck:factory_e2e_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:factory_e2e_v1] taskId=${taskId}`)

// 1) Build Map (always) so ssot_map gate is stable across schema additions.
const mapPath = path.join(repoRoot, "map", "map.json")
const mapVersionPath = path.join(repoRoot, "map", "version.json")
const mapBuildCmd = process.platform === "win32" ? 'npm --prefix oc-scc-local run map:build' : 'npm --prefix oc-scc-local run map:build'
execFileSync(process.platform === "win32" ? "cmd.exe" : "sh", process.platform === "win32" ? ["/c", mapBuildCmd] : ["-lc", mapBuildCmd], {
  cwd: repoRoot,
  stdio: "inherit",
  windowsHide: true,
  timeout: 240000,
})
if (!fs.existsSync(mapVersionPath)) {
  console.error("[selfcheck:factory_e2e_v1] FAIL: missing map/version.json after map:build")
  process.exit(2)
}
const mapVersion = readJson(mapVersionPath)
const mapHash = String(mapVersion?.hash ?? "").trim()
if (!mapHash.startsWith("sha256:")) {
  console.error("[selfcheck:factory_e2e_v1] FAIL: invalid map/version.json hash")
  process.exit(2)
}

// 2) Build pins from Map.
const childTask = {
  title: "Factory e2e selfcheck (no-op)",
  goal: "Prove Map->Pins->Preflight->CI gates can pass in --strict mode without any backfill.",
  role: "executor",
  files: ["oc-scc-local/src/gateway.mjs"],
  allowedTests: ["python -m compileall ."],
  pins: { allowed_paths: ["oc-scc-local/src/gateway.mjs"] },
}

const pinsReq = {
  schema_version: "scc.pins_request.v1",
  task_id: taskId,
  child_task: childTask,
  signals: { keywords: ["gateway", "preflight", "pins"], failing_test: null, stacktrace: null },
  budgets: { max_files: 12, max_loc: 200, default_line_window: 140, max_pins_tokens: 8000 },
  map_ref: { path: "map/map.json", hash: mapHash },
}

const pinsOut = buildPinsFromMapV1({ repoRoot, request: pinsReq })
if (!pinsOut.ok) {
  console.error(`[selfcheck:factory_e2e_v1] FAIL: pins build failed: ${pinsOut.error}`)
  if (pinsOut.message) console.error(pinsOut.message)
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

// 3) Preflight (contract+pins+policy -> pass/fail).
const rolePolicy = readJson(path.join(repoRoot, "roles", "executor.json"))
const pf = runPreflightV1({ repoRoot, taskId, childTask, pinsSpec: pinsOut.pins, rolePolicy })
if (!pf.ok) {
  console.error(`[selfcheck:factory_e2e_v1] FAIL: preflight runner failed: ${pf.error}`)
  process.exit(4)
}
writePreflightV1Output({ repoRoot, taskId, preflight: pf.preflight })
if (!pf.preflight?.pass) {
  console.error(`[selfcheck:factory_e2e_v1] FAIL: preflight expected pass=true, got pass=false missing=${JSON.stringify(pf.preflight?.missing)}`)
  process.exit(4)
}

// 4) Create minimal submit + replay bundle and run strict CI gates.
writeText(path.join(artDir, "report.md"), "# factory e2e selfcheck\n")
writeText(path.join(artDir, "patch.diff"), "\n")
writeText(path.join(artDir, "selftest.log"), "factory e2e selfcheck\nEXIT_CODE=0\n")
writeText(
  path.join(artDir, "events.jsonl"),
  JSON.stringify(
    {
      schema_version: "scc.event.v1",
      t: new Date().toISOString(),
      event_type: "SUCCESS",
      task_id: taskId,
      parent_id: null,
      role: "selfcheck",
      area: "selfcheck",
      executor: "selfcheck",
      model: null,
      reason: "factory_e2e_selfcheck",
      details: { note: "strict gates require at least one event row" },
    },
    null,
    0,
  ) + "\n",
)

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

try {
  writeTraceV1({ repoRoot, taskId, routing: { executor: "selfcheck", model: null, model_effective: null } })
} catch {
  console.error("[selfcheck:factory_e2e_v1] FAIL: trace.json write failed")
  process.exit(5)
}

const replayBundle = {
  schema_version: "scc.replay_bundle.v1",
  task_id: taskId,
  created_at: new Date().toISOString(),
  source: { job_id: null, executor: "selfcheck", model: null, job_status: "DONE", exit_code: 0 },
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
    lane: "fastlane",
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
  console.error("[selfcheck:factory_e2e_v1] FAIL: strict run_ci_gates did not PASS")
  process.exit(5)
}

console.log("[selfcheck:factory_e2e_v1] OK")
