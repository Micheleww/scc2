import http from "node:http"
import { URL } from "node:url"
import process from "node:process"
import httpProxy from "http-proxy"
import fs from "node:fs"
import path from "node:path"
import { execFile } from "node:child_process"
import crypto from "node:crypto"

const gatewayPort = Number(process.env.GATEWAY_PORT ?? "18788")
const sccUpstream = new URL(process.env.SCC_UPSTREAM ?? "http://127.0.0.1:18789")
const opencodeUpstream = new URL(process.env.OPENCODE_UPSTREAM ?? "http://127.0.0.1:18790")
const codexBin = process.env.CODEX_BIN ?? process.env.CODEXCLI_BIN ?? "codex"
const codexModelDefault = process.env.CODEX_MODEL ?? "gpt-5.1-codex-max"
const occliBin = process.env.OPENCODE_BIN ?? "C:/scc/OpenCode/opencode-cli.exe"
let occliModelDefault = process.env.OPENCODE_MODEL ?? "opencode/kimi-k2.5-free"
const occliVariantDefault = process.env.OPENCODE_VARIANT ?? "high"
const codexMax = Number(process.env.EXEC_CONCURRENCY_CODEX ?? "4")
const occliMax = Number(process.env.EXEC_CONCURRENCY_OPENCODE ?? "6")
const execRoot = process.env.EXEC_ROOT ?? "C:/scc/opencode-dev"
const execLogDir = process.env.EXEC_LOG_DIR ?? "C:/scc/artifacts/executor_logs"
const execLogJobs = path.join(execLogDir, "jobs.jsonl")
const execLogFailures = path.join(execLogDir, "failures.jsonl")
const execLogHeartbeat = path.join(execLogDir, "heartbeat.jsonl")
const ciGateResultsFile = path.join(execLogDir, "ci_gate_results.jsonl")
const learnedPatternsFile = path.join(execLogDir, "learned_patterns.jsonl")
const learnedPatternsSummaryFile = path.join(execLogDir, "learned_patterns_summary.json")
const stateEventsFile = path.join(execLogDir, "state_events.jsonl")
const pinsCandidatesFile = path.join(execLogDir, "pins_candidates.jsonl")
const pinsGuideErrorsFile = path.join(execLogDir, "pins_guide_errors.jsonl")
const ciFailuresFile = path.join(execLogDir, "ci_failures.jsonl")
const roleErrorsDir = path.join(execLogDir, "role_errors")
const auditTriggerStateFile = path.join(execLogDir, "audit_trigger_state.json")
const flowManagerStateFile = path.join(execLogDir, "flow_manager_state.json")
const feedbackHookStateFile = path.join(execLogDir, "feedback_hook_state.json")
const learnedPatternsHookStateFile = path.join(execLogDir, "learned_patterns_hook_state.json")
const tokenCfoHookStateFile = path.join(execLogDir, "token_cfo_hook_state.json")
const fiveWhysHookStateFile = path.join(execLogDir, "five_whys_hook_state.json")
const instinctDir = path.join(execLogDir, "instinct")
const instinctPatternsFile = path.join(instinctDir, "patterns.json")
const instinctPlaybooksFile = path.join(instinctDir, "playbooks.yaml")
const instinctSkillsDraftFile = path.join(instinctDir, "skills_draft.yaml")
const instinctSchemasFile = path.join(instinctDir, "schemas.yaml")
const instinctStateFile = path.join(instinctDir, "instinct_state.json")
const designerFailuresFile = path.join(execLogDir, "designer_failures.jsonl")
const executorFailuresFile = path.join(execLogDir, "executor_failures.jsonl")
const routerFailuresFile = path.join(execLogDir, "router_failures.jsonl")
const verifierFailuresFile = path.join(execLogDir, "verifier_failures.jsonl")
const routeDecisionsFile = path.join(execLogDir, "route_decisions.jsonl")
const execStateFile = path.join(execLogDir, "jobs_state.json")
const execLeaderLog = path.join(execLogDir, "leader.jsonl")
const docsRoot = process.env.DOCS_ROOT ?? "C:/scc/docs"
const boardDir = process.env.BOARD_DIR ?? "C:/scc/artifacts/taskboard"
const boardFile = path.join(boardDir, "tasks.json")
const missionFile = path.join(boardDir, "mission.json")
const runtimeEnvFile = process.env.RUNTIME_ENV_FILE ?? "C:/scc/oc-scc-local/config/runtime.env"
const allowedRootsRaw =
  process.env.EXEC_ALLOWED_ROOTS ?? `${execRoot};C:/scc/scc-top;${docsRoot};${execLogDir};${boardDir}`
const allowedRoots = allowedRootsRaw
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
  .map((x) => path.resolve(x))

const timeoutCodexMs = Number(process.env.EXEC_TIMEOUT_CODEX_MS ?? "1200000") // 20 min
const timeoutOccliMs = Number(process.env.EXEC_TIMEOUT_OPENCODE_MS ?? "1200000") // 20 min

const warnLongMs = Number(process.env.EXEC_WARN_LONG_MS ?? "1200000") // 20 min
const warnOcLongMs = Number(process.env.EXEC_WARN_OC_LONG_MS ?? "1200000") // 20 min
const warnFailWindowMs = Number(process.env.EXEC_WARN_FAIL_WINDOW_MS ?? "600000") // 10 min
const warnFailBurstN = Number(process.env.EXEC_WARN_FAIL_BURST_N ?? "3")
const workerLeaseMsDefault = Number(process.env.EXEC_WORKER_LEASE_MS ?? "720000") // 12 min
const modelRoutingMode = String(process.env.MODEL_ROUTING_MODE ?? "rr").toLowerCase() // rr|strong_first|ladder
const autoRequeueModelFailures = String(process.env.AUTO_REQUEUE_MODEL_FAILURES ?? "true").toLowerCase() !== "false"
const autoRequeueModelFailMax = Number(process.env.AUTO_REQUEUE_MODEL_FAIL_MAX ?? "2")
const autoRequeueModelFailCooldownMs = Number(process.env.AUTO_REQUEUE_MODEL_FAIL_COOLDOWN_MS ?? "60000")
let modelsFree = (process.env.MODEL_POOL_FREE ?? "opencode/kimi-k2.5-free")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
let modelsVision = (process.env.MODEL_POOL_VISION ?? "opencode/kimi-k2.5-free")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
const modelsPaid = (process.env.MODEL_POOL_PAID ?? "gpt-5.1-codex-max,gpt-5.2").split(/[;,]/g).map((x) => x.trim()).filter((x) => x.length > 0)

function estimateParamsB(model) {
  const s = String(model ?? "").toLowerCase()
  // Typical patterns: "...-27b-...", ".../70b", "... 1.5b ..."
  const m = s.match(/(^|[^0-9])(\d+(?:\.\d+)?)\s*b([^a-z]|$)/i)
  if (!m) return 0
  const n = Number(m[2])
  return Number.isFinite(n) ? n : 0
}

function modelStrengthScore(model) {
  const s = String(model ?? "").toLowerCase()
  // Hard pins: prefer specific high-performing models when present.
  if (s.includes("kimi-k2.5")) return 1_000_000 + estimateParamsB(s)
  if (s.includes("gpt-5") || s.includes("gpt-4.1")) return 800_000 + estimateParamsB(s)
  return estimateParamsB(s)
}

function sortModelPool(models) {
  const arr = Array.isArray(models) ? models.map((x) => String(x).trim()).filter(Boolean) : []
  // Strong -> weak; stable-ish tie break by name.
  arr.sort((a, b) => {
    const sa = modelStrengthScore(a)
    const sb = modelStrengthScore(b)
    if (sa !== sb) return sb - sa
    return String(a).localeCompare(String(b))
  })
  return arr
}

modelsFree = sortModelPool(modelsFree)
modelsVision = sortModelPool(modelsVision)

const ctxDir = path.join(execLogDir, "contextpacks")
const threadDir = path.join(execLogDir, "threads")
const requirePins = String(process.env.EXEC_REQUIRE_PINS ?? "false").toLowerCase() === "true"
const requirePinsTemplate = String(process.env.EXEC_REQUIRE_PINS_TEMPLATE ?? "false").toLowerCase() === "true"
const requireContract = String(process.env.EXEC_REQUIRE_CONTRACT ?? "false").toLowerCase() === "true"
const autoPinsCandidates = String(process.env.AUTO_PINS_CANDIDATES ?? "true").toLowerCase() !== "false"
const autoFilesFromText = String(process.env.AUTO_FILES_FROM_TEXT ?? "true").toLowerCase() !== "false"
const autoPinsFromFiles = String(process.env.AUTO_PINS_FROM_FILES ?? "true").toLowerCase() !== "false"
const dispatchIdempotency = String(process.env.DISPATCH_IDEMPOTENCY ?? "true").toLowerCase() !== "false"
const occliRequireSubmit = String(process.env.OCCLI_REQUIRE_SUBMIT ?? "true").toLowerCase() !== "false"
const splitTwoPhasePins = String(process.env.SPLIT_TWO_PHASE_PINS ?? "true").toLowerCase() !== "false"
const auditTriggerEnabled = String(process.env.AUDIT_TRIGGER_ENABLED ?? "true").toLowerCase() !== "false"
const auditTriggerEveryN = Number(process.env.AUDIT_TRIGGER_EVERY_N ?? "10")
const auditTriggerLookback = Number(process.env.AUDIT_TRIGGER_LOOKBACK ?? "30")
const designerStateFile = path.join(execLogDir, "designer_state.json")
const defaultProjectMap = { version: "v1", areas: {}, entry_points: {}, forbidden_paths: [] }
const defaultSsotAxioms = { ssot_hash: "sha256:TODO", axioms: [] }
const defaultTaskClassLibrary = { version: "v1", classes: [] }
const defaultPinsTemplates = { version: "v1", templates: [] }
let auditTriggerState = loadAuditTriggerState()
let auditTriggerBusy = false

function loadDesignerState() {
  try {
    if (!fs.existsSync(designerStateFile)) {
      return {
        l0: { frozen: true, navigation: "docs/START_HERE.md", ssot_index: "docs/ssot/00_index.md", principles: [] },
        l1: { map: null, recent_changes: [], task_classes: [] },
        l2: { current_task: null, draft_pins: null, draft_assumptions: [], draft_task_class: null },
        history: [],
      }
    }
    const raw = fs.readFileSync(designerStateFile, "utf8")
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === "object" ? parsed : null
  } catch {
    return null
  }
}

function saveDesignerState(state) {
  try {
    fs.writeFileSync(designerStateFile, JSON.stringify(state, null, 2), "utf8")
  } catch {
    // best-effort
  }
}

const configRegistry = [
  { key: "GATEWAY_PORT", type: "number", frequent: false, note: "gateway listen port (default 18788)" },
  { key: "SCC_UPSTREAM", type: "string", frequent: false, note: "SCC upstream base URL" },
  { key: "OPENCODE_UPSTREAM", type: "string", frequent: false, note: "OpenCode upstream base URL" },
  { key: "EXEC_CONCURRENCY_CODEX", type: "number", frequent: true, note: "internal codex concurrency" },
  { key: "EXEC_CONCURRENCY_OPENCODE", type: "number", frequent: true, note: "internal opencodecli concurrency" },
  { key: "EXTERNAL_MAX_CODEX", type: "number", frequent: true, note: "external codex throttle for board tasks" },
  { key: "EXTERNAL_MAX_OPENCODECLI", type: "number", frequent: true, note: "external occli throttle for board tasks" },
  { key: "AUDIT_TRIGGER_ENABLED", type: "bool", frequent: true, note: "enable auto audit trigger on completed tasks" },
  { key: "AUDIT_TRIGGER_EVERY_N", type: "number", frequent: true, note: "trigger audit after N completed tasks" },
  { key: "AUDIT_TRIGGER_LOOKBACK", type: "number", frequent: false, note: "lookback completed tasks included in audit batch" },
  { key: "DESIRED_RATIO_CODEX", type: "number", frequent: true, note: "routing share for codex (when both allowed)" },
  { key: "DESIRED_RATIO_OPENCODECLI", type: "number", frequent: true, note: "routing share for occli (when both allowed)" },
  { key: "EXEC_TIMEOUT_CODEX_MS", type: "number", frequent: true, note: "codex timeout in ms (default 20min)" },
  { key: "EXEC_TIMEOUT_OPENCODE_MS", type: "number", frequent: true, note: "occli timeout in ms (default 20min)" },
  { key: "MODEL_POOL_FREE", type: "string", frequent: true, note: "comma-separated free models (opencode/*)" },
  { key: "MODEL_POOL_VISION", type: "string", frequent: true, note: "comma-separated vision-capable models" },
  { key: "OPENCODE_MODEL", type: "string", frequent: true, note: "default opencodecli model" },
  { key: "AUTO_ASSIGN_OPENCODE_MODELS", type: "bool", frequent: true, note: "auto round-robin model selection for occli" },
  { key: "WORKER_IDLE_EXIT_SECONDS", type: "number", frequent: true, note: "worker idle auto-exit seconds" },
  { key: "EXEC_REQUIRE_PINS", type: "bool", frequent: false, note: "require pins for atomic jobs (reduce repo reading)" },
  { key: "EXEC_REQUIRE_PINS_TEMPLATE", type: "bool", frequent: false, note: "require pins template or pins for classed tasks" },
  { key: "EXEC_REQUIRE_CONTRACT", type: "bool", frequent: false, note: "require contract for atomic jobs (executor is pure function)" },
  { key: "AUTO_PINS_CANDIDATES", type: "bool", frequent: false, note: "auto persist pins candidates from successful tasks" },
  { key: "AUTO_FILES_FROM_TEXT", type: "bool", frequent: false, note: "auto infer task.files by extracting repo-relative paths from title/goal" },
  { key: "AUTO_PINS_FROM_FILES", type: "bool", frequent: false, note: "auto create default pins when task.files is present and pins missing" },
  { key: "DISPATCH_IDEMPOTENCY", type: "bool", frequent: true, note: "prevent duplicate dispatch for a task when an active job exists" },
  { key: "OCCLI_REQUIRE_SUBMIT", type: "bool", frequent: true, note: "fail-closed if occli task completes without SUBMIT contract" },
  { key: "FIXUP_FUSE_ENABLED", type: "bool", frequent: true, note: "disable auto fixups under high backlog to prevent storms" },
  { key: "FIXUP_FUSE_QUEUE_THRESHOLD", type: "number", frequent: false, note: "queued jobs threshold for fixup fuse" },
  { key: "QUALITY_GATE_FAIL_RATE", type: "number", frequent: false, note: "block dispatch if area fail rate >= threshold (0-1)" },
  { key: "QUALITY_GATE_WINDOW", type: "number", frequent: false, note: "recent events window size for quality gate" },
  { key: "QUALITY_GATE_MIN_SAMPLES", type: "number", frequent: false, note: "min samples before quality gate applies" },
  { key: "AUTO_FLOW_CONTROLLER", type: "bool", frequent: true, note: "auto split parent tasks + log bottlenecks" },
  { key: "AUTO_FLOW_CONTROLLER_TICK_MS", type: "number", frequent: false, note: "controller tick interval in ms" },
  { key: "AUTO_FLOW_CONTROLLER_MAX_SPLIT", type: "number", frequent: false, note: "max parent splits per tick" },
  { key: "AUTO_FLOW_CONTROLLER_MAX_LOG", type: "number", frequent: false, note: "max bottleneck logs per tick" },
  { key: "FLOW_MANAGER_HOOK_ENABLED", type: "bool", frequent: true, note: "auto create factory_manager task on flow bottleneck" },
  { key: "FLOW_MANAGER_HOOK_MIN_MS", type: "number", frequent: false, note: "min ms between flow manager tasks (per reasons key)" },
  { key: "FLOW_MANAGER_HOOK_TAIL", type: "number", frequent: false, note: "leader log tail size for bottleneck summary" },
  { key: "FLOW_MANAGER_TASK_TIMEOUT_MS", type: "number", frequent: false, note: "timeout for flow manager tasks" },
  { key: "FEEDBACK_HOOK_ENABLED", type: "bool", frequent: true, note: "auto create factory_manager tasks on robustness feedback events" },
  { key: "FEEDBACK_HOOK_MIN_MS", type: "number", frequent: false, note: "min ms between feedback tasks for same event key" },
  { key: "FEEDBACK_HOOK_TAIL", type: "number", frequent: false, note: "leader log tail size for feedback summary" },
  { key: "LEARNED_PATTERNS_HOOK_ENABLED", type: "bool", frequent: true, note: "auto create factory_manager task when failure patterns shift/spike" },
  { key: "LEARNED_PATTERNS_HOOK_TICK_MS", type: "number", frequent: false, note: "learned patterns check interval in ms" },
  { key: "LEARNED_PATTERNS_HOOK_MIN_MS", type: "number", frequent: false, note: "min ms between learned patterns tasks" },
  { key: "LEARNED_PATTERNS_HOOK_DELTA_THRESHOLD", type: "number", frequent: false, note: "min delta in top reason count to trigger" },
  { key: "LEARNED_PATTERNS_TASK_TIMEOUT_MS", type: "number", frequent: false, note: "timeout for learned patterns manager tasks" },
  { key: "TOKEN_CFO_HOOK_ENABLED", type: "bool", frequent: true, note: "auto create factory_manager task when token waste is detected" },
  { key: "TOKEN_CFO_HOOK_TICK_MS", type: "number", frequent: false, note: "token CFO check interval in ms" },
  { key: "TOKEN_CFO_HOOK_MIN_MS", type: "number", frequent: false, note: "min ms between token CFO tasks" },
  { key: "TOKEN_CFO_UNUSED_RATIO", type: "number", frequent: false, note: "unused_ratio threshold to consider context waste" },
  { key: "TOKEN_CFO_INCLUDED_MIN", type: "number", frequent: false, note: "min included files before considering waste" },
  { key: "TOKEN_CFO_TASK_TIMEOUT_MS", type: "number", frequent: false, note: "timeout for token CFO manager tasks" },
  { key: "CI_GATE_ENABLED", type: "bool", frequent: true, note: "run CI/selftest gate after task completion" },
  { key: "CI_GATE_STRICT", type: "bool", frequent: true, note: "fail closed if tests required but cannot run" },
  { key: "CI_GATE_ALLOW_ALL", type: "bool", frequent: false, note: "allow any allowedTests command (unsafe)" },
  { key: "CI_GATE_TIMEOUT_MS", type: "number", frequent: false, note: "CI/selftest timeout in ms" },
  { key: "CI_GATE_CWD", type: "string", frequent: false, note: "CI/selftest working directory" },
  { key: "CI_ANTIFORGERY_SINCE_MS", type: "number", frequent: true, note: "from this timestamp, enforce anti-forgery validators (CI log hashes, mtime window)" },
  { key: "CI_FIXUP_ENABLED", type: "bool", frequent: true, note: "auto create CI fixup task when CI gate fails" },
  { key: "CI_FIXUP_MAX_PER_TASK", type: "number", frequent: false, note: "max CI fixups per task" },
  { key: "CI_FIXUP_ROLE", type: "string", frequent: false, note: "role for CI fixup tasks" },
  { key: "CI_FIXUP_ALLOWED_EXECUTORS", type: "string", frequent: false, note: "allowed executors for CI fixup" },
  { key: "CI_FIXUP_ALLOWED_MODELS", type: "string", frequent: false, note: "allowed models for CI fixup" },
  { key: "CI_FIXUP_TIMEOUT_MS", type: "number", frequent: false, note: "timeout for CI fixup tasks" },
  { key: "PINS_FIXUP_ENABLED", type: "bool", frequent: true, note: "auto create pins fixup task when a task fails due to pins" },
  { key: "PINS_FIXUP_MAX_PER_TASK", type: "number", frequent: false, note: "max pins fixups per task" },
  { key: "PINS_FIXUP_ROLE", type: "string", frequent: false, note: "role for pins fixup tasks" },
  { key: "PINS_FIXUP_ALLOWED_EXECUTORS", type: "string", frequent: false, note: "allowed executors for pins fixup" },
  { key: "PINS_FIXUP_ALLOWED_MODELS", type: "string", frequent: false, note: "allowed models for pins fixup" },
  { key: "PINS_FIXUP_TIMEOUT_MS", type: "number", frequent: false, note: "timeout for pins fixup tasks" },
]

function parseEnvText(raw) {
  const out = {}
  for (const line of String(raw ?? "").split(/\r?\n/g)) {
    const s = line.trim()
    if (!s || s.startsWith("#")) continue
    const idx = s.indexOf("=")
    if (idx <= 0) continue
    const k = s.slice(0, idx).trim()
    const v = s.slice(idx + 1).trim()
    if (!k) continue
    out[k] = v
  }
  return out
}

function readRuntimeEnv() {
  try {
    if (!fs.existsSync(runtimeEnvFile)) return { exists: false, path: runtimeEnvFile, values: {} }
    const raw = fs.readFileSync(runtimeEnvFile, "utf8")
    return { exists: true, path: runtimeEnvFile, values: parseEnvText(raw) }
  } catch {
    return { exists: false, path: runtimeEnvFile, values: {}, error: "read_failed" }
  }
}

function writeRuntimeEnv(values) {
  const keys = Object.keys(values || {}).sort((a, b) => a.localeCompare(b))
  const lines = ["# managed by oc-scc-local gateway", "# restart gateway/ensure-workers to apply changes", ""]
  for (const k of keys) {
    const v = values[k]
    if (v == null) continue
    lines.push(`${k}=${String(v)}`)
  }
  lines.push("")
  fs.mkdirSync(path.dirname(runtimeEnvFile), { recursive: true })
  fs.writeFileSync(runtimeEnvFile, lines.join("\n"), "utf8")
}

function loadFeatures() {
  const cfgPath = path.join(process.cwd(), "config", "features.json")
  const fallback = path.join(process.cwd(), "config", "features.sample.json")
  const base = {
    exposeScc: true,
    exposeOpenCode: true,
    exposeSccMcp: true,
    exposeOpenCodeMcp: false,
    exposeOpenCodeUi: true,
    exposeOpenCodeApi: true,
  }
  const file = fs.existsSync(cfgPath) ? cfgPath : fs.existsSync(fallback) ? fallback : null
  if (!file) return base
  try {
    const raw = fs.readFileSync(file, "utf8")
    return { ...base, ...JSON.parse(raw) }
  } catch {
    return base
  }
}

const features = loadFeatures()

function updateModelPools({ free, vision, occliDefault }) {
  if (Array.isArray(free) && free.length) {
    modelsFree = sortModelPool(free)
  }
  if (Array.isArray(vision) && vision.length) {
    modelsVision = sortModelPool(vision)
  }
  if (occliDefault) {
    occliModelDefault = String(occliDefault).trim()
  } else if (modelsFree.length) {
    occliModelDefault = modelsFree[0]
  }
}

fs.mkdirSync(execLogDir, { recursive: true })
fs.mkdirSync(ctxDir, { recursive: true })
fs.mkdirSync(threadDir, { recursive: true })
fs.mkdirSync(boardDir, { recursive: true })
fs.mkdirSync(roleErrorsDir, { recursive: true })

const proxy = httpProxy.createProxyServer({
  ws: true,
  xfwd: true,
  changeOrigin: true,
})

const SCC_PREFIXES = [
  "/desktop",
  "/scc",
  "/dashboard",
  "/viewer",
  "/client-config",
  "/mcp",
  "/health",
]

function isSccPath(pathname) {
  return SCC_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj, null, 2)
  res.statusCode = status
  res.setHeader("content-type", "application/json; charset=utf-8")
  res.setHeader("content-length", Buffer.byteLength(body))
  res.end(body)
}

function sendText(res, status, body) {
  res.statusCode = status
  res.setHeader("content-type", "text/plain; charset=utf-8")
  res.setHeader("content-length", Buffer.byteLength(body))
  res.end(body)
}

function readDocFile(relPath) {
  try {
    const file = path.join(docsRoot, relPath)
    if (!fs.existsSync(file)) return null
    return { file, text: fs.readFileSync(file, "utf8") }
  } catch {
    return null
  }
}

function extractJsonBlock(text, blockName) {
  const start = `<!-- MACHINE:${blockName} -->`
  const end = `<!-- /MACHINE:${blockName} -->`
  const s = text.indexOf(start)
  const e = text.indexOf(end)
  if (s < 0 || e < 0 || e <= s) return null
  const inner = text.slice(s + start.length, e).trim()
  const fenceStart = inner.indexOf("```json")
  const fenceEnd = inner.lastIndexOf("```")
  if (fenceStart >= 0 && fenceEnd > fenceStart) {
    const jsonText = inner.slice(fenceStart + "```json".length, fenceEnd).trim()
    return jsonText
  }
  return inner.trim()
}

function upsertJsonBlock(text, blockName, jsonObj) {
  const start = `<!-- MACHINE:${blockName} -->`
  const end = `<!-- /MACHINE:${blockName} -->`
  const jsonText = JSON.stringify(jsonObj, null, 2)
  const block = `${start}\n\`\`\`json\n${jsonText}\n\`\`\`\n${end}`
  const s = text.indexOf(start)
  const e = text.indexOf(end)
  if (s < 0 || e < 0 || e <= s) {
    return `${text.trim()}\n\n${block}\n`
  }
  return text.slice(0, s) + block + text.slice(e + end.length)
}

function readDocJsonBlock(relPath, blockName, fallback) {
  const doc = readDocFile(relPath)
  if (!doc) return { ok: false, error: "doc_missing", file: path.join(docsRoot, relPath) }
  const jsonText = extractJsonBlock(doc.text, blockName)
  if (!jsonText) return { ok: true, file: doc.file, data: fallback, missing: true }
  try {
    const data = JSON.parse(jsonText)
    return { ok: true, file: doc.file, data, missing: false }
  } catch (e) {
    return { ok: false, error: "json_invalid", file: doc.file, message: String(e) }
  }
}

function getCiHandbookText() {
  const block = readDocJsonBlock("AI_CONTEXT.md", "SSOT_AXIOMS_JSON", defaultSsotAxioms)
  if (!block.ok) return null
  const handbook = block.data?.ci_handbook
  if (!handbook) return null
  const steps = Array.isArray(handbook.steps)
    ? handbook.steps.map((s, i) => `${i + 1}. ${s}`).join("\n")
    : ""
  return `CI_HANDBOOK: ${handbook.title ?? "CI guide"}\n${steps}`
}

function readJsonlTail(file, limit) {
  try {
    if (!fs.existsSync(file)) return []
    const raw = fs.readFileSync(file, "utf8")
    const lines = raw
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0)
    const tail = Number.isFinite(limit) && limit > 0 ? lines.slice(-limit) : lines
    return tail
      .map((l) => {
        try {
          return JSON.parse(l)
        } catch {
          return null
        }
      })
      .filter(Boolean)
  } catch {
    return []
  }
}

function loadAuditTriggerState() {
  try {
    if (!fs.existsSync(auditTriggerStateFile)) {
      return {
        done_since_last: 0,
        total_done: 0,
        last_audit_at: null,
        last_audit_batch: null,
        last_audit_task_id: null,
      }
    }
    const raw = fs.readFileSync(auditTriggerStateFile, "utf8")
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") throw new Error("invalid")
    return {
      done_since_last: Number(parsed.done_since_last ?? 0),
      total_done: Number(parsed.total_done ?? 0),
      last_audit_at: parsed.last_audit_at ?? null,
      last_audit_batch: parsed.last_audit_batch ?? null,
      last_audit_task_id: parsed.last_audit_task_id ?? null,
    }
  } catch {
    return {
      done_since_last: 0,
      total_done: 0,
      last_audit_at: null,
      last_audit_batch: null,
      last_audit_task_id: null,
    }
  }
}

function saveAuditTriggerState(state) {
  try {
    fs.writeFileSync(auditTriggerStateFile, JSON.stringify(state, null, 2), "utf8")
  } catch {
    // best-effort
  }
}

function loadFlowManagerState() {
  try {
    if (!fs.existsSync(flowManagerStateFile)) {
      return {
        last_created_at: 0,
        last_reasons_key: null,
      }
    }
    const raw = fs.readFileSync(flowManagerStateFile, "utf8")
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") throw new Error("invalid")
    return {
      last_created_at: Number(parsed.last_created_at ?? 0),
      last_reasons_key: parsed.last_reasons_key ?? null,
    }
  } catch {
    return {
      last_created_at: 0,
      last_reasons_key: null,
    }
  }
}

function saveFlowManagerState(state) {
  try {
    fs.writeFileSync(flowManagerStateFile, JSON.stringify(state, null, 2), "utf8")
  } catch {
    // best-effort
  }
}

function loadFeedbackHookState() {
  try {
    if (!fs.existsSync(feedbackHookStateFile)) {
      return { last_created_at: {} }
    }
    const raw = fs.readFileSync(feedbackHookStateFile, "utf8")
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") throw new Error("invalid")
    const last = parsed.last_created_at && typeof parsed.last_created_at === "object" ? parsed.last_created_at : {}
    return { last_created_at: last }
  } catch {
    return { last_created_at: {} }
  }
}

function saveFeedbackHookState(state) {
  try {
    fs.writeFileSync(feedbackHookStateFile, JSON.stringify(state, null, 2), "utf8")
  } catch {
    // best-effort
  }
}

function computeHotspots(events) {
  const byArea = {}
  const byFile = {}
  for (const e of events) {
    const area = String(e?.area ?? "").trim()
    if (area) byArea[area] = (byArea[area] ?? 0) + 1
    const files = Array.isArray(e?.files) ? e.files : []
    for (const f of files) {
      const key = String(f)
      if (!key) continue
      byFile[key] = (byFile[key] ?? 0) + 1
    }
  }
  const topAreas = Object.entries(byArea)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([area, count]) => ({ area, count }))
  const topFiles = Object.entries(byFile)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([file, count]) => ({ file, count }))
  return { areas: topAreas, files: topFiles }
}

function summarizePins(pins) {
  if (!pins || typeof pins !== "object") return null
  const allowed = Array.isArray(pins.allowed_paths) ? pins.allowed_paths.map((x) => String(x)) : []
  const forbidden = Array.isArray(pins.forbidden_paths) ? pins.forbidden_paths.map((x) => String(x)) : []
  return {
    allowed_paths: allowed.slice(0, 8),
    forbidden_paths: forbidden.slice(0, 8),
    max_files: Number.isFinite(pins.max_files) ? pins.max_files : null,
    max_loc: Number.isFinite(pins.max_loc) ? pins.max_loc : null,
    symbols: Array.isArray(pins.symbols) ? pins.symbols.slice(0, 8) : null,
    line_windows: pins.line_windows ? Object.keys(pins.line_windows).slice(0, 6) : null,
  }
}

function computeAreaFailRate(area, windowSize, minSamples) {
  const key = String(area ?? "").trim()
  if (!key) return null
  const limit = Number.isFinite(windowSize) ? windowSize : 80
  const events = readJsonlTail(stateEventsFile, limit).filter((e) => String(e?.area ?? "").trim() === key)
  const relevant = events.filter((e) => e?.status === "done" || e?.status === "failed")
  if (!relevant.length) return null
  const min = Number.isFinite(minSamples) ? minSamples : 8
  if (relevant.length < min) return null
  const failed = relevant.filter((e) => e?.status === "failed").length
  return failed / relevant.length
}

function appendPinsCandidate(task, job) {
  if (!autoPinsCandidates) return
  const pins = resolvePinsForTask(task)
  if (!pins) return
  const candidate = {
    t: new Date().toISOString(),
    task_id: task?.id ?? null,
    area: task?.area ?? null,
    task_class: task?.task_class_id ?? task?.task_class_candidate ?? null,
    executor: job?.executor ?? null,
    model: job?.model ?? null,
    pins,
  }
  appendJsonl(pinsCandidatesFile, candidate)
}

function loadTaskClassLibrary() {
  const out = readDocJsonBlock("AI_CONTEXT.md", "TASK_CLASS_LIBRARY_JSON", defaultTaskClassLibrary)
  return out.ok ? out.data : defaultTaskClassLibrary
}

function loadPinsTemplates() {
  const out = readDocJsonBlock("AI_CONTEXT.md", "PINS_TEMPLATES_JSON", defaultPinsTemplates)
  return out.ok ? out.data : defaultPinsTemplates
}

function findTaskClass(task) {
  const id = String(task?.task_class_id ?? task?.task_class_candidate ?? "").trim()
  if (!id) return null
  const lib = loadTaskClassLibrary()
  const classes = Array.isArray(lib?.classes) ? lib.classes : []
  return classes.find((c) => String(c?.id ?? c?.name ?? c?.key ?? "").trim() === id) ?? null
}

function findPinsTemplateById(id) {
  const key = String(id ?? "").trim()
  if (!key) return null
  const lib = loadPinsTemplates()
  const templates = Array.isArray(lib?.templates) ? lib.templates : []
  return templates.find((t) => String(t?.id ?? t?.name ?? t?.key ?? "").trim() === key) ?? null
}

function mergePinsTemplate(template, instance) {
  if (!template && !instance) return null
  const t = template && typeof template === "object" ? template : {}
  const i = instance && typeof instance === "object" ? instance : {}
  const allowedBase = Array.isArray(t.allowed_paths) ? t.allowed_paths : []
  const forbiddenBase = Array.isArray(t.forbidden_paths) ? t.forbidden_paths : []
  const symbolsBase = Array.isArray(t.symbols) ? t.symbols : []
  const allowedExtra = Array.isArray(i.allowed_paths) ? i.allowed_paths : Array.isArray(i.allowed_paths_add) ? i.allowed_paths_add : []
  const forbiddenExtra = Array.isArray(i.forbidden_paths) ? i.forbidden_paths : Array.isArray(i.forbidden_paths_add) ? i.forbidden_paths_add : []
  const symbolsExtra = Array.isArray(i.symbols) ? i.symbols : Array.isArray(i.symbols_add) ? i.symbols_add : []
  const lineWindows = { ...(t.line_windows ?? {}), ...(i.line_windows ?? {}) }
  const maxFiles = Number.isFinite(i.max_files) ? i.max_files : Number.isFinite(t.max_files) ? t.max_files : null
  const maxLoc = Number.isFinite(i.max_loc) ? i.max_loc : Number.isFinite(t.max_loc) ? t.max_loc : null
  const ssotAssumptions = Array.isArray(i.ssot_assumptions) ? i.ssot_assumptions : Array.isArray(t.ssot_assumptions) ? t.ssot_assumptions : null
  return {
    allowed_paths: Array.from(new Set([...allowedBase, ...allowedExtra].map((x) => String(x)))).slice(0, 64),
    forbidden_paths: Array.from(new Set([...forbiddenBase, ...forbiddenExtra].map((x) => String(x)))).slice(0, 64),
    symbols: Array.from(new Set([...symbolsBase, ...symbolsExtra].map((x) => String(x)))).slice(0, 64),
    line_windows: Object.keys(lineWindows).length ? lineWindows : undefined,
    max_files: maxFiles ?? undefined,
    max_loc: maxLoc ?? undefined,
    ssot_assumptions: Array.isArray(ssotAssumptions) && ssotAssumptions.length ? ssotAssumptions.slice(0, 7) : undefined,
  }
}

function pickAllowedTestsForTask(task) {
  if (Array.isArray(task?.allowedTests) && task.allowedTests.length) return task.allowedTests
  const found = findTaskClass(task)
  const tests = Array.isArray(found?.allowlist_tests) ? found.allowlist_tests : Array.isArray(found?.allowed_tests) ? found.allowed_tests : Array.isArray(found?.allowedTests) ? found.allowedTests : null
  let list = Array.isArray(tests) ? tests.filter(Boolean) : []
  const hasNonSelf = list.some((t) => !String(t ?? "").toLowerCase().includes("task_selftest"))
  if (!hasNonSelf) list.push("python -m pytest -q")
  return list.length ? list : ["python -m pytest -q"]
}

function resolvePinsForTask(task) {
  if (task?.pins && typeof task.pins === "object") return task.pins
  const pinsInstance = task?.pins_instance && typeof task.pins_instance === "object" ? task.pins_instance : null
  const classInfo = findTaskClass(task)
  const templateId =
    String(pinsInstance?.template_id ?? pinsInstance?.templateId ?? classInfo?.pins_template ?? classInfo?.pinsTemplate ?? "").trim() || null
  const template = templateId ? findPinsTemplateById(templateId) : null
  if (!template && !pinsInstance) return null
  const merged = mergePinsTemplate(template, pinsInstance)
  return merged
}

