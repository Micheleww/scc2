import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { execFileSync } from "node:child_process"

import { buildPinsFromMapV1, writePinsV1Outputs } from "../src/pins_builder_v1.mjs"
import { runPreflightV1, writePreflightV1Output } from "../src/preflight_v1.mjs"

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

function writeEventRow({ taskId, eventType, executor, reasonCode, details }) {
  const row = {
    schema_version: "scc.event.v1",
    t: new Date().toISOString(),
    event_type: String(eventType),
    task_id: String(taskId),
    parent_id: null,
    role: "selfcheck",
    area: "selfcheck",
    executor: executor ?? null,
    model: null,
    reason: String(reasonCode ?? ""),
    details: details && typeof details === "object" ? details : {},
  }
  return JSON.stringify(row) + "\n"
}

function ensureCleanDir(dir) {
  if (fs.existsSync(dir)) fs.rmSync(dir, { recursive: true, force: true })
  fs.mkdirSync(dir, { recursive: true })
}

function runStrictGates({ repoRoot, taskId }) {
  execFileSync("python", ["tools/scc/gates/run_ci_gates.py", "--strict", "--submit", `artifacts/${taskId}/submit.json`], {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    timeout: 240000,
  })
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
console.log(`[selfcheck:eval_samples_v1] repoRoot=${repoRoot}`)

// Ensure Map is fresh (pins_builder_v1 requires it).
execFileSync("cmd.exe", ["/c", "npm --prefix oc-scc-local run -s map:build"], { cwd: repoRoot, stdio: "inherit", windowsHide: true, timeout: 240000 })
const mapVersionPath = path.join(repoRoot, "map", "version.json")
if (!fs.existsSync(mapVersionPath)) {
  console.error("[selfcheck:eval_samples_v1] FAIL: missing map/version.json")
  process.exit(2)
}
const mapVersion = readJson(mapVersionPath)
const mapHash = String(mapVersion?.hash ?? "").trim()

const rolePolicyExecutor = readJson(path.join(repoRoot, "roles", "executor.json"))

const samples = [
  {
    taskId: "eval_sample_failed_v1",
    status: "FAILED",
    eventType: "EXECUTOR_ERROR",
    executor: "selfcheck",
    reasonCode: "synthetic_failed_sample",
    preflight: { pass: true },
    tests: { commands: ["python -m compileall ."], passed: false, summary: "synthetic sample (failed)" },
    exitCode: 1,
  },
  {
    taskId: "eval_sample_executor_error_opencodecli_v1",
    status: "FAILED",
    eventType: "EXECUTOR_ERROR",
    executor: "opencodecli",
    reasonCode: "synthetic_executor_error_opencodecli",
    preflight: { pass: true },
    tests: { commands: ["python -m compileall ."], passed: false, summary: "synthetic executor error" },
    exitCode: 1,
  },
  {
    taskId: "eval_sample_executor_error_codex_v1",
    status: "FAILED",
    eventType: "EXECUTOR_ERROR",
    executor: "codex",
    reasonCode: "synthetic_executor_error_codex",
    preflight: { pass: true },
    tests: { commands: ["python -m compileall ."], passed: false, summary: "synthetic executor error" },
    exitCode: 1,
  },
  {
    taskId: "eval_sample_ci_failed_opencodecli_v1",
    status: "FAILED",
    eventType: "CI_FAILED",
    executor: "opencodecli",
    reasonCode: "synthetic_ci_failed_opencodecli",
    preflight: { pass: true },
    tests: { commands: ["python -m compileall ."], passed: false, summary: "synthetic ci failed" },
    exitCode: 1,
    details: { failing_tests: ["(synthetic)"], stacktrace_hash: "sha256:ci_failed_synthetic" },
  },
  {
    taskId: "eval_sample_pins_insufficient_codex_v1",
    status: "NEED_INPUT",
    eventType: "PINS_INSUFFICIENT",
    executor: "codex",
    reasonCode: "synthetic_pins_insufficient_codex",
    preflight: { pass: true },
    tests: { commands: [], passed: false, summary: "not run (pins insufficient)" },
    exitCode: 0,
    needsInput: [{ type: "pins", missing: ["(synthetic)"], note: "pins insufficient synthetic sample" }],
  },
  {
    taskId: "eval_sample_pins_insufficient_unknown_v1",
    status: "NEED_INPUT",
    eventType: "PINS_INSUFFICIENT",
    executor: null,
    reasonCode: "synthetic_pins_insufficient_unknown",
    preflight: { pass: true },
    tests: { commands: [], passed: false, summary: "not run (pins insufficient)" },
    exitCode: 0,
    needsInput: [{ type: "pins", missing: ["(synthetic)"], note: "pins insufficient synthetic sample" }],
  },
  {
    taskId: "eval_sample_preflight_failed_v1",
    status: "NEED_INPUT",
    eventType: "PREFLIGHT_FAILED",
    executor: null,
    reasonCode: "synthetic_preflight_failed",
    preflight: { pass: false, missing: { files: [], symbols: [], tests: [], write_scope: ["(synthetic)"] } },
    tests: { commands: [], passed: false, summary: "not run (preflight failed)" },
    exitCode: 0,
    needsInput: [{ type: "preflight", missing: ["(synthetic)"], note: "preflight failed synthetic sample" }],
  },
]

for (const s of samples) {
  const taskId = String(s.taskId)
  const artDir = path.join(repoRoot, "artifacts", taskId)
  ensureCleanDir(artDir)
  fs.mkdirSync(path.join(artDir, "evidence"), { recursive: true })

  // Minimal child_task for pins/preflight.
  const childTask = {
    title: `Eval sample: ${taskId}`,
    goal: `Synthetic eval sample (${taskId}) for curated replay gating.`,
    role: "executor",
    files: [],
    allowedTests: Array.isArray(s.tests?.commands) ? s.tests.commands : [],
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
    console.error(`[selfcheck:eval_samples_v1] FAIL: pins build failed for ${taskId}: ${pinsOut.error}`)
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

  if (s.preflight?.pass === false) {
    const preflight = {
      schema_version: "scc.preflight.v1",
      task_id: taskId,
      pass: false,
      missing: s.preflight?.missing ?? { files: [], symbols: [], tests: [], write_scope: ["(synthetic)"] },
      notes: "synthetic preflight FAIL sample (expected)",
    }
    writePreflightV1Output({ repoRoot, taskId, preflight })
  } else {
    const pf = runPreflightV1({ repoRoot, taskId, childTask, pinsSpec: pinsOut.pins, rolePolicy: rolePolicyExecutor })
    if (!pf.ok || !pf.preflight) {
      console.error(`[selfcheck:eval_samples_v1] FAIL: preflight runner failed for ${taskId}: ${pf.error}`)
      process.exit(4)
    }
    writePreflightV1Output({ repoRoot, taskId, preflight: pf.preflight })
    if (!pf.preflight.pass) {
      console.error(`[selfcheck:eval_samples_v1] FAIL: expected preflight pass=true for ${taskId}`)
      process.exit(4)
    }
  }

  writeText(path.join(artDir, "report.md"), `# ${taskId}\nSynthetic eval sample.\n`)
  writeText(path.join(artDir, "patch.diff"), "\n")
  writeText(path.join(artDir, "selftest.log"), `selfcheck eval sample: ${taskId}\nEXIT_CODE=0\n`)
  writeText(
    path.join(artDir, "events.jsonl"),
    writeEventRow({
      taskId,
      eventType: s.eventType,
      executor: s.executor,
      reasonCode: s.reasonCode,
      details: s.details ?? { note: "synthetic eval sample" },
    }),
  )

  const submit = {
    schema_version: "scc.submit.v1",
    task_id: taskId,
    status: s.status,
    reason_code: s.reasonCode,
    changed_files: [],
    new_files: [],
    touched_files: [],
    allow_paths: { read: ["**"], write: ["**"] },
    tests: s.tests,
    artifacts: {
      report_md: `artifacts/${taskId}/report.md`,
      selftest_log: `artifacts/${taskId}/selftest.log`,
      evidence_dir: `artifacts/${taskId}/evidence/`,
      patch_diff: `artifacts/${taskId}/patch.diff`,
      submit_json: `artifacts/${taskId}/submit.json`,
    },
    exit_code: Number.isInteger(s.exitCode) ? s.exitCode : 1,
    needs_input: Array.isArray(s.needsInput) ? s.needsInput : [],
    summary: `Synthetic eval sample: ${taskId}`,
  }
  writeJson(path.join(artDir, "submit.json"), submit)

  const replayBundle = {
    schema_version: "scc.replay_bundle.v1",
    task_id: taskId,
    created_at: new Date().toISOString(),
    source: { job_id: null, executor: s.executor ?? null, model: null, job_status: s.status, exit_code: submit.exit_code },
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
      allowedExecutors: ["codex", "opencodecli"],
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
    runStrictGates({ repoRoot, taskId })
  } catch {
    console.error(`[selfcheck:eval_samples_v1] FAIL: strict gates did not PASS for ${taskId}`)
    process.exit(5)
  }
}

console.log("[selfcheck:eval_samples_v1] OK")