function buildContractForTask(task, goal) {
  const classInfo = findTaskClass(task)
  const baseContract = task?.contract && typeof task.contract === "object" ? task.contract : null
  const acceptance =
    baseContract?.acceptance ??
    classInfo?.acceptance_template ??
    classInfo?.acceptanceTemplate ??
    classInfo?.acceptance ??
    null
  const stopCodes = baseContract?.stop_codes ?? baseContract?.stopCodes ?? classInfo?.stop_codes ?? classInfo?.stopCodes ?? null
  const stop =
    baseContract?.stop ??
    classInfo?.stop ??
    "If pins are insufficient or tests fail, return fail."
  const out = {
    goal: baseContract?.goal ?? goal ?? task?.goal ?? "",
    acceptance,
    stop,
    stop_codes: Array.isArray(stopCodes) && stopCodes.length ? stopCodes : undefined,
  }
  return out
}

function appendJsonl(file, value) {
  try {
    fs.appendFileSync(file, JSON.stringify(value) + "\n", "utf8")
  } catch {
    // best-effort logging; do not break request execution
  }
}

function getLastCiGateSummary(taskId) {
  if (!taskId) return null
  const rows = readJsonlTail(ciGateResultsFile, 200).reverse()
  const hit = rows.find((r) => String(r?.task_id ?? "") === String(taskId))
  if (!hit) return null
  return {
    when: hit.t ?? hit.startedAt ?? null,
    ran: hit.ran ?? null,
    skipped: hit.skipped ?? null,
    exitCode: hit.exitCode ?? null,
    timedOut: hit.timedOut ?? null,
    stderrPreview: hit.stderrPreview ?? null,
    stdoutPreview: hit.stdoutPreview ?? null,
    command: hit.command ?? null,
  }
}

function getLastCiFailure(taskId) {
  if (!taskId) return null
  const rows = readJsonlTail(ciFailuresFile, 200).reverse()
  const hit = rows.find((r) => String(r?.task_id ?? "") === String(taskId))
  if (!hit) return null
  return {
    when: hit.t ?? null,
    reason: hit.reason ?? null,
    exitCode: hit.exitCode ?? null,
    skipped: hit.skipped ?? null,
    stderrPreview: hit.stderrPreview ?? null,
    stdoutPreview: hit.stdoutPreview ?? null,
  }
}

// Append with hash-chain for anti-tamper (simple, local).
function appendJsonlChained(file, value) {
  let prevHash = null
  try {
    if (fs.existsSync(file)) {
      const lines = fs.readFileSync(file, "utf8").trim().split("\n")
      for (let i = lines.length - 1; i >= 0; i--) {
        const s = lines[i].trim()
        if (!s) continue
        try {
          const obj = JSON.parse(s)
          if (obj && obj.chain_hash) {
            prevHash = obj.chain_hash
            break
          }
        } catch {
          // ignore parse errors
        }
      }
    }
  } catch {
    // ignore
  }

  const record = { ...value, chain_prev_hash: prevHash ?? null }
  try {
    const payload = JSON.stringify(record)
    const hash = crypto.createHash("sha256").update(payload).digest("hex")
    record.chain_hash = hash
    fs.appendFileSync(file, JSON.stringify(record) + "\n", "utf8")
  } catch {
    // best effort
  }
}

function ensureDir(dir) {
  try {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
  } catch {
    // ignore
  }
}

function countJsonlLines(file) {
  try {
    if (!fs.existsSync(file)) return 0
    const raw = fs.readFileSync(file, "utf8")
    if (!raw) return 0
    return raw.split("\n").filter((l) => String(l).trim().length > 0).length
  } catch {
    return 0
  }
}

function loadFiveWhysHookState() {
  try {
    if (!fs.existsSync(fiveWhysHookStateFile)) return { last_triggered_at: 0, last_failures_count: 0 }
    const raw = fs.readFileSync(fiveWhysHookStateFile, "utf8")
    const parsed = JSON.parse(raw)
    return {
      last_triggered_at: Number(parsed?.last_triggered_at ?? 0),
      last_failures_count: Number(parsed?.last_failures_count ?? 0),
    }
  } catch {
    return { last_triggered_at: 0, last_failures_count: 0 }
  }
}

function saveFiveWhysHookState(next) {
  try {
    fs.writeFileSync(fiveWhysHookStateFile, JSON.stringify(next, null, 2), "utf8")
  } catch {
    // best effort
  }
}

function loadRadiusAuditHookState() {
  try {
    if (!fs.existsSync(radiusAuditHookStateFile)) return { last_triggered_at: 0, done_since_last: 0 }
    const raw = fs.readFileSync(radiusAuditHookStateFile, "utf8")
    const parsed = JSON.parse(raw)
    return {
      last_triggered_at: Number(parsed?.last_triggered_at ?? 0),
      done_since_last: Number(parsed?.done_since_last ?? 0),
    }
  } catch {
    return { last_triggered_at: 0, done_since_last: 0 }
  }
}

function saveRadiusAuditHookState(next) {
  try {
    fs.writeFileSync(radiusAuditHookStateFile, JSON.stringify(next, null, 2), "utf8")
  } catch {
    // best effort
  }
}

async function runRadiusAuditReport(taskId) {
  return new Promise((resolve) => {
    const safeTask = String(taskId || "").trim()
    const runId = `${safeTask || "unknown"}__${Date.now()}`
    const outDir = path.join(execLogDir, "radius_audit", "runs", runId)
    try {
      fs.mkdirSync(outDir, { recursive: true })
    } catch {
      // ignore
    }
    const script = "scc-top/tools/scc/ops/radius_audit.py"
    const args = [
      script,
      "--exec-log-dir",
      execLogDir.replaceAll("\\", "/"),
      "--board-dir",
      boardDir.replaceAll("\\", "/"),
      "--task-id",
      safeTask,
      "--out-dir",
      outDir.replaceAll("\\", "/"),
    ]
    execFile(
      "python",
      args,
      {
        cwd: "C:/scc",
        timeout: Math.max(60000, Math.min(10 * 60 * 1000, Number(radiusAuditHookTimeoutMs) || 180000)),
        maxBuffer: 10 * 1024 * 1024,
      },
      (err, stdout, stderr) => {
        resolve({
          ok: !err,
          code: err?.code ?? 0,
          outDir,
          stdout: String(stdout ?? "").trim(),
          stderr: String(stderr ?? "").trim() || (err ? String(err) : ""),
        })
      },
    )
  })
}

async function runFiveWhysReport() {
  return new Promise((resolve) => {
    const script = "scc-top/tools/scc/ops/five_whys.py"
    const args = [
      script,
      "--exec-log-dir",
      execLogDir.replaceAll("\\", "/"),
      "--events-tail",
      String(fiveWhysEventsTail),
      "--failures-tail",
      String(fiveWhysFailuresTail),
      "--max-items",
      String(fiveWhysMaxItems),
    ]
    execFile(
      "python",
      args,
      {
        cwd: "C:/scc",
        timeout: Math.max(60000, Math.min(20 * 60 * 1000, Number(fiveWhysTimeoutMs) || 300000)),
        maxBuffer: 10 * 1024 * 1024,
      },
      (err, stdout, stderr) => {
        resolve({
          ok: !err,
          code: err?.code ?? 0,
          stdout: String(stdout ?? "").trim(),
          stderr: String(stderr ?? "").trim() || (err ? String(err) : ""),
        })
      },
    )
  })
}

function yamlEscapeScalar(v) {
  const s = String(v ?? "")
  // Quote scalars by default to keep output stable even if it contains ":" or "#".
  const escaped = s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
  return `"${escaped}"`
}

function toYaml(value, indent = 0) {
  const pad = " ".repeat(indent)
  if (value === null || value === undefined) return "null"
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  if (typeof value === "string") return yamlEscapeScalar(value)
  if (Array.isArray(value)) {
    if (!value.length) return "[]"
    const lines = []
    for (const item of value) {
      if (item && typeof item === "object") {
        lines.push(`${pad}- ${toYaml(item, indent + 2).replace(/^\s*/, "")}`)
      } else {
        lines.push(`${pad}- ${toYaml(item, 0)}`)
      }
    }
    return lines.join("\n")
  }
  if (typeof value === "object") {
    const keys = Object.keys(value)
    if (!keys.length) return "{}"
    const lines = []
    for (const k of keys) {
      const v = value[k]
      if (v && typeof v === "object") {
        const rendered = toYaml(v, indent + 2)
        lines.push(`${pad}${k}:\n${rendered}`)
      } else {
        lines.push(`${pad}${k}: ${toYaml(v, 0)}`)
      }
    }
    return lines.join("\n")
  }
  return yamlEscapeScalar(String(value))
}

function sha1(text) {
  return crypto.createHash("sha1").update(String(text ?? ""), "utf8").digest("hex")
}

function normalizeForSignature(text) {
  const s = String(text ?? "")
    .replace(/[A-Z]:[\\/][^\\s"']+/gi, "<PATH>")
    .replace(/https?:\/\/\S+/gi, "<URL>")
    .replace(/\b\d+\b/g, "<N>")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
  return s.slice(0, 2000)
}

function tokensForSimhash(text) {
  const s = normalizeForSignature(text).replace(/[^a-z0-9_<>\u4e00-\u9fff ]/g, " ")
  const parts = s.split(" ").map((x) => x.trim()).filter(Boolean)
  const out = []
  for (const p of parts) {
    if (p.length <= 2) continue
    out.push(p)
  }
  return out.slice(0, 512)
}

function simhash64(tokens) {
  const v = new Array(64).fill(0)
  for (const t of tokens) {
    const h = crypto.createHash("sha1").update(t, "utf8").digest()
    // Take first 8 bytes as 64-bit hash basis.
    for (let i = 0; i < 64; i++) {
      const byte = h[Math.floor(i / 8)]
      const bit = (byte >> (i % 8)) & 1
      v[i] += bit ? 1 : -1
    }
  }
  let out = 0n
  for (let i = 0; i < 64; i++) {
    if (v[i] > 0) out |= 1n << BigInt(i)
  }
  return out
}

function hamming64(a, b) {
  let x = (a ^ b) & ((1n << 64n) - 1n)
  let c = 0
  while (x) {
    x &= x - 1n
    c++
  }
  return c
}

function classifyInstinctTaxonomy(failure) {
  const reason = String(failure?.reason ?? "unknown")
  const stderr = normalizeForSignature(failure?.stderrPreview ?? failure?.stderr ?? "")
  const stdout = normalizeForSignature(failure?.stdoutPreview ?? failure?.stdout ?? "")
  const msg = `${reason} ${stderr} ${stdout}`
  if (msg.includes("file not found") || msg.includes("no such file") || msg.includes("enotfound")) return "infra.fs.missing_file"
  if (msg.includes("&&") && msg.includes("not a valid statement separator")) return "infra.shell.powershell_syntax"
  if (msg.includes("missing_submit_contract") || msg.includes("submit")) return "executor.contract.submit"
  if (reason === "timeout") return "infra.process.timeout"
  if (reason.includes("unauthorized") || msg.includes("401")) return "model.auth.unauthorized"
  if (reason.includes("rate") || msg.includes("too many requests") || msg.includes("rate limit")) return "model.throttle.rate_limited"
  if (reason.includes("ci") || msg.includes("ci_gate")) return "ci.gate.failed"
  if (msg.includes("pins") || msg.includes("pins_apply_failed")) return "pins.quality.insufficient"
  return "unknown"
}

function extractErrorSignature(failure) {
  const reason = String(failure?.reason ?? "unknown")
  const stderr = String(failure?.stderrPreview ?? failure?.stderr ?? "")
  const stdout = String(failure?.stdoutPreview ?? failure?.stdout ?? "")
  const msg = `${stderr}\n${stdout}`
  const s = normalizeForSignature(msg)
  if (s.includes("&&") && s.includes("not a valid statement separator")) return "powershell_andand_separator"
  if (s.includes("file not found: follow the attached file")) return "occli_file_not_found_attached_file"
  if (s.includes("missing_submit_contract")) return "missing_submit_contract"
  if (s.includes("buninstallfailederror")) return "occli_bun_install_failed"
  if (s.includes("show help") && String(failure?.executor ?? "") === "opencodecli") return "occli_wrong_subcommand"
  if (reason === "timeout") return "timeout"
  // Try to capture the first explicit error line.
  const lines = msg.split(/\r?\n/g).map((l) => l.trim()).filter(Boolean)
  const errorLine =
    lines.find((l) => /^error[: ]/i.test(l)) ||
    lines.find((l) => l.toLowerCase().includes("exception")) ||
    lines.find((l) => l.toLowerCase().includes("traceback")) ||
    lines.find((l) => l.toLowerCase().includes("failed"))
  if (errorLine) return normalizeForSignature(errorLine).slice(0, 160)
  return "unknown"
}

function buildInstinctSnapshot({ failuresTail = 2000, jobsTail = 4000 } = {}) {
  ensureDir(instinctDir)
  const failures = readJsonlTail(execLogFailures, failuresTail).filter(Boolean)
  const jobs = readJsonlTail(execLogJobs, jobsTail).filter(Boolean)
  const jobUsageById = new Map()
  for (const j of jobs) {
    if (!j?.id) continue
    if (j?.usage && typeof j.usage === "object") jobUsageById.set(String(j.id), j.usage)
  }

  const patterns = new Map()
  for (const f of failures) {
    const taxonomy = classifyInstinctTaxonomy(f)
    const signature = extractErrorSignature(f)
    const reason = String(f?.reason ?? "unknown")
    const role = String(f?.role ?? "unknown")
    const taskClass = String(f?.task_class ?? f?.taskClass ?? "none")
    const executor = String(f?.executor ?? "unknown")
    const clusterKey = `${taxonomy}|${reason}|${signature}|${role}|${taskClass}|${executor}`

    const msg = `${f?.reason ?? ""} ${f?.stderrPreview ?? ""} ${f?.stdoutPreview ?? ""}`
    const sh = simhash64(tokensForSimhash(msg))

    const id = sha1(clusterKey)
    const cur = patterns.get(id) ?? {
      id,
      taxonomy,
      cluster_key: { taxonomy, reason, signature, role, task_class: taskClass, executor },
      count: 0,
      first_seen: f?.t ?? null,
      last_seen: f?.t ?? null,
      total_duration_ms: 0,
      sample_task_ids: [],
      sample_job_ids: [],
      sample_signatures: new Set(),
      simhashes: [],
      usage: { input_tokens: 0, output_tokens: 0, cached_input_tokens: 0, n: 0 },
    }

    cur.count += 1
    cur.last_seen = f?.t ?? cur.last_seen
    if (!cur.first_seen) cur.first_seen = f?.t ?? null
    cur.total_duration_ms += Number(f?.durationMs ?? 0)
    if (f?.task_id && cur.sample_task_ids.length < 6) cur.sample_task_ids.push(String(f.task_id))
    if (f?.id && cur.sample_job_ids.length < 6) cur.sample_job_ids.push(String(f.id))
    cur.sample_signatures.add(signature)
    cur.simhashes.push(sh)

    const usage = jobUsageById.get(String(f?.id ?? ""))
    if (usage) {
      cur.usage.input_tokens += Number(usage?.input_tokens ?? 0)
      cur.usage.output_tokens += Number(usage?.output_tokens ?? 0)
      cur.usage.cached_input_tokens += Number(usage?.cached_input_tokens ?? 0)
      cur.usage.n += 1
    }

    patterns.set(id, cur)
  }

  // Secondary merge: if two clusters share taxonomy+reason+role+task_class+executor and are simhash-close, merge signatures.
  const ids = Array.from(patterns.keys())
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      const a = patterns.get(ids[i])
      const b = patterns.get(ids[j])
      if (!a || !b) continue
      const ak = a.cluster_key
      const bk = b.cluster_key
      const sameLane =
        ak.taxonomy === bk.taxonomy &&
        ak.reason === bk.reason &&
        ak.role === bk.role &&
        ak.task_class === bk.task_class &&
        ak.executor === bk.executor
      if (!sameLane) continue
      const ah = a.simhashes.length ? a.simhashes[0] : null
      const bh = b.simhashes.length ? b.simhashes[0] : null
      if (!ah || !bh) continue
      if (hamming64(ah, bh) > 6) continue
      // Merge b into a (keep a's id as canonical).
      a.count += b.count
      a.total_duration_ms += b.total_duration_ms
      a.last_seen = a.last_seen && b.last_seen ? (a.last_seen > b.last_seen ? a.last_seen : b.last_seen) : a.last_seen ?? b.last_seen
      a.first_seen = a.first_seen && b.first_seen ? (a.first_seen < b.first_seen ? a.first_seen : b.first_seen) : a.first_seen ?? b.first_seen
      for (const t of b.sample_task_ids) if (a.sample_task_ids.length < 10) a.sample_task_ids.push(t)
      for (const jid of b.sample_job_ids) if (a.sample_job_ids.length < 10) a.sample_job_ids.push(jid)
      for (const sig of b.sample_signatures) a.sample_signatures.add(sig)
      a.usage.input_tokens += b.usage.input_tokens
      a.usage.output_tokens += b.usage.output_tokens
      a.usage.cached_input_tokens += b.usage.cached_input_tokens
      a.usage.n += b.usage.n
      patterns.delete(b.id)
      // Restart comparisons for safety.
      j = i
    }
  }

  const outPatterns = Array.from(patterns.values())
    .map((p) => ({
      id: p.id,
      taxonomy: p.taxonomy,
      cluster_key: p.cluster_key,
      count: p.count,
      first_seen: p.first_seen,
      last_seen: p.last_seen,
      avg_duration_ms: p.count ? Math.round(p.total_duration_ms / p.count) : 0,
      usage_avgs:
        p.usage.n > 0
          ? {
              input_tokens: Math.round(p.usage.input_tokens / p.usage.n),
              output_tokens: Math.round(p.usage.output_tokens / p.usage.n),
              cached_input_tokens: Math.round(p.usage.cached_input_tokens / p.usage.n),
            }
          : null,
      sample_task_ids: p.sample_task_ids,
      sample_job_ids: p.sample_job_ids,
      signatures: Array.from(p.sample_signatures).slice(0, 12),
    }))
    .sort((a, b) => (b.count * (b.avg_duration_ms + 1) - a.count * (a.avg_duration_ms + 1)))

  const taxonomyCounts = {}
  for (const p of outPatterns) taxonomyCounts[p.taxonomy] = (taxonomyCounts[p.taxonomy] ?? 0) + p.count

  const taxonomy = Object.entries(taxonomyCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ taxonomy: k, count: v }))

  const clustering_keys = [
    "taxonomy",
    "reason",
    "signature",
    "role",
    "task_class",
    "executor",
    "simhash(message) secondary-merge (hamming<=6) within same lane",
  ]

  return {
    t: new Date().toISOString(),
    window: { failures_tail: failuresTail, jobs_tail: jobsTail, failures: failures.length, patterns: outPatterns.length },
    taxonomy,
    clustering_keys,
    patterns: outPatterns.slice(0, 200),
  }
}

function renderInstinctSchemasYaml() {
  return toYaml({
    version: "v1",
    pattern_schema: {
      id: "sha1(cluster_key)",
      taxonomy: "string",
      cluster_key: {
        taxonomy: "string",
        reason: "string",
        signature: "string",
        role: "string",
        task_class: "string",
        executor: "string",
      },
      count: "int",
      first_seen: "iso8601|null",
      last_seen: "iso8601|null",
      avg_duration_ms: "int",
      usage_avgs: "object|null",
      sample_task_ids: ["uuid"],
      sample_job_ids: ["uuid"],
      signatures: ["string"],
    },
    playbook_schema: {
      id: "string",
      enabled_flag: "ENV var name; default false-safe",
      trigger: { taxonomy: "string", reason: "string", signature_contains: "string|null", min_count: "int" },
      observation: { metrics: ["string"], files: ["path"], endpoint_hints: ["string"] },
      remediation: { actions: ["string"], minimal_change_points: ["string"] },
      verification: { replay: ["command"], expected: "exit_code=0 and evidence present" },
      rollback: { steps: ["string"] },
    },
    skills_draft_schema: {
      name: "string",
      version: "string",
      trigger_patterns: ["pattern_id"],
      instructions: ["string"],
      verification: { replay: ["command"], expected: "exit_code=0" },
      rollout: { enabled_flag: "ENV var name" },
      rollback: { steps: ["string"] },
    },
  })
}

function renderInstinctPlaybooksYaml(snapshot) {
  const patterns = Array.isArray(snapshot?.patterns) ? snapshot.patterns : []
  const top = patterns.slice(0, 12)
  const playbooks = []
  for (const p of top) {
    const k = p.cluster_key ?? {}
    const id = `playbook__${p.id.slice(0, 12)}__v1`
    const enabledFlag = `PLAYBOOK_${p.id.slice(0, 12).toUpperCase()}_ENABLED`
    playbooks.push({
      id,
      enabled_flag: enabledFlag,
      trigger: {
        taxonomy: String(k.taxonomy ?? p.taxonomy ?? "unknown"),
        reason: String(k.reason ?? "unknown"),
        signature_contains: String((k.signature ?? "").slice(0, 64) || "unknown"),
        min_count: Math.min(5, Math.max(2, Number(p.count ?? 2))),
      },
      observation: {
        metrics: ["failures.count", "avg_duration_ms", "usage_avgs.input_tokens"],
        files: [execLogFailures, execLogJobs, stateEventsFile],
        endpoint_hints: ["/executor/debug/failures", "/executor/debug/summary", "/replay/task?task_id=..."],
      },
      remediation: {
        actions: [
          "生成一个厂长(factory_manager)任务：定位根因 -> 产出最小修复补丁 -> 增加可回放/自测证据。",
          "如属于 pins/contract 问题：优先补 pins 或收紧 pins allowlist，再重试(<=2)；避免无限重试风暴。",
        ],
        minimal_change_points: [
          "gateway: preflight/contract checks",
          "task_selftest.py: 增补可裁决证据要求",
          "pins templates: 收紧 files/window",
        ],
      },
      verification: {
        replay: [
          `powershell -ExecutionPolicy Bypass -Command \"Invoke-RestMethod http://127.0.0.1:${gatewayPort}/replay/task?task_id=${(p.sample_task_ids && p.sample_task_ids[0]) || "..." }\"`,
          `python scc-top/tools/scc/ops/task_selftest.py --task-id ${(p.sample_task_ids && p.sample_task_ids[0]) || "..."}`,
        ],
        expected: "exit_code=0 AND SUBMIT(touched_files/tests_run) present for new tasks",
      },
      rollback: {
        steps: [
          `在 runtime.env 将 ${enabledFlag}=false 并重启 daemon。`,
          "若修复引入行为回归：回滚对应最小 patch 或关闭触发条件。",
        ],
      },
    })
  }
  return toYaml({ version: "v1", generated_at: new Date().toISOString(), playbooks })
}

function renderInstinctSkillsDraftYaml(snapshot) {
  const patterns = Array.isArray(snapshot?.patterns) ? snapshot.patterns : []
  const top = patterns.slice(0, 6)
  const drafts = top.map((p) => ({
    name: `skill__auto__${p.taxonomy.replace(/[^a-z0-9_\\.]/gi, "_")}__v1`,
    version: "v1",
    trigger_patterns: [p.id],
    instructions: [
      "先用 /replay/task 回放失败上下文，复现失败并固定最小触发条件。",
      "输出最小修复补丁(只改必要文件)，并把验证命令写入 SUBMIT.tests_run。",
      "若 pins 不足：输出 pins patch + 原任务可重跑的证据，避免扩大上下文。",
    ],
    verification: {
      replay: [
        `powershell -ExecutionPolicy Bypass -Command \"Invoke-RestMethod http://127.0.0.1:${gatewayPort}/replay/task?task_id=${(p.sample_task_ids && p.sample_task_ids[0]) || "..." }\"`,
      ],
      expected: "replay->ci gate exit_code=0",
    },
    rollout: { enabled_flag: `SKILL_${p.id.slice(0, 12).toUpperCase()}_ENABLED` },
    rollback: { steps: ["关闭 enabled_flag 并重启", "回滚技能文件/规则文件"] },
  }))
  return toYaml({ version: "v1", generated_at: new Date().toISOString(), skills_draft: drafts })
}

function loadInstinctState() {
  try {
    if (!fs.existsSync(instinctStateFile)) return { seen: {}, last_run_at: null, last_triggered_at: 0, last_top_id: null }
    const raw = fs.readFileSync(instinctStateFile, "utf8")
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") throw new Error("invalid")
    const seen = parsed.seen && typeof parsed.seen === "object" ? parsed.seen : {}
    return {
      seen,
      last_run_at: parsed.last_run_at ?? null,
      last_triggered_at: Number(parsed.last_triggered_at ?? 0),
      last_top_id: parsed.last_top_id ?? null,
    }
  } catch {
    return { seen: {}, last_run_at: null, last_triggered_at: 0, last_top_id: null }
  }
}

function saveInstinctState(state) {
  try {
    fs.writeFileSync(instinctStateFile, JSON.stringify(state, null, 2), "utf8")
  } catch {
    // ignore
  }
}

function updateInstinctArtifacts() {
  ensureDir(instinctDir)
  const snap = buildInstinctSnapshot({ failuresTail: Number(process.env.INSTINCT_FAIL_TAIL ?? "2000"), jobsTail: Number(process.env.INSTINCT_JOBS_TAIL ?? "4000") })
  const state = loadInstinctState()
  state.last_run_at = new Date().toISOString()
  try {
    const top = Array.isArray(snap?.patterns) && snap.patterns.length ? snap.patterns[0] : null
    if (top?.id) state.seen[String(top.id)] = Number(top.count ?? 0)
  } catch {
    // ignore
  }
  saveInstinctState(state)
  try {
    fs.writeFileSync(instinctPatternsFile, JSON.stringify(snap, null, 2), "utf8")
  } catch {
    // ignore
  }
  try {
    fs.writeFileSync(instinctSchemasFile, renderInstinctSchemasYaml() + "\n", "utf8")
  } catch {
    // ignore
  }
  try {
    fs.writeFileSync(instinctPlaybooksFile, renderInstinctPlaybooksYaml(snap) + "\n", "utf8")
  } catch {
    // ignore
  }
  try {
    fs.writeFileSync(instinctSkillsDraftFile, renderInstinctSkillsDraftYaml(snap) + "\n", "utf8")
  } catch {
    // ignore
  }
  return snap
}

function maybeTriggerFactoryManagerFromInstinctSnapshot(snapshot) {
  if (!instinctHookEnabled) return { ok: false, error: "disabled" }
  if (!snapshot || typeof snapshot !== "object") return { ok: false, error: "missing_snapshot" }
  const patterns = Array.isArray(snapshot?.patterns) ? snapshot.patterns : []
  const top = patterns.length ? patterns[0] : null
  if (!top?.id) return { ok: false, error: "no_patterns" }
  const count = Number(top.count ?? 0)
  if (Number.isFinite(instinctHookMinCount) && instinctHookMinCount > 0 && count < instinctHookMinCount) {
    return { ok: false, error: "below_threshold" }
  }

  const state = loadInstinctState()
  const now = Date.now()
  if (Number.isFinite(instinctHookMinMs) && instinctHookMinMs > 0 && now - (state.last_triggered_at ?? 0) < instinctHookMinMs) {
    return { ok: false, error: "rate_limited" }
  }
  if (state.last_top_id === top.id) return { ok: false, error: "duplicate" }

  const title = `Instinct Builder: new top failure pattern (${top.taxonomy})`
  const goal = [
    "Role: FACTORY_MANAGER.",
    "Goal: turn clustered failures into a verified fix strategy (playbook) + a rollback-safe skill draft.",
    "Constraints: prefer minimal changes, add replay/CI evidence, avoid token-heavy investigation.",
    "Output: JSON {pattern, root_causes[], playbook, skill_draft, verification, rollback}.",
    "",
    "Top pattern:",
    JSON.stringify(top, null, 2),
    "",
    "Full snapshot (trimmed):",
    JSON.stringify({ t: snapshot.t, window: snapshot.window, taxonomy: snapshot.taxonomy, patterns: snapshot.patterns.slice(0, 30) }, null, 2),
  ].join("\n")

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "instinct_builder_response_v1",
    allowedExecutors: ["codex"],
    allowedModels: instinctHookAllowedModels,
    timeoutMs: instinctHookTimeoutMs,
  })
  if (!created.ok) return created

  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (dispatched.job) {
    dispatched.job.priority = 930
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCounts()
    const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
    else schedule()
  }

  state.last_triggered_at = now
  state.last_top_id = top.id
  saveInstinctState(state)
  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

function updateLearnedPatternsSummary() {
  // Best-effort aggregation of recent failures without LLM calls.
  const rows = readJsonlTail(learnedPatternsFile, 2000).filter(Boolean)
  const byReason = {}
  const byExecutor = {}
  const byTaskClass = {}
  for (const r of rows) {
    const reason = String(r.reason ?? "unknown")
    const exec = String(r.executor ?? "unknown")
    const cls = String(r.task_class ?? "none")
    byReason[reason] = (byReason[reason] ?? 0) + 1
    byExecutor[exec] = (byExecutor[exec] ?? 0) + 1
    byTaskClass[cls] = (byTaskClass[cls] ?? 0) + 1
  }
  const top = (obj) =>
    Object.entries(obj)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20)
      .map(([k, v]) => ({ key: k, count: v }))
  const summary = {
    t: new Date().toISOString(),
    window: { tail: 2000, total: rows.length },
    top_reasons: top(byReason),
    top_executors: top(byExecutor),
    top_task_classes: top(byTaskClass),
  }
  try {
    fs.writeFileSync(learnedPatternsSummaryFile, JSON.stringify(summary, null, 2), "utf8")
  } catch {
    // ignore
  }
  return summary
}

function leader(event) {
  const enriched = { t: new Date().toISOString(), ...event }
  appendJsonl(execLeaderLog, enriched)
  maybeTriggerFactoryManagerFromEvent(enriched)
}

function saveState() {
  try {
    const arr = Array.from(jobs.values())
    fs.writeFileSync(execStateFile, JSON.stringify(arr, null, 2), "utf8")
  } catch {
    // best-effort
  }
}

function loadState() {
  try {
    if (!fs.existsSync(execStateFile)) return []
    const raw = fs.readFileSync(execStateFile, "utf8")
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function classifyFailure(job, result) {
  const stderr = String(result?.stderr ?? "")
  if (stderr.includes("BunInstallFailedError")) return "occli_bun_install_failed"
  if (stderr.includes("registry.npmjs.org") && stderr.includes("404")) return "occli_plugin_404"
  if (stderr.toLowerCase().includes("rate limit") || stderr.toLowerCase().includes("too many requests")) return "rate_limited"
  if (stderr.toLowerCase().includes("unauthorized") || stderr.includes("401")) return "unauthorized"
  if (stderr.toLowerCase().includes("forbidden") || stderr.includes("403")) return "forbidden"
  if (stderr.toLowerCase().includes("network") || stderr.toLowerCase().includes("econnreset")) return "network_error"
  if (stderr.toLowerCase().includes("timeout") || result?.timedOut) return "timeout"
  if (stderr.includes("No such file or directory") || stderr.includes("not recognized")) return "missing_binary"
  if (job.executor === "opencodecli" && stderr.includes("show help")) return "wrong_subcommand"
  return "executor_error"
}

const execCodex = (args, input, { timeoutMs } = {}) =>
  new Promise((resolve) => {
    const child = execFile(codexBin, args, { timeout: timeoutMs ?? timeoutCodexMs, maxBuffer: 50 * 1024 * 1024 }, (err, stdout, stderr) => {
      const code = err?.code ?? 0
      resolve({
        ok: !err,
        code,
        stdout: stdout?.trim() ?? "",
        stderr: stderr?.trim() ?? (err ? String(err) : ""),
        timedOut: Boolean(err && (err.killed || String(err).toLowerCase().includes("etimedout"))),
      })
    })
    if (input && child.stdin) {
      child.stdin.write(input)
      child.stdin.end()
    }
  })

async function codexHealth() {
  return execCodex(["--version"])
}

async function codexRunSingle(prompt, model = codexModelDefault, { timeoutMs } = {}) {
  // Use non-interactive exec mode; pass prompt via stdin.
  return execCodex(
    ["exec", "--model", model, "--sandbox", "read-only", "--skip-git-repo-check", "--json", "-C", execRoot, "--dangerously-bypass-approvals-and-sandbox"],
    prompt,
    { timeoutMs },
  )
}

async function occliRunSingle(prompt, model = occliModelDefault, { timeoutMs } = {}) {
  return new Promise((resolve) => {
    // Avoid Windows ENAMETOOLONG by attaching the full prompt as a temp file.
    // 已知 --file 容易触发 “File not found: <message>”，这里强制禁用文件路径，直接传消息。
    let promptFile = null

    const message = promptFile ? "" : String(prompt ?? "")
    const child = execFile(
      occliBin,
      [
        "run",
        "--format",
        "json",
        "--model",
        model,
        "--variant",
        occliVariantDefault,
        ...(promptFile ? ["--file", promptFile] : []),
        ...(message ? [message] : []),
      ],
      {
        timeout: timeoutMs ?? timeoutOccliMs,
        maxBuffer: 50 * 1024 * 1024,
        cwd: execRoot,
        env: {
          ...process.env,
          OPENCODE_DISABLE_PROJECT_CONFIG: "true",
          OPENCODE_CONFIG_CONTENT: JSON.stringify({
            $schema: "https://opencode.ai/config.json",
            plugin: [],
          }),
        },
      },
      (err, stdout, stderr) => {
        resolve({
          ok: !err || err?.code === 0,
          code: err?.code ?? (err ? 1 : 0),
          stdout: stdout?.trim() ?? "",
          stderr: stderr?.trim() ?? (err ? String(err) : ""),
          timedOut: Boolean(err && (err.killed || String(err).toLowerCase().includes("etimedout"))),
        })
        if (promptFile) {
          try {
            fs.unlinkSync(promptFile)
          } catch {
            // best-effort cleanup
          }
        }
      },
    )
    if (child.stdin) child.stdin.end()
  })
}

// ---------------- Job queue for non-blocking execution ----------------
const jobs = new Map()
const newJobId = () => crypto.randomUUID()
let scheduling = false

const newCtxId = () => crypto.randomUUID()
const newThreadId = () => crypto.randomUUID()
const newBoardTaskId = () => crypto.randomUUID()

// ---------------- Project taskboard (long-lived) ----------------
const boardTasks = new Map()

const ROLE_NAMES = [
  "designer",
  "architect",
  "integrator",
  "engineer",
  "qa",
  "doc",
  "auditor",
  "status_review",
  "factory_manager",
  "pinser",
]

const STRICT_DESIGNER_MODEL = process.env.STRICT_DESIGNER_MODEL ?? "gpt-5.2"
const roleConfigFile = process.env.ROLE_CONFIG_FILE ?? "C:/scc/oc-scc-local/config/roles.json"

function normalizeRole(v) {
  const s = String(v ?? "").trim().toLowerCase()
  return ROLE_NAMES.includes(s) ? s : null
}

function loadRoleConfig() {
  try {
    if (!fs.existsSync(roleConfigFile)) return null
    const raw = fs.readFileSync(roleConfigFile, "utf8")
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === "object" ? parsed : null
  } catch {
    return null
  }
}

function roleConfigRules(role) {
  const cfg = loadRoleConfig()
  const roles = cfg?.roles && typeof cfg.roles === "object" ? cfg.roles : null
  const r = roles?.[role]
  const rules = Array.isArray(r?.rules) ? r.rules.map((x) => String(x)) : null
  return rules && rules.length ? rules.join("\n") : null
}

function roleConfigSkills(role) {
  const cfg = loadRoleConfig()
  const roles = cfg?.roles && typeof cfg.roles === "object" ? cfg.roles : null
  const r = roles?.[role]
  const skills = Array.isArray(r?.skills) ? r.skills.map((x) => String(x)).filter((x) => x.trim().length) : null
  return skills && skills.length ? skills.slice(0, 16) : null
}

function roleRules(role) {
  const fromConfig = roleConfigRules(role)
  if (fromConfig) return fromConfig

  if (role === "designer") {
    return [
      "Role: DESIGNER.",
      "Primary job: produce an actionable task breakdown and clear interfaces for others to implement.",
      "Output MUST be structured JSON when asked (no prose-only).",
      "Prefer small, independently runnable atomic tasks (<10 minutes each).",
      "Do not propose scanning the repo; use provided context pack only.",
    ].join("\n")
  }
  if (role === "auditor") {
    return [
      "Role: AUDITOR.",
      "Primary job: inspect logs and on-disk evidence, then report findings + concrete next actions.",
      "Focus on: failures bursts, timeouts, model/role constraints, missing patches, queue health.",
      "Output MUST be a JSON report with: summary, findings[], recommendations[], nextTasks[].",
      "Do NOT propose scanning the repo; only use provided context pack and listed endpoints.",
    ].join("\n")
  }
  if (role === "status_review") {
    return [
      "Role: STATUS_REVIEW.",
      "Primary job: audit completion/evidence/functional status for a batch of tasks and emit a status review report.",
      "Output MUST be a markdown report under docs/REPORT/control_plane with a STATUS_REVIEW tag and a JSON summary block.",
      "Do NOT modify code; only inspect logs, board state, and referenced artifacts.",
    ].join("\n")
  }
  if (role === "architect") {
    return [
      "Role: ARCHITECT.",
      "Primary job: define module boundaries, APIs, and migration strategy.",
      "Keep changes minimal and consistent with existing style.",
    ].join("\n")
  }
  if (role === "integrator") {
    return [
      "Role: INTEGRATOR.",
      "Primary job: wire systems together with minimal diffs and predictable behavior.",
      "Prefer glue code and adapters; avoid sweeping refactors.",
    ].join("\n")
  }
  if (role === "qa") {
    return [
      "Role: QA.",
      "Primary job: define acceptance tests, smoke checks, and failure triage steps.",
      "Output exact commands and expected outputs.",
    ].join("\n")
  }
  if (role === "doc") {
    return [
      "Role: DOC.",
      "Primary job: write concise runbooks and navigation; ensure single authoritative entrypoints.",
    ].join("\n")
  }
  return [
    "Role: ENGINEER.",
    "Primary job: implement requested changes with patches or exact commands.",
  ].join("\n")
}

function roleSkills(role) {
  return roleConfigSkills(role) ?? []
}

function loadMission() {
  const fallback = {
    id: "mission",
    title: "SCC automated code factory",
    goal: "SCC becomes a fully automated code-generation factory. Current parent task: SCC x OpenCode fusion.",
    statusDocUrl: `http://127.0.0.1:${gatewayPort}/docs/STATUS.md`,
    worklogUrl: `http://127.0.0.1:${gatewayPort}/docs/WORKLOG.md`,
    missionDocUrl: `http://127.0.0.1:${gatewayPort}/docs/MISSION.md`,
    updatedAt: Date.now(),
  }
  try {
    if (!fs.existsSync(missionFile)) return fallback
    const raw = fs.readFileSync(missionFile, "utf8")
    const parsed = JSON.parse(raw)
    return { ...fallback, ...(parsed && typeof parsed === "object" ? parsed : {}) }
  } catch {
    return fallback
  }
}

function saveMission(m) {
  try {
    fs.writeFileSync(missionFile, JSON.stringify(m, null, 2), "utf8")
  } catch {
    // best-effort
  }
}

function loadBoard() {
  try {
    if (!fs.existsSync(boardFile)) return []
    const raw = fs.readFileSync(boardFile, "utf8")
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveBoard() {
  try {
    const arr = Array.from(boardTasks.values())
    fs.writeFileSync(boardFile, JSON.stringify(arr, null, 2), "utf8")
  } catch {
    // best-effort
  }
}

const BOARD_STATUS = ["backlog", "needs_split", "ready", "in_progress", "blocked", "done", "failed"]

function normalizeBoardStatus(v) {
  const s = String(v ?? "").trim()
  return BOARD_STATUS.includes(s) ? s : null
}

function listBoardTasks() {
  return Array.from(boardTasks.values()).sort((a, b) => (a.createdAt ?? 0) - (b.createdAt ?? 0))
}

function getBoardTask(id) {
  return boardTasks.get(id) ?? null
}

function putBoardTask(t) {
  boardTasks.set(t.id, t)
  saveBoard()
}

function deleteBoardTask(id) {
  if (!boardTasks.has(id)) return false
  boardTasks.delete(id)
  saveBoard()
  leader({ level: "info", type: "board_task_deleted", id })
  return true
}

function normalizeRepoPath(v) {
  let s = String(v ?? "").trim()
  if (!s) return null
  s = s.replaceAll("\\", "/")
  s = s.replace(/^\.\/+/, "")
  // Strip a leading absolute workspace prefix if present.
  s = s.replace(/^[a-zA-Z]:\/scc\//, "")
  // Reject absolute / traversal / urls.
  if (s.startsWith("/") || s.includes("..") || s.includes("://")) return null
  // Reject other drive paths.
  if (/^[a-zA-Z]:\//.test(s)) return null
  if (s.length > 240) return null
  return s
}

function extractRepoPathsFromText(text) {
  const t = String(text ?? "")
  const out = new Set()
  // Avoid partial matches inside longer extensions (e.g. "jobs.jsonl" should NOT match "jobs.js").
  const re = /([a-zA-Z0-9_.\-\\/]+?\.(?:md|mjs|js|ts|tsx|py|json|yaml|yml|toml|ps1|sh))(?![a-zA-Z0-9])/g
  let m
  while ((m = re.exec(t))) {
    const norm = normalizeRepoPath(m[1])
    if (norm) out.add(norm)
    if (out.size >= 16) break
  }
  return Array.from(out)
}

function defaultPinsForFiles(files) {
  const allowed = Array.isArray(files) ? files.map((x) => String(x)).slice(0, 16) : []
  return {
    allowed_paths: allowed,
    forbidden_paths: [".git", "node_modules", "dist", "build", "coverage"],
    symbols: [],
    line_windows: {},
    max_files: Math.max(1, Math.min(allowed.length, 8)),
    max_loc: 240,
    ssot_assumptions: [],
  }
}

function createBoardTask(payload) {
  const now = Date.now()
  const title = String(payload?.title ?? "").trim()
  const goal = String(payload?.goal ?? "").trim()
  if (!title) return { ok: false, error: "missing_title" }
  if (!goal) return { ok: false, error: "missing_goal" }
  const status = normalizeBoardStatus(payload?.status) ?? "backlog"
  const kind = payload?.kind === "parent" ? "parent" : "atomic"
  const id = newBoardTaskId()
  const role = normalizeRole(payload?.role)
  const allowedExecutors = Array.isArray(payload?.allowedExecutors)
    ? payload.allowedExecutors.map((x) => String(x)).filter((x) => x === "codex" || x === "opencodecli")
    : ["opencodecli", "codex"]
  const allowedModels = Array.isArray(payload?.allowedModels) ? payload.allowedModels.map((x) => String(x)).slice(0, 8) : []
  let files = Array.isArray(payload?.files) ? payload.files.map((x) => String(x)).slice(0, 16) : []
  const skillsFromPayload = Array.isArray(payload?.skills) ? payload.skills.map((x) => String(x)).slice(0, 16) : []
  const skills = skillsFromPayload.length ? skillsFromPayload : role ? roleSkills(role) : []
  const pointers = payload?.pointers && typeof payload.pointers === "object" ? payload.pointers : null
  let pins = payload?.pins && typeof payload.pins === "object" ? payload.pins : null
  const pinsInstance = payload?.pins_instance && typeof payload.pins_instance === "object" ? payload.pins_instance : null
  const pinsPending = payload?.pins_pending === true
  const pinsTargetId = payload?.pins_target_id ? String(payload.pins_target_id) : null
  const contract = payload?.contract && typeof payload.contract === "object" ? payload.contract : null
  const assumptions = Array.isArray(payload?.assumptions) ? payload.assumptions.map((x) => String(x)).slice(0, 16) : null
  let allowedTests = Array.isArray(payload?.allowedTests) ? payload.allowedTests.map((x) => String(x)).slice(0, 24) : null
  const toolingRules = payload?.toolingRules && typeof payload.toolingRules === "object" ? payload.toolingRules : null
  const area = payload?.area != null ? String(payload.area).trim() : null
  const taskClassId = payload?.task_class_id != null ? String(payload.task_class_id).trim() : null
  const taskClassCandidate = payload?.task_class_candidate != null ? String(payload.task_class_candidate).trim() : null
  const taskClassParams = payload?.task_class_params && typeof payload.task_class_params === "object" ? payload.task_class_params : null
  const timeoutMs = payload?.timeoutMs != null ? Number(payload.timeoutMs) : null
  const runner = payload?.runner === "external" ? "external" : payload?.runner === "internal" ? "internal" : "external"

  // Hard gate: must include至少一条非 task_selftest 的 allowedTests
  const normalizedTests = Array.isArray(allowedTests) ? allowedTests.map((t) => String(t ?? "").trim()).filter(Boolean) : []
  const hasNonSelf = normalizedTests.some((t) => !t.toLowerCase().includes("task_selftest"))
  if (!hasNonSelf) return { ok: false, error: "missing_real_test", message: "allowedTests must include at least one non-task_selftest command" }

  // B-mode friendly defaults: infer files and pins aggressively to reduce pins churn and token burn.
  if (autoFilesFromText && (!Array.isArray(files) || files.length === 0)) {
    files = extractRepoPathsFromText(`${title}\n${goal}`)
  }
  if (autoPinsFromFiles && (!pins || typeof pins !== "object") && Array.isArray(files) && files.length) {
    pins = defaultPinsForFiles(files)
  }

  const task = {
    id,
    kind,
    title,
    goal,
    parentId: payload?.parentId ? String(payload.parentId) : null,
    status,
    role,
    allowedExecutors,
    allowedModels,
    files,
    skills,
    pointers,
    pins,
    pins_instance: pinsInstance,
    pins_pending: pinsPending,
    pins_target_id: pinsTargetId,
    contract,
    assumptions,
    allowedTests,
    toolingRules,
    area,
    task_class_id: taskClassId,
    task_class_candidate: taskClassCandidate,
    task_class_params: taskClassParams,
    runner,
    timeoutMs: Number.isFinite(timeoutMs) ? timeoutMs : null,
    createdAt: now,
    updatedAt: now,
    lastJobId: null,
  }
  // From CI_ENFORCE_SINCE_MS onward, ensure every new task has allowedTests (auto-default when missing).
  if (
    Number.isFinite(ciEnforceSinceMs) &&
    ciEnforceSinceMs > 0 &&
    now >= ciEnforceSinceMs &&
    (!Array.isArray(task.allowedTests) || task.allowedTests.length === 0)
  ) {
    if (autoDefaultAllowedTests) {
      task.allowedTests = [`python scc-top/tools/scc/ops/task_selftest.py --task-id ${task.id}`]
    } else {
      return { ok: false, error: "missing_allowedTests" }
    }
  }
  putBoardTask(task)
  leader({ level: "info", type: "board_task_created", id, kind, status, title: title.slice(0, 120) })
  return { ok: true, task }
}

function summarizeFlowBottlenecks(limit) {
  const events = readJsonlTail(execLeaderLog, limit).filter((e) => e && e.type === "flow_bottleneck")
  const reasonsCount = {}
  const lastSeen = {}
  for (const e of events) {
    const reasons = Array.isArray(e.reasons) && e.reasons.length ? e.reasons : ["unknown"]
    for (const r of reasons) {
      const key = String(r)
      reasonsCount[key] = (reasonsCount[key] ?? 0) + 1
      lastSeen[key] = e.t ?? lastSeen[key] ?? null
    }
  }
  const reasons = Object.entries(reasonsCount)
    .map(([reason, count]) => ({ reason, count, lastSeen: lastSeen[reason] ?? null }))
    .sort((a, b) => b.count - a.count)
  const samples = events.slice(-6).map((e) => ({
    t: e.t ?? null,
    reasons: e.reasons ?? null,
    parentNeedsSplit: e.parentNeedsSplit ?? null,
    atomicReady: e.atomicReady ?? null,
    queued: e.queued ?? null,
    running: e.running ?? null,
    max: e.max ?? null,
  }))
  return { total: events.length, reasons, samples }
}

function formatFlowBottleneckSummary(summary) {
  const lines = []
  lines.push("Historical flow_bottleneck summary:")
  lines.push(`- total: ${summary.total}`)
  const topReasons = summary.reasons.slice(0, 6)
  lines.push(
    `- top_reasons: ${
      topReasons.length ? topReasons.map((r) => `${r.reason}(${r.count})`).join(", ") : "none"
    }`
  )
  for (const r of topReasons) {
    if (r.lastSeen) lines.push(`- last_seen ${r.reason}: ${r.lastSeen}`)
  }
  if (summary.samples.length) {
    lines.push("Recent samples:")
    for (const s of summary.samples) {
      lines.push(
        `- ${s.t ?? "n/a"} reasons=${Array.isArray(s.reasons) ? s.reasons.join("|") : "n/a"} parentNeedsSplit=${
          s.parentNeedsSplit ?? "n/a"
        } atomicReady=${s.atomicReady ?? "n/a"} queued=${s.queued ?? "n/a"}`
      )
    }
  }
  return lines.join("\n")
}

function maybeTriggerFlowManagerTask(bottleneck) {
  if (!flowManagerHookEnabled) return { ok: false, error: "disabled" }
  const state = loadFlowManagerState()
  const now = Date.now()
  const reasonsKey = JSON.stringify((bottleneck?.reasons ?? []).slice().sort())
  if (Number.isFinite(flowManagerHookMinMs) && flowManagerHookMinMs > 0) {
    if (state.last_reasons_key === reasonsKey && now - state.last_created_at < flowManagerHookMinMs) {
      return { ok: false, error: "rate_limited" }
    }
  }

  const summary = summarizeFlowBottlenecks(flowManagerHookTail)
  const summaryText = formatFlowBottleneckSummary(summary)
  const title = `Flow bottleneck response: ${(bottleneck?.reasons ?? []).join("|") || "unknown"}`
  const goal = [
    "Role: FACTORY_MANAGER.",
    "Goal: on flow_bottleneck trigger, provide dispatch/split plan and bottleneck fixes.",
    "Output: JSON {summary, bottlenecks[], actions[], nextTasks[]}.",
    "",
    "Current trigger:",
    JSON.stringify(
      {
        t: bottleneck?.t ?? null,
        reasons: bottleneck?.reasons ?? null,
        parentNeedsSplit: bottleneck?.parentNeedsSplit ?? null,
        atomicReady: bottleneck?.atomicReady ?? null,
        queued: bottleneck?.queued ?? null,
        running: bottleneck?.running ?? null,
        max: bottleneck?.max ?? null,
      },
      null,
      2
    ),
    "",
    summaryText,
  ].join("\n")

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "flow_bottleneck_response_v1",
    allowedExecutors: ["codex"],
    allowedModels: ["gpt-5.2"],
    timeoutMs: flowManagerTaskTimeoutMs,
  })

  if (!created.ok) return created
  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "flow_manager_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 1000
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCounts()
    const canRun =
      dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") {
      runJob(dispatched.job)
    } else {
      schedule()
    }
    leader({ level: "info", type: "flow_manager_dispatched", id: created.task.id, jobId: dispatched.job.id })
  }

  saveFlowManagerState({ last_created_at: now, last_reasons_key: reasonsKey })
  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

function summarizeFeedbackEvents(eventType, limit) {
  const events = readJsonlTail(execLeaderLog, limit).filter((e) => e && e.type === eventType)
  const count = events.length
  const samples = events.slice(-6).map((e) => ({
    t: e.t ?? null,
    type: e.type ?? null,
    reason: e.reason ?? null,
    area: e.area ?? null,
    task_id: e.task_id ?? e.id ?? null,
  }))
  return { count, samples }
}

function feedbackKeyForEvent(event) {
  const type = String(event?.type ?? "")
  const reason = event?.reason != null ? String(event.reason) : ""
  return reason ? `${type}:${reason}` : type
}

function loadLearnedPatternsHookState() {
  try {
    if (!fs.existsSync(learnedPatternsHookStateFile)) return { last_triggered_at: 0, last_top_reason: null, last_top_count: 0 }
    const raw = fs.readFileSync(learnedPatternsHookStateFile, "utf8")
    const parsed = JSON.parse(raw)
    return {
      last_triggered_at: Number(parsed?.last_triggered_at ?? 0),
      last_top_reason: parsed?.last_top_reason ?? null,
      last_top_count: Number(parsed?.last_top_count ?? 0),
    }
  } catch {
    return { last_triggered_at: 0, last_top_reason: null, last_top_count: 0 }
  }
}

function saveLearnedPatternsHookState(next) {
  try {
    fs.writeFileSync(learnedPatternsHookStateFile, JSON.stringify(next, null, 2), "utf8")
  } catch {
    // best effort
  }
}

function maybeTriggerFactoryManagerFromLearnedPatterns(summary) {
  if (!summary || typeof summary !== "object") return { ok: false, error: "missing_summary" }
  const state = loadLearnedPatternsHookState()
  const now = Date.now()
  if (Number.isFinite(learnedPatternsHookMinMs) && learnedPatternsHookMinMs > 0 && now - (state.last_triggered_at ?? 0) < learnedPatternsHookMinMs) {
    return { ok: false, error: "rate_limited" }
  }

  const top = Array.isArray(summary?.top_reasons) && summary.top_reasons.length ? summary.top_reasons[0] : null
  const topReason = top?.key ?? null
  const topCount = Number(top?.count ?? 0)
  const prevReason = state.last_top_reason
  const prevCount = Number(state.last_top_count ?? 0)
  const delta = topCount - prevCount
  const threshold = Number.isFinite(learnedPatternsHookDeltaThreshold) ? learnedPatternsHookDeltaThreshold : 10
  const should = Boolean(topReason && (topReason !== prevReason || (Number.isFinite(delta) && delta >= threshold)))
  if (!should) return { ok: false, error: "no_change" }

  const title = `Robustness: learned pattern spike (${topReason})`
  const goal = [
    "Role: FACTORY_MANAGER.",
    "Goal: analyze recent failure patterns and propose concrete fixes that reduce retries/token burn.",
    "Output: JSON {summary, bottlenecks[], actions[], nextTasks[]}.",
    "",
    "Learned patterns summary:",
    JSON.stringify(summary, null, 2),
    "",
    "Notes:",
    "- Prefer fixes that reduce context needs (pins/templates), enforce evidence, and avoid retries.",
    "- If a fix requires code changes, propose a minimal patch plan and the smallest set of atomic tasks.",
  ].join("\n")

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "learned_patterns_response_v1",
    allowedExecutors: ["codex"],
    allowedModels: ["gpt-5.2"],
    timeoutMs: learnedPatternsTaskTimeoutMs,
  })
  if (!created.ok) return created

  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "learned_patterns_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 920
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCounts()
    const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
    else schedule()
    leader({ level: "info", type: "learned_patterns_dispatched", id: created.task.id, jobId: dispatched.job.id, topReason, topCount, delta })
  }

  saveLearnedPatternsHookState({ last_triggered_at: now, last_top_reason: topReason, last_top_count: topCount })
  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

function loadTokenCfoHookState() {
  try {
    if (!fs.existsSync(tokenCfoHookStateFile)) return { last_triggered_at: 0, last_key: null }
    const raw = fs.readFileSync(tokenCfoHookStateFile, "utf8")
    const parsed = JSON.parse(raw)
    return { last_triggered_at: Number(parsed?.last_triggered_at ?? 0), last_key: parsed?.last_key ?? null }
  } catch {
    return { last_triggered_at: 0, last_key: null }
  }
}

function saveTokenCfoHookState(next) {
  try {
    fs.writeFileSync(tokenCfoHookStateFile, JSON.stringify(next, null, 2), "utf8")
  } catch {
    // best effort
  }
}

function maybeTriggerFactoryManagerFromTokenWaste(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return { ok: false, error: "missing_snapshot" }
  const state = loadTokenCfoHookState()
  const now = Date.now()
  if (Number.isFinite(tokenCfoHookMinMs) && tokenCfoHookMinMs > 0 && now - (state.last_triggered_at ?? 0) < tokenCfoHookMinMs) {
    return { ok: false, error: "rate_limited" }
  }
  const top = Array.isArray(snapshot?.top_wasted_contextpacks) && snapshot.top_wasted_contextpacks.length ? snapshot.top_wasted_contextpacks[0] : null
  if (!top) return { ok: false, error: "no_waste" }
  const unusedRatio = Number(top.unused_ratio ?? 0)
  const included = Number(top.included ?? 0)
  if (unusedRatio < tokenCfoUnusedRatio || included < tokenCfoIncludedMin) return { ok: false, error: "below_threshold" }

  const key = `${top.task_class ?? "none"}:${top.executor ?? "unknown"}:${included}:${Math.round(unusedRatio * 100)}`
  if (state.last_key === key) return { ok: false, error: "duplicate" }

  const title = `Token CFO: context waste detected (${Math.round(unusedRatio * 100)}% unused)`
  const goal = [
    "Role: FACTORY_MANAGER.",
    "Goal: reduce wasted context and token burn without lowering 1-pass success rate.",
    "Output: JSON {summary, waste_cases[], actions[], nextTasks[]}.",
    "",
    "Token CFO snapshot:",
    JSON.stringify(snapshot, null, 2),
  ].join("\n")

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "token_cfo_response_v1",
    allowedExecutors: ["codex"],
    allowedModels: ["gpt-5.2"],
    timeoutMs: tokenCfoTaskTimeoutMs,
  })
  if (!created.ok) return created
  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (dispatched.job) {
    dispatched.job.priority = 910
    jobs.set(dispatched.job.id, dispatched.job)
  }
  saveTokenCfoHookState({ last_triggered_at: now, last_key: key })
  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

function shouldTriggerFeedback(event) {
  const type = String(event?.type ?? "")
  if (!type) return false
  // Treat CI gate failures/skips as robustness events.
  if (type === "ci_gate_result") {
    const ok = event?.ok
    if (ok === false) return true
    return false
  }
  if (type === "ci_gate_skipped") {
    const required = event?.required
    if (required === true) return true
    return false
  }
  if (type === "pins_apply_failed") return true
  if (
    [
      "underutilized",
      "job_lease_expired",
      "board_task_recovered",
      "parent_recovered",
      "autorescue_triggered",
      "autorescue_error",
      "dispatch_quality_gate",
      "failure_report_written",
    ].includes(type)
  )
    return true
  if (type === "dispatch_rejected") {
    const reason = String(event?.reason ?? "")
    return ["missing_pins", "missing_pins_template", "missing_contract"].includes(reason)
  }
  if (type === "job_finished") {
    const reason = String(event?.reason ?? "")
    return ["pins_insufficient", "missing_pins", "ci_failed", "ci_skipped"].includes(reason)
  }
  return false
}

function maybeTriggerFactoryManagerFromEvent(event) {
  if (!feedbackHookEnabled) return { ok: false, error: "disabled" }
  if (!shouldTriggerFeedback(event)) return { ok: false, error: "ignored" }
  const state = loadFeedbackHookState()
  const key = feedbackKeyForEvent(event)
  const now = Date.now()
  const lastAt = Number(state.last_created_at?.[key] ?? 0)
  if (Number.isFinite(feedbackHookMinMs) && feedbackHookMinMs > 0 && now - lastAt < feedbackHookMinMs) {
    return { ok: false, error: "rate_limited" }
  }

  const summary = summarizeFeedbackEvents(event.type, feedbackHookTail)
  const title = `Feedback response: ${event.type}${event.reason ? `:${event.reason}` : ""}`
  const goal = [
    "Role: FACTORY_MANAGER.",
    "Goal: respond to robustness feedback events; locate bottlenecks and propose fixes/mitigations.",
    "Output: JSON {summary, bottlenecks[], actions[], nextTasks[]}.",
    "",
    "Trigger event:",
    JSON.stringify(event, null, 2),
    "",
    "Similar events summary:",
    `count=${summary.count}`,
    "samples=",
    JSON.stringify(summary.samples, null, 2),
  ].join("\n")

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "feedback_response_v1",
    allowedExecutors: ["codex"],
    allowedModels: ["gpt-5.2"],
    timeoutMs: flowManagerTaskTimeoutMs,
  })

  if (!created.ok) return created
  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "feedback_manager_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 900
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCounts()
    const canRun =
      dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") {
      runJob(dispatched.job)
    } else {
      schedule()
    }
    leader({ level: "info", type: "feedback_manager_dispatched", id: created.task.id, jobId: dispatched.job.id })
  }

  const next = { ...state.last_created_at, [key]: now }
  saveFeedbackHookState({ last_created_at: next })
  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

async function maybeRunRadiusAuditFromJob(done, boardTask, ciGate) {
  try {
    if (!radiusAuditHookEnabled) return { ok: false, error: "disabled" }
    if (!boardTask || boardTask.kind !== "atomic") return { ok: false, error: "not_atomic" }
    const role = String(boardTask.role ?? "")
    if (!role || !radiusAuditHookRoles.includes(role)) return { ok: false, error: "role_ignored" }
    if (done?.status !== "done") return { ok: false, error: "not_done" }

    const state = loadRadiusAuditHookState()
    const now = Date.now()
    const minMs = Number.isFinite(radiusAuditHookMinMs) ? radiusAuditHookMinMs : 600000
    if (minMs > 0 && now - (state.last_triggered_at ?? 0) < minMs) return { ok: false, error: "rate_limited" }

    const nextCount = Number(state.done_since_last ?? 0) + 1
    const force = ciGate && ciGate.ran && ciGate.ok === false
    if (!force && Number.isFinite(radiusAuditHookEveryN) && radiusAuditHookEveryN > 1 && nextCount < radiusAuditHookEveryN) {
      saveRadiusAuditHookState({ ...state, done_since_last: nextCount })
      return { ok: false, error: "below_threshold", done_since_last: nextCount }
    }

    const run = await runRadiusAuditReport(boardTask.id)
    leader({
      level: run.ok ? "info" : "warn",
      type: "radius_audit_run",
      task_id: boardTask.id,
      job_id: done.id,
      ok: run.ok,
      code: run.code,
      outDir: run.outDir,
      stderr: run.ok ? null : String(run.stderr || ""),
    })

    try {
      const srcJson = path.join(run.outDir, "report.json")
      const srcMd = path.join(run.outDir, "report.md")
      const latestDir = path.join(execLogDir, "radius_audit")
      ensureDir(latestDir)
      if (fs.existsSync(srcJson)) fs.copyFileSync(srcJson, path.join(latestDir, "latest.json"))
      if (fs.existsSync(srcMd)) fs.copyFileSync(srcMd, path.join(latestDir, "latest.md"))

      const rep = fs.existsSync(srcJson) ? JSON.parse(fs.readFileSync(srcJson, "utf8")) : null
      const violations = rep?.audit?.violations
      const hasS0 = Array.isArray(violations) && violations.some((v) => String(v?.severity ?? "") === "S0")
      if (hasS0) {
        const title = `Radius Audit: fail-closed violations detected (${role})`
        const goal = [
          "Role: FACTORY_MANAGER.",
          "Goal: fix radius expansion guardrails so violations become fail-closed, and add replay/regression proof.",
          "Output: JSON {violations, fixes[], tests[], rollback}.",
          "",
          "Radius audit report:",
          JSON.stringify(rep?.audit ?? {}, null, 2),
        ].join("\n")
        const created = createBoardTask({
          kind: "atomic",
          status: "ready",
          title,
          goal,
          role: "factory_manager",
          runner: "internal",
          area: "control_plane",
          task_class_id: "radius_audit_response_v1",
          allowedExecutors: ["codex"],
          allowedModels: ["gpt-5.2"],
          timeoutMs: 900000,
          files: ["artifacts/executor_logs/radius_audit/latest.json", "scc-top/tools/scc/ops/task_selftest.py"],
        })
        if (created.ok) {
          const dispatched = dispatchBoardTaskToExecutor(created.task.id)
          if (dispatched.job) {
            dispatched.job.priority = 945
            jobs.set(dispatched.job.id, dispatched.job)
            const running = runningCounts()
            const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
            if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
            else schedule()
          }
          leader({ level: "warn", type: "radius_audit_violation_task_created", taskId: created.task.id, auditedTaskId: boardTask.id })
        }
      }
    } catch (e) {
      leader({ level: "warn", type: "radius_audit_postprocess_error", error: String(e) })
    }

    saveRadiusAuditHookState({ last_triggered_at: now, done_since_last: 0 })
    return { ok: true }
  } catch (e) {
    leader({ level: "warn", type: "radius_audit_hook_error", error: String(e) })
    return { ok: false, error: "exception" }
  }
}

function shouldCountForAuditTask(t) {
  if (!t || t.kind !== "atomic") return false
  if (t.status !== "done") return false
  const role = String(t.role ?? "").trim().toLowerCase()
  if (role === "auditor" || role === "status_review") return false
  const cls = String(t.task_class_id ?? "")
  if (cls === "status_review_audit_v1") return false
  return true
}

function collectRecentDoneTasks(limit, lookback) {
  const lim = Math.max(1, Number(limit) || 1)
  const lb = Math.max(50, Number(lookback) || lim * 6)
  const events = readJsonlTail(stateEventsFile, lb)
  const filtered = events.filter((e) => {
    if (!e || String(e.status ?? "") !== "done") return false
    if (String(e.kind ?? "") !== "atomic") return false
    const role = String(e.role ?? "").trim().toLowerCase()
    if (role === "auditor" || role === "status_review") return false
    return true
  })
  return filtered.slice(-lim).map((e) => ({
    task_id: e.task_id ?? null,
    parent_id: e.parent_id ?? null,
    role: e.role ?? null,
    area: e.area ?? null,
    task_class: e.task_class ?? null,
    durationMs: e.durationMs ?? null,
    files: Array.isArray(e.files) ? e.files.slice(0, 8) : [],
    reason: e.reason ?? null,
  }))
}

function buildStatusReviewAuditGoal({ batchId, tasks }) {
  const reportPath = `docs/REPORT/control_plane/REPORT__STATUS_REVIEW_AUDIT__${batchId}.md`
  const lines = []
  lines.push("You are a STATUS_REVIEW auditor. Audit completion/evidence/functionality for the batch below.")
  lines.push("")
  lines.push(`Required output: ${reportPath}`)
  lines.push("Report MUST include the tag: STATUS_REVIEW")
  lines.push("Report MUST include sections: Summary, Findings, Evidence, Gaps, Next Actions, JSON Summary.")
  lines.push("Do NOT modify code. Use board + executor logs + referenced artifacts only.")
  lines.push("")
  lines.push("Checks per task:")
  lines.push("- board status is done, lastJobStatus is done, no error reason")
  lines.push("- evidence exists under docs/REPORT/ or artifacts/ if referenced in task")
  lines.push("- functionality status: mark ok / unknown / needs_followup based on evidence")
  lines.push("")
  lines.push("Batch tasks (latest done):")
  for (const t of tasks) {
    lines.push(`- ${t.task_id} | role=${t.role ?? "?"} | area=${t.area ?? "?"} | class=${t.task_class ?? "?"} | reason=${t.reason ?? "ok"}`)
  }
  lines.push("")
  lines.push("JSON Summary block format (include in report):")
  lines.push("{")
  lines.push('  "batch_id": "' + batchId + '",')
  lines.push('  "tasks_total": ' + tasks.length + ",")
  lines.push('  "ok": [],')
  lines.push('  "unknown": [],')
  lines.push('  "needs_followup": []')
  lines.push("}")
  return lines.join("\n")
}

function createStatusReviewAuditTask({ batchId, tasks }) {
  const title = `Status Review Audit: Batch ${batchId} (${tasks.length})`
  const goal = buildStatusReviewAuditGoal({ batchId, tasks })
  return createBoardTask({
    title,
    goal,
    kind: "atomic",
    status: "ready",
    role: "status_review",
    area: "control_plane",
    allowedExecutors: ["codex"],
    allowedModels: ["gpt-5.1-codex-max", "gpt-5.2"],
    task_class_id: "status_review_audit_v1",
    task_class_params: {
      batch_id: batchId,
      tasks: tasks.map((t) => t.task_id).filter(Boolean).slice(0, 60),
      report_path: `docs/REPORT/control_plane/REPORT__STATUS_REVIEW_AUDIT__${batchId}.md`,
    },
  })
}

function maybeTriggerAuditOnDone(t) {
  if (!auditTriggerEnabled) return
  const n = Number.isFinite(auditTriggerEveryN) && auditTriggerEveryN > 0 ? Math.floor(auditTriggerEveryN) : 0
  if (!n) return
  if (!shouldCountForAuditTask(t)) return
  auditTriggerState.done_since_last = Number(auditTriggerState.done_since_last ?? 0) + 1
  auditTriggerState.total_done = Number(auditTriggerState.total_done ?? 0) + 1
  if (auditTriggerState.done_since_last < n || auditTriggerBusy) {
    saveAuditTriggerState(auditTriggerState)
    return
  }
  auditTriggerBusy = true
  const batchId = new Date().toISOString().replace(/[-:.]/g, "").replace("Z", "Z")
  const tasks = collectRecentDoneTasks(n, auditTriggerLookback)
  const created = createStatusReviewAuditTask({ batchId, tasks })
  if (created?.ok) {
    auditTriggerState.done_since_last = 0
    auditTriggerState.last_audit_at = new Date().toISOString()
    auditTriggerState.last_audit_batch = batchId
    auditTriggerState.last_audit_task_id = created.task?.id ?? null
    leader({ level: "info", type: "audit_triggered", batch_id: batchId, tasks: tasks.length, taskId: created.task?.id ?? null })
  }
  saveAuditTriggerState(auditTriggerState)
  auditTriggerBusy = false
}

function updateBoardTaskStatus(id, status) {
  const t = getBoardTask(id)
  if (!t) return null
  t.status = status
  t.updatedAt = Date.now()
  putBoardTask(t)
  leader({ level: "info", type: "board_task_status", id, status })
  return t
}

function updateBoardFromJob(job) {
  let t = null
  const taskId = job?.boardTaskId ? String(job.boardTaskId) : null
  if (taskId) t = getBoardTask(taskId)
  if (!t) {
    // Back-compat for jobs created before boardTaskId existed
    t = listBoardTasks().find((x) => x.lastJobId === job.id) ?? null
  }
  if (!t) return
  if (t.lastJobId !== job.id) return
  if (t.status !== "in_progress") return
  if (job.status === "done") {
    t.status = "done"
    // Reset model ladder on success so future retries start from strongest again.
    t.modelAttempt = 0
  }
  else if (job.status === "failed") {
    const autoRequeueTimeoutEnabled = String(process.env.AUTO_REQUEUE_TIMEOUT ?? "true").toLowerCase() !== "false"
    const autoRequeueTimeoutMax = Number(process.env.AUTO_REQUEUE_TIMEOUT_MAX ?? "3")
    const autoRequeueCooldownMs = Number(process.env.AUTO_REQUEUE_TIMEOUT_COOLDOWN_MS ?? "60000")
    const autoRequeueModelMax = Number.isFinite(autoRequeueModelFailMax) && autoRequeueModelFailMax > 0 ? Math.floor(autoRequeueModelFailMax) : 0

    if (
      autoRequeueTimeoutEnabled &&
      t.kind === "atomic" &&
      String(job.reason ?? "") === "timeout" &&
      Number.isFinite(autoRequeueTimeoutMax) &&
      autoRequeueTimeoutMax > 0 &&
      (t.timeoutRetries ?? 0) < autoRequeueTimeoutMax
    ) {
      t.timeoutRetries = (t.timeoutRetries ?? 0) + 1
      t.cooldownUntil = Date.now() + (Number.isFinite(autoRequeueCooldownMs) ? Math.max(5000, autoRequeueCooldownMs) : 60000)
      t.status = "ready"
      t.updatedAt = Date.now()
      t.lastJobStatus = job.status
      t.lastJobReason = job.reason ?? null
      t.lastJobFinishedAt = job.finishedAt ?? Date.now()
      putBoardTask(t)
      leader({
        level: "warn",
        type: "board_task_requeued",
        id: t.id,
        jobId: job.id,
        reason: "timeout",
        timeoutRetries: t.timeoutRetries,
        cooldownUntil: t.cooldownUntil,
      })
      return
    }

    const modelReason = String(job.reason ?? "")
    const isModelThrottle = modelReason === "rate_limited" || modelReason === "unauthorized" || modelReason === "forbidden"
    if (autoRequeueModelFailures && autoRequeueModelMax > 0 && t.kind === "atomic" && isModelThrottle) {
      const attempt = Number.isFinite(Number(t.modelAttempt)) ? Number(t.modelAttempt) : 0
      const executor = String(job.executor ?? "")
      const allowed = Array.isArray(t.allowedModels) ? t.allowedModels.map((x) => String(x)) : []
      const pool =
        executor === "opencodecli" ? allowed.filter((m) => m.startsWith("opencode/")) : allowed.filter((m) => !m.startsWith("opencode/"))
      const fallbackPool = executor === "opencodecli" ? modelsFree : modelsPaid
      const effectivePool = pool.length ? pool : fallbackPool
      const canAdvance = effectivePool.length > 1 && attempt < effectivePool.length - 1 && attempt < autoRequeueModelMax
      if (canAdvance) {
        t.modelAttempt = attempt + 1
        t.cooldownUntil =
          Date.now() + (Number.isFinite(autoRequeueModelFailCooldownMs) ? Math.max(5000, autoRequeueModelFailCooldownMs) : 60000)
        t.status = "ready"
        t.updatedAt = Date.now()
        t.lastJobStatus = job.status
        t.lastJobReason = job.reason ?? null
        t.lastJobFinishedAt = job.finishedAt ?? Date.now()
        putBoardTask(t)
        leader({
          level: "warn",
          type: "board_task_requeued",
          id: t.id,
          jobId: job.id,
          reason: modelReason,
          modelAttempt: t.modelAttempt,
          cooldownUntil: t.cooldownUntil,
        })
        return
      }
    }

    t.status = "failed"
  }
  else return
  t.updatedAt = Date.now()
  t.lastJobStatus = job.status
  t.lastJobReason = job.reason ?? null
  t.lastJobFinishedAt = job.finishedAt ?? Date.now()
  putBoardTask(t)
  leader({ level: job.status === "failed" ? "error" : "info", type: "board_task_completed", id: t.id, jobId: job.id, status: t.status, reason: t.lastJobReason })
  // Pins statistics: log pins-related failures to pins_guide_errors.jsonl for later analytics.
  if (t.status === "failed") {
    const reason = String(t.lastJobReason ?? "")
    if (["pins_insufficient", "missing_pins", "missing_pins_template"].includes(reason)) {
      appendJsonlChained(pinsGuideErrorsFile, {
        t: new Date().toISOString(),
        task_id: t.id,
        role: t.role ?? null,
        reason,
        allowed_paths: t.pins?.allowed_paths ?? null,
        forbidden_paths: t.pins?.forbidden_paths ?? null,
        files: Array.isArray(t.files) ? t.files.slice(0, 20) : null,
        job_id: job.id,
        executor: job.executor ?? null,
        model: job.model ?? null,
      })
    }
  }
  appendJsonl(stateEventsFile, {
    t: new Date().toISOString(),
    task_id: t.id,
    parent_id: t.parentId ?? null,
    kind: t.kind ?? null,
    status: t.status,
    role: t.role ?? null,
    area: t.area ?? null,
    task_class: t.task_class_id ?? t.task_class_candidate ?? null,
    task_class_params: t.task_class_params ?? null,
    executor: job.executor ?? null,
    model: job.model ?? null,
    durationMs: job.startedAt && job.finishedAt ? job.finishedAt - job.startedAt : null,
    files: Array.isArray(t.files) ? t.files.slice(0, 12) : [],
    allowed_tests: Array.isArray(t.allowedTests) ? t.allowedTests.slice(0, 12) : null,
    pins_summary: summarizePins(t.pins),
    context_bytes: job.contextBytes ?? null,
    context_files: job.contextFiles ?? null,
    context_source: job.contextSource ?? null,
    patch_added: job.patch_stats?.added ?? null,
    patch_removed: job.patch_stats?.removed ?? null,
    patch_files: job.patch_stats?.filesCount ?? null,
    touched_files: Array.isArray(job.submit?.touched_files)
      ? job.submit.touched_files.slice(0, 30)
      : Array.isArray(job.patch_stats?.files)
        ? job.patch_stats.files.slice(0, 30)
        : null,
    tests_run: Array.isArray(job.submit?.tests_run) ? job.submit.tests_run.slice(0, 20) : null,
    ci_gate_ok: job.ci_gate?.ok ?? null,
    ci_gate_required: job.ci_gate?.required ?? null,
    ci_gate_skipped: job.ci_gate?.skipped ?? null,
    reason: t.lastJobReason ?? null,
  })
  if (t.status === "failed") {
    // Auto-create a pins fixup task for pins-related failures (trigger -> handle, high priority).
    maybeCreatePinsFixupTask({ boardTask: t, job })
  }
  if (t.status === "done") {
    maybeTriggerAuditOnDone(t)
  }
  if (t.status === "done" && t.task_class_id === "ci_fixup_v1") {
    const sourceId = t.pointers?.sourceTaskId ?? null
    if (sourceId) {
      const src = getBoardTask(String(sourceId))
      if (src && src.status === "failed" && String(src.lastJobReason ?? "").startsWith("ci_")) {
        const prev = Number(src.ci_requeue_count ?? 0)
        if (prev < 1) {
          src.ci_requeue_count = prev + 1
          src.status = "ready"
          src.updatedAt = Date.now()
          putBoardTask(src)
          const out = dispatchBoardTaskToExecutor(src.id)
          leader({
            level: out.ok ? "info" : "warn",
            type: "ci_fixup_requeued",
            sourceId: src.id,
            fixupId: t.id,
            jobId: job.id,
            dispatched: out.ok,
            error: out.ok ? null : out.error,
          })
        }
      }
    }
  }
  if (t.status === "done" && t.task_class_id === "pins_fixup_v1") {
    const sourceId = t.pointers?.sourceTaskId ?? null
    if (sourceId) {
      const src = getBoardTask(String(sourceId))
      const result = extractPinsResult(job.stdout)
      if (src && result?.pins) {
        src.pins = result.pins
        src.pins_pending = false
        src.updatedAt = Date.now()
        const srcReason = String(src.lastJobReason ?? "")
        const prev = Number(src.pins_requeue_count ?? 0)
        if (src.status === "failed" && ["pins_insufficient", "missing_pins", "missing_pins_template"].includes(srcReason) && prev < 2) {
          src.pins_requeue_count = prev + 1
          src.status = "ready"
        }
        putBoardTask(src)
        if (src.status === "ready") {
          const out = dispatchBoardTaskToExecutor(src.id)
          leader({
            level: out.ok ? "info" : "warn",
            type: "pins_fixup_requeued",
            sourceId: src.id,
            fixupId: t.id,
            jobId: job.id,
            dispatched: out.ok,
            error: out.ok ? null : out.error,
          })
        }
      } else if (src && result?.error) {
        appendJsonl(pinsGuideErrorsFile, {
          t: new Date().toISOString(),
          task_id: src.id,
          error: result.error,
          hint: "Pins fixup returned error; ensure task.files contains all touched files and key symbols.",
        })
      }
    }
  }
}

function dispatchBoardTaskToExecutor(id) {
  const t = getBoardTask(id)
  if (!t) return { ok: false, error: "not_found" }
  if (t.kind !== "atomic") return { ok: false, error: "not_atomic" }
  if (t.status !== "ready" && t.status !== "backlog") return { ok: false, error: "bad_status" }
  if (t.pins_pending) return { ok: false, error: "pins_pending" }

  // Preflight: must have allowedTests (non-task_selftest) and pins/allowlist.
  const hasTests =
    Array.isArray(t.allowedTests) && t.allowedTests.some((x) => !String(x ?? "").toLowerCase().includes("task_selftest"))
  if (!hasTests) {
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: "missing_real_test",
      role: t.role ?? null,
      area: t.area ?? null,
    })
    return { ok: false, error: "missing_real_test" }
  }

  if (dispatchIdempotency) {
    const active = Array.from(jobs.values()).find(
      (j) => String(j?.boardTaskId ?? "") === String(t.id) && (j.status === "queued" || j.status === "running")
    )
    if (active) {
      leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: "already_dispatched", jobId: active.id })
      return { ok: false, error: "already_dispatched", jobId: active.id }
    }
    const last = t.lastJobId ? jobs.get(String(t.lastJobId)) : null
    if (last && (last.status === "queued" || last.status === "running")) {
      leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: "already_dispatched", jobId: last.id })
      return { ok: false, error: "already_dispatched", jobId: last.id }
    }
  }

  // Dispatch-time preflight: infer missing files/pins to avoid guaranteed fail-fast runs.
  if (autoFilesFromText && (!Array.isArray(t.files) || t.files.length === 0)) {
    const inferred = extractRepoPathsFromText(`${t.title ?? ""}\n${t.goal ?? ""}`)
    if (inferred.length) {
      t.files = inferred
      if (autoPinsFromFiles && (!t.pins || typeof t.pins !== "object")) t.pins = defaultPinsForFiles(inferred)
      t.updatedAt = Date.now()
      putBoardTask(t)
      leader({ level: "info", type: "preflight_files_inferred", id: t.id, files: inferred.slice(0, 8) })
    }
  }

  const executor = pickExecutorForTask(t) ?? "codex"
  const model = executor === "opencodecli" ? pickOccliModelForTask(t) : pickCodexModelForTask(t)
  const qualityGateRate = Number(process.env.QUALITY_GATE_FAIL_RATE ?? "")
  if (Number.isFinite(qualityGateRate) && qualityGateRate > 0 && t.area) {
    const windowSize = Number(process.env.QUALITY_GATE_WINDOW ?? "80")
    const minSamples = Number(process.env.QUALITY_GATE_MIN_SAMPLES ?? "8")
    const rate = computeAreaFailRate(t.area, windowSize, minSamples)
    if (Number.isFinite(rate) && rate >= qualityGateRate) {
      leader({ level: "warn", type: "dispatch_quality_gate", id: t.id, area: t.area, rate, threshold: qualityGateRate })
      appendJsonl(routerFailuresFile, {
        t: new Date().toISOString(),
        task_id: t.id,
        reason: "quality_gate_blocked",
        role: t.role ?? null,
        area: t.area ?? null,
        rate,
      })
      return { ok: false, error: "quality_gate_blocked", rate, area: t.area }
    }
  }
  const internalAfterAttempts = Number(process.env.AUTO_INTERNAL_AFTER_ATTEMPTS ?? "5")
  const prev = t.lastJobId ? jobs.get(t.lastJobId) : null
  const forceInternal = Number.isFinite(internalAfterAttempts) && internalAfterAttempts > 0 && prev && (prev.attempts ?? 0) >= internalAfterAttempts

  const payload = {
    goal: t.goal,
    files: Array.isArray(t.files) ? t.files : [],
    executor,
    model,
    timeoutMs: t.timeoutMs ?? undefined,
    taskType: "board",
    runner: forceInternal ? "internal" : t.runner ?? "external",
  }

  // reuse atomic job creation path
  const effectivePins = resolvePinsForTask(t)
  if (requirePinsTemplate && (t.task_class_id || t.task_class_candidate) && !effectivePins) {
    leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: "missing_pins_template" })
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: "missing_pins_template",
      role: t.role ?? null,
      area: t.area ?? null,
    })
    return { ok: false, error: "missing_pins_template" }
  }
  if (requirePins && !effectivePins) {
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: "missing_pins",
      role: t.role ?? null,
      area: t.area ?? null,
    })
    return { ok: false, error: "missing_pins" }
  }
  const ctx = effectivePins
    ? createContextPackFromPins({ pins: effectivePins, maxBytes: 220_000 })
    : payload.files.length
      ? createContextPackFromFiles({ files: payload.files, maxBytes: 220_000 })
      : { ok: true, id: null, bytes: 0 }
  if (!ctx.ok) return { ok: false, error: ctx.error }
  const contextSource = effectivePins ? "pins" : payload.files.length ? "files" : "none"
  const timeoutMs = Number.isFinite(payload.timeoutMs) ? payload.timeoutMs : executor === "opencodecli" ? timeoutOccliMs : timeoutCodexMs

  const contract = buildContractForTask(t, payload.goal)
  if (requireContract && !contract?.goal) return { ok: false, error: "missing_contract" }
  const allowedTests = Array.isArray(t.allowedTests) && t.allowedTests.length ? t.allowedTests : pickAllowedTestsForTask(t)
  const ciHandbookText = getCiHandbookText()
  const lastCi = getLastCiFailure(t.id) || getLastCiGateSummary(t.id)
  const ciSummary = lastCi
    ? `PREV_CI: exit=${lastCi.exitCode ?? "?"} skipped=${lastCi.skipped ?? false} timedOut=${lastCi.timedOut ?? false}\n` +
      `${lastCi.stderrPreview ? `STDERR_PREVIEW: ${String(lastCi.stderrPreview).slice(0, 400)}` : ""}`
    : null

  const execPrompt = {
    schema_version: "scc.exec_prompt.v1",
    role: "executor",
    output_mode: "ARTIFACTS_PLUS_SUBMIT_JSON",
    task: {
      task_id: t.id,
      parent_task_id: t.parentId ?? null,
      task_class: t.task_class_id ?? t.task_class_candidate ?? null,
      title: t.title ?? "",
      goal: t.goal ?? contract.goal ?? "",
      priority: t.priority ?? null,
      lane: t.lane ?? "mainlane",
    },
    inputs: {
      ssot_pointers: [],
      pins: {
        pins_json_path: "artifacts/pins/pins.json",
        pins_md_path: "artifacts/pins/pins.md",
        allowlist: {
          read_paths: Array.isArray(effectivePins?.allowed_paths) ? effectivePins.allowed_paths.slice(0, 64) : [],
          write_paths: Array.isArray(effectivePins?.allowed_paths) ? effectivePins.allowed_paths.slice(0, 64) : [],
        },
      },
      constraints: {
        must: ["patch-only", "minimal-diff", "keep-workspace-clean", "evidence-triplet"],
        forbid: ["reading outside pins allowlist", "introducing new deps without approval", "leaving stray scripts/files"],
        unknown_policy: "NEED_INPUT",
      },
      allowed_tests: {
        commands: Array.isArray(allowedTests) ? allowedTests : [],
        smoke: [],
        regression: [],
      },
      acceptance: [
        "All allowed_tests pass",
        "No changes outside write_paths",
        "Report includes rationale + change list",
        "selftest.log ends with EXIT_CODE=0",
      ],
      context: {
        facts: Array.isArray(t.assumptions) ? t.assumptions : [],
        error_snippets: ciSummary ? [ciSummary] : [],
        links: [],
      },
    },
    execution_plan: {
      max_attempts: 2,
      stop_conditions: ["pins_insufficient", "scope_conflict", "test_command_missing", "ci_failed"],
      fallback: [
        { when: "pins_insufficient", action: "emit_event", event_type: "PINS_INSUFFICIENT", notes: "List missing files/symbols/tests needed" },
        { when: "ci_failed_unexplained", action: "emit_event", event_type: "CI_FAILED", notes: "Attach failing tests + logs + suspected cause" },
        { when: "tooling_error", action: "emit_event", event_type: "EXECUTOR_ERROR", notes: "Include stacktrace_hash + reproduction" },
      ],
    },
    required_artifacts: {
      workspace_root: execRoot,
      paths: {
        report_md: "artifacts/report.md",
        selftest_log: "artifacts/selftest.log",
        evidence_dir: "artifacts/evidence/",
        patch_diff: "artifacts/patch.diff",
        submit_json: "artifacts/submit.json",
      },
    },
    submit_contract: {
      schema_version: "scc.submit.v1",
      task_id: t.id,
      status: "DONE|NEED_INPUT|FAILED",
      changed_files: [],
      tests: {
        commands: Array.isArray(allowedTests) ? allowedTests : [],
        passed: true,
        summary: "All tests passed",
      },
      artifacts: {
        report_md: "artifacts/report.md",
        selftest_log: "artifacts/selftest.log",
        evidence_dir: "artifacts/evidence/",
        patch_diff: "artifacts/patch.diff",
      },
      exit_code: 0,
      needs_input: [],
    },
    handbook: ciHandbookText || "CI_HANDBOOK missing; see docs/AI_CONTEXT.md",
  }

  const prompt = JSON.stringify(execPrompt, null, 2)

  appendJsonl(routeDecisionsFile, {
    t: new Date().toISOString(),
    task_id: t.id,
    role: t.role ?? null,
    area: t.area ?? null,
    allowedExecutors: t.allowedExecutors ?? null,
    allowedModels: t.allowedModels ?? null,
    pickedExecutor: payload.executor,
    pickedModel: payload.model,
    reason: "dispatch",
  })

  const job = makeJob({ prompt, model: payload.model, executor: payload.executor, taskType: payload.taskType, timeoutMs })
  job.runner = payload.runner === "internal" ? "internal" : "external"
  job.contextPackId = ctx.id
  job.contextBytes = Number.isFinite(ctx.bytes) ? ctx.bytes : null
  job.contextFiles = Number.isFinite(ctx.fileCount) ? ctx.fileCount : null
  job.contextFilesList = Array.isArray(ctx.files) ? ctx.files : null
  job.contextSource = contextSource
  job.allowedTests = allowedTests
  job.boardTaskId = t.id
  jobs.set(job.id, job)
  schedule()

  t.lastJobId = job.id
  t.status = "in_progress"
  t.updatedAt = Date.now()
  putBoardTask(t)

  leader({ level: "info", type: "board_task_dispatched", id: t.id, jobId: job.id, executor: job.executor, runner: job.runner })
  return { ok: true, task: t, job }
}

function requireDesigner52(task) {
  const role = task?.role ?? null
  if (role !== "designer") return { ok: false, error: "role_must_be_designer" }
  const allowed = Array.isArray(task?.allowedModels) ? task.allowedModels : []
  if (!allowed.includes(STRICT_DESIGNER_MODEL)) return { ok: false, error: "missing_required_model" }
  const chosen = task.allowedModels?.[0]
  if (chosen !== STRICT_DESIGNER_MODEL) return { ok: false, error: "must_use_required_model" }
  const exec = task.allowedExecutors?.[0] ?? "codex"
  if (exec !== "codex") return { ok: false, error: "designer_must_use_codex" }
  return { ok: true }
}

function extractFirstJsonArray(text) {
  const s = String(text ?? "")
  const start = s.indexOf("[")
  if (start < 0) return null
  let depth = 0
  for (let i = start; i < s.length; i += 1) {
    const c = s[i]
    if (c === "[") depth += 1
    if (c === "]") depth -= 1
    if (depth === 0) {
      const slice = s.slice(start, i + 1)
      try {
        const parsed = JSON.parse(slice)
        return Array.isArray(parsed) ? parsed : null
      } catch {
        return null
      }
    }
  }
  return null
}

function extractFirstJsonObject(text) {
  const s = String(text ?? "")
  const start = s.indexOf("{")
  if (start < 0) return null
  let depth = 0
  for (let i = start; i < s.length; i += 1) {
    const c = s[i]
    if (c === "{") depth += 1
    if (c === "}") depth -= 1
    if (depth === 0) {
      const slice = s.slice(start, i + 1)
      try {
        const parsed = JSON.parse(slice)
        return parsed && typeof parsed === "object" ? parsed : null
      } catch {
        return null
      }
    }
  }
  return null
}

function extractPinsResult(stdout) {
  const msg = extractAgentMessageText(stdout)
  const source = msg || stdout
  const obj = extractFirstJsonObject(source)
  if (!obj || typeof obj !== "object") return null
  if (obj.error) return { error: String(obj.error) }
  const pins = obj.pins && typeof obj.pins === "object" ? obj.pins : obj
  if (!pins || typeof pins !== "object") return null
  if (!Array.isArray(pins.allowed_paths) && !Array.isArray(pins.forbidden_paths) && !pins.line_windows) return null
  return { pins }
}

function readPinsGuideErrors(limit) {
  const rows = readJsonlTail(pinsGuideErrorsFile, limit)
  return rows.map((r) => ({
    t: r.t,
    task_id: r.task_id,
    error: r.error,
    hint: r.hint,
  }))
}

function roleErrorsFile(role) {
  const r = String(role ?? "unknown").trim().toLowerCase() || "unknown"
  return path.join(roleErrorsDir, `${r}.jsonl`)
}

function appendRoleError(role, entry) {
  appendJsonl(roleErrorsFile(role), entry)
}

function readRoleErrors(role, limit) {
  return readJsonlTail(roleErrorsFile(role), limit)
}

function extractAgentMessageText(stdout) {
  const text = String(stdout ?? "")
  const lines = text.split("\n").map((l) => l.trimEnd())
  for (const l of lines) {
    if (!l) continue
    let obj
    try {
      obj = JSON.parse(l)
    } catch {
      continue
    }
    const item = obj?.item
    if (!item || item.type !== "agent_message") continue
    const body = item?.text
    if (typeof body === "string" && body.length) return body
  }
  return null
}

function extractSubmitResult(stdout) {
  const text = String(stdout ?? "")
  const lines = text.split("\n")
  for (const line of lines) {
    if (!line.startsWith("SUBMIT:")) continue
    const payload = line.slice("SUBMIT:".length).trim()
    try {
      const obj = JSON.parse(payload)
      if (obj && typeof obj === "object") return obj
    } catch {
      return null
    }
  }
  return null
}

function extractUsageFromStdout(stdout) {
  const text = String(stdout ?? "")
  const lines = text.split("\n").map((l) => l.trim()).filter((l) => l.length > 0)
  let last = null
  for (const l of lines) {
    let obj
    try {
      obj = JSON.parse(l)
    } catch {
      continue
    }
    const usage = obj?.usage
    if (!usage || typeof usage !== "object") continue
    const input = usage.input_tokens
    const output = usage.output_tokens
    const cached = usage.cached_input_tokens ?? null
    if (Number.isFinite(input) && Number.isFinite(output)) {
      last = { input_tokens: Number(input), output_tokens: Number(output), cached_input_tokens: cached != null ? Number(cached) : null }
    }
  }
  return last
}

function normalizePathish(v) {
  let s = String(v ?? "").trim()
  if (!s) return ""
  s = s.replaceAll("\\", "/")
  s = s.replace(/^\.\/+/, "")
  s = s.replace(/^[a-zA-Z]:\/scc\//, "")
  return s
}

function computeTokenCfoSnapshot({ tail = 1200 } = {}) {
  const rows = readJsonlTail(execLogJobs, Number.isFinite(tail) ? tail : 1200).filter(Boolean)
  const board = rows.filter((r) => r && (r.taskType === "board" || r.taskType === "board_split"))
  const withUsage = board.filter((r) => r && r.usage && typeof r.usage === "object")

  const sum = (arr, key) => arr.reduce((acc, r) => acc + (Number(r?.[key] ?? 0) || 0), 0)
  const avg = (arr, key) => (arr.length ? sum(arr, key) / arr.length : 0)

  const by = (arr, keyFn) => {
    const m = new Map()
    for (const r of arr) {
      const k = String(keyFn(r) ?? "")
      const cur = m.get(k) ?? []
      cur.push(r)
      m.set(k, cur)
    }
    return Array.from(m.entries()).map(([k, g]) => ({ key: k, count: g.length, rows: g }))
  }

  const wasted = []
  for (const r of board) {
    const included = Array.isArray(r.context_files_list) ? r.context_files_list.map(normalizePathish).filter(Boolean) : []
    const touched = Array.isArray(r.submit?.touched_files)
      ? r.submit.touched_files.map(normalizePathish).filter(Boolean)
      : Array.isArray(r.patch_stats?.files)
        ? r.patch_stats.files.map(normalizePathish).filter(Boolean)
        : []
    if (!included.length) continue
    const touchedSet = new Set(touched)
    const unused = included.filter((f) => !touchedSet.has(f))
    wasted.push({
      task_id: r.task_id ?? null,
      executor: r.executor ?? null,
      task_class: r.task_class ?? null,
      role: null,
      included: included.length,
      touched: touched.length,
      unused: unused.length,
      unused_ratio: unused.length / included.length,
      sample_unused: unused.slice(0, 8),
    })
  }

  const topUnused = wasted
    .filter((x) => x.unused_ratio >= 0.6 && x.included >= 3)
    .sort((a, b) => b.unused_ratio - a.unused_ratio)
    .slice(0, 20)

  const byTaskClass = by(withUsage, (r) => r.task_class ?? "none").map((g) => ({
    task_class: g.key || "none",
    count: g.count,
    input_avg: Math.round(avg(g.rows.map((x) => x.usage), "input_tokens")),
    output_avg: Math.round(avg(g.rows.map((x) => x.usage), "output_tokens")),
    cached_avg: Math.round(avg(g.rows.map((x) => x.usage), "cached_input_tokens")),
  }))

  const totalInput = sum(withUsage.map((x) => x.usage), "input_tokens")
  const totalOutput = sum(withUsage.map((x) => x.usage), "output_tokens")
  const totalCached = sum(withUsage.map((x) => x.usage), "cached_input_tokens")

  return {
    t: new Date().toISOString(),
    window: { tail: Number.isFinite(tail) ? tail : 1200, rows: rows.length, board: board.length, withUsage: withUsage.length },
    usage_totals: { input_tokens: totalInput, output_tokens: totalOutput, cached_input_tokens: totalCached },
    usage_avgs: {
      input_tokens: Math.round(totalInput / Math.max(1, withUsage.length)),
      output_tokens: Math.round(totalOutput / Math.max(1, withUsage.length)),
      cached_input_tokens: Math.round(totalCached / Math.max(1, totalInput)),
      cache_ratio: withUsage.length ? Math.round((totalCached / Math.max(1, totalInput)) * 1000) / 1000 : 0,
    },
    by_task_class: byTaskClass.sort((a, b) => b.input_avg - a.input_avg).slice(0, 20),
    top_wasted_contextpacks: topUnused,
  }
}

function extractSplitArrayFromStdout(stdout) {
  // Prefer structured codex JSONL agent_message text when available.
  const msg = extractAgentMessageText(stdout)
  if (msg) {
    try {
      const parsed = JSON.parse(msg)
      if (Array.isArray(parsed)) return parsed
    } catch {
      // fall through
    }
    const arr = extractFirstJsonArray(msg)
    if (arr) return arr
  }
  return extractFirstJsonArray(stdout)
}

function applySplitFromJob({ parentId, jobId }) {
  const parent = getBoardTask(parentId)
  if (!parent) return { ok: false, error: "parent_not_found" }
  const job = jobs.get(jobId)
  if (!job) return { ok: false, error: "job_not_found" }
  if (job.status !== "done") return { ok: false, error: "job_not_done" }

  const arr = extractSplitArrayFromStdout(job.stdout)
  if (!arr) return { ok: false, error: "no_json_array_found" }

  const created = []
  const createdPins = []
  for (const item of arr.slice(0, 30)) {
    const title = String(item?.title ?? "").trim()
    const goal = String(item?.goal ?? "").trim()
    if (!title || !goal) continue
    const allowedExecutors = Array.isArray(item?.allowedExecutors) ? item.allowedExecutors : ["opencodecli", "codex"]
    const allowedModels = Array.isArray(item?.allowedModels) ? item.allowedModels : []
    const files = Array.isArray(item?.files) ? item.files : []
    const skills = Array.isArray(item?.skills) ? item.skills : []
    const pointers = item?.pointers && typeof item.pointers === "object" ? item.pointers : null
    const pinsRaw = item?.pins && typeof item.pins === "object" ? item.pins : null
    const pinsInstance = item?.pins_instance && typeof item.pins_instance === "object" ? item.pins_instance : null
    const assumptions = Array.isArray(item?.assumptions)
      ? item.assumptions
      : Array.isArray(item?.pins?.ssot_assumptions)
        ? item.pins.ssot_assumptions
        : []
    const allowedTests = Array.isArray(item?.allowedTests) ? item.allowedTests : []
    const toolingRules = item?.toolingRules && typeof item.toolingRules === "object" ? item.toolingRules : null
    const taskClassId = item?.task_class_id != null ? String(item.task_class_id).trim() : null
    const taskClassCandidate = item?.task_class_candidate != null ? String(item.task_class_candidate).trim() : null
    const taskClassParams = item?.task_class_params && typeof item.task_class_params === "object" ? item.task_class_params : null
    const area = item?.area != null ? String(item.area).trim() : null
    const acceptanceTemplate = item?.acceptance_template != null ? String(item.acceptance_template) : null
    const stopCodes = Array.isArray(item?.stop_codes) ? item.stop_codes : null
    const contract =
      item?.contract && typeof item.contract === "object"
        ? item.contract
        : acceptanceTemplate || (Array.isArray(stopCodes) && stopCodes.length)
          ? { goal, acceptance: acceptanceTemplate ?? null, stop_codes: stopCodes ?? undefined, stop: "If pins are insufficient or tests fail, return fail." }
          : null
    const runner = item?.runner === "internal" ? "internal" : "external"
    const status = normalizeBoardStatus(item?.status) ?? "ready"
    const pinsFromTemplate = resolvePinsForTask({ task_class_id: taskClassId, pins_instance: pinsInstance, pins: null })
    const pins = pinsRaw || pinsFromTemplate
    const pinsPending = splitTwoPhasePins && !pins
    const role = normalizeRole(item?.role)
    const out = createBoardTask({
      kind: "atomic",
      title,
      goal,
      parentId,
      status: pinsPending ? "blocked" : status,
      role,
      allowedExecutors,
      allowedModels,
      files,
      skills,
      pointers,
      pins,
      pins_instance: pinsInstance,
      pins_pending: pinsPending,
      assumptions: assumptions.length ? assumptions : null,
      allowedTests: allowedTests.length ? allowedTests : null,
      toolingRules,
      area,
      task_class_id: taskClassId,
      task_class_candidate: taskClassCandidate,
      task_class_params: taskClassParams,
      contract,
      runner,
    })
    if (out.ok) {
      created.push(out.task)
      if (pinsPending) createdPins.push(out.task)
    }
  }

  if (createdPins.length) {
    for (const t of createdPins) {
      if (!Array.isArray(t.files) || !t.files.length) continue
      const ctx = createContextPackFromFiles({ files: t.files, maxBytes: 200_000 })
      const prompt = [
        "You are a PINS GUIDE. Your job is to produce ONLY pins JSON for the target task.",
        "Output MUST be a single JSON object. No prose.",
        "If pins cannot be derived from provided files, output {\"error\":\"missing_context\"}.",
        "",
        "Recent pins errors (avoid these):",
        JSON.stringify(readPinsGuideErrors(5), null, 2),
        "",
        "Target title:",
        t.title,
        "",
        "Target goal:",
        t.goal,
        "",
        "Return JSON (example):",
        JSON.stringify(
          {
            pins: {
              allowed_paths: t.files,
              forbidden_paths: [],
              symbols: [],
              line_windows: {},
              max_files: 3,
              max_loc: 200,
              ssot_assumptions: [],
            },
          },
          null,
          2,
        ),
      ].join("\n")

      const job = makeJob({
        prompt,
        model: STRICT_DESIGNER_MODEL,
        executor: "codex",
        taskType: "pins_generate",
        timeoutMs: timeoutCodexMs,
      })
      job.runner = "external"
      job.contextPackId = ctx.ok ? ctx.id : null
      job.pinsTargetId = t.id
      jobs.set(job.id, job)
      schedule()

      const pinsTask = createBoardTask({
        kind: "atomic",
        title: `Pins guide: ${t.title}`.slice(0, 180),
        goal: `Generate pins for task ${t.id}`,
        parentId,
        status: "in_progress",
        role: "pinser",
        allowedExecutors: ["opencodecli"],
        allowedModels: [modelsFree?.[0] ?? occliModelDefault],
        files: t.files,
        runner: "external",
        pins_target_id: t.id,
      })
      if (pinsTask.ok) {
        pinsTask.task.lastJobId = job.id
        putBoardTask(pinsTask.task)
      }
    }
  }

  parent.status = "ready"
  parent.updatedAt = Date.now()
  putBoardTask(parent)
  leader({ level: "info", type: "board_task_split_applied", id: parentId, jobId, created: created.length })
  return { ok: true, created }
}

function boardCounts(tasks) {
  const counts = {
    total: tasks.length,
    parent: 0,
    atomic: 0,
    byStatus: {},
    byRole: {},
  }
  for (const t of tasks) {
    if (t.kind === "parent") counts.parent += 1
    else counts.atomic += 1
    counts.byStatus[t.status] = (counts.byStatus[t.status] ?? 0) + 1
    counts.byRole[t.role] = (counts.byRole[t.role] ?? 0) + 1
  }
  return counts
}

function detachWorkerFromJob(job) {
  if (!job?.workerId) return
  const w = getWorker(job.workerId)
  if (w && w.runningJobId === job.id) {
    w.runningJobId = null
    w.lastSeen = Date.now()
    putWorker(w)
  }
}

function cancelExternalJob({ id, reason }) {
  const job = jobs.get(id)
  if (!job) return { ok: false, error: "not_found" }
  if (job.runner !== "external") return { ok: false, error: "not_external_job" }
  if (job.status !== "running" && job.status !== "queued") return { ok: false, error: "not_cancelable" }

  detachWorkerFromJob(job)
  job.status = "failed"
  job.finishedAt = Date.now()
  job.lastUpdate = job.finishedAt
  job.exit_code = 124
  job.error = "canceled"
  job.reason = reason ? String(reason) : "canceled_by_leader"
  job.workerId = null
  job.leaseUntil = null
  jobs.set(job.id, job)
  saveState()
  leader({ level: "warn", type: "job_canceled", id: job.id, executor: job.executor, reason: job.reason })
  updateBoardFromJob(job)
  return { ok: true, job }
}

function requeueExternalJob({ id, reason }) {
  const job = jobs.get(id)
  if (!job) return { ok: false, error: "not_found" }
  if (job.runner !== "external") return { ok: false, error: "not_external_job" }
  if (job.status !== "running" && job.status !== "failed") return { ok: false, error: "not_requeueable" }

  detachWorkerFromJob(job)
  job.status = "queued"
  job.workerId = null
  job.leaseUntil = null
  job.startedAt = null
  job.finishedAt = null
  job.lastUpdate = Date.now()
  job.exit_code = null
  job.error = null
  job.reason = null
  job.warned_long = false
  job.stdout = ""
  if (reason) job.stderr = `requeued: ${String(reason)}`
  jobs.set(job.id, job)
  saveState()
  leader({ level: "info", type: "job_requeued", id: job.id, executor: job.executor, note: reason ? String(reason) : null })
  schedule()
  return { ok: true, job }
}

function readTextSafe(filePath, maxBytes) {
  try {
    const st = fs.statSync(filePath)
    if (!st.isFile()) return null
    const bytes = Math.min(st.size, maxBytes)
    const fd = fs.openSync(filePath, "r")
    try {
      const buf = Buffer.alloc(bytes)
      fs.readSync(fd, buf, 0, bytes, 0)
      return buf.toString("utf8")
    } finally {
      fs.closeSync(fd)
    }
  } catch {
    return null
  }
}

function resolveUnderRoot(p) {
  const abs = path.isAbsolute(p) ? p : path.join(execRoot, p)
  const norm = path.resolve(abs)
  const normLc = norm.toLowerCase()
  for (const root of allowedRoots) {
    const rootLc = root.toLowerCase()
    if (normLc.startsWith(rootLc)) return norm
  }
  return null
}

function threadPath(id) {
  return path.join(threadDir, `${id}.json`)
}

function getThread(id) {
  try {
    const raw = fs.readFileSync(threadPath(id), "utf8")
    const j = JSON.parse(raw)
    return j && typeof j === "object" ? j : null
  } catch {
    return null
  }
}

function putThread(t) {
  try {
    fs.writeFileSync(threadPath(t.id), JSON.stringify(t, null, 2), "utf8")
  } catch {
    // ignore
  }
}

function ctxPath(id) {
  return path.join(ctxDir, `${id}.md`)
}

function getContextPack(id) {
  try {
    return fs.readFileSync(ctxPath(id), "utf8")
  } catch {
    return null
  }
}

const makeJob = ({ prompt, model, executor, taskType, timeoutMs }) => ({
  id: newJobId(),
  prompt,
  model,
  executor,
  taskType: taskType ?? "atomic",
  timeoutMs: typeof timeoutMs === "number" && Number.isFinite(timeoutMs) ? timeoutMs : null,
  runner: "internal", // internal|external
  workerId: null,
  leaseUntil: null,
  status: "queued", // queued|running|done|failed
  attempts: 0,
  createdAt: Date.now(),
  startedAt: null,
  finishedAt: null,
  lastUpdate: null,
  exit_code: null,
  stdout: "",
  stderr: "",
  error: null,
  reason: null,
  warned_long: false,
  threadId: null,
  contextPackId: null,
})

const ATOMIC_DEFAULT_RULES = [
  "You are running as an atomic Executor with strict constraints.",
  "Do NOT scan the repo or run broad searches. Use only the provided <context_pack> (pins/slices).",
  "If pins are provided, you MUST NOT read any files outside pins.",
  "If pins are missing or insufficient, FAIL fast (this is correct behavior).",
  "Do NOT restate requirements. Do NOT redesign. Do NOT add suggestions.",
  "OUTPUT FORMAT (strict, no extra text):",
  "REPORT: <one-line outcome>",
  "SELFTEST.LOG: <commands run or 'none'>",
  "EVIDENCE: <paths or 'none'>",
  "SUBMIT: {\"status\":\"pass|fail\",\"reason_code\":\"...\",\"touched_files\":[...],\"tests_run\":[...]}",
].join("\n")

function normalizePins(pins) {
  if (!pins || typeof pins !== "object") return null
  return pins
}

function sliceLineWindow(lines, start, end) {
  const s = Math.max(1, Number(start ?? 1))
  const e = Math.max(s, Number(end ?? s))
  const max = lines.length
  const ss = Math.min(max, s)
  const ee = Math.min(max, e)
  const out = []
  for (let i = ss; i <= ee; i += 1) {
    const ln = String(i).padStart(5, " ")
    out.push(`${ln}: ${lines[i - 1] ?? ""}`)
  }
  return out.join("\n")
}

function createContextPackFromPins({ pins, maxBytes }) {
  const p = normalizePins(pins)
  if (!p) return { ok: false, error: "missing_pins" }
  const limit = Number(maxBytes ?? 200_000)
  if (!Number.isFinite(limit) || limit <= 0) return { ok: false, error: "bad_maxBytes" }
  if (limit > 400_000) return { ok: false, error: "maxBytes_too_large" }

  const allowedPaths = Array.isArray(p.allowed_paths) ? p.allowed_paths.map((x) => String(x)) : []
  const lineWindows = p.line_windows && typeof p.line_windows === "object" ? p.line_windows : {}
  const snippets = Array.isArray(p.snippets) ? p.snippets : []
  const id = newCtxId()
  let used = 0
  const parts = []
  const usedFiles = new Set()

  const addSlice = (resolved, rel, start, end, note = "") => {
    const remain = limit - used
    if (remain <= 0) return false
    const text = readTextSafe(resolved, Math.min(remain, 200_000))
    if (!text) return false
    const lines = String(text).split(/\r?\n/g)
    const slice = sliceLineWindow(lines, start, end)
    const header = `## ${rel} (lines ${start}-${end})${note ? ` 鈥?${note}` : ""}`
    const block = `${header}\n\n\`\`\`\n${slice}\n\`\`\`\n`
    const bytes = Buffer.byteLength(block, "utf8")
    if (bytes <= 0) return false
    parts.push(block)
    used += bytes
    usedFiles.add(rel)
    return true
  }

  for (const [file, windows] of Object.entries(lineWindows)) {
    const resolved = resolveUnderRoot(file)
    if (!resolved) continue
    const rel = path.relative(execRoot, resolved)
    if (allowedPaths.length && !allowedPaths.includes(file) && !allowedPaths.includes(rel)) continue
    const pairs = Array.isArray(windows) ? windows : []
    for (const w of pairs) {
      const start = Array.isArray(w) ? w[0] : w?.start
      const end = Array.isArray(w) ? w[1] : w?.end
      addSlice(resolved, rel, start, end)
    }
  }

  for (const s of snippets) {
    const file = s?.path ? String(s.path) : null
    if (!file) continue
    const resolved = resolveUnderRoot(file)
    if (!resolved) continue
    const rel = path.relative(execRoot, resolved)
    if (allowedPaths.length && !allowedPaths.includes(file) && !allowedPaths.includes(rel)) continue
    addSlice(resolved, rel, s.start, s.end, s.note ? String(s.note) : "")
  }

  const pinsText = JSON.stringify(p, null, 2)
  const pinsBlock = `# pins.json\n\n\`\`\`json\n${pinsText.slice(0, 4000)}\n\`\`\`\n`
  parts.unshift(pinsBlock)
  const out = parts.join("\n")
  fs.writeFileSync(ctxPath(id), out, "utf8")
  const windowsCount = Object.values(lineWindows).reduce((acc, win) => acc + (Array.isArray(win) ? win.length : 0), 0)
  const filesList = Array.from(usedFiles)
  leader({
    level: "info",
    type: "contextpack_pins_created",
    id,
    bytes: used,
    fileCount: filesList.length,
    windowsCount,
    snippetsCount: snippets.length,
    files: filesList.slice(0, 30),
  })
  return {
    ok: true,
    id,
    bytes: used,
    file: ctxPath(id),
    fileCount: filesList.length,
    files: filesList.slice(0, 30),
    windowsCount,
    snippetsCount: snippets.length,
  }
}

function createContextPackFromFiles({ files, maxBytes }) {
  const list = Array.isArray(files) ? files.map((x) => String(x)) : []
  const limit = Number(maxBytes ?? 200_000)
  if (!list.length) return { ok: false, error: "missing_files" }
  if (!Number.isFinite(limit) || limit <= 0) return { ok: false, error: "bad_maxBytes" }
  if (limit > 400_000) return { ok: false, error: "maxBytes_too_large" }
  const id = newCtxId()
  let used = 0
  const parts = []
  const usedFiles = []
  for (const f of list) {
    const resolved = resolveUnderRoot(f)
    if (!resolved) continue
    const remain = limit - used
    if (remain <= 0) break
    const text = readTextSafe(resolved, Math.min(remain, 60_000))
    if (!text) continue
    const rel = path.relative(execRoot, resolved)
    parts.push(`## ${rel}\n\n\`\`\`\n${text}\n\`\`\`\n`)
    usedFiles.push(rel)
    used += Buffer.byteLength(text, "utf8")
  }
  const out = parts.join("\n")
  fs.writeFileSync(ctxPath(id), out, "utf8")
  leader({ level: "info", type: "contextpack_created", id, files: usedFiles.slice(0, 30), bytes: used, fileCount: usedFiles.length })
  return { ok: true, id, bytes: used, file: ctxPath(id), fileCount: usedFiles.length, files: usedFiles.slice(0, 30) }
}

function extractPatchFromStdout(stdout) {
  const text = String(stdout ?? "")
  const lines = text
    .split("\n")
    .map((l) => l.trimEnd())
    .filter((l) => l.length > 0)
  let sawStructured = false
  for (const l of lines) {
    let obj
    try {
      obj = JSON.parse(l)
    } catch {
      continue
    }
    const item = obj?.item
    if (!item) continue
    sawStructured = true
    if (item.type !== "agent_message") continue
    const body = item?.text
    if (typeof body === "string" && body.includes("*** Begin Patch")) return body
  }
  if (sawStructured) return null

  const idx = text.indexOf("*** Begin Patch")
  if (idx < 0) return null
  const tail = text.slice(idx)
  const end = tail.lastIndexOf("*** End Patch")
  const sliced = end >= 0 ? tail.slice(0, end + "*** End Patch".length) : tail
  const looksEscaped = sliced.includes("\\n***") && !sliced.includes("\n***")
  if (!looksEscaped) return sliced
  return sliced
    .replaceAll("\\r\\n", "\n")
    .replaceAll("\\n", "\n")
    .replaceAll("\\t", "\t")
    .replaceAll("\\\"", "\"")
    .replaceAll("\\\\", "\\")
}

function computePatchStats(patchText) {
  const text = String(patchText ?? "")
  const lines = text.split(/\r?\n/g)
  let added = 0
  let removed = 0
  let hunks = 0
  const files = new Set()
  for (const line of lines) {
    if (line.startsWith("+++ ")) {
      const f = line.slice(4).trim()
      if (f && f !== "/dev/null") files.add(f.replace(/^b\//, ""))
      continue
    }
    if (line.startsWith("--- ")) continue
    if (line.startsWith("@@")) {
      hunks += 1
      continue
    }
    if (line.startsWith("+") && !line.startsWith("+++") ) {
      added += 1
      continue
    }
    if (line.startsWith("-") && !line.startsWith("---") ) {
      removed += 1
    }
  }
  return { files: Array.from(files).slice(0, 30), filesCount: files.size, added, removed, hunks }
}

function isCiCommandAllowed(cmd) {
  const s = String(cmd ?? "").trim().toLowerCase()
  if (!s) return false
  const prefixes = [
    "bun test",
    "npm test",
    "pnpm test",
    "yarn test",
    "pytest",
    "python -m pytest",
    "python scc-top/tools/scc/ops/task_selftest.py",
    "go test",
    "cargo test",
    "dotnet test",
  ]
  return prefixes.some((p) => s.startsWith(p))
}

function pickCiGateCommand(allowedTests) {
  const list = Array.isArray(allowedTests) ? allowedTests : []
  for (const raw of list) {
    const cmd = String(raw ?? "").trim()
    if (!cmd) continue
    if (ciGateAllowAll || isCiCommandAllowed(cmd)) return cmd
  }
  return null
}

function applyCiTemplate(cmd, { taskId, jobId, area }) {
  let out = String(cmd ?? "")
  out = out.replaceAll("{task_id}", String(taskId ?? ""))
  out = out.replaceAll("{job_id}", String(jobId ?? ""))
  out = out.replaceAll("{area}", String(area ?? ""))
  return out
}

function resolveCiGateCwd() {
  const preferred = String(ciGateCwd ?? "").trim()
  if (preferred && fs.existsSync(preferred)) return preferred
  if (execRoot && fs.existsSync(execRoot)) return execRoot
  return process.cwd()
}

function runCiGateCommand(cmd) {
  return new Promise((resolve) => {
    const start = Date.now()
    const cwd = resolveCiGateCwd()
    execFile(
      "cmd.exe",
      ["/c", cmd],
      { cwd, timeout: Number.isFinite(ciGateTimeoutMs) ? ciGateTimeoutMs : 1_200_000, windowsHide: true, maxBuffer: 10 * 1024 * 1024 },
      (err, stdout, stderr) => {
        const finishedAt = Date.now()
        const durationMs = finishedAt - start
        const exitCode = err && typeof err.code === "number" ? err.code : 0
        const ok = !err && exitCode === 0
        const stdoutText = String(stdout || "")
        const stderrText = String(stderr || "")

        // Evidence anti-forgery: persist full CI logs and record hashes.
        // This makes CI results auditable and cross-checkable by task_selftest.
        let stdoutPath = null
        let stderrPath = null
        let stdoutSha256 = null
        let stderrSha256 = null
        try {
          const sha = (s) => crypto.createHash("sha256").update(Buffer.from(String(s || ""), "utf8")).digest("hex")
          stdoutSha256 = sha(stdoutText)
          stderrSha256 = sha(stderrText)
          const dir = path.join(execLogDir, "ci_gate")
          fs.mkdirSync(dir, { recursive: true })
          const id = `${start}_${Math.random().toString(16).slice(2, 8)}`
          stdoutPath = path.join(dir, `ci_${id}.stdout.log`)
          stderrPath = path.join(dir, `ci_${id}.stderr.log`)
          fs.writeFileSync(stdoutPath, stdoutText, "utf8")
          fs.writeFileSync(stderrPath, stderrText, "utf8")
        } catch {
          // best-effort; CI still functions without persisted logs
        }
        resolve({
          ok,
          exitCode,
          durationMs,
          startedAt: start,
          finishedAt,
          command: cmd,
          stdoutPreview: stdoutText.slice(0, 2000),
          stderrPreview: stderrText.slice(0, 2000),
          stdoutPath,
          stderrPath,
          stdoutSha256,
          stderrSha256,
          timedOut: err && String(err.message || "").toLowerCase().includes("timed out"),
        })
      }
    )
  })
}

async function runCiGateForTask({ job, boardTask }) {
  if (!ciGateEnabled) return { ran: false, skipped: "disabled" }
  if (!boardTask) return { ran: false, skipped: "no_task" }
  const allowedTests = Array.isArray(job?.allowedTests) && job.allowedTests.length ? job.allowedTests : boardTask.allowedTests
  const hasTests = Array.isArray(allowedTests) && allowedTests.length > 0
  const required = Number.isFinite(ciEnforceSinceMs) && ciEnforceSinceMs > 0 ? (boardTask.createdAt ?? 0) >= ciEnforceSinceMs : true
  const normalizedTests = Array.isArray(allowedTests)
    ? allowedTests.map((t) => String(t ?? "").trim()).filter((t) => t.length > 0)
    : []
  const hasNonSelfTest = normalizedTests.some((t) => !t.toLowerCase().includes("task_selftest"))
  if (required && normalizedTests.length > 0 && !hasNonSelfTest) return { ran: false, skipped: "tests_only_task_selftest", required: true }
  if (!hasTests) return { ran: false, skipped: "no_tests", required }
  const rawCmd = pickCiGateCommand(allowedTests)
  const cmd = rawCmd ? applyCiTemplate(rawCmd, { taskId: boardTask.id, jobId: job?.id ?? "", area: boardTask.area ?? "" }) : null
  if (!cmd) return { ran: false, skipped: "no_allowed_command", required: true }
  const result = await runCiGateCommand(cmd)
  return { ran: true, required: true, ...result }
}

function runHygieneChecks({ job, boardTask }) {
  // submit must exist
  const submit = job.submit
  if (!submit) return { ok: false, reason: "missing_submit" }
  // artifacts must be under artifacts/
  const art = submit.artifacts || job.artifacts || {}
  const artifactsList = ["report_md", "selftest_log", "evidence_dir", "patch_diff", "submit_json"]
  for (const k of artifactsList) {
    const v = art[k]
    if (!v) return { ok: false, reason: `missing_artifact_${k}` }
    if (!String(v).startsWith("artifacts/")) return { ok: false, reason: `artifact_out_of_root_${k}` }
  }
  // allowlist enforcement: touched_files within pins allowed_paths
  const touched = Array.isArray(submit.touched_files) ? submit.touched_files : []
  const pins = boardTask?.pins
  const allow = Array.isArray(pins?.allowed_paths) ? pins.allowed_paths : null
  if (allow && allow.length && touched.length) {
    for (const f of touched) {
      if (!allow.some((a) => String(f).startsWith(String(a)))) {
        return { ok: false, reason: "touched_file_outside_allow_paths", file: f }
      }
    }
  }
  return { ok: true }
}

function maybeCreateCiFixupTask({ boardTask, job, ciGate }) {
  if (!ciFixupEnabled) return { ok: false, error: "disabled" }
  if (fixupFuseTripped()) {
    leader({ level: "warn", type: "fixup_fused", kind: "ci", task_id: boardTask?.id ?? null })
    return { ok: false, error: "fused" }
  }
  if (!boardTask || boardTask.kind !== "atomic") return { ok: false, error: "not_atomic" }
  if (boardTask.task_class_id === "ci_fixup_v1") return { ok: false, error: "self_task" }
  const current = Number(boardTask.ci_fixup_count ?? 0)
  if (Number.isFinite(ciFixupMaxPerTask) && ciFixupMaxPerTask > 0 && current >= ciFixupMaxPerTask) {
    return { ok: false, error: "limit_reached" }
  }

  // Lock to original executor/model when possible, fallback to config.
  const originalExecutor = job?.executor && (job.executor === "codex" || job.executor === "opencodecli") ? job.executor : null
  const originalModel = job?.model ? String(job.model) : null
  const safeExecutors = ciFixupAllowedExecutors.filter((x) => x === "codex" || x === "opencodecli")
  const allowedExecutors = [originalExecutor, ...safeExecutors, "codex"].filter(Boolean).slice(0, 2)
  const allowedModels = originalModel
    ? [originalModel]
    : ciFixupAllowedModels.length
      ? ciFixupAllowedModels.slice(0, 6)
      : ["gpt-5.2"]

  boardTask.ci_fixup_count = current + 1
  boardTask.updatedAt = Date.now()
  putBoardTask(boardTask)

  const title = `CI fixup: ${boardTask.title ?? boardTask.id}`
  const goal = [
    "Role: QA/ENGINEER.",
    "Goal: CI/selftest failed or missing. Provide evidence, fix issues, and runnable test commands until exit_code=0.",
    "Output: patch or exact commands + evidence paths; explain failure root cause and fixes.",
    "",
    "CI gate:",
    JSON.stringify(ciGate ?? {}, null, 2),
    "",
    "Original task:",
    JSON.stringify(
      {
        task_id: boardTask.id,
        title: boardTask.title,
        goal: boardTask.goal,
        role: boardTask.role,
        allowedTests: boardTask.allowedTests ?? job?.allowedTests ?? null,
        context_source: job?.contextSource ?? null,
        context_files: job?.contextFiles ?? null,
      },
      null,
      2
    ),
  ].join("\n")

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: ciFixupRole,
    runner: "internal",
    area: boardTask.area ?? "control_plane",
    task_class_id: "ci_fixup_v1",
    parentId: boardTask.parentId ?? null,
    allowedExecutors,
    allowedModels,
    timeoutMs: ciFixupTimeoutMs,
    pointers: {
      sourceTaskId: boardTask.id,
      jobId: job?.id ?? null,
      ci_gate: ciGate ?? null,
    },
  })

  if (!created.ok) return created
  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "ci_fixup_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 950
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCounts()
    const canRun =
      dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") {
      runJob(dispatched.job)
    } else {
      schedule()
    }
    leader({ level: "info", type: "ci_fixup_dispatched", id: created.task.id, jobId: dispatched.job.id })
  }

  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

function maybeCreatePinsFixupTask({ boardTask, job }) {
  if (!pinsFixupEnabled) return { ok: false, error: "disabled" }
  if (fixupFuseTripped()) {
    leader({ level: "warn", type: "fixup_fused", kind: "pins", task_id: boardTask?.id ?? null })
    return { ok: false, error: "fused" }
  }
  if (!boardTask || boardTask.kind !== "atomic") return { ok: false, error: "not_atomic" }
  if (boardTask.task_class_id === "pins_fixup_v1") return { ok: false, error: "self_task" }
  const reason = String(job?.reason ?? boardTask?.lastJobReason ?? "")
  if (!["pins_insufficient", "missing_pins", "missing_pins_template"].includes(reason)) return { ok: false, error: "not_pins_failure" }
  if (!Array.isArray(boardTask.files) || boardTask.files.length === 0) return { ok: false, error: "missing_files" }

  const current = Number(boardTask.pins_fixup_count ?? 0)
  if (Number.isFinite(pinsFixupMaxPerTask) && pinsFixupMaxPerTask > 0 && current >= pinsFixupMaxPerTask) {
    return { ok: false, error: "limit_reached" }
  }
  boardTask.pins_fixup_count = current + 1
  boardTask.updatedAt = Date.now()
  putBoardTask(boardTask)

  const safeExecutors = pinsFixupAllowedExecutors.filter((x) => x === "codex" || x === "opencodecli")
  const allowedExecutors = safeExecutors.length ? safeExecutors : ["opencodecli"]
  const allowedModels = pinsFixupAllowedModels.length
    ? pinsFixupAllowedModels.slice(0, 6)
    : modelsFree.length
      ? [modelsFree[0]]
      : [occliModelDefault]

  const title = `Pins fixup: ${boardTask.title ?? boardTask.id}`
  const goal = JSON.stringify(
    {
      schema_version: "scc.pins_fill_prompt.v1",
      role: "pins_filler",
      output_mode: "JSON_ONLY",
      task: {
        task_id: `PF-${crypto.randomUUID()}`,
        parent_task_id: boardTask.parentId ?? null,
        goal: "为子任务构建足够且最小的 pins（路径/符号/行窗），满足 preflight 与 allowedTests",
        task_class: boardTask.task_class_id ?? boardTask.task_class_candidate ?? null,
        repo_root_policy: "repo_root_relative_only",
        unknown_policy: "NEED_INPUT",
      },
      inputs: {
        ssot_pointers: [],
        child_task_contract: {
          title: boardTask.title ?? "",
          goal: boardTask.goal ?? "",
          acceptance: Array.isArray(boardTask.acceptance) ? boardTask.acceptance : [],
          allowed_tests: { commands: Array.isArray(boardTask.allowedTests) ? boardTask.allowedTests : [] },
          patch_scope: {
            allow_paths: Array.isArray(boardTask.files) ? boardTask.files : [],
            deny_paths: Array.isArray(boardTask.forbidden_paths) ? boardTask.forbidden_paths : [],
          },
        },
        existing_pins: {
          pins_json_path: null,
          pins_md_path: null,
        },
        signals: {
          preflight_missing: [],
          ci_failures: [reason],
          error_snippets: readPinsGuideErrors(4),
        },
      },
      rules: {
        must: [
          "pins 只包含与子任务直接相关的最小集合（禁止全仓/大目录）",
          "每个 pin 必须可解释：为什么需要它（reason）",
          "优先 pin 入口/接口/配置/测试相关文件，再 pin 具体实现",
          "如果缺少关键信息（入口路径/模块名/测试命令），输出 NEED_INPUT 并给出具体问题",
        ],
        forbid: [
          "编造文件路径/符号名",
          "输出任何非 JSON 文本",
          "超出 patch_scope 的 pin（除非标注为 read_only 且解释原因）",
        ],
        budgets: { max_total_pins_tokens: 4000, max_files: 20, default_line_window: 120 },
      },
      desired_outputs: {
        pins_json: { required: true, fields: ["pins[].path", "pins[].symbols[]", "pins[].line_windows[]", "pins[].purpose", "pins[].reason", "pins[].read_only"] },
        pins_md: { required: false, notes: "可选：给人看的简版 pins 摘要（不放长原文）" },
        recommended_search_queries: { required: true },
        preflight_expectation: { required: true, notes: "列出这些 pins 能覆盖哪些 preflight 必需项/测试路径" },
      },
      original_task: {
        task_id: boardTask.id,
        role: boardTask.role,
        files: boardTask.files,
        current_pins: boardTask.pins ?? null,
        failure_reason: reason,
      },
    },
    null,
    2
  )

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: pinsFixupRole,
    runner: "internal",
    area: boardTask.area ?? "control_plane",
    task_class_id: "pins_fixup_v1",
    parentId: boardTask.parentId ?? null,
    allowedExecutors,
    allowedModels,
    files: boardTask.files,
    timeoutMs: pinsFixupTimeoutMs,
    pointers: { sourceTaskId: boardTask.id, jobId: job?.id ?? null, reason },
  })
  if (!created.ok) return created

  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "pins_fixup_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 980
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCounts()
    const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
    else schedule()
    leader({ level: "info", type: "pins_fixup_dispatched", id: created.task.id, jobId: dispatched.job.id })
  }

  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

const runningCounts = () => {
  let codex = 0
  let opencodecli = 0
  for (const j of jobs.values()) {
    if (j.status !== "running") continue
    if (j.executor === "opencodecli") opencodecli += 1
    else codex += 1
  }
  return { codex, opencodecli }
}

const nextQueued = (executor) => Array.from(jobs.values()).find((j) => j.status === "queued" && j.executor === executor)
const nextQueuedInternal = (executor) => {
  const queued = Array.from(jobs.values()).filter(
    (j) => j.status === "queued" && j.executor === executor && j.runner !== "external"
  )
  if (!queued.length) return null
  queued.sort((a, b) => {
    const pa = Number(a.priority ?? 0)
    const pb = Number(b.priority ?? 0)
    if (pa !== pb) return pb - pa
    return Number(a.createdAt ?? 0) - Number(b.createdAt ?? 0)
  })
  return queued[0]
}

const externalMaxCodex = Number.isFinite(Number(process.env.EXTERNAL_MAX_CODEX)) ? Number(process.env.EXTERNAL_MAX_CODEX) : 4
const externalMaxOccli = Number.isFinite(Number(process.env.EXTERNAL_MAX_OPENCODECLI)) ? Number(process.env.EXTERNAL_MAX_OPENCODECLI) : 6

const desiredRatioCodex = Number.isFinite(Number(process.env.DESIRED_RATIO_CODEX)) ? Number(process.env.DESIRED_RATIO_CODEX) : 4
const desiredRatioOccli = Number.isFinite(Number(process.env.DESIRED_RATIO_OPENCODECLI)) ? Number(process.env.DESIRED_RATIO_OPENCODECLI) : 6
const autoAssignOccliModels = String(process.env.AUTO_ASSIGN_OPENCODE_MODELS ?? "true").toLowerCase() !== "false"
const modelRrFile = path.join(execLogDir, "model_rr.json")
let modelRrIndex = 0
try {
  const raw = fs.readFileSync(modelRrFile, "utf8")
  const parsed = JSON.parse(raw)
  if (Number.isFinite(parsed?.index)) modelRrIndex = Number(parsed.index)
} catch {
  // ignore
}
function saveModelRr() {
  try {
    fs.writeFileSync(modelRrFile, JSON.stringify({ index: modelRrIndex }, null, 2), "utf8")
  } catch {
    // best effort
  }
}
function pickOccliModelForTask(t) {
  if (!autoAssignOccliModels) return occliModelDefault
  const allowed = Array.isArray(t?.allowedModels) ? t.allowedModels.map((x) => String(x)) : []
  const explicit = allowed.filter((m) => m.startsWith("opencode/"))
  const attempt = Number.isFinite(Number(t?.modelAttempt)) ? Number(t.modelAttempt) : 0
  if (explicit.length) {
    if (modelRoutingMode === "strong_first") return explicit[0]
    if (modelRoutingMode === "ladder") return explicit[Math.min(Math.max(0, attempt), explicit.length - 1)]
    // rr
    const idx = Math.abs(modelRrIndex) % explicit.length
    modelRrIndex += 1
    saveModelRr()
    return explicit[idx]
  }

  const text = `${t?.title ?? ""}\n${t?.goal ?? ""}`.toLowerCase()
  const wantsVision = /(vision|image|ocr|瑙嗚|鍥剧墖|鍥惧儚)/i.test(text)
  const pool = wantsVision && modelsVision.length ? modelsVision : modelsFree.length ? modelsFree : [occliModelDefault]
  if (modelRoutingMode === "strong_first") return pool[0]
  if (modelRoutingMode === "ladder") return pool[Math.min(Math.max(0, attempt), pool.length - 1)]
  const idx = Math.abs(modelRrIndex) % pool.length
  modelRrIndex += 1
  saveModelRr()
  return pool[idx]
}

function pickCodexModelForTask(t) {
  const allowed = Array.isArray(t?.allowedModels) ? t.allowedModels.map((x) => String(x)) : []
  // Codex models are typically unprefixed slugs; treat non-opencode entries as codex candidates.
  const pool0 = allowed.filter((m) => !m.startsWith("opencode/"))
  const pool = pool0.length ? pool0 : (modelsPaid.length ? modelsPaid : [codexModelDefault])
  const attempt = Number.isFinite(Number(t?.modelAttempt)) ? Number(t.modelAttempt) : 0
  if (modelRoutingMode === "strong_first") return pool[0]
  if (modelRoutingMode === "ladder") return pool[Math.min(Math.max(0, attempt), pool.length - 1)]
  return pool[0]
}
function runningByExecutor() {
  const counts = { codex: 0, opencodecli: 0 }
  for (const j of jobs.values()) {
    if (j.status !== "running") continue
    if (j.executor === "opencodecli") counts.opencodecli += 1
    else if (j.executor === "codex") counts.codex += 1
  }
  return counts
}
function pickExecutorForTask(t) {
  const allowed = Array.isArray(t?.allowedExecutors) ? t.allowedExecutors : []
  if (t?.role === "designer") return "codex"
  if (allowed.length === 1) return allowed[0]
  if (!allowed.includes("codex") && !allowed.includes("opencodecli")) return "codex"
  if (!allowed.includes("opencodecli")) return "codex"
  if (!allowed.includes("codex")) return "opencodecli"

  // 强优先 occli，只有当 occli 预计占比已超阈值才回落 codex
  const total = Math.max(1, desiredRatioCodex + desiredRatioOccli)
  const wantOcShare = desiredRatioOccli / total
  const running = runningByExecutor()
  const runningTotal = running.codex + running.opencodecli
  const currentOcShare = runningTotal > 0 ? running.opencodecli / runningTotal : 0
  if (currentOcShare < wantOcShare) return "opencodecli"
  return "codex"
}

async function schedule() {
  if (scheduling) return
  scheduling = true
  try {
    while (true) {
      const counts = runningCounts()
      const canCodex = counts.codex < codexMax
      const canOc = counts.opencodecli < occliMax

      const pickOc = canOc ? nextQueuedInternal("opencodecli") : null
      const pickCodex = canCodex ? nextQueuedInternal("codex") : null
      const pick = pickOc ?? pickCodex
      if (!pick) break
      runJob(pick)
    }
  } finally {
    scheduling = false
  }
}

async function runJob(job) {
  const current = jobs.get(job.id)
  if (!current || current.status !== "queued") return
  current.status = "running"
  current.attempts = (current.attempts ?? 0) + 1
  current.startedAt = Date.now()
  current.lastUpdate = current.startedAt
  jobs.set(job.id, current)
  saveState()
  leader({
    level: "info",
    type: "job_started",
    id: current.id,
    executor: current.executor,
    model: current.model,
    attempts: current.attempts,
    promptPreview: String(current.prompt || "").slice(0, 140),
  })

  let result
  let failureHint = null
  const prefixParts = []
  if (current.contextPackId) {
    const ctxText = getContextPack(current.contextPackId)
    if (ctxText) prefixParts.push(`<context_pack id="${current.contextPackId}">\n${ctxText}\n</context_pack>\n`)
  }
  if (current.threadId) {
    const t = getThread(current.threadId)
    const history = Array.isArray(t?.history) ? t.history : []
    if (history.length) {
      const last = history.slice(-6).map((x) => `- ${x}`).join("\n")
      prefixParts.push(`<thread id="${current.threadId}">\nRecent decisions:\n${last}\n</thread>\n`)
    }
  }
  const injected = prefixParts.length ? prefixParts.join("\n") + "\n" + current.prompt : current.prompt

  if (job.executor === "opencodecli") {
    result = await occliRunSingle(injected, job.model || occliModelDefault, { timeoutMs: current.timeoutMs ?? undefined })
  } else {
    result = await codexRunSingle(injected, job.model || codexModelDefault, { timeoutMs: current.timeoutMs ?? undefined })
  }

  const done = jobs.get(job.id)
  if (!done) return
  done.status = result.ok ? "done" : "failed"
  done.finishedAt = Date.now()
  done.lastUpdate = done.finishedAt
  done.exit_code = result.code
  done.stdout = result.stdout
  done.stderr = result.stderr
  done.error = result.ok ? null : "executor_error"
  done.reason = result.ok ? null : classifyFailure(done, result)
  const boardTask = job?.boardTaskId ? getBoardTask(String(job.boardTaskId)) : null
  const patchText = extractPatchFromStdout(done.stdout)
  const patchStats = patchText ? computePatchStats(patchText) : null
  done.patch_stats = patchStats ?? null
  // Executor contract includes a structured SUBMIT payload. Persist it for audit/evidence and
  // for cases where we cannot infer touched files from a unified diff (e.g. tool-based writes).
  done.submit = extractSubmitResult(done.stdout) ?? null
  done.usage = done.executor === "codex" ? extractUsageFromStdout(done.stdout) : null
  if (done.status === "done" && done.executor === "opencodecli" && occliRequireSubmit && !done.submit) {
    done.status = "failed"
    done.error = "missing_submit_contract"
    done.reason = "missing_submit_contract"
  }

  let ciGate = null
  if (done.status === "done") {
    ciGate = await runCiGateForTask({ job: done, boardTask })
    if (ciGate?.required && !ciGate.ran && ciGateStrict) {
      done.status = "failed"
      done.error = "ci_failed"
      done.reason = "ci_skipped"
    } else if (ciGate?.ran && !ciGate.ok) {
      done.status = "failed"
      done.error = "ci_failed"
      done.reason = "ci_failed"
    }
    // Hygiene gate：submit必需，改动不可越界，产物路径必须在 artifacts/。
    if (done.status === "done") {
      const hygiene = runHygieneChecks({ job: done, boardTask })
      if (!hygiene.ok) {
        done.status = "failed"
        done.error = "hygiene_failed"
        done.reason = hygiene.reason ?? "hygiene_failed"
      }
    }
  }
  done.ci_gate = ciGate ?? null
  if (ciGate && done.error === "ci_failed") {
    maybeCreateCiFixupTask({ boardTask, job: done, ciGate })
  }
  if (ciGate) {
    appendJsonlChained(ciGateResultsFile, {
      t: new Date().toISOString(),
      job_id: done.id,
      task_id: boardTask?.id ?? null,
      ok: ciGate.ok ?? null,
      ran: ciGate.ran ?? null,
      required: ciGate.required ?? null,
      skipped: ciGate.skipped ?? null,
      exitCode: ciGate.exitCode ?? null,
      durationMs: ciGate.durationMs ?? null,
      startedAt: ciGate.startedAt ?? null,
      finishedAt: ciGate.finishedAt ?? null,
      command: ciGate.command ?? null,
      timedOut: ciGate.timedOut ?? null,
      stdoutPreview: ciGate.stdoutPreview ?? null,
      stderrPreview: ciGate.stderrPreview ?? null,
      stdoutPath: ciGate.stdoutPath ?? null,
      stderrPath: ciGate.stderrPath ?? null,
      stdoutSha256: ciGate.stdoutSha256 ?? null,
      stderrSha256: ciGate.stderrSha256 ?? null,
      submit: done.submit
        ? {
            status: done.submit.status ?? null,
            reason_code: done.submit.reason_code ?? null,
            touched_files: Array.isArray(done.submit.touched_files) ? done.submit.touched_files.slice(0, 30) : null,
            tests_run: Array.isArray(done.submit.tests_run) ? done.submit.tests_run.slice(0, 20) : null,
          }
        : null,
    })
    if (done.error === "ci_failed") {
      appendJsonl(ciFailuresFile, {
        t: new Date().toISOString(),
        task_id: boardTask?.id ?? null,
        job_id: done.id,
        reason: done.reason ?? "ci_failed",
        exitCode: ciGate.exitCode ?? null,
        skipped: ciGate.skipped ?? null,
        stdoutPreview: ciGate.stdoutPreview ?? null,
        stderrPreview: ciGate.stderrPreview ?? null,
      })
    }
  }
  jobs.set(job.id, done)
  saveState()

  if (done.status === "done" && done.threadId) {
    const t = getThread(done.threadId) ?? { id: done.threadId, createdAt: Date.now(), history: [] }
    const line = `${done.executor}:${done.id}:${done.model}:${String(done.stdout || done.stderr || "").slice(0, 200).replace(/\s+/g, " ")}`
    const history = Array.isArray(t.history) ? t.history : []
    t.history = history.concat([line]).slice(-50)
    putThread(t)
  }

  const record = {
    t: new Date().toISOString(),
    id: done.id,
    executor: done.executor,
    model: done.model,
    status: done.status,
    task_id: boardTask?.id ?? null,
    area: boardTask?.area ?? null,
    task_class: boardTask?.task_class_id ?? boardTask?.task_class_candidate ?? null,
    exit_code: done.exit_code,
    reason: done.reason,
    createdAt: done.createdAt,
    startedAt: done.startedAt,
    finishedAt: done.finishedAt,
    durationMs: done.startedAt && done.finishedAt ? done.finishedAt - done.startedAt : null,
    context_bytes: done.contextBytes ?? null,
    context_files: done.contextFiles ?? null,
    context_source: done.contextSource ?? null,
    context_files_list: Array.isArray(done.contextFilesList) ? done.contextFilesList.slice(0, 30) : null,
    patch_stats: patchStats ?? null,
    submit: done.submit
      ? {
          status: done.submit.status ?? null,
          reason_code: done.submit.reason_code ?? null,
          touched_files: Array.isArray(done.submit.touched_files) ? done.submit.touched_files.slice(0, 30) : null,
          tests_run: Array.isArray(done.submit.tests_run) ? done.submit.tests_run.slice(0, 20) : null,
        }
      : null,
    usage: done.usage
      ? {
          input_tokens: done.usage.input_tokens ?? null,
          output_tokens: done.usage.output_tokens ?? null,
          cached_input_tokens: done.usage.cached_input_tokens ?? null,
        }
      : null,
    ci_gate: ciGate
      ? {
          ok: ciGate.ok ?? null,
          ran: ciGate.ran ?? null,
          required: ciGate.required ?? null,
          skipped: ciGate.skipped ?? null,
          exitCode: ciGate.exitCode ?? null,
          durationMs: ciGate.durationMs ?? null,
          command: ciGate.command ?? null,
          timedOut: ciGate.timedOut ?? null,
        }
      : null,
    promptPreview: String(done.prompt || "").slice(0, 2000),
    stdoutPreview: String(done.stdout || "").slice(0, 4000),
    stderrPreview: String(done.stderr || "").slice(0, 4000),
  }
  appendJsonl(execLogJobs, record)
  if (done.status === "failed") {
    appendJsonl(execLogFailures, record)
    appendJsonl(learnedPatternsFile, {
      t: record.t,
      job_id: done.id,
      task_id: boardTask?.id ?? null,
      parent_id: boardTask?.parentId ?? null,
      area: boardTask?.area ?? null,
      role: boardTask?.role ?? null,
      task_class: boardTask?.task_class_id ?? boardTask?.task_class_candidate ?? null,
      executor: done.executor,
      model: done.model,
      reason: done.reason ?? done.error ?? "failed",
      context_source: done.contextSource ?? null,
      context_files: done.contextFiles ?? null,
      ci_gate: done.ci_gate ? { ok: done.ci_gate.ok ?? null, skipped: done.ci_gate.skipped ?? null } : null,
    })
    // Keep a cheap rolling summary on disk for dashboards/audit.
    updateLearnedPatternsSummary()
    if (boardTask?.role) {
      appendRoleError(boardTask.role, {
        t: record.t,
        task_id: boardTask.id,
        role: boardTask.role,
        executor: done.executor,
        model: done.model,
        reason: done.reason ?? done.error ?? "failed",
        job_id: done.id,
        hint: "Check pins scope, context pack, and allowed tests.",
      })
    }
    if (job.taskType === "board_split") {
      appendJsonl(designerFailuresFile, {
        t: record.t,
        task_id: boardTask?.id ?? null,
        reason: done.reason ?? done.error ?? "failed",
        executor: done.executor,
        model: done.model,
        job_id: done.id,
      })
    } else if (boardTask?.kind === "atomic") {
      appendJsonl(executorFailuresFile, {
        t: record.t,
        task_id: boardTask?.id ?? null,
        role: boardTask?.role ?? null,
        reason: done.reason ?? done.error ?? "failed",
        executor: done.executor,
        model: done.model,
        job_id: done.id,
      })
    }
  }
  leader({
    level: done.status === "failed" ? "error" : "info",
    type: "job_finished",
    id: done.id,
    executor: done.executor,
    model: done.model,
    status: done.status,
    reason: done.reason,
    exit_code: done.exit_code,
    durationMs: record.durationMs,
    promptPreview: record.promptPreview?.slice?.(0, 140),
  })
  if (ciGate) {
    leader({
      level: ciGate.ran && ciGate.ok ? "info" : ciGate.required ? "warn" : "info",
      type: ciGate.ran ? "ci_gate_result" : "ci_gate_skipped",
      id: done.id,
      task_id: boardTask?.id ?? null,
      ok: ciGate.ok ?? null,
      ran: ciGate.ran ?? null,
      required: ciGate.required ?? null,
      skipped: ciGate.skipped ?? null,
      exit_code: ciGate.exitCode ?? null,
      durationMs: ciGate.durationMs ?? null,
      command: ciGate.command ?? null,
      timedOut: ciGate.timedOut ?? null,
    })
  }
  updateBoardFromJob(done)
  if (done.status === "done" && boardTask) {
    appendPinsCandidate(boardTask, done)
  }
  if (boardTask && (boardTask.role === "auditor" || boardTask.role === "status_review")) {
    if (done.status === "failed") {
      const created = createBoardTask({
        kind: "atomic",
        status: "ready",
        title: "Audit follow-up: clarify/fix",
        goal: `Audit failed for task ${boardTask.parentId ?? boardTask.id}. Clarify pins or fix findings, then re-run CI.`,
        role: "factory_manager",
        area: "control_plane",
        runner: "internal",
        allowedExecutors: ["codex"],
        allowedModels: ["gpt-5.2"],
        task_class_id: "audit_fix_v1",
        parentId: boardTask.parentId ?? null,
      })
      if (created.ok) dispatchBoardTaskToExecutor(created.task.id)
    } else if (done.status === "done") {
      const already = boardTask.pointers?.designer_followup_created
      if (!already) {
        const title = `Designer follow-up from audit ${boardTask.id}`
        const goal = [
          "依据审计报告，决定是生成新父任务还是宣布目标已完成。",
          "如需要新父任务：输出父任务合同并置为 needs_split；如无需继续，输出结论并关闭相关目标。",
          `审计 evidence 参考：job=${done.id}, stdoutPreview=${String(done.stdout || "").slice(0, 400)}`,
        ].join("\n")
        const parent = createBoardTask({
          kind: "parent",
          status: "needs_split",
          title,
          goal,
          role: "designer",
          area: boardTask.area ?? "control_plane",
          runner: "external",
          pointers: { auditTaskId: boardTask.id, jobId: done.id, designer_followup_created: true },
        })
        if (parent.ok) putBoardTask(parent.task)
        const bt = getBoardTask(boardTask.id)
        if (bt) {
          bt.pointers = { ...(bt.pointers || {}), designer_followup_created: true }
          putBoardTask(bt)
        }
      }
    }
  }
  if (done.status === "done" && boardTask) {
    // Best-effort radius audit to detect "silent scope expansion" (rate limited).
    maybeRunRadiusAuditFromJob(done, boardTask, ciGate)
  }
  if (job.taskType === "pins_generate" && job.pinsTargetId) {
    const target = getBoardTask(String(job.pinsTargetId))
    if (target) {
      const result = done.status === "done" ? extractPinsResult(done.stdout) : null
      if (result?.pins) {
        target.pins = result.pins
        target.pins_pending = false
        if (target.status === "blocked") target.status = "ready"
        target.updatedAt = Date.now()
        putBoardTask(target)
        leader({ level: "info", type: "pins_applied", id: target.id })
      } else {
        const err = result?.error ?? done.reason ?? "pins_missing"
        appendJsonl(pinsGuideErrorsFile, {
          t: new Date().toISOString(),
          task_id: target.id,
          error: err,
          hint: "Missing pins or insufficient context. Ensure files list is complete.",
        })
        leader({ level: "warn", type: "pins_apply_failed", id: target.id, error: err })
      }
    }
  }
  if (done.status === "done") {
    const submit = extractSubmitResult(done.stdout)
    if (submit && submit.status === "fail") {
      appendJsonl(verifierFailuresFile, {
        t: record.t,
        task_id: boardTask?.id ?? null,
        role: boardTask?.role ?? null,
        reason: submit.reason_code ?? "verification_failed",
        executor: done.executor,
        model: done.model,
        job_id: done.id,
      })
    }
  }
  if (boardTask && (boardTask.role === "auditor" || boardTask.role === "status_review")) {
    if (done.status === "failed") {
      const created = createBoardTask({
        kind: "atomic",
        status: "ready",
        title: "Audit follow-up: clarify/fix",
        goal: `Audit failed for task ${boardTask.parentId ?? boardTask.id}. Clarify pins or fix findings, then re-run CI.`,
        role: "factory_manager",
        area: "control_plane",
        runner: "internal",
        allowedExecutors: ["codex"],
        allowedModels: ["gpt-5.2"],
        task_class_id: "audit_fix_v1",
        parentId: boardTask.parentId ?? null,
      })
      if (created.ok) dispatchBoardTaskToExecutor(created.task.id)
    } else if (done.status === "done" && boardTask.parentId) {
      const parent = getBoardTask(boardTask.parentId)
      if (parent && parent.status !== "done") {
        parent.status = "done"
        parent.updatedAt = Date.now()
        putBoardTask(parent)
      }
    }
  }
  schedule()
}

// Heartbeat updates for visibility while running
setInterval(() => {
  const now = Date.now()
  for (const j of jobs.values()) {
    if (j.status !== "running") continue
    if (j.runner === "external") continue
    j.lastUpdate = now
  }
}, 5000)

// Periodic debug snapshot
setInterval(() => {
  const counts = runningCounts()
  const queued = Array.from(jobs.values()).filter((j) => j.status === "queued").length
  const done = Array.from(jobs.values()).filter((j) => j.status === "done").length
  const failed = Array.from(jobs.values()).filter((j) => j.status === "failed").length
  appendJsonl(execLogHeartbeat, {
    t: new Date().toISOString(),
    counts: { ...counts, queued, done, failed, total: jobs.size },
  })
}, 15000)

// Continuous learning hook: turn rolling failure summaries into actionable factory_manager tasks.
setInterval(() => {
  if (!learnedPatternsHookEnabled) return
  try {
    const summary = updateLearnedPatternsSummary()
    const top = Array.isArray(summary?.top_reasons) && summary.top_reasons.length ? summary.top_reasons[0] : null
    leader({
      level: "info",
      type: "learned_patterns_tick",
      top_reason: top?.key ?? null,
      top_count: top?.count ?? null,
      total: summary?.window?.total ?? null,
    })
    maybeTriggerFactoryManagerFromLearnedPatterns(summary)
  } catch (e) {
    leader({ level: "warn", type: "learned_patterns_tick_error", error: String(e) })
  }
}, (() => {
  const ms = Number(process.env.LEARNED_PATTERNS_HOOK_TICK_MS ?? "60000")
  return Number.isFinite(ms) && ms > 5000 ? ms : 60000
})())

// Token CFO hook: detect context waste and trigger a factory_manager mitigation task.
setInterval(() => {
  if (!tokenCfoHookEnabled) return
  try {
    const snap = computeTokenCfoSnapshot({ tail: 1500 })
    const top = Array.isArray(snap?.top_wasted_contextpacks) && snap.top_wasted_contextpacks.length ? snap.top_wasted_contextpacks[0] : null
    leader({
      level: "info",
      type: "token_cfo_tick",
      top_unused_ratio: top?.unused_ratio ?? null,
      top_included: top?.included ?? null,
      usage_avg_input: snap?.usage_avgs?.input_tokens ?? null,
      cache_ratio: snap?.usage_avgs?.cache_ratio ?? null,
    })
    maybeTriggerFactoryManagerFromTokenWaste(snap)
  } catch (e) {
    leader({ level: "warn", type: "token_cfo_tick_error", error: String(e) })
  }
}, (() => {
  const ms = Number(process.env.TOKEN_CFO_HOOK_TICK_MS ?? "120000")
  return Number.isFinite(ms) && ms > 5000 ? ms : 120000
})())

// Five Whys hook: when failures.jsonl grows by >=K, generate five_whys report and trigger a mitigation task.
setInterval(async () => {
  if (!fiveWhysHookEnabled) return
  const state = loadFiveWhysHookState()
  const now = Date.now()
  if (Number.isFinite(fiveWhysHookMinMs) && fiveWhysHookMinMs > 0 && now - (state.last_triggered_at ?? 0) < fiveWhysHookMinMs) return
  const failuresCount = countJsonlLines(execLogFailures)
  const prev = Number(state.last_failures_count ?? 0)
  const delta = failuresCount - prev
  if (!Number.isFinite(delta) || delta < fiveWhysHookDeltaThreshold) return

  const run = await runFiveWhysReport()
  leader({
    level: run.ok ? "info" : "warn",
    type: "five_whys_hook_report",
    ok: run.ok,
    code: run.code,
    delta,
    failuresCount,
    stderr: run.ok ? null : String(run.stderr || ""),
  })

  try {
    const reportFile = path.join(execLogDir, "five_whys", "report.json")
    let report = null
    if (fs.existsSync(reportFile)) report = JSON.parse(fs.readFileSync(reportFile, "utf8"))
    const top = Array.isArray(report?.taxonomy_summary) && report.taxonomy_summary.length ? report.taxonomy_summary[0] : null
    const topTax = top?.taxonomy ?? null
    const title = `Five Whys: prevention plan (${topTax ?? "unknown"})`
    const goal = [
      "Role: FACTORY_MANAGER.",
      "Goal: convert Five Whys report into minimal, verifiable, rollback-safe system changes.",
      "Output: JSON {top_taxonomy, root_causes[], actions[], atomic_tasks[]} with replay/CI proof for each action.",
      "",
      "Five Whys report (paths):",
      "- artifacts/executor_logs/five_whys/report.md",
      "- artifacts/executor_logs/five_whys/report.json",
      "",
      "Taxonomy summary:",
      JSON.stringify(report?.taxonomy_summary ?? [], null, 2),
    ].join("\n")
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title,
      goal,
      role: "factory_manager",
      runner: "internal",
      area: "control_plane",
      task_class_id: "five_whys_response_v1",
      allowedExecutors: ["codex"],
      allowedModels: fiveWhysAllowedModels,
      timeoutMs: 900000,
      files: ["artifacts/executor_logs/five_whys/report.json", "artifacts/executor_logs/five_whys/report.md"],
    })
    if (created.ok) {
      const dispatched = dispatchBoardTaskToExecutor(created.task.id)
      if (dispatched.job) {
        dispatched.job.priority = 940
        jobs.set(dispatched.job.id, dispatched.job)
        const running = runningCounts()
        const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
        if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
        else schedule()
      }
      leader({ level: "info", type: "five_whys_hook_task_created", taskId: created.task.id, topTax, delta })
    }
  } catch (e) {
    leader({ level: "warn", type: "five_whys_hook_task_error", error: String(e) })
  }

  saveFiveWhysHookState({ last_triggered_at: now, last_failures_count: failuresCount })
}, (() => {
  const ms = Number(process.env.FIVE_WHYS_HOOK_TICK_MS ?? "180000")
  return Number.isFinite(ms) && ms > 5000 ? ms : 180000
})())

// Instinct Builder: mine failures/state_events into patterns/playbooks/skills drafts (no LLM), then optionally trigger a mitigation task.
setInterval(() => {
  if (!instinctBuilderEnabled) return
  try {
    const snap = updateInstinctArtifacts()
    const top = Array.isArray(snap?.patterns) && snap.patterns.length ? snap.patterns[0] : null
    leader({
      level: "info",
      type: "instinct_builder_tick",
      patterns: snap?.window?.patterns ?? null,
      top_taxonomy: top?.taxonomy ?? null,
      top_count: top?.count ?? null,
    })
    maybeTriggerFactoryManagerFromInstinctSnapshot(snap)
  } catch (e) {
    leader({ level: "warn", type: "instinct_builder_tick_error", error: String(e) })
  }
}, (() => {
  const ms = Number(process.env.INSTINCT_BUILDER_TICK_MS ?? "300000")
  return Number.isFinite(ms) && ms > 5000 ? ms : 300000
})())

// Autopump: apply split results + dispatch ready tasks (no manual monitoring required)
const autoPumpEnabled = String(process.env.AUTO_PUMP ?? "true").toLowerCase() !== "false"
const autoPumpTickMs = Number(process.env.AUTO_PUMP_TICK_MS ?? "20000")
const autoPumpMaxDispatch = Number(process.env.AUTO_PUMP_MAX_DISPATCH ?? "6")
const autoPumpMaxApply = Number(process.env.AUTO_PUMP_MAX_APPLY ?? "4")
const autoFlowEnabled = String(process.env.AUTO_FLOW_CONTROLLER ?? "true").toLowerCase() !== "false"
const autoFlowTickMs = Number(process.env.AUTO_FLOW_CONTROLLER_TICK_MS ?? "20000")
const autoFlowMaxSplit = Number(process.env.AUTO_FLOW_CONTROLLER_MAX_SPLIT ?? "3")
const autoFlowMaxLog = Number(process.env.AUTO_FLOW_CONTROLLER_MAX_LOG ?? "1")
const flowManagerHookEnabled = String(process.env.FLOW_MANAGER_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const flowManagerHookMinMs = Number(process.env.FLOW_MANAGER_HOOK_MIN_MS ?? "120000")
const flowManagerHookTail = Number(process.env.FLOW_MANAGER_HOOK_TAIL ?? "2000")
const flowManagerTaskTimeoutMs = Number(process.env.FLOW_MANAGER_TASK_TIMEOUT_MS ?? "900000")
const feedbackHookEnabled = String(process.env.FEEDBACK_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const feedbackHookMinMs = Number(process.env.FEEDBACK_HOOK_MIN_MS ?? "120000")
const feedbackHookTail = Number(process.env.FEEDBACK_HOOK_TAIL ?? "1200")
const learnedPatternsHookEnabled = String(process.env.LEARNED_PATTERNS_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const learnedPatternsHookTickMs = Number(process.env.LEARNED_PATTERNS_HOOK_TICK_MS ?? "60000")
const learnedPatternsHookMinMs = Number(process.env.LEARNED_PATTERNS_HOOK_MIN_MS ?? "600000")
const learnedPatternsHookDeltaThreshold = Number(process.env.LEARNED_PATTERNS_HOOK_DELTA_THRESHOLD ?? "10")
const learnedPatternsTaskTimeoutMs = Number(process.env.LEARNED_PATTERNS_TASK_TIMEOUT_MS ?? "900000")
const tokenCfoHookEnabled = String(process.env.TOKEN_CFO_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const tokenCfoHookTickMs = Number(process.env.TOKEN_CFO_HOOK_TICK_MS ?? "120000")
const tokenCfoHookMinMs = Number(process.env.TOKEN_CFO_HOOK_MIN_MS ?? "600000")
const tokenCfoUnusedRatio = Number(process.env.TOKEN_CFO_UNUSED_RATIO ?? "0.6")
const tokenCfoIncludedMin = Number(process.env.TOKEN_CFO_INCLUDED_MIN ?? "3")
const tokenCfoTaskTimeoutMs = Number(process.env.TOKEN_CFO_TASK_TIMEOUT_MS ?? "900000")

const fiveWhysHookEnabled = String(process.env.FIVE_WHYS_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const fiveWhysHookTickMs = Number(process.env.FIVE_WHYS_HOOK_TICK_MS ?? "180000")
const fiveWhysHookMinMs = Number(process.env.FIVE_WHYS_HOOK_MIN_MS ?? "900000")
const fiveWhysHookDeltaThreshold = Number(process.env.FIVE_WHYS_HOOK_DELTA_THRESHOLD ?? "6")
const fiveWhysEventsTail = Number(process.env.FIVE_WHYS_EVENTS_TAIL ?? "800")
const fiveWhysFailuresTail = Number(process.env.FIVE_WHYS_FAILURES_TAIL ?? "3000")
const fiveWhysMaxItems = Number(process.env.FIVE_WHYS_MAX_ITEMS ?? "30")
const fiveWhysTimeoutMs = Number(process.env.FIVE_WHYS_TIMEOUT_MS ?? "300000")
const fiveWhysAllowedModels = (process.env.FIVE_WHYS_ALLOWED_MODELS ?? "gpt-5.2")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length)

const radiusAuditHookEnabled = String(process.env.RADIUS_AUDIT_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const radiusAuditHookEveryN = Number(process.env.RADIUS_AUDIT_HOOK_EVERY_N ?? "10")
const radiusAuditHookMinMs = Number(process.env.RADIUS_AUDIT_HOOK_MIN_MS ?? "600000")
const radiusAuditHookRoles = (process.env.RADIUS_AUDIT_HOOK_ROLES ?? "engineer,integrator")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length)
const radiusAuditHookTimeoutMs = Number(process.env.RADIUS_AUDIT_HOOK_TIMEOUT_MS ?? "180000")
const radiusAuditHookStateFile = path.join(execLogDir, "radius_audit_hook_state.json")

const instinctBuilderEnabled = String(process.env.INSTINCT_BUILDER_ENABLED ?? "true").toLowerCase() !== "false"
const instinctBuilderTickMs = Number(process.env.INSTINCT_BUILDER_TICK_MS ?? "300000")
const instinctHookEnabled = String(process.env.INSTINCT_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const instinctHookMinMs = Number(process.env.INSTINCT_HOOK_MIN_MS ?? "1800000")
const instinctHookMinCount = Number(process.env.INSTINCT_HOOK_MIN_COUNT ?? "6")
const instinctHookAllowedModels = (process.env.INSTINCT_HOOK_ALLOWED_MODELS ?? "gpt-5.2")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length)
const instinctHookTimeoutMs = Number(process.env.INSTINCT_HOOK_TIMEOUT_MS ?? "900000")
const ciGateEnabled = String(process.env.CI_GATE_ENABLED ?? "true").toLowerCase() !== "false"
const ciFixupEnabled = String(process.env.CI_FIXUP_ENABLED ?? "true").toLowerCase() !== "false"
const ciFixupMaxPerTask = Number(process.env.CI_FIXUP_MAX_PER_TASK ?? "2")
const ciFixupRole = process.env.CI_FIXUP_ROLE ?? "qa"
const ciFixupAllowedExecutors = (process.env.CI_FIXUP_ALLOWED_EXECUTORS ?? "codex").split(/[;,]/g).map((x) => x.trim()).filter((x) => x.length)
const ciFixupAllowedModels = (process.env.CI_FIXUP_ALLOWED_MODELS ?? "gpt-5.2").split(/[;,]/g).map((x) => x.trim()).filter((x) => x.length)
const ciFixupTimeoutMs = Number(process.env.CI_FIXUP_TIMEOUT_MS ?? "1200000")

const pinsFixupEnabled = String(process.env.PINS_FIXUP_ENABLED ?? "true").toLowerCase() !== "false"
const pinsFixupMaxPerTask = Number(process.env.PINS_FIXUP_MAX_PER_TASK ?? "2")
const pinsFixupRole = process.env.PINS_FIXUP_ROLE ?? "pinser"
const pinsFixupAllowedExecutors = (process.env.PINS_FIXUP_ALLOWED_EXECUTORS ?? "opencodecli").split(/[;,]/g).map((x) => x.trim()).filter((x) => x.length)
const pinsFixupAllowedModels = (process.env.PINS_FIXUP_ALLOWED_MODELS ?? "").split(/[;,]/g).map((x) => x.trim()).filter((x) => x.length)
const pinsFixupTimeoutMs = Number(process.env.PINS_FIXUP_TIMEOUT_MS ?? "900000")

const fixupFuseEnabled = String(process.env.FIXUP_FUSE_ENABLED ?? "true").toLowerCase() !== "false"
const fixupFuseQueueThreshold = Number(process.env.FIXUP_FUSE_QUEUE_THRESHOLD ?? "220")
function fixupFuseTripped() {
  if (!fixupFuseEnabled) return false
  if (!Number.isFinite(fixupFuseQueueThreshold) || fixupFuseQueueThreshold <= 0) return false
  const queued = Array.from(jobs.values()).filter((j) => j.status === "queued").length
  return queued >= fixupFuseQueueThreshold
}
const ciGateStrict = String(process.env.CI_GATE_STRICT ?? "true").toLowerCase() !== "false"
const ciGateAllowAll = String(process.env.CI_GATE_ALLOW_ALL ?? "false").toLowerCase() === "true"
const ciGateTimeoutMs = Number(process.env.CI_GATE_TIMEOUT_MS ?? "1200000")
const ciGateCwd = process.env.CI_GATE_CWD ?? "C:/scc"
const ciEnforceSinceMs = Number(process.env.CI_ENFORCE_SINCE_MS ?? "0")
const ciAntiforgerySinceMs = Number(process.env.CI_ANTIFORGERY_SINCE_MS ?? "0")
const autoDefaultAllowedTests = String(process.env.AUTO_DEFAULT_ALLOWED_TESTS ?? "true").toLowerCase() !== "false"
const autoRecoverEnabled = String(process.env.AUTO_RECOVER_STALE_TASKS ?? "true").toLowerCase() !== "false"
const autoRecoverTickMs = Number(process.env.AUTO_RECOVER_TICK_MS ?? "60000")
const autoRecoverStaleMs = Number(process.env.AUTO_RECOVER_STALE_MS ?? "1800000") // 30 min
const autoRescueEnabled = String(process.env.AUTO_RESCUE ?? "true").toLowerCase() !== "false"
const autoRescueTickMs = Number(process.env.AUTO_RESCUE_TICK_MS ?? "30000")
const autoRescueAttempts = Number(process.env.AUTO_RESCUE_ATTEMPTS ?? "10")

setInterval(() => {
  if (!autoPumpEnabled) return
  try {
    // 1) Apply parent splits once their split job is done
    let applied = 0
    for (const t of listBoardTasks()) {
      if (applied >= autoPumpMaxApply) break
      if (t.kind !== "parent") continue
      if (t.status !== "in_progress") continue
      const jobId = t.splitJobId ?? t.lastJobId
      if (!jobId) continue
      const j = jobs.get(jobId)
      if (!j || j.status !== "done") continue
      const out = applySplitFromJob({ parentId: t.id, jobId })
      if (!out.ok) {
        leader({ level: "warn", type: "autopump_split_apply_failed", id: t.id, jobId, error: out.error })
        continue
      }
      applied += 1
      leader({ level: "info", type: "autopump_split_applied", id: t.id, jobId, created: out.created.length })
    }

    // 2) Dispatch atomic tasks that are ready/backlog, bounded per tick
    let dispatched = 0
    const now = Date.now()
    for (const t of listBoardTasks()) {
      if (dispatched >= autoPumpMaxDispatch) break
      if (t.kind !== "atomic") continue
      if (t.status !== "ready" && t.status !== "backlog") continue
      if (t.cooldownUntil && now < t.cooldownUntil) continue
      const out = dispatchBoardTaskToExecutor(t.id)
      if (!out.ok) continue
      dispatched += 1
    }
  } catch (e) {
    leader({ level: "warn", type: "autopump_error", error: String(e) })
  }
}, Number.isFinite(autoPumpTickMs) ? Math.max(5000, autoPumpTickMs) : 20000)

// Auto flow controller: ensure parents split + surface bottlenecks
setInterval(() => {
  if (!autoFlowEnabled) return
  try {
    let started = 0
    for (const t of listBoardTasks()) {
      if (started >= autoFlowMaxSplit) break
      if (t.kind !== "parent") continue
      if (t.status !== "needs_split") continue
      const out = startSplitForParent(t, { reason: "auto_flow_controller" })
      if (out.ok) started += 1
    }

    if (autoFlowMaxLog > 0) {
      const tasks = listBoardTasks()
      const parentNeedsSplit = tasks.filter((t) => t.kind === "parent" && t.status === "needs_split").length
      const now = Date.now()
      const atomicReady = tasks.filter((t) => {
        if (t.kind !== "atomic") return false
        if (t.status !== "ready" && t.status !== "backlog") return false
        if (t.cooldownUntil && now < t.cooldownUntil) return false
        return true
      }).length
      const running = runningCounts()
      const runningTotal = running.codex + running.opencodecli
      const queued = Array.from(jobs.values()).filter((j) => j.status === "queued").length
      const maxTotal = codexMax + occliMax
      const reasons = []
      if (parentNeedsSplit > 0 && started === 0) reasons.push("parents_need_split")
      if (atomicReady > 0 && runningTotal >= maxTotal) reasons.push("executor_capacity_full")
      if (queued > Math.max(20, autoPumpMaxDispatch * 4)) reasons.push("job_queue_backlog")
      if (reasons.length) {
        const event = {
          level: "warn",
          type: "flow_bottleneck",
          reasons,
          parentNeedsSplit,
          atomicReady,
          queued,
          running,
          max: { codex: codexMax, opencodecli: occliMax },
        }
        leader(event)
        maybeTriggerFlowManagerTask(event)
      }
    }
  } catch (e) {
    leader({ level: "warn", type: "auto_flow_controller_error", error: String(e) })
  }
}, Number.isFinite(autoFlowTickMs) ? Math.max(5000, autoFlowTickMs) : 20000)

// Auto-recover stale board tasks (no active job)
setInterval(() => {
  if (!autoRecoverEnabled) return
  const now = Date.now()
  for (const t of listBoardTasks()) {
    if (t.kind === "atomic" && t.status === "in_progress") {
      const job = t.lastJobId ? jobs.get(t.lastJobId) : null
      const age = now - (t.updatedAt ?? t.createdAt ?? now)
      if (!job && age >= autoRecoverStaleMs) {
        t.status = "ready"
        t.updatedAt = now
        t.lastJobStatus = "stale"
        t.lastJobReason = "job_missing"
        putBoardTask(t)
        leader({ level: "warn", type: "board_task_recovered", id: t.id, reason: "job_missing" })
      } else if (job && (job.status === "done" || job.status === "failed")) {
        updateBoardFromJob(job)
      }
    }
    if (t.kind === "parent" && t.status === "in_progress") {
      const job = t.splitJobId ? jobs.get(t.splitJobId) : t.lastJobId ? jobs.get(t.lastJobId) : null
      const age = now - (t.updatedAt ?? t.createdAt ?? now)
      if (!job && age >= autoRecoverStaleMs) {
        t.status = "needs_split"
        t.updatedAt = now
        putBoardTask(t)
        leader({ level: "warn", type: "parent_recovered", id: t.id, reason: "job_missing" })
      }
    }
  }
}, Number.isFinite(autoRecoverTickMs) ? Math.max(10000, autoRecoverTickMs) : 60000)

// Autorescue: if an external board job flaps (attempts too high), cancel and retry internally
setInterval(() => {
  if (!autoRescueEnabled) return
  if (!Number.isFinite(autoRescueAttempts) || autoRescueAttempts <= 0) return
  try {
    const now = Date.now()
    for (const t of listBoardTasks()) {
      if (t.kind !== "atomic") continue
      if (t.status !== "in_progress") continue
      const jobId = t.lastJobId
      if (!jobId) continue
      const j = jobs.get(jobId)
      if (!j) continue
      if (j.runner !== "external") continue
      if (j.status !== "running") continue
      const attempts = j.attempts ?? 0
      if (attempts < autoRescueAttempts) continue

      cancelExternalJob({ id: j.id, reason: "auto_rescue_attempts" })
      const cur = getBoardTask(t.id)
      if (!cur) continue
      cur.status = "ready"
      cur.runner = "internal"
      cur.updatedAt = now
      putBoardTask(cur)
      leader({ level: "warn", type: "autorescue_triggered", taskId: cur.id, jobId: j.id, attempts })
    }
  } catch (e) {
    leader({ level: "warn", type: "autorescue_error", error: String(e) })
  }
}, Number.isFinite(autoRescueTickMs) ? Math.max(5000, autoRescueTickMs) : 30000)

// Leader alerts: long-running jobs + failure bursts
let lastUnderutilizedAt = 0
setInterval(() => {
  const now = Date.now()
  const running = Array.from(jobs.values()).filter((j) => j.status === "running")
  for (const j of running) {
    const started = j.startedAt ?? j.createdAt
    const age = now - started
    const limit = j.executor === "opencodecli" ? warnOcLongMs : warnLongMs
    if (age < limit) continue
    if (j.warned_long) continue
    j.warned_long = true
    jobs.set(j.id, j)
    saveState()
    leader({
      level: "warn",
      type: "job_long_running",
      id: j.id,
      executor: j.executor,
      model: j.model,
      ageMs: age,
      promptPreview: String(j.prompt || "").slice(0, 140),
    })
  }

  // Underutilization alert: if we have queued jobs but low running, nudge the leader to scale workers.
  const counts = runningCounts()
  const runningTotal = counts.codex + counts.opencodecli
  const queued = Array.from(jobs.values()).filter((j) => j.status === "queued").length
  if (queued > 0 && runningTotal < 4 && now - lastUnderutilizedAt > 60_000) {
    lastUnderutilizedAt = now
    leader({ level: "warn", type: "underutilized", running: runningTotal, queued, hint: "start ensure-workers.ps1 or add workers" })
  }

  const failures = (() => {
    try {
      const raw = fs.readFileSync(execLogFailures, "utf8")
      return raw
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l.length > 0)
        .map((l) => {
          try {
            return JSON.parse(l)
          } catch {
            return null
          }
        })
        .filter(Boolean)
    } catch {
      return []
    }
  })()

  const recent = failures.filter((f) => {
    const t = Date.parse(f.t || "")
    return Number.isFinite(t) && now - t <= warnFailWindowMs
  })

  if (recent.length >= warnFailBurstN) {
    const byReason = {}
    for (const f of recent) {
      const k = f.reason || "unknown"
      byReason[k] = (byReason[k] || 0) + 1
    }
    leader({
      level: "warn",
      type: "failure_burst",
      windowMs: warnFailWindowMs,
      count: recent.length,
      byReason,
    })
  }
}, 15000)

// Restore jobs after restart: requeue previously running jobs (best-effort).
for (const j of loadState()) {
  if (!j?.id) continue
  const status = j.status === "running" ? "queued" : j.status
  jobs.set(j.id, { ...j, status, startedAt: status === "queued" ? null : j.startedAt, finishedAt: j.finishedAt })
}
schedule()

for (const t of loadBoard()) {
  if (!t?.id) continue
  boardTasks.set(t.id, t)
}

// ---------------- External worker pool (optional) ----------------
const workers = new Map()
const newWorkerId = () => crypto.randomUUID()

function listWorkers() {
  return Array.from(workers.values())
}

function getWorker(id) {
  return workers.get(id) ?? null
}

function putWorker(w) {
  workers.set(w.id, w)
}

function claimNextJob({ executor, worker }) {
  const supported = Array.isArray(worker?.models) ? worker.models.map((x) => String(x)) : null
  const canRunModel = (model) => {
    if (!supported || supported.length === 0) return true
    return supported.includes(String(model))
  }
  const queued = Array.from(jobs.values())
    .filter((j) => j.status === "queued" && j.runner === "external" && j.executor === executor)
    .filter((j) => canRunModel(j.model))
    .sort((a, b) => (a.createdAt ?? 0) - (b.createdAt ?? 0))
  return queued[0] ?? null
}

function buildInjectedPrompt(job) {
  const prefixParts = []
  if (job.contextPackId) {
    const ctxText = getContextPack(job.contextPackId)
    if (ctxText) prefixParts.push(`<context_pack id="${job.contextPackId}">\n${ctxText}\n</context_pack>\n`)
  }
  if (job.threadId) {
    const t = getThread(job.threadId)
    const history = Array.isArray(t?.history) ? t.history : []
    if (history.length) {
      const last = history.slice(-6).map((x) => `- ${x}`).join("\n")
      prefixParts.push(`<thread id="${job.threadId}">\nRecent decisions:\n${last}\n</thread>\n`)
    }
  }
  const base = prefixParts.length ? prefixParts.join("\n") + "\n" + job.prompt : job.prompt
  const ciHandbookText = getCiHandbookText()
  return ciHandbookText ? `${base}\n\n${ciHandbookText}` : base
}

setInterval(() => {
  const now = Date.now()
  for (const j of jobs.values()) {
    if (j.status !== "running") continue
    if (j.runner !== "external") continue
    const leaseUntil = typeof j.leaseUntil === "number" ? j.leaseUntil : null
    if (!leaseUntil || leaseUntil > now) continue
    const w = j.workerId ? getWorker(j.workerId) : null
    if (w && w.runningJobId === j.id) {
      w.runningJobId = null
      w.lastSeen = now
      putWorker(w)
    }
    j.status = "queued"
    j.workerId = null
    j.leaseUntil = null
    j.startedAt = null
    jobs.set(j.id, j)
    saveState()
    leader({ level: "warn", type: "job_lease_expired", id: j.id, executor: j.executor })
  }
}, 10_000)

async function fetchOk(url) {
  try {
    const r = await fetch(url, { method: "GET" })
    return r.ok
  } catch {
    return false
  }
}

async function statusSnapshot() {
  const [sccReady, sccMcp, ocReady] = await Promise.all([
    fetchOk(new URL("/health/ready", sccUpstream)),
    fetchOk(new URL("/mcp/health", sccUpstream)),
    fetchOk(new URL("/global/health", opencodeUpstream)),
  ])
  return {
    gateway: { ok: true, port: gatewayPort, features },
    scc: {
      upstream: sccUpstream.toString().replace(/\/$/, ""),
      healthReady: sccReady,
      mcpHealth: sccMcp,
      enabled: features.exposeScc,
    },
    opencode: {
      upstream: opencodeUpstream.toString().replace(/\/$/, ""),
      globalHealth: ocReady,
      basePath: "/opencode",
      enabled: features.exposeOpenCode,
    },
  }
}

function renderHomeHtml(snapshot) {
  const esc = (s) => String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  const badge = (ok) =>
    ok
      ? `<span style="color:#0a0">OK</span>`
      : `<span style="color:#a00">DOWN</span>`
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>oc-scc-local</title>
    <style>
      body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:24px;line-height:1.4}
      code{background:#f3f3f3;padding:2px 6px;border-radius:6px}
      .row{margin:10px 0}
      .card{border:1px solid #ddd;border-radius:12px;padding:14px;margin:12px 0}
      a{color:#06c;text-decoration:none}
      a:hover{text-decoration:underline}
    </style>
  </head>
  <body>
    <h1>oc-scc-local</h1>
    <div class="row">缁熶竴鍏ュ彛锛?code>http://127.0.0.1:${esc(snapshot.gateway.port)}</code></div>

    <div class="card">
      <h2>SCC</h2>
      <div>Upstream: <code>${esc(snapshot.scc.upstream)}</code></div>
      <div>health/ready: ${badge(snapshot.scc.healthReady)}</div>
      <div>mcp/health: ${badge(snapshot.scc.mcpHealth)}</div>
      <div class="row">
        <a href="/desktop">/desktop</a> 路
        <a href="/scc">/scc</a> 路
        <a href="/dashboard">/dashboard</a> 路
        <a href="/viewer">/viewer</a> 路
        <a href="/mcp/health">/mcp/health</a>
      </div>
    </div>

    <div class="card">
      <h2>OpenCode</h2>
      <div>Upstream: <code>${esc(snapshot.opencode.upstream)}</code></div>
      <div>global/health: ${badge(snapshot.opencode.globalHealth)}</div>
      <div class="row">
        <a href="/opencode/global/health">/opencode/global/health</a> 路
        <a href="/opencode/doc">/opencode/doc</a> 路
        <a href="/opencode/mcp">/opencode/mcp</a>
      </div>
    </div>

    <div class="card">
      <h2>API</h2>
      <div><a href="/status">/status</a></div>
      <div><a href="/health">/health</a></div>
      <div><a href="/nav">/nav</a></div>
      <div><a href="/docs">/docs</a></div>
      <div><a href="/executor/leader">/executor/leader</a></div>
    </div>
  </body>
</html>`
}

function safeReadDoc(requestPath) {
  const rel = requestPath.replace(/^\/docs\/?/, "")
  const target = rel.length === 0 ? "README.md" : rel
  const norm = path.resolve(docsRoot, target)
  const root = path.resolve(docsRoot)
  if (!norm.toLowerCase().startsWith(root.toLowerCase())) return null
  const ext = path.extname(norm).toLowerCase()
  if (ext !== ".md" && ext !== ".txt") return null
  if (!fs.existsSync(norm)) return null
  try {
    return { file: norm, content: fs.readFileSync(norm, "utf8") }
  } catch {
    return null
  }
}

function poolSnapshot() {
  const board = listBoardTasks()
  const byBoardStatus = {}
  for (const t of board) {
    const s = t.status ?? "unknown"
    byBoardStatus[s] = (byBoardStatus[s] || 0) + 1
  }

  const exWorkers = listWorkers()
  const byExecutorWorker = {}
  for (const w of exWorkers) {
    const ex = Array.isArray(w.executors) ? w.executors.join(",") : "unknown"
    byExecutorWorker[ex] = (byExecutorWorker[ex] || 0) + 1
  }
  const now = Date.now()
  const activeWindowMs = Number(process.env.WORKER_ACTIVE_WINDOW_MS ?? "120000")
  const active = exWorkers.filter((w) => typeof w.lastSeen === "number" && now - w.lastSeen <= activeWindowMs)
  const byExecutorWorkerActive = {}
  for (const w of active) {
    const ex = Array.isArray(w.executors) ? w.executors.join(",") : "unknown"
    byExecutorWorkerActive[ex] = (byExecutorWorkerActive[ex] || 0) + 1
  }

  const jobArr = Array.from(jobs.values())
  const byJobStatus = {}
  for (const j of jobArr) {
    const s = j.status ?? "unknown"
    byJobStatus[s] = (byJobStatus[s] || 0) + 1
  }

  const logs = {
    execLogDir,
    leader: execLeaderLog,
    jobs: execLogJobs,
    failures: execLogFailures,
    heartbeat: execLogHeartbeat,
    state: execStateFile,
    boardDir,
    boardFile,
  }

  return {
    taskPool: {
      boardFile,
      total: board.length,
      byStatus: byBoardStatus,
    },
    executorPool: {
      workers: exWorkers.length,
      activeWindowMs,
      activeWorkers: active.length,
      byExecutors: byExecutorWorker,
      byExecutorsActive: byExecutorWorkerActive,
      desiredRatio: { codex: desiredRatioCodex, opencodecli: desiredRatioOccli },
      externalMax: { codex: externalMaxCodex, opencodecli: externalMaxOccli },
    },
    modelPool: {
      free: modelsFree,
      vision: modelsVision,
      paid: modelsPaid,
      requiredDesignerModel: STRICT_DESIGNER_MODEL,
    },
    rolePool: {
      roles: ROLE_NAMES,
      strictDesignerSplitModel: STRICT_DESIGNER_MODEL,
    },
    skillsPool: {
      configFile: roleConfigFile,
      note: "Role rules can be overridden via config/roles.json; per-skill packs not yet enforced at runtime.",
    },
    logsPool: logs,
    reportsPool: {
      docsRoot,
      urls: {
        docs: "/docs",
        status: "/docs/STATUS.md",
        worklog: "/docs/WORKLOG.md",
        mission: "/docs/MISSION.md",
        navigation: "/docs/NAVIGATION.md",
        missionTable: "/artifacts/taskboard/mission_fusion_table.json (file)",
      },
    },
    jobs: {
      total: jobArr.length,
      byStatus: byJobStatus,
      queuedExternal: jobArr.filter((j) => j.status === "queued" && j.runner === "external").length,
      runningExternal: jobArr.filter((j) => j.status === "running" && j.runner === "external").length,
    },
  }
}

function proxyTo(req, res, upstream, newPathname, { rewriteCookiePathPrefix } = {}) {
  const base = upstream.toString().replace(/\/$/, "")
  const target = new URL(base)

  const url = new URL(req.url ?? "/", "http://gateway.local")
  const outgoingPath = newPathname + url.search

  // http-proxy will forward req.url to upstream; set it before proxying.
  req.url = outgoingPath

  proxy.web(
    req,
    res,
    {
      target: target.toString(),
      selfHandleResponse: false,
      headers: {
        ...req.headers,
        host: target.host,
      },
      prependPath: false,
    },
    (err) => {
      sendJson(res, 502, { error: "proxy_failed", message: String(err?.message ?? err) })
    },
  )

  // http-proxy emits 'proxyRes' globally; do per-request header rewrites there.
  // (see handler below)
  res.__ocCookiePrefix = rewriteCookiePathPrefix
}

proxy.on("proxyRes", (proxyRes, req, res) => {
  const cookiePrefix = res.__ocCookiePrefix
  if (!cookiePrefix) return

  const location = proxyRes.headers.location
  if (typeof location === "string" && location.startsWith("/")) {
    proxyRes.headers.location = `${cookiePrefix}${location}`
  }

  const setCookie = proxyRes.headers["set-cookie"]
  if (Array.isArray(setCookie)) {
    proxyRes.headers["set-cookie"] = setCookie.map((v) =>
      v.replace(/;\s*Path=\/(?=;|$)/i, `; Path=${cookiePrefix}`),
    )
  } else if (typeof setCookie === "string") {
    proxyRes.headers["set-cookie"] = setCookie.replace(/;\s*Path=\/(?=;|$)/i, `; Path=${cookiePrefix}`)
  }
})

const server = http.createServer(async (req, res) => {
  const method = req.method ?? "GET"
  const url = new URL(req.url ?? "/", "http://gateway.local")
  const pathname = url.pathname

  if (pathname === "/health") {
    return sendJson(res, 200, { ok: true })
  }

  if (pathname === "/status") {
    const snapshot = await statusSnapshot()
    return sendJson(res, 200, snapshot)
  }

  if (pathname === "/" && method === "GET") {
    const snapshot = await statusSnapshot()
    const html = renderHomeHtml(snapshot)
    res.statusCode = 200
    res.setHeader("content-type", "text/html; charset=utf-8")
    res.end(html)
    return
  }

  if (pathname === "/favicon.ico") {
    return sendText(res, 204, "")
  }

  if (pathname === "/nav" && method === "GET") {
    return sendJson(res, 200, {
      base: `http://127.0.0.1:${gatewayPort}`,
      scc: SCC_PREFIXES,
      opencode: "/opencode/*",
      docs: "/docs/*",
      board: "/board/*",
      pools: "/pools",
      config: {
        schema: "/config/schema",
        get: "/config",
        set: "/config/set",
      },
      models: {
        list: "/models",
        set: "/models/set",
      },
      designer: {
        state: "/designer/state",
        freeze: "/designer/freeze",
        context_pack: "/designer/context_pack",
      },
      map: "/map",
      axioms: "/axioms",
      task_classes: "/task_classes",
      pins_templates: "/pins/templates",
      pins_candidates: "/pins/candidates",
      events: "/events",
      learned_patterns: {
        list: "/learned_patterns",
        summary: "/learned_patterns/summary",
      },
      instinct: {
        patterns: "/instinct/patterns",
        schemas: "/instinct/schemas",
        playbooks: "/instinct/playbooks",
        skills_draft: "/instinct/skills_draft",
      },
      replay: {
        task: "/replay/task?task_id=...",
      },
      executor: {
        atomic: "/executor/jobs/atomic",
        jobs: "/executor/jobs",
        leader: "/executor/leader",
        failures: "/executor/debug/failures",
        summary: "/executor/debug/summary",
        workers: "/executor/workers",
      },
    })
  }

  if (pathname === "/pools" && method === "GET") {
    return sendJson(res, 200, poolSnapshot())
  }

  if (pathname === "/config/schema" && method === "GET") {
    return sendJson(res, 200, {
      runtimeEnvFile,
      registry: configRegistry,
      note: "POST /config/set writes config/runtime.env (requires daemon restart to take effect).",
    })
  }

  if (pathname === "/config" && method === "GET") {
    const runtime = readRuntimeEnv()
    const live = {
      GATEWAY_PORT: gatewayPort,
      SCC_UPSTREAM: sccUpstream.toString(),
      OPENCODE_UPSTREAM: opencodeUpstream.toString(),
      EXEC_CONCURRENCY_CODEX: codexMax,
      EXEC_CONCURRENCY_OPENCODE: occliMax,
      EXTERNAL_MAX_CODEX: externalMaxCodex,
      EXTERNAL_MAX_OPENCODECLI: externalMaxOccli,
      DESIRED_RATIO_CODEX: desiredRatioCodex,
      DESIRED_RATIO_OPENCODECLI: desiredRatioOccli,
      EXEC_TIMEOUT_CODEX_MS: timeoutCodexMs,
      EXEC_TIMEOUT_OPENCODE_MS: timeoutOccliMs,
      MODEL_POOL_FREE: modelsFree.join(","),
      MODEL_POOL_VISION: modelsVision.join(","),
      OPENCODE_MODEL: occliModelDefault,
      AUTO_ASSIGN_OPENCODE_MODELS: autoAssignOccliModels,
    }

    return sendJson(res, 200, {
      runtime,
      live,
      restartHint: {
        daemonStart: "C:/scc/oc-scc-local/scripts/daemon-start.ps1",
        daemonStop: "C:/scc/oc-scc-local/scripts/daemon-stop.ps1",
        note: "Changes in runtime.env apply on next daemon restart.",
      },
    })
  }

  if (pathname === "/models" && method === "GET") {
    return sendJson(res, 200, {
      free: modelsFree,
      vision: modelsVision,
      opencodeDefault: occliModelDefault,
      note: "POST /models/set { free:[], vision:[], opencodeDefault:\"opencode/model\" } to update in-memory + runtime.env",
    })
  }

    if (pathname === "/models/set" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }

      const free = Array.isArray(payload?.free) ? payload.free.map((x) => String(x).trim()).filter(Boolean) : null
      const vision = Array.isArray(payload?.vision) ? payload.vision.map((x) => String(x).trim()).filter(Boolean) : null
      const opDefault = payload?.opencodeDefault ? String(payload.opencodeDefault).trim() : null

      if (free && !free.length) return sendJson(res, 400, { error: "free_empty" })
      if (vision && !vision.length) return sendJson(res, 400, { error: "vision_empty" })

      updateModelPools({ free, vision, occliDefault: opDefault })

      // persist to runtime.env for next restart
      const current = readRuntimeEnv()
      const next = { ...(current.values ?? {}) }
      next.MODEL_POOL_FREE = modelsFree.join(",")
      next.MODEL_POOL_VISION = modelsVision.join(",")
      next.OPENCODE_MODEL = occliModelDefault
      writeRuntimeEnv(next)

      leader({
        level: "info",
        type: "models_updated",
        free: modelsFree,
        vision: modelsVision,
        opencodeDefault: occliModelDefault,
      })

      return sendJson(res, 200, {
        ok: true,
        free: modelsFree,
        vision: modelsVision,
        opencodeDefault: occliModelDefault,
        persisted: runtimeEnvFile,
        restartRequired: false,
      })
    })
    return
  }

  if (pathname === "/designer/state" && method === "GET") {
    const state = loadDesignerState()
    if (!state) return sendJson(res, 500, { error: "state_load_failed" })
    return sendJson(res, 200, state)
  }

  if (pathname === "/designer/state" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const state = loadDesignerState()
      if (!state) return sendJson(res, 500, { error: "state_load_failed" })
      const layer = String(payload?.layer ?? "").toLowerCase()
      const mode = String(payload?.mode ?? "merge").toLowerCase()
      const patch = payload?.patch && typeof payload.patch === "object" ? payload.patch : null
      if (!["l0", "l1", "l2"].includes(layer) || !patch) return sendJson(res, 400, { error: "bad_payload" })
      if (mode === "replace") state[layer] = patch
      else state[layer] = { ...(state[layer] ?? {}), ...patch }
      saveDesignerState(state)
      leader({ level: "info", type: "designer_state_updated", layer, mode })
      return sendJson(res, 200, state)
    })
    return
  }

  if (pathname === "/designer/freeze" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const state = loadDesignerState()
      if (!state) return sendJson(res, 500, { error: "state_load_failed" })
      const record = {
        t: new Date().toISOString(),
        pins: payload?.pins ?? state.l2?.draft_pins ?? null,
        assumptions: payload?.assumptions ?? state.l2?.draft_assumptions ?? [],
        task_class_candidate: payload?.task_class_candidate ?? state.l2?.draft_task_class ?? null,
        area: payload?.area ?? null,
        confidence: payload?.confidence ?? null,
        contract: payload?.contract ?? null,
      }
      state.history = Array.isArray(state.history) ? state.history : []
      state.history.push(record)
      if (state.history.length > 200) state.history.shift()
      state.l2 = { current_task: null, draft_pins: null, draft_assumptions: [], draft_task_class: null }
      saveDesignerState(state)
      leader({ level: "info", type: "designer_freeze", area: record.area, task_class_candidate: record.task_class_candidate })
      return sendJson(res, 200, { ok: true, record })
    })
    return
  }

  if (pathname === "/config/set" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }

      const allowedKeys = new Set(configRegistry.map((x) => x.key))
      const incoming = payload?.values && typeof payload.values === "object" ? payload.values : payload
      const updates = {}
      for (const [k0, v0] of Object.entries(incoming || {})) {
        const k = String(k0)
        if (!allowedKeys.has(k)) continue
        updates[k] = v0
      }

      const current = readRuntimeEnv()
      const next = { ...(current.values ?? {}) }

      const typeByKey = Object.fromEntries(configRegistry.map((x) => [x.key, x.type]))
      const errors = []
      for (const [k, v] of Object.entries(updates)) {
        const t = typeByKey[k] ?? "string"
        if (v == null) {
          delete next[k]
          continue
        }
        if (t === "number") {
          const n = Number(v)
          if (!Number.isFinite(n)) {
            errors.push({ key: k, error: "not_a_number" })
            continue
          }
          next[k] = String(n)
          continue
        }
        if (t === "bool") {
          const s = String(v).toLowerCase()
          if (!["true", "false", "1", "0"].includes(s)) {
            errors.push({ key: k, error: "not_a_bool" })
            continue
          }
          next[k] = s === "1" ? "true" : s === "0" ? "false" : s
          continue
        }
        next[k] = String(v)
      }

      if (errors.length) {
        leader({ level: "warn", type: "config_set_rejected", errors })
        return sendJson(res, 400, { error: "validation_failed", errors })
      }

      writeRuntimeEnv(next)
      leader({ level: "info", type: "config_set", keys: Object.keys(updates).sort() })
      return sendJson(res, 200, { ok: true, runtimeEnvFile, values: next, restartRequired: true })
    })
    return
  }

  if (pathname === "/docs" || pathname.startsWith("/docs/")) {
    const doc = safeReadDoc(pathname)
    if (!doc) return sendJson(res, 404, { error: "not_found" })
    res.statusCode = 200
    res.setHeader("content-type", "text/markdown; charset=utf-8")
    res.end(doc.content)
    return
  }

  if (pathname === "/map" && method === "GET") {
    const doc = readDocFile("NAVIGATION.md")
    if (!doc) return sendJson(res, 404, { error: "nav_missing" })
    const jsonText = extractJsonBlock(doc.text, "PROJECT_MAP_JSON")
    if (!jsonText) return sendJson(res, 404, { error: "map_block_missing", file: doc.file })
    try {
      const data = JSON.parse(jsonText)
      return sendJson(res, 200, { file: doc.file, data })
    } catch (e) {
      return sendJson(res, 400, { error: "map_json_invalid", message: String(e), file: doc.file })
    }
  }

  if (pathname === "/map" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const doc = readDocFile("NAVIGATION.md")
      if (!doc) return sendJson(res, 404, { error: "nav_missing" })
      const nextText = upsertJsonBlock(doc.text, "PROJECT_MAP_JSON", payload)
      try {
        fs.writeFileSync(doc.file, nextText, "utf8")
      } catch (e) {
        return sendJson(res, 500, { error: "map_write_failed", message: String(e) })
      }
      leader({ level: "info", type: "map_updated", file: doc.file })
      return sendJson(res, 200, { ok: true, file: doc.file })
    })
    return
  }

  if (pathname === "/axioms" && method === "GET") {
    const doc = readDocFile("AI_CONTEXT.md")
    if (!doc) return sendJson(res, 404, { error: "ai_context_missing" })
    const jsonText = extractJsonBlock(doc.text, "SSOT_AXIOMS_JSON")
    if (!jsonText) return sendJson(res, 404, { error: "axioms_block_missing", file: doc.file })
    try {
      const data = JSON.parse(jsonText)
      return sendJson(res, 200, { file: doc.file, data })
    } catch (e) {
      return sendJson(res, 400, { error: "axioms_json_invalid", message: String(e), file: doc.file })
    }
  }

  if (pathname === "/axioms" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const doc = readDocFile("AI_CONTEXT.md")
      if (!doc) return sendJson(res, 404, { error: "ai_context_missing" })
      const nextText = upsertJsonBlock(doc.text, "SSOT_AXIOMS_JSON", payload)
      try {
        fs.writeFileSync(doc.file, nextText, "utf8")
      } catch (e) {
        return sendJson(res, 500, { error: "axioms_write_failed", message: String(e) })
      }
      leader({ level: "info", type: "axioms_updated", file: doc.file })
      return sendJson(res, 200, { ok: true, file: doc.file })
    })
    return
  }

  if (pathname === "/task_classes" && method === "GET") {
    const out = readDocJsonBlock("AI_CONTEXT.md", "TASK_CLASS_LIBRARY_JSON", defaultTaskClassLibrary)
    if (!out.ok) return sendJson(res, out.error === "doc_missing" ? 404 : 400, { error: out.error, file: out.file, message: out.message })
    return sendJson(res, 200, { file: out.file, data: out.data, missing: out.missing === true })
  }

  if (pathname === "/task_classes" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const doc = readDocFile("AI_CONTEXT.md")
      if (!doc) return sendJson(res, 404, { error: "ai_context_missing" })
      const normalized = {
        version: String(payload?.version ?? "v1"),
        classes: Array.isArray(payload?.classes) ? payload.classes : [],
      }
      const nextText = upsertJsonBlock(doc.text, "TASK_CLASS_LIBRARY_JSON", normalized)
      try {
        fs.writeFileSync(doc.file, nextText, "utf8")
      } catch (e) {
        return sendJson(res, 500, { error: "task_class_write_failed", message: String(e) })
      }
      leader({ level: "info", type: "task_class_updated", file: doc.file, count: normalized.classes.length })
      return sendJson(res, 200, { ok: true, file: doc.file, count: normalized.classes.length })
    })
    return
  }

  if (pathname === "/pins/templates" && method === "GET") {
    const out = readDocJsonBlock("AI_CONTEXT.md", "PINS_TEMPLATES_JSON", defaultPinsTemplates)
    if (!out.ok) return sendJson(res, out.error === "doc_missing" ? 404 : 400, { error: out.error, file: out.file, message: out.message })
    return sendJson(res, 200, { file: out.file, data: out.data, missing: out.missing === true })
  }

  if (pathname === "/pins/templates" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const doc = readDocFile("AI_CONTEXT.md")
      if (!doc) return sendJson(res, 404, { error: "ai_context_missing" })
      const normalized = {
        version: String(payload?.version ?? "v1"),
        templates: Array.isArray(payload?.templates) ? payload.templates : [],
      }
      const nextText = upsertJsonBlock(doc.text, "PINS_TEMPLATES_JSON", normalized)
      try {
        fs.writeFileSync(doc.file, nextText, "utf8")
      } catch (e) {
        return sendJson(res, 500, { error: "pins_template_write_failed", message: String(e) })
      }
      leader({ level: "info", type: "pins_templates_updated", file: doc.file, count: normalized.templates.length })
      return sendJson(res, 200, { ok: true, file: doc.file, count: normalized.templates.length })
    })
    return
  }

  if (pathname === "/pins/guide/errors" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const rows = readJsonlTail(pinsGuideErrorsFile, Number.isFinite(limit) ? limit : 50)
    return sendJson(res, 200, { file: pinsGuideErrorsFile, count: rows.length, rows })
  }

  if (pathname === "/errors/designer" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const rows = readJsonlTail(designerFailuresFile, Number.isFinite(limit) ? limit : 50)
    return sendJson(res, 200, { file: designerFailuresFile, count: rows.length, rows })
  }
  if (pathname === "/errors/executor" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const rows = readJsonlTail(executorFailuresFile, Number.isFinite(limit) ? limit : 50)
    return sendJson(res, 200, { file: executorFailuresFile, count: rows.length, rows })
  }
  if (pathname === "/errors/router" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const rows = readJsonlTail(routerFailuresFile, Number.isFinite(limit) ? limit : 50)
    return sendJson(res, 200, { file: routerFailuresFile, count: rows.length, rows })
  }
  if (pathname === "/errors/verifier" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const rows = readJsonlTail(verifierFailuresFile, Number.isFinite(limit) ? limit : 50)
    return sendJson(res, 200, { file: verifierFailuresFile, count: rows.length, rows })
  }
  if (pathname === "/routes/decisions" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const rows = readJsonlTail(routeDecisionsFile, Number.isFinite(limit) ? limit : 50)
    return sendJson(res, 200, { file: routeDecisionsFile, count: rows.length, rows })
  }
  if (pathname === "/learned_patterns" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "100")
    const rows = readJsonlTail(learnedPatternsFile, Number.isFinite(limit) ? limit : 100)
    return sendJson(res, 200, { file: learnedPatternsFile, count: rows.length, rows })
  }
  if (pathname === "/learned_patterns/summary" && method === "GET") {
    try {
      if (fs.existsSync(learnedPatternsSummaryFile)) {
        const raw = fs.readFileSync(learnedPatternsSummaryFile, "utf8")
        return sendJson(res, 200, { file: learnedPatternsSummaryFile, summary: JSON.parse(raw) })
      }
    } catch {
      // fall through
    }
    const summary = updateLearnedPatternsSummary()
    return sendJson(res, 200, { file: learnedPatternsSummaryFile, summary })
  }

  if (pathname === "/instinct/patterns" && method === "GET") {
    try {
      if (fs.existsSync(instinctPatternsFile)) {
        const raw = fs.readFileSync(instinctPatternsFile, "utf8")
        return sendJson(res, 200, { file: instinctPatternsFile, patterns: JSON.parse(raw) })
      }
    } catch {
      // fall through
    }
    const snap = updateInstinctArtifacts()
    return sendJson(res, 200, { file: instinctPatternsFile, patterns: snap })
  }

  if (pathname === "/instinct/schemas" && method === "GET") {
    try {
      if (fs.existsSync(instinctSchemasFile)) {
        return sendText(res, 200, fs.readFileSync(instinctSchemasFile, "utf8"))
      }
    } catch {
      // fall through
    }
    const text = renderInstinctSchemasYaml() + "\n"
    try {
      ensureDir(instinctDir)
      fs.writeFileSync(instinctSchemasFile, text, "utf8")
    } catch {
      // ignore
    }
    return sendText(res, 200, text)
  }

  if (pathname === "/instinct/playbooks" && method === "GET") {
    try {
      if (fs.existsSync(instinctPlaybooksFile)) {
        return sendText(res, 200, fs.readFileSync(instinctPlaybooksFile, "utf8"))
      }
    } catch {
      // fall through
    }
    const snap = updateInstinctArtifacts()
    const text = renderInstinctPlaybooksYaml(snap) + "\n"
    try {
      fs.writeFileSync(instinctPlaybooksFile, text, "utf8")
    } catch {
      // ignore
    }
    return sendText(res, 200, text)
  }

  if (pathname === "/instinct/skills_draft" && method === "GET") {
    try {
      if (fs.existsSync(instinctSkillsDraftFile)) {
        return sendText(res, 200, fs.readFileSync(instinctSkillsDraftFile, "utf8"))
      }
    } catch {
      // fall through
    }
    const snap = updateInstinctArtifacts()
    const text = renderInstinctSkillsDraftYaml(snap) + "\n"
    try {
      fs.writeFileSync(instinctSkillsDraftFile, text, "utf8")
    } catch {
      // ignore
    }
    return sendText(res, 200, text)
  }

  if (pathname === "/roles/errors" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const role = String(url.searchParams.get("role") ?? "").trim()
    const safeLimit = Number.isFinite(limit) ? limit : 50
    if (role) {
      const rows = readRoleErrors(role, safeLimit)
      return sendJson(res, 200, { role, file: roleErrorsFile(role), count: rows.length, rows })
    }
    const out = {}
    for (const r of ROLE_NAMES) {
      const rows = readRoleErrors(r, Math.min(10, safeLimit))
      out[r] = { file: roleErrorsFile(r), count: rows.length, rows }
    }
    return sendJson(res, 200, { roles: out })
  }

  if (pathname === "/pins/candidates" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const areaFilter = String(url.searchParams.get("area") ?? "").trim()
    const classFilter = String(url.searchParams.get("task_class") ?? "").trim()
    const raw = readJsonlTail(pinsCandidatesFile, Number.isFinite(limit) ? limit : 50)
    const events = raw.filter((e) => {
      if (areaFilter && String(e?.area ?? "").trim() !== areaFilter) return false
      if (classFilter && String(e?.task_class ?? "").trim() !== classFilter) return false
      return true
    })
    return sendJson(res, 200, { file: pinsCandidatesFile, count: events.length, events, area: areaFilter || null, task_class: classFilter || null })
  }

  if (pathname === "/designer/context_pack" && method === "GET") {
    const limit = Number(url.searchParams.get("events") ?? "20")
    const areaFilter = String(url.searchParams.get("area") ?? "").trim()
    const map = readDocJsonBlock("NAVIGATION.md", "PROJECT_MAP_JSON", defaultProjectMap)
    const axioms = readDocJsonBlock("AI_CONTEXT.md", "SSOT_AXIOMS_JSON", defaultSsotAxioms)
    const classes = readDocJsonBlock("AI_CONTEXT.md", "TASK_CLASS_LIBRARY_JSON", defaultTaskClassLibrary)
    const templates = readDocJsonBlock("AI_CONTEXT.md", "PINS_TEMPLATES_JSON", defaultPinsTemplates)
    if (!map.ok) return sendJson(res, map.error === "doc_missing" ? 404 : 400, { error: map.error, file: map.file, message: map.message })
    if (!axioms.ok) return sendJson(res, axioms.error === "doc_missing" ? 404 : 400, { error: axioms.error, file: axioms.file, message: axioms.message })
    if (!classes.ok) return sendJson(res, classes.error === "doc_missing" ? 404 : 400, { error: classes.error, file: classes.file, message: classes.message })
    if (!templates.ok) return sendJson(res, templates.error === "doc_missing" ? 404 : 400, { error: templates.error, file: templates.file, message: templates.message })
    const warnings = []
    if (map.missing) warnings.push("project_map_missing")
    if (axioms.missing) warnings.push("ssot_axioms_missing")
    if (classes.missing) warnings.push("task_classes_missing")
    if (templates.missing) warnings.push("pins_templates_missing")
    const rawEvents = readJsonlTail(stateEventsFile, Number.isFinite(limit) ? limit : 20)
    const events = areaFilter ? rawEvents.filter((e) => String(e?.area ?? "").trim() === areaFilter) : rawEvents
    const hotspots = computeHotspots(events)
    return sendJson(res, 200, {
      l0: { project_map: map.data, ssot_axioms: axioms.data },
      l1: { task_classes: classes.data, pins_templates: templates.data, recent_events: events, hotspots },
      l2: null,
      warnings,
    })
  }

  if (pathname === "/designer/context_pack" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const limit = Number(payload?.events ?? payload?.eventsLimit ?? 20)
      const areaFilter = String(payload?.area ?? "").trim()
      const map = readDocJsonBlock("NAVIGATION.md", "PROJECT_MAP_JSON", defaultProjectMap)
      const axioms = readDocJsonBlock("AI_CONTEXT.md", "SSOT_AXIOMS_JSON", defaultSsotAxioms)
      const classes = readDocJsonBlock("AI_CONTEXT.md", "TASK_CLASS_LIBRARY_JSON", defaultTaskClassLibrary)
      const templates = readDocJsonBlock("AI_CONTEXT.md", "PINS_TEMPLATES_JSON", defaultPinsTemplates)
      if (!map.ok) return sendJson(res, map.error === "doc_missing" ? 404 : 400, { error: map.error, file: map.file, message: map.message })
      if (!axioms.ok) return sendJson(res, axioms.error === "doc_missing" ? 404 : 400, { error: axioms.error, file: axioms.file, message: axioms.message })
      if (!classes.ok) return sendJson(res, classes.error === "doc_missing" ? 404 : 400, { error: classes.error, file: classes.file, message: classes.message })
      if (!templates.ok) return sendJson(res, templates.error === "doc_missing" ? 404 : 400, { error: templates.error, file: templates.file, message: templates.message })
      const warnings = []
      if (map.missing) warnings.push("project_map_missing")
      if (axioms.missing) warnings.push("ssot_axioms_missing")
      if (classes.missing) warnings.push("task_classes_missing")
      if (templates.missing) warnings.push("pins_templates_missing")
      const rawEvents = readJsonlTail(stateEventsFile, Number.isFinite(limit) ? limit : 20)
      const events = areaFilter ? rawEvents.filter((e) => String(e?.area ?? "").trim() === areaFilter) : rawEvents
      const hotspots = computeHotspots(events)
      return sendJson(res, 200, {
        l0: { project_map: map.data, ssot_axioms: axioms.data },
        l1: { task_classes: classes.data, pins_templates: templates.data, recent_events: events, hotspots },
        l2: payload?.task ?? payload?.l2 ?? payload?.directive ?? payload ?? null,
        warnings,
      })
    })
    return
  }

  if (pathname === "/events" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const areaFilter = String(url.searchParams.get("area") ?? "").trim()
    const rawEvents = readJsonlTail(stateEventsFile, Number.isFinite(limit) ? limit : 50)
    const events = areaFilter ? rawEvents.filter((e) => String(e?.area ?? "").trim() === areaFilter) : rawEvents
    return sendJson(res, 200, { file: stateEventsFile, count: events.length, events, area: areaFilter || null })
  }

  if (pathname === "/board" && method === "GET") {
    const tasks = listBoardTasks()
    return sendJson(res, 200, {
      file: boardFile,
      counts: boardCounts(tasks),
      tasks,
    })
  }

  if (pathname === "/board/clear" && method === "POST") {
    let body = ""
    req.on("data", (d) => (body += d))
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const kind = String(payload?.kind ?? "atomic").trim()
      const includeInProgress = payload?.include_in_progress === true
      const statusFilter = Array.isArray(payload?.status)
        ? payload.status.map((s) => String(s))
        : payload?.status != null
          ? [String(payload.status)]
          : null

      const tasks = listBoardTasks()
      let removed = 0
      let canceledExternal = 0
      let skippedInProgress = 0

      for (const t of tasks) {
        if (kind !== "all" && t.kind !== kind) continue
        if (!includeInProgress && t.status === "in_progress") {
          skippedInProgress += 1
          continue
        }
        if (statusFilter && !statusFilter.includes(t.status)) continue
        const job = t.lastJobId ? jobs.get(t.lastJobId) : null
        if (job && (job.status === "running" || job.status === "queued") && job.runner === "external") {
          const out = cancelExternalJob({ id: job.id, reason: "cleared_by_leader" })
          if (out.ok) canceledExternal += 1
        }
        if (deleteBoardTask(t.id)) removed += 1
      }

      return sendJson(res, 200, { ok: true, removed, canceledExternal, skippedInProgress })
    })
    return
  }

  if (pathname === "/mission" && method === "GET") {
    return sendJson(res, 200, loadMission())
  }

  if (pathname === "/mission/consume" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }

      const m = loadMission()
      const title = String(payload?.title ?? "Parent design: SCC x OpenCode fusion").trim()
      const goal = String(payload?.goal ?? "Decompose fusion goal into parent tasks, then atomic subtasks.").trim()
      const statusDocUrl = String(payload?.statusDocUrl ?? m.statusDocUrl).trim()
      const worklogUrl = String(payload?.worklogUrl ?? m.worklogUrl).trim()
      const missionDocUrl = String(payload?.missionDocUrl ?? m.missionDocUrl).trim()

      const combinedGoal = [
        "SYSTEM CURRENT STATUS DOC (use as ground truth):",
        statusDocUrl,
        "",
        "WORKLOG:",
        worklogUrl,
        "",
        "MISSION:",
        missionDocUrl,
        "",
        "GOAL:",
        goal,
      ].join("\n")

      const out = createBoardTask({
        kind: "parent",
        title,
        goal: combinedGoal,
        status: "needs_split",
        role: "designer",
        allowedExecutors: ["codex"],
        allowedModels: [STRICT_DESIGNER_MODEL],
        runner: "external",
      })
      if (!out.ok) return sendJson(res, 400, { error: out.error })

      m.updatedAt = Date.now()
      saveMission(m)
      leader({ level: "info", type: "mission_consumed", parentId: out.task.id, requiredModel: STRICT_DESIGNER_MODEL })
      return sendJson(res, 201, { mission: m, parentTask: out.task })
    })
    return
  }

  if (pathname === "/board/tasks" && method === "GET") {
    return sendJson(res, 200, listBoardTasks())
  }

  if (pathname === "/board/tasks" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const out = createBoardTask(payload)
      if (!out.ok) return sendJson(res, 400, { error: out.error })
      return sendJson(res, 201, out.task)
    })
    return
  }

  if (pathname.startsWith("/board/tasks/") && method === "GET") {
    const id = pathname.replace("/board/tasks/", "")
    const t = getBoardTask(id)
    if (!t) return sendJson(res, 404, { error: "not_found" })
    return sendJson(res, 200, t)
  }

  if (pathname.startsWith("/board/tasks/") && pathname.endsWith("/status") && method === "POST") {
    const id = pathname.replace("/board/tasks/", "").replace("/status", "")
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const st = normalizeBoardStatus(payload?.status)
      if (!st) return sendJson(res, 400, { error: "bad_status" })
      const t = updateBoardTaskStatus(id, st)
      if (!t) return sendJson(res, 404, { error: "not_found" })
      return sendJson(res, 200, t)
    })
    return
  }

  if (pathname.startsWith("/board/tasks/") && pathname.endsWith("/update") && method === "POST") {
    const id = pathname.replace("/board/tasks/", "").replace("/update", "")
    const t = getBoardTask(id)
    if (!t) return sendJson(res, 404, { error: "not_found" })
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const status = payload?.status != null ? normalizeBoardStatus(payload.status) : null
      const allowedExecutors = Array.isArray(payload?.allowedExecutors) ? payload.allowedExecutors.map((x) => String(x)).slice(0, 4) : null
      const allowedModels = Array.isArray(payload?.allowedModels) ? payload.allowedModels.map((x) => String(x)).slice(0, 8) : null
      const runner = payload?.runner === "internal" ? "internal" : payload?.runner === "external" ? "external" : null
      const goal = payload?.goal != null ? String(payload.goal) : null
      const files = Array.isArray(payload?.files) ? payload.files.map((x) => String(x)).slice(0, 16) : null
      const skills = Array.isArray(payload?.skills) ? payload.skills.map((x) => String(x)).slice(0, 16) : null
      const pointers = payload?.pointers && typeof payload.pointers === "object" ? payload.pointers : null
      const pins = payload?.pins && typeof payload.pins === "object" ? payload.pins : null
      const pinsInstance = payload?.pins_instance && typeof payload.pins_instance === "object" ? payload.pins_instance : null
      const pinsPending = payload?.pins_pending === true
      const pinsTargetId = payload?.pins_target_id ? String(payload.pins_target_id) : null
      const contract = payload?.contract && typeof payload.contract === "object" ? payload.contract : null
      const assumptions = Array.isArray(payload?.assumptions) ? payload.assumptions.map((x) => String(x)).slice(0, 16) : null
      const allowedTests = Array.isArray(payload?.allowedTests) ? payload.allowedTests.map((x) => String(x)).slice(0, 24) : null
      const toolingRules = payload?.toolingRules && typeof payload.toolingRules === "object" ? payload.toolingRules : null
      const area = payload?.area != null ? String(payload.area).trim() : null
      const taskClassId = payload?.task_class_id != null ? String(payload.task_class_id).trim() : null
      const taskClassCandidate = payload?.task_class_candidate != null ? String(payload.task_class_candidate).trim() : null
      const taskClassParams = payload?.task_class_params && typeof payload.task_class_params === "object" ? payload.task_class_params : null

      if (status) t.status = status
      if (allowedExecutors) t.allowedExecutors = allowedExecutors
      if (allowedModels) t.allowedModels = allowedModels
      if (runner) t.runner = runner
      if (goal) t.goal = goal
      if (files) t.files = files
      if (skills) t.skills = skills
      if (payload?.pointers != null) t.pointers = pointers
      if (payload?.pins != null) t.pins = pins
      if (payload?.pins_instance != null) t.pins_instance = pinsInstance
      if (payload?.pins_pending != null) t.pins_pending = pinsPending
      if (payload?.pins_target_id != null) t.pins_target_id = pinsTargetId
      if (payload?.contract != null) t.contract = contract
      if (payload?.assumptions != null) t.assumptions = assumptions
      if (payload?.allowedTests != null) t.allowedTests = allowedTests
      if (payload?.toolingRules != null) t.toolingRules = toolingRules
      if (payload?.area != null) t.area = area
      if (payload?.task_class_id != null) t.task_class_id = taskClassId
      if (payload?.task_class_candidate != null) t.task_class_candidate = taskClassCandidate
      if (payload?.task_class_params != null) t.task_class_params = taskClassParams
      t.updatedAt = Date.now()
      putBoardTask(t)
      leader({ level: "info", type: "board_task_updated", id: t.id, status: t.status, runner: t.runner })
      return sendJson(res, 200, t)
    })
    return
  }

  if (pathname.startsWith("/board/tasks/") && pathname.endsWith("/dispatch") && method === "POST") {
    const id = pathname.replace("/board/tasks/", "").replace("/dispatch", "")
    const out = dispatchBoardTaskToExecutor(id)
    if (!out.ok) return sendJson(res, 400, { error: out.error })
    return sendJson(res, 202, { task: out.task, job: out.job })
  }

  if (pathname.startsWith("/board/tasks/") && pathname.endsWith("/split") && method === "POST") {
    const id = pathname.replace("/board/tasks/", "").replace("/split", "")
    const t = getBoardTask(id)
    if (!t) return sendJson(res, 404, { error: "not_found" })
    if (t.kind !== "parent") return sendJson(res, 400, { error: "not_parent" })
    const strict = requireDesigner52(t)
    if (!strict.ok) {
      leader({ level: "warn", type: "board_task_split_rejected", id: t.id, error: strict.error, requiredModel: STRICT_DESIGNER_MODEL })
      appendJsonl(designerFailuresFile, {
        t: new Date().toISOString(),
        task_id: t.id,
        reason: strict.error,
        role: t.role ?? null,
        area: t.area ?? null,
      })
      return sendJson(res, 400, { error: strict.error, requiredModel: STRICT_DESIGNER_MODEL })
    }
    const executor = t.allowedExecutors?.[0] ?? "codex"
    const model = t.allowedModels?.[0] ?? (executor === "opencodecli" ? occliModelDefault : codexModelDefault)
    const files = Array.isArray(t.files) ? t.files : []
    const ctx = files.length ? createContextPackFromFiles({ files, maxBytes: 260_000 }) : { ok: true, id: null, bytes: 0 }
    if (!ctx.ok) return sendJson(res, 400, { error: ctx.error })

    const schema = {
      title: "string (short)",
      goal: "string (detailed, includes deliverables)",
      status: "ready|backlog|blocked (default ready)",
      role: "designer|architect|integrator|engineer|qa|doc",
      skills: ["skill ids / names (optional)"],
      pointers: { docs: ["doc urls (optional)"], rules: ["doc urls (optional)"], maps: ["doc urls (optional)"] },
      pins: {
        allowed_paths: ["exact files/dirs"],
        forbidden_paths: ["paths to forbid"],
        symbols: ["symbol names (optional)"],
        line_windows: { "file": [[10, 20]] },
        max_files: 3,
        max_loc: 200,
        ssot_assumptions: ["<=7 items, no quotes, no reasoning"],
      },
      pins_instance: {
        template_id: "pins_template_id (optional)",
        allowed_paths_add: ["additional files/dirs"],
        forbidden_paths_add: ["additional forbidden paths"],
        symbols_add: ["additional symbols"],
        line_windows: { "file": [[10, 20]] },
        max_files: 3,
        max_loc: 200,
        ssot_assumptions: ["<=7 items"],
      },
      task_class_id: "schema_add_field_v1|none",
      task_class_candidate: "schema_add_field_v1|none",
      task_class_params: { "param_name": "value" },
      acceptance_template: "string (optional)",
      stop_codes: ["pins_insufficient", "needs_split", "needs_upgrade"],
      allowedExecutors: ["codex|opencodecli"],
      allowedModels: ["model id strings (optional)"],
      files: ["relative file paths to include in context pack (optional)"],
      runner: "external|internal",
    }

    const prompt = [
      "You are SCC Planner (strong model). Output MUST be pure JSON (UTF-8), no markdown, no prose.",
      "Goal: turn the parent task into a machine-routable task graph (scc.task_graph.v1) with atomic children.",
      "Hard rules:",
      "- 子任务<=3 steps，可独立验证，改动半径写清楚。",
      "- fail-closed：信息不足写 NEED_INPUT 并生成 pins_fix/clarify 子任务，禁止猜测。",
      "- 每个子任务都要给 role、task_class、pins_spec、allowed_tests(至少1条非 task_selftest)、acceptance、stop_conditions、fallback。",
      "- 给出队列分区 lane (fastlane/mainlane/batchlane) 和优先级。",
      "- 若父任务跨模块/高风险，必须拆出 preflight 与 eval/regression 子任务。",
      "- patch_scope.allow_paths/deny_paths 要求最小改动半径。",
      "- 严格使用下方 JSON schema 字段，可增字段但不可乱序删除；缺信息用 null/空数组，并在 needs_input 说明。",
      "",
      "Parent goal and context:",
      t.goal,
      "",
      "Schema (scc.task_graph.v1):",
      JSON.stringify(schema, null, 2),
      "",
      "输出仅此 JSON。模型假设：",
      `executor model = '${STRICT_DESIGNER_MODEL}', pins-first, CI 必须有非 task_selftest 自测。`,
    ].join("\n")

    const timeoutMs = Number.isFinite(t.timeoutMs) ? t.timeoutMs : executor === "opencodecli" ? timeoutOccliMs : timeoutCodexMs
    const job = makeJob({ prompt, model, executor, taskType: "board_split", timeoutMs })
    job.runner = t.runner === "internal" ? "internal" : "external"
    job.contextPackId = ctx.id
    jobs.set(job.id, job)
    schedule()

    t.lastJobId = job.id
    t.splitJobId = job.id
    t.status = "in_progress"
    t.updatedAt = Date.now()
    putBoardTask(t)
    leader({ level: "info", type: "board_task_split_started", id: t.id, jobId: job.id, executor, model })
    return sendJson(res, 202, { task: t, job, contextPackId: ctx.id })
  }

  if (pathname.startsWith("/board/tasks/") && pathname.endsWith("/split/apply") && method === "POST") {
    const id = pathname.replace("/board/tasks/", "").replace("/split/apply", "")
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
      const parent = getBoardTask(id)
      const jobId =
        payload?.jobId ? String(payload.jobId) : parent?.splitJobId ? String(parent.splitJobId) : parent?.lastJobId ? String(parent.lastJobId) : null
      if (!jobId) return sendJson(res, 400, { error: "missing_jobId" })
      const out = applySplitFromJob({ parentId: id, jobId })
      if (!out.ok) return sendJson(res, 400, { error: out.error })
      return sendJson(res, 200, out)
    })
    return
  }

  // OpenCode under /opencode/*
  if (pathname === "/opencode" || pathname.startsWith("/opencode/")) {
    if (!features.exposeOpenCode) {
      return sendJson(res, 404, { error: "opencode_disabled" })
    }
    if (!features.exposeOpenCodeUi && pathname !== "/opencode/global/health") {
      return sendJson(res, 404, { error: "opencode_ui_disabled" })
    }
    const stripped = pathname === "/opencode" ? "/" : pathname.slice("/opencode".length)
    proxyTo(req, res, opencodeUpstream, stripped, { rewriteCookiePathPrefix: "/opencode" })
    return
  }

  // SCC on root paths
  if (isSccPath(pathname)) {
    if (!features.exposeScc) {
      return sendJson(res, 404, { error: "scc_disabled" })
    }
    if (!features.exposeSccMcp && (pathname === "/mcp" || pathname.startsWith("/mcp/"))) {
      return sendJson(res, 404, { error: "scc_mcp_disabled" })
    }
    proxyTo(req, res, sccUpstream, pathname)
    return
  }

  // Codex executor (host codex CLI)
  if (pathname === "/executor/codex/health" && method === "GET") {
    const h = await codexHealth()
    return sendJson(res, h.ok ? 200 : 500, h)
  }

  if (pathname === "/executor/opencodecli/health" && method === "GET") {
    const h = await new Promise((resolve) => {
      execFile(occliBin, ["--version"], { timeout: 8000 }, (err, stdout, stderr) => {
        resolve({
          ok: !err,
          code: err?.code ?? 0,
          stdout: stdout?.trim() ?? "",
          stderr: stderr?.trim() ?? (err ? String(err) : ""),
        })
      })
    })
    return sendJson(res, h.ok ? 200 : 500, h)
  }

  if (pathname === "/executor/codex" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", async () => {
      try {
        const payload = JSON.parse(body || "{}")
        const prompt = String(payload.prompt ?? "").trim()
        const model = payload.model ? String(payload.model).trim() : codexModelDefault
        if (!prompt) return sendJson(res, 400, { error: "missing_prompt" })
        const timeoutMs = payload.timeoutMs ? Number(payload.timeoutMs) : undefined
        const out = await codexRunSingle(prompt, model, { timeoutMs })
        return sendJson(res, out.ok ? 200 : 500, {
          success: out.ok,
          exit_code: out.code,
          stdout: out.stdout,
          stderr: out.stderr,
          executor: "codex",
          model,
        })
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
    })
    return
  }

  if (pathname === "/executor/codex/run" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", async () => {
      try {
        const payload = JSON.parse(body || "{}")
        const model = payload.model ? String(payload.model).trim() : codexModelDefault
        const parents = (payload.parents?.parents ?? payload.parents ?? []).map((p) => ({
          id: String(p.id ?? ""),
          description: String(p.description ?? "").trim(),
        }))
        if (!Array.isArray(parents) || parents.length === 0) {
          return sendJson(res, 400, { error: "missing_parents" })
        }
        const results = []
        for (const p of parents) {
          const out = await codexRunSingle(p.description || "no description provided", model)
          results.push({
            id: p.id,
            exit_code: out.code,
            stdout: out.stdout,
            stderr: out.stderr,
            error: out.ok ? undefined : "executor_error",
          })
        }
        const success = results.every((r) => r.exit_code === 0)
        return sendJson(res, success ? 200 : 500, {
          success,
          executor: "codex",
          model,
          results,
        })
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
    })
    return
  }

  // Async job submission: /executor/jobs
  if (pathname === "/executor/jobs" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", async () => {
      try {
        const payload = JSON.parse(body || "{}")
        const prompt = String(payload.prompt ?? "").trim()
        const executor = (payload.executor ? String(payload.executor).trim() : "codex") || "codex"
        const model =
          payload.model
            ? String(payload.model).trim()
            : executor === "opencodecli"
              ? occliModelDefault
              : codexModelDefault
        const threadId = payload.threadId ? String(payload.threadId).trim() : null
        if (threadId) return sendJson(res, 400, { error: "thread_not_allowed_for_executor" })
        const contextPackId = payload.contextPackId ? String(payload.contextPackId).trim() : null
        const taskType = payload.taskType ? String(payload.taskType).trim() : "atomic"
        const timeoutMs = payload.timeoutMs ? Number(payload.timeoutMs) : null
        const runner = payload.runner ? String(payload.runner).trim() : "internal"
        if (!prompt) return sendJson(res, 400, { error: "missing_prompt" })
        const job = makeJob({ prompt, model, executor, taskType, timeoutMs })
        job.runner = runner === "external" ? "external" : "internal"
        job.threadId = threadId
        job.contextPackId = contextPackId
        jobs.set(job.id, job)
        schedule()
        return sendJson(res, 202, job)
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
    })
    return
  }

  // Atomic job helper: build context pack + inject strict rules for <10m jobs
  if (pathname === "/executor/jobs/atomic" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      try {
        const payload = JSON.parse(body || "{}")
        const goal = String(payload.goal ?? "").trim()
        const executor = (payload.executor ? String(payload.executor).trim() : "codex") || "codex"
        const model =
          payload.model
            ? String(payload.model).trim()
            : executor === "opencodecli"
              ? occliModelDefault
              : codexModelDefault
        const threadId = payload.threadId ? String(payload.threadId).trim() : null
        if (threadId) return sendJson(res, 400, { error: "thread_not_allowed_for_executor" })
        const files = Array.isArray(payload.files) ? payload.files.map((x) => String(x)) : []
        const pins = payload?.pins && typeof payload.pins === "object" ? payload.pins : null
        const maxBytes = Number(payload.maxBytes ?? 220_000)
        const taskType = payload.taskType ? String(payload.taskType).trim() : "atomic"
        const runner = payload.runner ? String(payload.runner).trim() : "internal"
        const timeoutMsRaw = payload.timeoutMs ? Number(payload.timeoutMs) : null
        const timeoutMs = Number.isFinite(timeoutMsRaw) ? timeoutMsRaw : executor === "opencodecli" ? timeoutOccliMs : timeoutCodexMs
        if (!goal) return sendJson(res, 400, { error: "missing_goal" })
        if (goal.length < 20) return sendJson(res, 400, { error: "goal_too_small" })
        if (goal.length > 4000) return sendJson(res, 400, { error: "goal_too_large" })
        if (requirePins && !pins) return sendJson(res, 400, { error: "missing_pins" })
        if (executor === "codex" && files.length === 0 && !pins && payload.allowNoContext !== true) {
          return sendJson(res, 400, { error: "missing_files_for_codex" })
        }
        if (files.length > 16) return sendJson(res, 400, { error: "too_many_files" })

        const ctx = pins
          ? createContextPackFromPins({ pins, maxBytes })
          : files.length
            ? createContextPackFromFiles({ files, maxBytes })
            : { ok: true, id: null, bytes: 0 }
        if (!ctx.ok) return sendJson(res, 400, { error: ctx.error })

        const prompt = [
          ATOMIC_DEFAULT_RULES,
          pins ? `\nPins:\n${JSON.stringify(pins, null, 2).slice(0, 4000)}` : "",
          "",
          `Goal:`,
          goal,
          "",
          `Deliverable:`,
          "- Return a concrete, minimal output: file paths to change + what to change; or exact commands to run; or a small patch snippet if appropriate.",
          "- Do not include unrelated suggestions.",
        ].join("\n")

        const job = makeJob({ prompt, model, executor, taskType, timeoutMs })
        job.runner = runner === "external" ? "external" : "internal"
        job.threadId = threadId
        job.contextPackId = ctx.id
        jobs.set(job.id, job)
        schedule()
        leader({ level: "info", type: "atomic_job_created", id: job.id, executor, model, taskType, contextPackId: ctx.id })
        return sendJson(res, 202, { ...job, contextPackBytes: ctx.bytes })
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
    })
    return
  }

  // Context packs: build and reuse a single prompt-friendly context blob
  if (pathname === "/executor/contextpacks" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      try {
        const payload = JSON.parse(body || "{}")
        const files = Array.isArray(payload.files) ? payload.files.map((x) => String(x)) : []
        const pins = payload?.pins && typeof payload.pins === "object" ? payload.pins : null
        const maxBytes = Number(payload.maxBytes ?? 200_000)
        const out = pins
          ? createContextPackFromPins({ pins, maxBytes })
          : createContextPackFromFiles({ files, maxBytes })
        if (!out.ok) return sendJson(res, 400, { error: out.error })
        return sendJson(res, 201, { id: out.id, file: out.file, bytes: out.bytes })
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
    })
    return
  }

  if (pathname.startsWith("/executor/contextpacks/") && method === "GET") {
    const id = pathname.replace("/executor/contextpacks/", "")
    const text = getContextPack(id)
    if (!text) return sendJson(res, 404, { error: "not_found" })
    return sendJson(res, 200, { id, file: ctxPath(id), content: text })
  }

  // Threads: lightweight context reinjection across atomic tasks
  if (pathname === "/executor/threads" && method === "POST") {
    const id = newThreadId()
    const t = { id, createdAt: Date.now(), history: [] }
    putThread(t)
    leader({ level: "info", type: "thread_created", id })
    return sendJson(res, 201, t)
  }

  if (pathname.startsWith("/executor/threads/") && method === "GET") {
    const id = pathname.replace("/executor/threads/", "")
    const t = getThread(id)
    if (!t) return sendJson(res, 404, { error: "not_found" })
    return sendJson(res, 200, t)
  }

  if (pathname === "/executor/jobs" && method === "GET") {
    return sendJson(res, 200, Array.from(jobs.values()))
  }

  if (pathname === "/executor/workers" && method === "GET") {
    return sendJson(res, 200, listWorkers())
  }

  if (pathname === "/executor/workers/register" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      try {
        const payload = JSON.parse(body || "{}")
        const name = payload.name ? String(payload.name).trim() : "worker"
        const executors = Array.isArray(payload.executors) ? payload.executors.map((x) => String(x)) : []
        const allowed = executors.filter((x) => x === "codex" || x === "opencodecli")
        if (!allowed.length) return sendJson(res, 400, { error: "missing_executors" })
        const models = Array.isArray(payload.models) ? payload.models.map((x) => String(x)).slice(0, 32) : []
        const id = newWorkerId()
        const w = { id, name, executors: allowed, models, startedAt: Date.now(), lastSeen: Date.now(), runningJobId: null }
        putWorker(w)
        leader({ level: "info", type: "worker_registered", id, name, executors: allowed, models: models.slice(0, 8) })
        return sendJson(res, 201, w)
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
    })
    return
  }

  if (pathname.startsWith("/executor/workers/") && pathname.endsWith("/heartbeat") && method === "POST") {
    const id = pathname.replace("/executor/workers/", "").replace("/heartbeat", "")
    const w = getWorker(id)
    if (!w) return sendJson(res, 404, { error: "not_found" })
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch {
        payload = {}
      }
      const now = Date.now()
      w.lastSeen = now
      const runningJobId = payload?.runningJobId ? String(payload.runningJobId) : null
      if (runningJobId) w.runningJobId = runningJobId
      putWorker(w)
      if (runningJobId) {
        const j = jobs.get(runningJobId)
        if (j && j.runner === "external" && j.workerId === id && j.status === "running") {
          j.leaseUntil = now + workerLeaseMsDefault
          j.lastUpdate = now
          jobs.set(j.id, j)
          saveState()
        }
      }
      return sendJson(res, 200, { ok: true, id })
    })
    return
  }

  if (pathname.startsWith("/executor/workers/") && pathname.includes("/claim") && method === "GET") {
    const id = pathname.replace("/executor/workers/", "").replace("/claim", "")
    const w = getWorker(id)
    if (!w) return sendJson(res, 404, { error: "not_found" })
    const url = new URL(req.url ?? "/", "http://gateway.local")
    const executor = url.searchParams.get("executor") ?? ""
    if (!w.executors.includes(executor)) return sendJson(res, 400, { error: "executor_not_allowed" })
    if (w.runningJobId) return sendJson(res, 409, { error: "worker_busy", runningJobId: w.runningJobId })
    const waitMs = Number(url.searchParams.get("waitMs") ?? "25000")
    const deadline = Date.now() + (Number.isFinite(waitMs) ? Math.max(0, Math.min(waitMs, 60000)) : 25000)

    while (Date.now() < deadline) {
      const counts = runningCounts()
      if (executor === "codex" && counts.codex >= externalMaxCodex) break
      if (executor === "opencodecli" && counts.opencodecli >= externalMaxOccli) break
      const pick = claimNextJob({ executor, worker: w })
      if (pick) {
        const now = Date.now()
        pick.status = "running"
        pick.workerId = id
        pick.leaseUntil = now + workerLeaseMsDefault
        pick.startedAt = now
        pick.lastUpdate = now
        pick.attempts = (pick.attempts ?? 0) + 1
        jobs.set(pick.id, pick)
        saveState()
        w.lastSeen = now
        w.runningJobId = pick.id
        putWorker(w)
        leader({ level: "info", type: "job_claimed", id: pick.id, executor: pick.executor, workerId: id })
        return sendJson(res, 200, {
          id: pick.id,
          executor: pick.executor,
          model: pick.model,
          taskType: pick.taskType,
          timeoutMs: pick.timeoutMs,
          prompt: buildInjectedPrompt(pick),
        })
      }
      await new Promise((r) => setTimeout(r, 500))
    }
    return sendJson(res, 204, { ok: true })
  }

  if (pathname.startsWith("/executor/jobs/") && pathname.endsWith("/cancel") && method === "POST") {
    const id = pathname.replace("/executor/jobs/", "").replace("/cancel", "")
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch {
        payload = {}
      }
      const out = cancelExternalJob({ id, reason: payload?.reason })
      if (!out.ok) return sendJson(res, 400, { error: out.error })
      return sendJson(res, 200, out)
    })
    return
  }

  if (pathname.startsWith("/executor/jobs/") && pathname.endsWith("/requeue") && method === "POST") {
    const id = pathname.replace("/executor/jobs/", "").replace("/requeue", "")
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      let payload = null
      try {
        payload = JSON.parse(body || "{}")
      } catch {
        payload = {}
      }
      const out = requeueExternalJob({ id, reason: payload?.reason })
      if (!out.ok) return sendJson(res, 400, { error: out.error })
      return sendJson(res, 200, out)
    })
    return
  }

  if (pathname.startsWith("/executor/jobs/") && pathname.endsWith("/complete") && method === "POST") {
    const id = pathname.replace("/executor/jobs/", "").replace("/complete", "")
    const job = jobs.get(id)
    if (!job) return sendJson(res, 404, { error: "not_found" })
    if (job.runner !== "external") return sendJson(res, 400, { error: "not_external_job" })
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", () => {
      try {
        const payload = JSON.parse(body || "{}")
        const workerId = payload.workerId ? String(payload.workerId) : ""
        if (!workerId || workerId !== job.workerId) return sendJson(res, 403, { error: "worker_mismatch" })
        const stdout = payload.stdout ? String(payload.stdout) : ""
        const stderr = payload.stderr ? String(payload.stderr) : ""
        const exit_code = payload.exit_code != null ? Number(payload.exit_code) : 0
        const ok = exit_code === 0

        job.status = ok ? "done" : "failed"
        job.finishedAt = Date.now()
        job.lastUpdate = job.finishedAt
        job.exit_code = exit_code
        job.stdout = stdout
        job.stderr = stderr
        job.error = ok ? null : "executor_error"
        job.reason = ok ? null : classifyFailure(job, { stderr, timedOut: false })
        jobs.set(job.id, job)
        saveState()

        const w = getWorker(workerId)
        if (w && w.runningJobId === job.id) {
          w.runningJobId = null
          w.lastSeen = Date.now()
          putWorker(w)
        }

        const record = {
          t: new Date().toISOString(),
          id: job.id,
          executor: job.executor,
          model: job.model,
          status: job.status,
          exit_code: job.exit_code,
          reason: job.reason,
          createdAt: job.createdAt,
          startedAt: job.startedAt,
          finishedAt: job.finishedAt,
          durationMs: job.startedAt && job.finishedAt ? job.finishedAt - job.startedAt : null,
          promptPreview: String(job.prompt || "").slice(0, 2000),
          stdoutPreview: String(job.stdout || "").slice(0, 4000),
          stderrPreview: String(job.stderr || "").slice(0, 4000),
        }
        appendJsonl(execLogJobs, record)
        if (job.status === "failed") appendJsonl(execLogFailures, record)
        leader({
          level: job.status === "failed" ? "error" : "info",
          type: "job_finished",
          id: job.id,
          executor: job.executor,
          model: job.model,
          status: job.status,
          reason: job.reason,
          exit_code: job.exit_code,
          durationMs: record.durationMs,
          promptPreview: record.promptPreview?.slice?.(0, 140),
        })
        updateBoardFromJob(job)
        schedule()
        return sendJson(res, 200, { ok: true, status: job.status })
      } catch (e) {
        return sendJson(res, 400, { error: "bad_json", message: String(e) })
      }
    })
    return
  }

  if (pathname.startsWith("/executor/jobs/") && pathname.endsWith("/patch") && method === "GET") {
    const id = pathname.replace("/executor/jobs/", "").replace("/patch", "")
    const job = jobs.get(id)
    if (!job) return sendJson(res, 404, { error: "not_found" })
    const patch = extractPatchFromStdout(job.stdout)
    if (!patch) return sendJson(res, 404, { error: "patch_not_found" })
    return sendJson(res, 200, { id, status: job.status, patch })
  }

  if (pathname.startsWith("/executor/jobs/") && method === "GET") {
    const id = pathname.replace("/executor/jobs/", "")
    const job = jobs.get(id)
    if (!job) return sendJson(res, 404, { error: "not_found" })
    return sendJson(res, 200, job)
  }

  if (pathname === "/executor/debug/failures" && method === "GET") {
    const raw = (() => {
      try {
        return fs.readFileSync(execLogFailures, "utf8")
      } catch {
        return ""
      }
    })()
    const lines = raw
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0)
      .slice(-200)
    return sendJson(res, 200, { file: execLogFailures, count: lines.length, lines })
  }

  if (pathname === "/executor/debug/summary" && method === "GET") {
    const raw = (() => {
      try {
        return fs.readFileSync(execLogFailures, "utf8")
      } catch {
        return ""
      }
    })()
    const rows = raw
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0)
      .slice(-500)
      .map((l) => {
        try {
          return JSON.parse(l)
        } catch {
          return null
        }
      })
      .filter(Boolean)

    const byReason = {}
    const byExecutor = {}
    const byReasonByArea = {}
    for (const r of rows) {
      const reason = r.reason || "unknown"
      byReason[reason] = (byReason[reason] || 0) + 1
      const ex = r.executor || "unknown"
      byExecutor[ex] = (byExecutor[ex] || 0) + 1
      const area = r.area || "unknown"
      byReasonByArea[area] = byReasonByArea[area] || {}
      byReasonByArea[area][reason] = (byReasonByArea[area][reason] || 0) + 1
    }

    return sendJson(res, 200, {
      failuresFile: execLogFailures,
      sampleN: rows.length,
      byReason,
      byExecutor,
      byReasonByArea,
    })
  }

  if (pathname === "/replay/task" && method === "GET") {
    const taskId = String(url.searchParams.get("task_id") ?? "").trim()
    const tail = Number(url.searchParams.get("tail") ?? "400")
    if (!taskId) return sendJson(res, 400, { error: "missing_task_id" })
    const t = getBoardTask(taskId)
    const limit = Number.isFinite(tail) ? tail : 400
    const recentJobs = readJsonlTail(execLogJobs, limit).filter((r) => String(r?.task_id ?? "") === taskId)
    const recentFailures = readJsonlTail(execLogFailures, limit).filter((r) => String(r?.task_id ?? "") === taskId)
    const recentEvents = readJsonlTail(stateEventsFile, limit).filter((r) => String(r?.task_id ?? "") === taskId)
    const lastJob = t?.lastJobId ? jobs.get(String(t.lastJobId)) ?? null : null
    return sendJson(res, 200, {
      task: t,
      lastJob,
      logs: {
        jobs: { file: execLogJobs, rows: recentJobs.slice(-60) },
        failures: { file: execLogFailures, rows: recentFailures.slice(-30) },
        state_events: { file: stateEventsFile, rows: recentEvents.slice(-30) },
      },
    })
  }

  if (pathname === "/executor/debug/token_cfo" && method === "GET") {
    const tail = Number(url.searchParams.get("tail") ?? "1200")
    const snap = computeTokenCfoSnapshot({ tail: Number.isFinite(tail) ? tail : 1200 })
    return sendJson(res, 200, snap)
  }

  if (pathname === "/executor/debug/metrics" && method === "GET") {
    const hoursRaw = url.searchParams.get("hours")
    const windowMsRaw = url.searchParams.get("windowMs")
    const hours = hoursRaw != null ? Number(hoursRaw) : 6
    const windowMs = windowMsRaw != null ? Number(windowMsRaw) : Number.isFinite(hours) ? hours * 60 * 60 * 1000 : 6 * 60 * 60 * 1000
    const sinceMs = Date.now() - (Number.isFinite(windowMs) && windowMs > 0 ? windowMs : 6 * 60 * 60 * 1000)

    const parseJsonl = (file) => {
      try {
        const raw = fs.readFileSync(file, "utf8")
        return raw
          .split("\n")
          .map((l) => l.trim())
          .filter((l) => l.length > 0)
          .map((l) => {
            try {
              return JSON.parse(l)
            } catch {
              return null
            }
          })
          .filter(Boolean)
      } catch {
        return []
      }
    }

    const leaderRows = parseJsonl(execLeaderLog).filter((r) => {
      const t = Date.parse(r.t ?? "")
      return Number.isFinite(t) && t >= sinceMs
    })
    const jobFinished = leaderRows.filter((r) => r.type === "job_finished")
    const done = jobFinished.filter((r) => r.status === "done").length
    const failed = jobFinished.filter((r) => r.status === "failed").length
    const successRate = done + failed > 0 ? Math.round((done / (done + failed)) * 1000) / 1000 : null

    const byExecutor = {}
    const byModel = {}
    for (const r of jobFinished) {
      const ex = r.executor || "unknown"
      byExecutor[ex] = byExecutor[ex] || { finished: 0, done: 0, failed: 0 }
      byExecutor[ex].finished += 1
      if (r.status === "done") byExecutor[ex].done += 1
      if (r.status === "failed") byExecutor[ex].failed += 1

      const m = r.model || "unknown"
      byModel[m] = byModel[m] || { finished: 0, done: 0, failed: 0 }
      byModel[m].finished += 1
      if (r.status === "done") byModel[m].done += 1
      if (r.status === "failed") byModel[m].failed += 1
    }

    const failures = parseJsonl(execLogFailures).filter((r) => {
      const t = Date.parse(r.t ?? "")
      return Number.isFinite(t) && t >= sinceMs
    })
    const byReason = {}
    for (const r of failures) {
      const reason = r.reason || "unknown"
      byReason[reason] = (byReason[reason] || 0) + 1
    }

    return sendJson(res, 200, {
      windowMs,
      sinceUtc: new Date(sinceMs).toISOString(),
      leaderFile: execLeaderLog,
      failuresFile: execLogFailures,
      jobsFinished: jobFinished.length,
      done,
      failed,
      successRate,
      byExecutor,
      byModel,
      failures: failures.length,
      byReason,
    })
  }

  if (pathname === "/executor/leader" && method === "GET") {
    const raw = (() => {
      try {
        return fs.readFileSync(execLeaderLog, "utf8")
      } catch {
        return ""
      }
    })()
    const lines = raw
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0)
      .slice(-200)
    return sendJson(res, 200, { file: execLeaderLog, count: lines.length, lines })
  }

  if (pathname === "/executor/prompt" && method === "GET") {
    const taskId = String(url.searchParams.get("task_id") ?? "").trim()
    if (!taskId) return sendJson(res, 400, { error: "missing_task_id" })
    const task = getBoardTask(taskId)
    const jobId = task?.lastJobId ?? task?.splitJobId ?? null
    const job = jobId ? jobs.get(jobId) : null
    if (!job) return sendJson(res, 404, { error: "job_not_found" })
    return sendJson(res, 200, {
      task_id: taskId,
      job_id: job.id,
      executor: job.executor,
      model: job.model,
      prompt: job.prompt ?? "",
    })
  }

  sendJson(res, 404, {
    error: "not_found",
    routes: {
      scc: SCC_PREFIXES,
      opencode: "/opencode/*",
      status: "/status",
    },
  })
})

server.on("upgrade", (req, socket, head) => {
  const url = new URL(req.url ?? "/", "http://gateway.local")
  const pathname = url.pathname

  if (pathname === "/opencode" || pathname.startsWith("/opencode/")) {
    const stripped = pathname === "/opencode" ? "/" : pathname.slice("/opencode".length)
    req.url = stripped + url.search
    proxy.ws(req, socket, head, { target: opencodeUpstream.toString(), changeOrigin: true })
    return
  }

  if (isSccPath(pathname)) {
    proxy.ws(req, socket, head, { target: sccUpstream.toString(), changeOrigin: true })
    return
  }

  socket.destroy()
})

server.listen(gatewayPort, "127.0.0.1", () => {
  console.log(`[oc-scc-local] listening on http://127.0.0.1:${gatewayPort}`)
  console.log(`[oc-scc-local] SCC upstream: ${sccUpstream}`)
  console.log(`[oc-scc-local] OpenCode upstream: ${opencodeUpstream} (mounted at /opencode)`)
})
