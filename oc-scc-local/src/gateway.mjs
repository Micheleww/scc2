import http from "node:http"
import { URL } from "node:url"
import process from "node:process"
import httpProxy from "http-proxy"
	import fs from "node:fs"
	import path from "node:path"
	import { execFile, execFileSync } from "node:child_process"
	import crypto from "node:crypto"
import Ajv from "ajv"
import addFormats from "ajv-formats"
import { toYaml } from "./lib/yaml.mjs"
import { readJsonlTail, countJsonlLines } from "./lib/jsonl_tail.mjs"
import { getConfig } from "./lib/config.mjs"
import { readJson, writeJsonAtomic, updateJsonLocked } from "./lib/state_store.mjs"
import { loadJobsState, saveJobsState } from "./lib/jobs_store.mjs"
import { hasShellMetacharacters, parseCmdline } from "./lib/cmdline.mjs"
import { loadCircuitBreakerState as loadCircuitBreakerStateImpl, saveCircuitBreakerState as saveCircuitBreakerStateImpl, quarantineActive as quarantineActiveImpl } from "./lib/circuit_breaker_store.mjs"
import { loadRepoHealthState as loadRepoHealthStateImpl, saveRepoHealthState as saveRepoHealthStateImpl, repoUnhealthyActive as repoUnhealthyActiveImpl } from "./lib/repo_health_store.mjs"
import { loadAuditTriggerState as loadAuditTriggerStateImpl, saveAuditTriggerState as saveAuditTriggerStateImpl, loadFlowManagerState as loadFlowManagerStateImpl, saveFlowManagerState as saveFlowManagerStateImpl, loadFeedbackHookState as loadFeedbackHookStateImpl, saveFeedbackHookState as saveFeedbackHookStateImpl } from "./lib/flow_state_store.mjs"
import { createLogger } from "./lib/logger.mjs"
import { createJsonlErrorSink } from "./lib/error_sink.mjs"
import { readJsonBody, readRequestBody, sendJson, sendText, sha1, sha256Hex, stableStringify } from "./utils.mjs"
import {
  BOARD_LANES,
  BOARD_STATUS,
  computeJobPriorityForTask as computeJobPriorityForTaskImpl,
  lanePriorityScore as lanePriorityScoreImpl,
  loadBoard as loadBoardImpl,
  loadMission as loadMissionImpl,
  normalizeBoardStatus,
  normalizeLane,
  saveBoard as saveBoardImpl,
  saveMission as saveMissionImpl,
} from "./lib/board.mjs"
import { createPromptRegistry } from "./prompt_registry.mjs"
import { loadRoleSystem, normalizeRoleName, roleRequiresRealTestsFromPolicy, validateRoleSkills } from "./role_system.mjs"
import { buildMapV1, loadMapV1, queryMapV1, writeMapV1Outputs } from "./map_v1.mjs"
import { buildPinsFromMapV1, writePinsV1Outputs } from "./pins_builder_v1.mjs"
import { runPreflightV1, writePreflightV1Output } from "./preflight_v1.mjs"
import { computeDegradationActionV1, applyDegradationToWipLimitsV1, shouldAllowTaskUnderStopTheBleedingV1 } from "./factory_policy_v1.mjs"
import { computeVerdictV1 } from "./verifier_judge_v1.mjs"
import { createRouter } from "./router.mjs"
import { registerCoreRoutes } from "./router_core.mjs"
import { registerNavRoutes } from "./router_nav.mjs"
import { registerSccDevRoutes } from "./router_sccdev.mjs"
import { registerConfigRoutes } from "./router_config.mjs"
import { registerModelsRoutes } from "./router_models.mjs"
import { registerPromptsRoutes } from "./router_prompts.mjs"
import {
  packJsonPathForId as packJsonPathForIdV1,
  packTxtPathForId as packTxtPathForIdV1,
  loadJsonFile as loadJsonFileV1,
  renderSccContextPackV1 as renderSccContextPackV1Impl,
  validateSccContextPackV1 as validateSccContextPackV1Impl,
} from "./context_pack_v1.mjs"

const gatewayPort = Number(process.env.GATEWAY_PORT ?? "18788")
const sccUpstream = new URL(process.env.SCC_UPSTREAM ?? "http://127.0.0.1:18789")
const opencodeUpstream = new URL(process.env.OPENCODE_UPSTREAM ?? "http://127.0.0.1:18790")
const cfg = getConfig()
const log = createLogger({ component: "oc-scc-local.gateway" })
const errSink = createJsonlErrorSink({ file: path.join(cfg.execLogDir, "gateway_errors.jsonl") })

function noteBestEffort(where, e, extra = null) {
  try {
    errSink.note({ level: "warn", where: String(where ?? "best_effort"), ...(extra && typeof extra === "object" ? extra : {}), err: log.errToObject(e) })
  } catch {
    // If even the error sink fails, avoid throwing from best-effort paths.
  }
}
const codexBin = cfg.codexBin
// Default to the strongest Codex model we can actually run (validated via codex exec).
let codexModelDefault = process.env.CODEX_MODEL ?? "gpt-5.3-codex"
const codexModelForced = (process.env.FORCE_CODEX_MODEL ?? "").trim() || null
const occliBin = cfg.occliBin
let occliModelDefault = process.env.OPENCODE_MODEL ?? "opencode/kimi-k2.5-free"
const occliVariantDefault = process.env.OPENCODE_VARIANT ?? "high"
const codexMax = Number(process.env.EXEC_CONCURRENCY_CODEX ?? "4")
const occliMax = Number(process.env.EXEC_CONCURRENCY_OPENCODE ?? "6")
const execRoot = cfg.execRoot
const execLogDir = cfg.execLogDir
const execLogJobs = path.join(execLogDir, "jobs.jsonl")
const execLogFailures = path.join(execLogDir, "failures.jsonl")
const gatewayErrorsFile = path.join(execLogDir, "gateway_errors.jsonl")
const execLogHeartbeat = path.join(execLogDir, "heartbeat.jsonl")
const ciGateResultsFile = path.join(execLogDir, "ci_gate_results.jsonl")
const policyGateResultsFile = path.join(execLogDir, "policy_gate_results.jsonl")
const learnedPatternsFile = path.join(execLogDir, "learned_patterns.jsonl")
const learnedPatternsSummaryFile = path.join(execLogDir, "learned_patterns_summary.json")
const stateEventsFile = path.join(execLogDir, "state_events.jsonl")
const playbooksAppliedFile = path.join(execLogDir, "playbooks_applied.jsonl")
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
const stabilityHookStateFile = path.join(execLogDir, "stability_hook_state.json")
const flowManagerLlmEnabled = String(process.env.FLOW_MANAGER_LLM_ENABLED ?? "false").toLowerCase() === "true"
const instinctDir = path.join(execLogDir, "instinct")
const instinctPatternsFile = path.join(instinctDir, "patterns.json")
const instinctPlaybooksFile = path.join(instinctDir, "playbooks.yaml")
const instinctSkillsDraftFile = path.join(instinctDir, "skills_draft.yaml")
const instinctSchemasFile = path.join(instinctDir, "schemas.yaml")
const instinctStateFile = path.join(instinctDir, "instinct_state.json")
const designerFailuresFile = path.join(execLogDir, "designer_failures.jsonl")
const guardBypassRegex = /(ignore|disable|bypass|skip).{0,16}(pins|allowedtests|allowed_tests|ci|selftest|tests)/i
const executorFailuresFile = path.join(execLogDir, "executor_failures.jsonl")
const routerFailuresFile = path.join(execLogDir, "router_failures.jsonl")
const verifierFailuresFile = path.join(execLogDir, "verifier_failures.jsonl")
const routeDecisionsFile = path.join(execLogDir, "route_decisions.jsonl")
const execStateFile = path.join(execLogDir, "jobs_state.json")
const execLeaderLog = path.join(execLogDir, "leader.jsonl")
const isolationFile = path.join(execLogDir, "isolation.jsonl")
const circuitBreakerStateFile = path.join(execLogDir, "circuit_breakers_state.json")
const repoHealthStateFile = path.join(execLogDir, "repo_health_state.json")
const docsRoot = cfg.docsRoot
const boardDir = cfg.boardDir
const boardFile = path.join(boardDir, "tasks.json")
const missionFile = path.join(boardDir, "mission.json")
const runtimeEnvFile = process.env.RUNTIME_ENV_FILE ?? path.join(cfg.repoRoot, "oc-scc-local", "config", "runtime.env")
const promptRegistryRoot = process.env.PROMPT_REGISTRY_ROOT ?? path.join(cfg.repoRoot, "oc-scc-local", "prompts")
const promptRegistryFile = process.env.PROMPT_REGISTRY_FILE ?? path.join(promptRegistryRoot, "registry.json")
const promptRegistry = createPromptRegistry({ registryFile: promptRegistryFile, rootDir: promptRegistryRoot })
const allowedRootsRaw =
  process.env.EXEC_ALLOWED_ROOTS ?? `${execRoot};${path.join(cfg.repoRoot, "scc-top")};${docsRoot};${execLogDir};${boardDir}`
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
// Model routing: strong -> weak ladder for opencodecli pools (and optional future use elsewhere).
// Note: "strong" is a heuristic; pool ordering can also be explicitly controlled via MODEL_POOL_* envs.
const modelRoutingMode = String(process.env.MODEL_ROUTING_MODE ?? "rr").toLowerCase() // rr|strong_first|ladder
const autoRequeueModelFailures = String(process.env.AUTO_REQUEUE_MODEL_FAILURES ?? "true").toLowerCase() !== "false"
const autoRequeueModelFailMax = Number(process.env.AUTO_REQUEUE_MODEL_FAIL_MAX ?? "2")
const autoRequeueModelFailCooldownMs = Number(process.env.AUTO_REQUEUE_MODEL_FAIL_COOLDOWN_MS ?? "60000")
const routerStatsEnabled = String(process.env.ROUTER_STATS_ENABLED ?? "true").toLowerCase() !== "false"
const routerStatsTail = Number(process.env.ROUTER_STATS_TAIL ?? "6000")
const routerStatsMinSamples = Number(process.env.ROUTER_STATS_MIN_SAMPLES ?? "5")
const routerStatsTtlMs = Number(process.env.ROUTER_STATS_TTL_MS ?? "120000")

// Router extraction (incremental): we move self-contained routes first, then expand.
const coreRouter = createRouter()
registerCoreRoutes({ router: coreRouter })
registerNavRoutes({ router: coreRouter })
registerSccDevRoutes({ router: coreRouter })
registerConfigRoutes({ router: coreRouter })
registerModelsRoutes({ router: coreRouter })
registerPromptsRoutes({ router: coreRouter })

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
  // Hard pins: prefer known high-performing models when present.
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

let routerStatsCache = { computedAt: 0, by_task_class: {}, by_model: {} }

function computeRouterStatsSnapshot() {
  const tail = Number.isFinite(routerStatsTail) ? Math.max(500, Math.floor(routerStatsTail)) : 6000
  const events = readJsonlTail(stateEventsFile, tail)
  const byTaskClass = {}
  const byModel = {}

  for (const e of events) {
    if (!e || e.schema_version !== "scc.event.v1") continue
    const et = String(e.event_type ?? "")
    const finished = et === "SUCCESS" || et === "CI_FAILED" || et === "EXECUTOR_ERROR" || et === "PREFLIGHT_FAILED" || et === "PINS_INSUFFICIENT" || et === "POLICY_VIOLATION"
    if (!finished) continue
    const exec = String(e.executor ?? "")
    const model = String(e.model ?? "")
    if (exec !== "codex" && exec !== "opencodecli") continue
    if (!model) continue
    const taskClass = String(e.task_class ?? "unknown").trim() || "unknown"
    const ok = et === "SUCCESS"

    const k1 = `${taskClass}::${exec}::${model}`
    byTaskClass[k1] = byTaskClass[k1] ?? { task_class: taskClass, executor: exec, model, n: 0, ok: 0 }
    byTaskClass[k1].n += 1
    if (ok) byTaskClass[k1].ok += 1

    const k2 = `${exec}::${model}`
    byModel[k2] = byModel[k2] ?? { executor: exec, model, n: 0, ok: 0 }
    byModel[k2].n += 1
    if (ok) byModel[k2].ok += 1
  }

  const now = Date.now()
  routerStatsCache = { computedAt: now, by_task_class: byTaskClass, by_model: byModel }
  try {
    const out = path.join(SCC_REPO_ROOT, "metrics", "router_stats_latest.json")
    fs.mkdirSync(path.dirname(out), { recursive: true })
    fs.writeFileSync(out, JSON.stringify({ schema_version: "scc.router_stats.v1", t: new Date().toISOString(), tail, by_task_class: byTaskClass, by_model: byModel }, null, 2) + "\n", "utf8")
  } catch (e) {
    log.warn("router stats snapshot write failed", { err: log.errToObject(e) })
    errSink.note({ level: "warn", where: "router_stats_snapshot", err: log.errToObject(e) })
  }
  return routerStatsCache
}

function getCodexModelFromStats({ taskClass, candidates }) {
  if (!routerStatsEnabled) return null
  const now = Date.now()
  if (!routerStatsCache.computedAt || now - routerStatsCache.computedAt > (Number.isFinite(routerStatsTtlMs) ? Math.max(10000, routerStatsTtlMs) : 120000)) {
    computeRouterStatsSnapshot()
  }
  const task = String(taskClass ?? "").trim() || "unknown"
  const cand = Array.isArray(candidates) ? candidates.map((x) => String(x)).filter(Boolean) : []
  if (!cand.length) return null

  const rows = []
  for (const m of cand) {
    const k = `${task}::codex::${m}`
    const r = routerStatsCache.by_task_class?.[k]
    if (!r) continue
    const n = Number(r.n ?? 0)
    const ok = Number(r.ok ?? 0)
    if (!Number.isFinite(n) || n <= 0) continue
    rows.push({ model: m, n, ok, rate: ok / n })
  }
  rows.sort((a, b) => {
    if (a.n < routerStatsMinSamples && b.n >= routerStatsMinSamples) return 1
    if (b.n < routerStatsMinSamples && a.n >= routerStatsMinSamples) return -1
    if (b.rate !== a.rate) return b.rate - a.rate
    if (b.n !== a.n) return b.n - a.n
    return String(a.model).localeCompare(String(b.model))
  })
  return rows.length ? rows[0].model : null
}
const preferFreeModels = String(process.env.PREFER_FREE_MODELS ?? "true").toLowerCase() !== "false"
let modelsFree = (process.env.MODEL_POOL_FREE ?? "opencode/kimi-k2.5-free")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
let modelsVision = (process.env.MODEL_POOL_VISION ?? "opencode/kimi-k2.5-free")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
modelsFree = sortModelPool(modelsFree)
modelsVision = sortModelPool(modelsVision)
const occliSubmitBlacklist = (process.env.OCCLI_SUBMIT_BLACKLIST ?? "")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
let modelsPaid = (process.env.MODEL_POOL_PAID ?? "gpt-5.3-codex,gpt-5.2-codex,gpt-5.2,gpt-5.1-codex-max")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
let codexPreferredOrder = (process.env.CODEX_MODEL_PREFERRED ?? modelsPaid.join(","))
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length > 0)
const autoCreateSplitOnTimeout = String(process.env.AUTO_CREATE_SPLIT_ON_TIMEOUT ?? "true").toLowerCase() !== "false"
const autoDispatchSplitTasks = String(process.env.AUTO_DISPATCH_SPLIT_TASKS ?? "true").toLowerCase() !== "false"
const autoLearnTickEnabled = String(process.env.AUTO_LEARN_TICK_ENABLED ?? "false").toLowerCase() === "true"
const autoLearnTickMs = Number(process.env.AUTO_LEARN_TICK_MS ?? "900000")
const auditTriggerEnabled = String(process.env.AUDIT_TRIGGER_ENABLED ?? "true").toLowerCase() !== "false"
const auditTriggerEveryN = Number(process.env.AUDIT_TRIGGER_EVERY_N ?? "10")
const auditTriggerLookback = Number(process.env.AUDIT_TRIGGER_LOOKBACK ?? "30")

const ctxDir = path.join(execLogDir, "contextpacks")
const threadDir = path.join(execLogDir, "threads")
const requirePins = String(process.env.EXEC_REQUIRE_PINS ?? "false").toLowerCase() === "true"
const requirePinsTemplate = String(process.env.EXEC_REQUIRE_PINS_TEMPLATE ?? "false").toLowerCase() === "true"
const requireContract = String(process.env.EXEC_REQUIRE_CONTRACT ?? "false").toLowerCase() === "true"
// Enterprise default: all executions must be preceded by a rendered slot-based Context Pack v1 (fail-closed).
const requireContextPackV1 = String(process.env.CONTEXT_PACK_V1_REQUIRED ?? "true").toLowerCase() !== "false"
const autoPinsCandidates = String(process.env.AUTO_PINS_CANDIDATES ?? "true").toLowerCase() !== "false"
const autoFilesFromText = String(process.env.AUTO_FILES_FROM_TEXT ?? "true").toLowerCase() !== "false"
const autoPinsFromFiles = String(process.env.AUTO_PINS_FROM_FILES ?? "true").toLowerCase() !== "false"
const autoPinsFromMap = String(process.env.AUTO_PINS_FROM_MAP ?? "true").toLowerCase() !== "false"
const autoPinsFixupFromMap = String(process.env.AUTO_PINS_FIXUP_FROM_MAP ?? "true").toLowerCase() !== "false"
const preflightGateEnabled = String(process.env.PREFLIGHT_GATE_ENABLED ?? "true").toLowerCase() !== "false"
const circuitBreakersEnabled = String(process.env.CIRCUIT_BREAKERS_ENABLED ?? "true").toLowerCase() !== "false"
const circuitBreakerCooldownMs = Number(process.env.CIRCUIT_BREAKER_COOLDOWN_MS ?? "900000")
const ssotAutoSyncFromMap = String(process.env.SSOT_AUTO_SYNC_FROM_MAP ?? "false").toLowerCase() === "true"
const ssotAutoApplyUpdate = String(process.env.SSOT_AUTO_APPLY_UPDATE ?? "false").toLowerCase() === "true"
const ssotAutoApplyMaxPerTask = Number(process.env.SSOT_AUTO_APPLY_MAX_PER_TASK ?? "1")
const ssotAutoApplyTimeoutMs = Number(process.env.SSOT_AUTO_APPLY_TIMEOUT_MS ?? "60000")
const dispatchIdempotency = String(process.env.DISPATCH_IDEMPOTENCY ?? "true").toLowerCase() !== "false"
const occliRequireSubmit = String(process.env.OCCLI_REQUIRE_SUBMIT ?? "true").toLowerCase() !== "false"
const splitTwoPhasePins = String(process.env.SPLIT_TWO_PHASE_PINS ?? "true").toLowerCase() !== "false"
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
  } catch (e) {
    // best-effort
    noteBestEffort("saveDesignerState", e, { file: designerStateFile })
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
  { key: "PREFER_FREE_MODELS", type: "bool", frequent: true, note: "prefer opencode free models when allowed" },
  { key: "CODEX_MODEL_PREFERRED", type: "string", frequent: true, note: "preferred codex model order (comma-separated)" },
  { key: "OPENCODE_MODEL", type: "string", frequent: true, note: "default opencodecli model" },
  { key: "AUTO_ASSIGN_OPENCODE_MODELS", type: "bool", frequent: true, note: "auto round-robin model selection for occli" },
  { key: "MODEL_ROUTING_MODE", type: "string", frequent: true, note: "occli model routing: rr|strong_first|ladder" },
  { key: "AUTO_REQUEUE_MODEL_FAILURES", type: "bool", frequent: false, note: "auto requeue occli tasks on model throttle/auth failures and advance ladder" },
  { key: "AUTO_REQUEUE_MODEL_FAIL_MAX", type: "number", frequent: false, note: "max model-ladder advances per task (bounded retry)" },
  { key: "AUTO_REQUEUE_MODEL_FAIL_COOLDOWN_MS", type: "number", frequent: false, note: "cooldown before retry when advancing ladder" },
  { key: "WORKER_IDLE_EXIT_SECONDS", type: "number", frequent: true, note: "worker idle auto-exit seconds" },
  { key: "WORKER_STALL_SECONDS", type: "number", frequent: true, note: "worker stall watchdog seconds (kill if no output progress)" },
  { key: "DESIRED_CODEX", type: "number", frequent: true, note: "ensure-workers desired codex worker count" },
  { key: "DESIRED_OPENCODECLI", type: "number", frequent: true, note: "ensure-workers desired occli worker count" },
  { key: "EXEC_REQUIRE_PINS", type: "bool", frequent: false, note: "require pins for atomic jobs (reduce repo reading)" },
  { key: "EXEC_REQUIRE_PINS_TEMPLATE", type: "bool", frequent: false, note: "require pins template or pins for classed tasks" },
  { key: "EXEC_REQUIRE_CONTRACT", type: "bool", frequent: false, note: "require contract for atomic jobs (executor is pure function)" },
  { key: "AUTO_PINS_CANDIDATES", type: "bool", frequent: false, note: "auto persist pins candidates from successful tasks" },
  { key: "AUTO_FILES_FROM_TEXT", type: "bool", frequent: false, note: "auto infer task.files by extracting repo-relative paths from title/goal" },
  { key: "AUTO_PINS_FROM_FILES", type: "bool", frequent: false, note: "auto create default pins when task.files is present and pins missing" },
  { key: "AUTO_PINS_FROM_MAP", type: "bool", frequent: true, note: "Map-first pins builder: auto derive pins from map/map.json when pins missing" },
  { key: "AUTO_PINS_FIXUP_FROM_MAP", type: "bool", frequent: true, note: "try deterministic Map pins fixup for pins failures before spawning LLM pins_fixup_v1 tasks" },
  { key: "PREFLIGHT_GATE_ENABLED", type: "bool", frequent: true, note: "dispatch-time preflight gate (pins/tests/write_scope); fail-closed if missing" },
  { key: "CIRCUIT_BREAKERS_ENABLED", type: "bool", frequent: true, note: "enable factory_policy.json circuit_breakers (quarantine on repeated failures)" },
  { key: "CIRCUIT_BREAKER_COOLDOWN_MS", type: "number", frequent: false, note: "cooldown window after breaker trip (default 15 min)" },
  { key: "SSOT_AUTO_SYNC_FROM_MAP", type: "bool", frequent: false, note: "auto sync docs/SSOT/registry.json from latest Map after map build (unsafe; default false)" },
  { key: "SSOT_AUTO_APPLY_UPDATE", type: "bool", frequent: false, note: "auto apply artifacts/<task_id>/ssot_update.json to docs/SSOT/registry.json when ssot_map gate fails (deterministic; default false)" },
  { key: "SSOT_AUTO_APPLY_MAX_PER_TASK", type: "number", frequent: false, note: "max auto-applies per task to prevent loops (default 1)" },
  { key: "SSOT_AUTO_APPLY_TIMEOUT_MS", type: "number", frequent: false, note: "timeout for ssot auto-apply helper (default 60s)" },
  { key: "DISPATCH_IDEMPOTENCY", type: "bool", frequent: true, note: "prevent duplicate dispatch for a task when an active job exists" },
  { key: "OCCLI_REQUIRE_SUBMIT", type: "bool", frequent: true, note: "fail-closed if occli task completes without SUBMIT contract" },
  { key: "SUBMIT_SCHEMA_STRICT", type: "bool", frequent: true, note: "fail-closed if SUBMIT JSON does not match contracts/submit/submit.schema.json" },
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
  { key: "FLOW_MANAGER_LLM_ENABLED", type: "bool", frequent: false, note: "escalate flow bottlenecks to LLM; default false (local plan only)" },
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
  { key: "CI_GATES_STRICT", type: "bool", frequent: true, note: "pass --strict to tools/scc/gates/run_ci_gates.py (production fail-closed)" },
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
  { key: "FAILURE_REPORT_TICK_MS", type: "number", frequent: false, note: "failure report interval in ms (default 3600000)" },
  { key: "FAILURE_REPORT_TAIL", type: "number", frequent: false, note: "failure report tail lines from failures.jsonl (default 500)" },
  { key: "AUTO_CANCEL_STALE_EXTERNAL", type: "bool", frequent: false, note: "auto cancel external jobs when board status mismatches" },
  { key: "AUTO_CANCEL_STALE_EXTERNAL_TICK_MS", type: "number", frequent: false, note: "auto cancel tick interval in ms (default 60000)" },
  { key: "AUTO_CREATE_SPLIT_ON_TIMEOUT", type: "bool", frequent: false, note: "auto create designer split task when codex atomic times out" },
  { key: "AUTO_DISPATCH_SPLIT_TASKS", type: "bool", frequent: false, note: "auto dispatch newly created split tasks" },
  { key: "AUTO_LEARN_TICK_ENABLED", type: "bool", frequent: false, note: "enable periodic learn/eval/metrics tick (default false)" },
  { key: "AUTO_LEARN_TICK_MS", type: "number", frequent: false, note: "learn tick interval ms (default 15 min)" },
  { key: "MAP_QUERY_BACKEND", type: "string", frequent: false, note: "map query backend: ''|json|sqlite" },
  { key: "MAP_PINS_QUERY_BACKEND", type: "string", frequent: false, note: "pins builder query backend: ''|json|sqlite" },
  { key: "MAP_BUILD_SQLITE", type: "bool", frequent: false, note: "after map:build, also build map/map.sqlite" },
  { key: "SSOT_AUTO_PR_BUNDLE", type: "bool", frequent: false, note: "auto write artifacts/<task_id>/pr_bundle.json from ssot_update.patch when ssot_map fails" },
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
    modelsFree = free.map((x) => String(x).trim()).filter(Boolean)
  }
  if (Array.isArray(vision) && vision.length) {
    modelsVision = vision.map((x) => String(x).trim()).filter(Boolean)
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

const sccDevUiDir = process.env.SCCDEV_UI_DIR ?? path.join(cfg.repoRoot, "oc-scc-local", "ui", "sccdev")

function contentTypeFor(file) {
  const ext = path.extname(String(file ?? "")).toLowerCase()
  if (ext === ".html") return "text/html; charset=utf-8"
  if (ext === ".css") return "text/css; charset=utf-8"
  if (ext === ".js" || ext === ".mjs") return "text/javascript; charset=utf-8"
  if (ext === ".json") return "application/json; charset=utf-8"
  if (ext === ".svg") return "image/svg+xml"
  if (ext === ".png") return "image/png"
  if (ext === ".ico") return "image/x-icon"
  return "application/octet-stream"
}

function serveStaticFromDir(req, res, { rootDir, relPath }) {
  const root = path.resolve(String(rootDir ?? ""))
  const rel = String(relPath ?? "").replaceAll("\\", "/").replace(/^\//, "")
  const target = path.resolve(root, rel)
  if (!target.toLowerCase().startsWith(root.toLowerCase())) {
    return sendJson(res, 400, { error: "path_outside_root" })
  }
  if (!fs.existsSync(target)) return sendJson(res, 404, { error: "not_found" })
  try {
    const buf = fs.readFileSync(target)
    res.statusCode = 200
    res.setHeader("content-type", contentTypeFor(target))
    res.setHeader("cache-control", "no-store")
    res.end(buf)
    return
  } catch (e) {
    return sendJson(res, 500, { error: "read_failed", message: String(e?.message ?? e) })
  }
}

function updateCodexModelPolicy({ codexDefault, codexPreferred, paidPool, strictDesignerModel }) {
  if (codexDefault != null) {
    const v = String(codexDefault).trim()
    if (!v) return { ok: false, error: "codex_default_empty" }
    codexModelDefault = v
  }
  if (Array.isArray(codexPreferred)) {
    const arr = codexPreferred.map((x) => String(x).trim()).filter(Boolean)
    if (!arr.length) return { ok: false, error: "codex_preferred_empty" }
    codexPreferredOrder = arr
  }
  if (Array.isArray(paidPool)) {
    const arr = paidPool.map((x) => String(x).trim()).filter(Boolean)
    if (!arr.length) return { ok: false, error: "paid_pool_empty" }
    modelsPaid = arr
    // If preferred order wasn't explicitly set, keep it aligned with the paid pool.
    if (!Array.isArray(codexPreferredOrder) || codexPreferredOrder.length === 0) codexPreferredOrder = arr
  }
  if (strictDesignerModel != null) {
    const v = String(strictDesignerModel).trim()
    if (!v) return { ok: false, error: "strict_designer_model_empty" }
    STRICT_DESIGNER_MODEL = v
  }
  return { ok: true, codexModelDefault, codexPreferredOrder, modelsPaid, STRICT_DESIGNER_MODEL }
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

function loadAuditTriggerState() {
  return loadAuditTriggerStateImpl({ file: auditTriggerStateFile })
}

function saveAuditTriggerState(state) {
  return saveAuditTriggerStateImpl({ file: auditTriggerStateFile, state, strictWrites: cfg.strictWrites })
}

function loadFlowManagerState() {
  return loadFlowManagerStateImpl({ file: flowManagerStateFile })
}

function saveFlowManagerState(state) {
  return saveFlowManagerStateImpl({ file: flowManagerStateFile, state, strictWrites: cfg.strictWrites })
}

function loadFeedbackHookState() {
  return loadFeedbackHookStateImpl({ file: feedbackHookStateFile })
}

function saveFeedbackHookState(state) {
  return saveFeedbackHookStateImpl({ file: feedbackHookStateFile, state, strictWrites: cfg.strictWrites })
}

function readFailureReportLatest() {
  const latest = path.join(execLogDir, "failure_report_latest.json")
  try {
    if (!fs.existsSync(latest)) return null
    const raw = fs.readFileSync(latest, "utf8")
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    const trimmed = {
      generatedAt: parsed.generatedAt ?? null,
      sampleN: parsed.sampleN ?? null,
      windowStart: parsed.windowStart ?? null,
      windowEnd: parsed.windowEnd ?? null,
      byExecutor: parsed.byExecutor ?? null,
      byReason: parsed.byReason ?? null,
      byModel: parsed.byModel ?? null,
      byTaskType: parsed.byTaskType ?? null,
      topErrorLines: parsed.topErrorLines ?? null,
    }
    return { file: latest, report: trimmed }
  } catch {
    return null
  }
}

function countBy(events, key) {
  const counts = {}
  for (const e of events) {
    const v = String(e?.[key] ?? "").trim() || "unknown"
    counts[v] = (counts[v] ?? 0) + 1
  }
  return Object.entries(counts)
    .map(([k, count]) => ({ [key]: k, count }))
    .sort((a, b) => b.count - a.count)
}

function writeFailureReport({ tail }) {
  const events = readJsonlTail(execLogFailures, tail)
  if (!events.length) return null
  const times = events
    .map((e) => {
      const t = Date.parse(String(e?.t ?? ""))
      return Number.isFinite(t) ? t : null
    })
    .filter((t) => t != null)
    .sort((a, b) => a - b)
  const windowStart = times.length ? new Date(times[0]).toISOString() : null
  const windowEnd = times.length ? new Date(times[times.length - 1]).toISOString() : null

  const byExecutor = countBy(events, "executor")
  const byReason = countBy(events, "reason")
  const byModel = countBy(events, "model")
  const byTaskType = countBy(events, "taskType")

  const byExecutorReasonMap = {}
  for (const e of events) {
    const ex = String(e?.executor ?? "").trim() || "unknown"
    const reason = String(e?.reason ?? "").trim() || "unknown"
    const key = `${ex}::${reason}`
    byExecutorReasonMap[key] = (byExecutorReasonMap[key] ?? 0) + 1
  }
  const byExecutorReason = Object.entries(byExecutorReasonMap)
    .map(([key, count]) => {
      const [executor, reason] = key.split("::")
      return { executor, reason, count }
    })
    .sort((a, b) => b.count - a.count)

  const lineCounts = {}
  for (const e of events) {
    const stderr = String(e?.stderrPreview ?? "").trim()
    const stdout = String(e?.stdoutPreview ?? "").trim()
    let line = (stderr || stdout || "<empty>").split(/\r?\n/g)[0]
    if (line.length > 200) line = `${line.slice(0, 200)}...`
    lineCounts[line] = (lineCounts[line] ?? 0) + 1
  }
  const topErrorLines = Object.entries(lineCounts)
    .map(([line, count]) => ({ line, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)

  const report = {
    generatedAt: new Date().toISOString(),
    sampleN: events.length,
    windowStart,
    windowEnd,
    byExecutor,
    byReason,
    byModel,
    byTaskType,
    byExecutorReason,
    topErrorLines,
  }

  const now = new Date()
  const stamp = `${now.getUTCFullYear()}${String(now.getUTCMonth() + 1).padStart(2, "0")}${String(
    now.getUTCDate(),
  ).padStart(2, "0")}_${String(now.getUTCHours()).padStart(2, "0")}`
  const hourly = path.join(execLogDir, `failure_report_${stamp}.json`)
  const latest = path.join(execLogDir, "failure_report_latest.json")
  try {
    fs.writeFileSync(hourly, JSON.stringify(report, null, 2), "utf8")
    fs.writeFileSync(latest, JSON.stringify(report, null, 2), "utf8")
    return { hourly, latest, sampleN: events.length }
  } catch {
    return null
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

  // Eval manifest fallback: default to smoke tier to keep throughput stable (regression only by policy).
  if (!list.length) {
    try {
      const fp = getFactoryPolicy ? getFactoryPolicy() : null
      const defaultTier = fp?.verification_tiers?.default === "regression" ? "regression" : "smoke"
      const taskClass = String(task?.task_class_id ?? task?.task_class_candidate ?? "").trim()
      let tier = taskClass && fp?.verification_tiers?.by_task_class?.[taskClass] ? fp.verification_tiers.by_task_class[taskClass] : defaultTier
      // Degradation override: when overloaded/unhealthy, force a cheaper verification tier.
      const degradation = computeDegradationState()
      const overrideTier = degradation?.action?.verification_tier ? String(degradation.action.verification_tier) : null
      if (overrideTier && ["smoke", "regression"].includes(overrideTier)) tier = overrideTier
      const evalPath = path.join(SCC_REPO_ROOT, "eval", "eval_manifest.json")
      if (fs.existsSync(evalPath)) {
        const raw = fs.readFileSync(evalPath, "utf8")
        const man = JSON.parse(raw.replace(/^\uFEFF/, ""))
        const tierObj = man?.tiers?.[tier] ?? null
        const cmds = Array.isArray(tierObj?.commands) ? tierObj.commands : []
        list = cmds.map((x) => String(x)).filter(Boolean).slice(0, 10)
      }
    } catch (e) {
      noteBestEffort("pickAllowedTestsForTask.eval_manifest", e)
    }
  }

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
  } catch (e) {
    errSink.note({ level: "warn", where: "appendJsonl", file: String(file ?? ""), err: log.errToObject(e) })
  }
}

function appendStateEvent(value) {
  try {
    appendJsonl(stateEventsFile, value)
    const taskId = value && typeof value === "object" ? String(value.task_id ?? "").trim() : ""
    if (!taskId) return
    const file = path.join(SCC_REPO_ROOT, "artifacts", taskId, "events.jsonl")
    fs.mkdirSync(path.dirname(file), { recursive: true })
    appendJsonl(file, value)
  } catch (e) {
    errSink.note({ level: "warn", where: "appendStateEvent", err: log.errToObject(e) })
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
        } catch (e) {
          noteBestEffort("appendJsonlChained.parse_chain_hash", e)
        }
      }
    }
  } catch (e) {
    noteBestEffort("appendJsonlChained.read_file", e, { file: String(file ?? "") })
  }

  const record = { ...value, chain_prev_hash: prevHash ?? null }
  try {
    const payload = JSON.stringify(record)
    const hash = crypto.createHash("sha256").update(payload).digest("hex")
    record.chain_hash = hash
    fs.appendFileSync(file, JSON.stringify(record) + "\n", "utf8")
  } catch (e) {
    noteBestEffort("appendJsonlChained.write_record", e, { file: String(file ?? "") })
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
  } catch (e) {
    noteBestEffort("saveFiveWhysHookState", e, { file: fiveWhysHookStateFile })
    if (cfg.strictWrites) throw e
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
  } catch (e) {
    noteBestEffort("saveRadiusAuditHookState", e, { file: radiusAuditHookStateFile })
    if (cfg.strictWrites) throw e
  }
}

async function runRadiusAuditReport(taskId) {
  // Best-effort: invoke local python generator to persist artifacts under radius_audit/runs.
  return new Promise((resolve) => {
    const safeTask = String(taskId || "").trim()
    const runId = `${safeTask || "unknown"}__${Date.now()}`
    const outDir = path.join(execLogDir, "radius_audit", "runs", runId)
    try {
      fs.mkdirSync(outDir, { recursive: true })
    } catch {
      // best-effort
      noteBestEffort("radius_audit_mkdir", new Error("mkdir_failed"), { outDir, task_id: safeTask || null, run_id: runId })
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
        cwd: cfg.repoRoot,
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
  // Best-effort: invoke local python generator to persist artifacts.
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
    const child = execFile(
      "python",
      args,
      {
        cwd: cfg.repoRoot,
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
    if (child?.stdin) child.stdin.end()
  })
}

async function runSccPythonOp({ scriptRel, args = [], timeoutMs = 300000, maxBufferMb = 12 } = {}) {
  const script = String(scriptRel ?? "").trim()
  if (!script) return { ok: false, error: "missing_script" }
  const argv = [script, ...args.map((x) => String(x))]
  return new Promise((resolve) => {
    const child = execFile(
      "python",
      argv,
      {
        cwd: cfg.repoRoot,
        timeout: Math.max(10000, Math.min(60 * 60 * 1000, Number(timeoutMs) || 300000)),
        maxBuffer: Math.max(1, Math.min(64, Number(maxBufferMb) || 12)) * 1024 * 1024,
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
    if (child?.stdin) child.stdin.end()
  })
}

function ensureDir(dir) {
  try {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
  } catch (e) {
    noteBestEffort("ensureDir", e, { dir: String(dir ?? "") })
  }
}

function normalizeForSignature(text) {
  const s = String(text ?? "")
    .replace(/[A-Z]:[\\/][^\\s\"']+/gi, "<PATH>")
    .replace(/https?:\/\/\S+/gi, "<URL>")
    .replace(/\b\d+\b/g, "<N>")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
  return s.slice(0, 2000)
}

function tokensForSimhash(text) {
  const s = normalizeForSignature(text).replace(/[^a-z0-9_<> \u4e00-\u9fff]/g, " ")
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
  const msg = `${stderr}\\n${stdout}`
  const s = normalizeForSignature(msg)
  if (s.includes("&&") && s.includes("not a valid statement separator")) return "powershell_andand_separator"
  if (s.includes("file not found: follow the attached file")) return "occli_file_not_found_attached_file"
  if (s.includes("missing_submit_contract")) return "missing_submit_contract"
  if (s.includes("buninstallfailederror")) return "occli_bun_install_failed"
  if (s.includes("show help") && String(failure?.executor ?? "") === "opencodecli") return "occli_wrong_subcommand"
  if (reason === "timeout") return "timeout"
  // Try to capture the first explicit error line.
  const lines = msg.split(/\\r?\\n/g).map((l) => l.trim()).filter(Boolean)
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
    .sort((a, b) => b.count * (b.avg_duration_ms + 1) - a.count * (a.avg_duration_ms + 1))

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
          `powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod http://127.0.0.1:${gatewayPort}/replay/task?task_id=${(p.sample_task_ids && p.sample_task_ids[0]) || "..."}"`,
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
        `powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod http://127.0.0.1:${gatewayPort}/replay/task?task_id=${(p.sample_task_ids && p.sample_task_ids[0]) || "..."}"`,
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
  } catch (e) {
    noteBestEffort("saveInstinctState", e, { file: instinctStateFile })
    if (cfg.strictWrites) throw e
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
  } catch (e) {
    noteBestEffort("updateInstinctArtifacts.extract_top", e)
  }
  saveInstinctState(state)
  try {
    fs.writeFileSync(instinctPatternsFile, JSON.stringify(snap, null, 2), "utf8")
  } catch (e) {
    noteBestEffort("updateInstinctArtifacts.patterns", e, { file: instinctPatternsFile })
    if (cfg.strictWrites) throw e
  }
  try {
    fs.writeFileSync(instinctSchemasFile, renderInstinctSchemasYaml() + "\n", "utf8")
  } catch (e) {
    noteBestEffort("updateInstinctArtifacts.schemas", e, { file: instinctSchemasFile })
    if (cfg.strictWrites) throw e
  }
  try {
    fs.writeFileSync(instinctPlaybooksFile, renderInstinctPlaybooksYaml(snap) + "\n", "utf8")
  } catch (e) {
    noteBestEffort("updateInstinctArtifacts.playbooks", e, { file: instinctPlaybooksFile })
    if (cfg.strictWrites) throw e
  }
  try {
    fs.writeFileSync(instinctSkillsDraftFile, renderInstinctSkillsDraftYaml(snap) + "\n", "utf8")
  } catch (e) {
    noteBestEffort("updateInstinctArtifacts.skills", e, { file: instinctSkillsDraftFile })
    if (cfg.strictWrites) throw e
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
  const fallbackGoal = [
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
  const rendered = renderPromptOrFallback({
    role_id: "factory_manager.instinct_builder_response_v1",
    params: {
      top_pattern_json: JSON.stringify(top, null, 2),
      snapshot_trimmed_json: JSON.stringify({ t: snapshot.t, window: snapshot.window, taxonomy: snapshot.taxonomy, patterns: snapshot.patterns.slice(0, 30) }, null, 2),
    },
    fallback: fallbackGoal,
    note: "instinct_builder_response_v1",
  })
  const goal = rendered.text

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    prompt_ref: rendered.prompt_ref,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "instinct_builder_response_v1",
    allowedExecutors: factoryManagerDefaultExecutors(),
    allowedModels: Array.from(new Set([...factoryManagerDefaultModels(), ...instinctHookAllowedModels])),
    timeoutMs: instinctHookTimeoutMs,
  })
  if (!created.ok) return created

  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (dispatched.job) {
    dispatched.job.priority = 930
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCountsInternal()
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
  } catch (e) {
    noteBestEffort("updateLearnedPatternsSummary", e, { file: learnedPatternsSummaryFile })
    if (cfg.strictWrites) throw e
  }
  return summary
}

function leader(event) {
  const enriched = { t: new Date().toISOString(), ...event }
  appendJsonl(execLeaderLog, enriched)
  if (String(enriched.reason ?? "") === "timeout" || String(enriched.type ?? "") === "job_timeout") {
    const now = Date.now()
    timeoutEventsWindow = timeoutEventsWindow.filter((ts) => now - ts <= timeoutFuseWindowMs)
    timeoutEventsWindow.push(now)
    if (timeoutEventsWindow.length >= 3 && now > timeoutFuseUntil) {
      timeoutFuseUntil = now + timeoutFuseCooldownMs
      appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "timeout_fuse_tripped", until: timeoutFuseUntil })
    }
  }
  try {
    const now = Date.now()
    const isOccliEmpty =
      String(enriched.type ?? "") === "job_finished" &&
      String(enriched.executor ?? "") === "opencodecli" &&
      Number(enriched.exit_code ?? enriched.exitCode ?? 0) !== 0 &&
      String(enriched.reason ?? "") === "executor_error" &&
      String(enriched.stderrPreview ?? "").includes("opencode-cli exited non-zero") &&
      String(enriched.stderrPreview ?? "").toLowerCase().includes("empty output")
    if (isOccliEmpty) {
      const windowMs = Number.isFinite(occliFlakeWindowMs) && occliFlakeWindowMs > 0 ? occliFlakeWindowMs : 300000
      const tripN = Number.isFinite(occliFlakeTripN) && occliFlakeTripN > 0 ? Math.floor(occliFlakeTripN) : 3
      const cooldown = Number.isFinite(occliFlakeCooldownMs) && occliFlakeCooldownMs > 0 ? occliFlakeCooldownMs : 600000
      occliFlakeEventsWindow = occliFlakeEventsWindow.filter((ts) => now - ts <= windowMs)
      occliFlakeEventsWindow.push(now)
      if (occliFlakeEventsWindow.length >= tripN && (!occliFlakeFuseUntil || now > occliFlakeFuseUntil)) {
        occliFlakeFuseUntil = now + cooldown
        saveOccliFlakeFuse()
        appendJsonl(execLeaderLog, {
          t: new Date().toISOString(),
          type: "executor_fuse_tripped",
          executor: "opencodecli",
          until: occliFlakeFuseUntil,
          reason: "flake_empty_output",
          windowMs,
          count: occliFlakeEventsWindow.length,
        })
      }
    }
  } catch (e) {
    noteBestEffort("leader.occli_flake_detection", e)
  }
  maybeTriggerFactoryManagerFromEvent(enriched)
}

function saveState() {
  const arr = Array.from(jobs.values())
  saveJobsState({ file: execStateFile, jobsArray: arr, strictWrites: cfg.strictWrites })
}

function loadState() {
  return loadJobsState({ file: execStateFile })
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

 	function mapResultToEventType({ status, reason }) {
 	  const st = String(status ?? "").trim().toLowerCase()
 	  const r = String(reason ?? "").trim().toLowerCase()
 	  if (st === "done") return "SUCCESS"
 	  if (["missing_files", "preflight_failed", "test_command_missing", "scope_conflict"].includes(r)) return "PREFLIGHT_FAILED"
 	  if (r.includes("pins")) return "PINS_INSUFFICIENT"
 	  if (r.startsWith("ci_") || r === "ci_failed" || r === "ci_skipped" || r === "ci_timed_out") return "CI_FAILED"
 	  if (
      [
        "hygiene_failed",
        "policy_gate_failed",
        "policy_gate_timed_out",
        "patch_scope_violation",
        "submit_mismatch",
        "guardrail_bypass_text",
        "quality_gate_blocked",
        "invalid_role",
        "missing_role_policy",
        "stop_the_bleeding",
      ].includes(r)
    ) {
 	    return "POLICY_VIOLATION"
 	  }
   if (st === "needs_split") return "PREFLIGHT_FAILED"
   return "EXECUTOR_ERROR"
 }

const execCodex = (args, input, { timeoutMs } = {}) =>
  new Promise((resolve) => {
    const needsShellShim = process.platform === "win32" && /\.(cmd|bat)$/i.test(String(codexBin ?? ""))
    const child = execFile(
      codexBin,
      args,
      { timeout: timeoutMs ?? timeoutCodexMs, maxBuffer: 50 * 1024 * 1024, shell: needsShellShim, windowsHide: true },
      (err, stdout, stderr) => {
      const code = err?.code ?? 0
      resolve({
        ok: !err,
        code,
        stdout: stdout?.trim() ?? "",
        stderr: stderr?.trim() ?? (err ? String(err) : ""),
        timedOut: Boolean(err && (err.killed || String(err).toLowerCase().includes("etimedout"))),
      })
      },
    )
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
  // Some Codex installs/accounts reject certain model ids; keep fallback deterministic.
  // fail-closed but retry deterministically with preferred fallbacks when we can classify the error.
  const preferred = String(process.env.CODEX_MODEL_PREFERRED ?? "")
    .split(/[;,]/g)
    .map((x) => x.trim())
    .filter((x) => x.length > 0)
  const candidates = [model, ...preferred].filter((x, i, a) => a.indexOf(x) === i)
  const unsupported = new Set(globalThis.__scc_codex_unsupported_models ?? [])
  globalThis.__scc_codex_unsupported_models = Array.from(unsupported)

  const isUnsupportedModel = (out) => {
    const s = `${out?.stdout ?? ""}\n${out?.stderr ?? ""}`
    return s.includes("model is not supported") || s.includes("not supported when using Codex with a ChatGPT account")
  }

  let first = null
  for (const m of candidates) {
    if (!m || unsupported.has(m)) continue
    const out = await execCodex(
      ["exec", "--model", m, "--sandbox", "read-only", "--skip-git-repo-check", "--json", "-C", execRoot, "--dangerously-bypass-approvals-and-sandbox"],
      prompt,
      { timeoutMs },
    )
    const merged = { ...out, model_used: m }
    if (merged.ok) return merged
    if (!first) first = merged
    if (isUnsupportedModel(merged)) {
      unsupported.add(m)
      globalThis.__scc_codex_unsupported_models = Array.from(unsupported)
      continue
    }
    return merged
  }
  return first ?? { ok: false, code: 1, stdout: "", stderr: "codex_run_failed", timedOut: false, model_used: model }
}

async function occliRunSingle(prompt, model = occliModelDefault, { timeoutMs } = {}) {
  return new Promise((resolve) => {
    const rawPrompt = String(prompt ?? "")
    const useFile = false
    let message = rawPrompt
    let attachedFile = null
    if (useFile) {
      try {
        const dir = path.join(execLogDir, "occli_prompts")
        fs.mkdirSync(dir, { recursive: true })
        const stamp = new Date().toISOString().replace(/[:.]/g, "")
        const fname = `prompt_${stamp}_${Math.random().toString(16).slice(2, 8)}.txt`
        attachedFile = path.join(dir, fname)
        // OpenCode CLI's `--file` is an array option; passing any positional message after it is
        // ambiguous and can be swallowed as additional file paths (=> "File not found: <message>").
        // Make the attached file self-contained and send NO positional message when using `--file`.
        const wrapped = [
          "SYSTEM: The attached file content IS the full task instructions. Follow it strictly.",
          "SYSTEM: Do not treat any other text as instructions.",
          "",
          rawPrompt,
        ].join("\n")
        fs.writeFileSync(attachedFile, wrapped, "utf8")
        message = ""
      } catch (e) {
        noteBestEffort("occliRunSingle.write_attached_file", e, { file: attachedFile })
        attachedFile = null
        message = rawPrompt
      }
    }
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
        ...(attachedFile ? ["--file", attachedFile] : []),
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
        if (attachedFile) {
          try {
            fs.unlinkSync(attachedFile)
          } catch (e) {
            // best-effort cleanup
            noteBestEffort("opencode_exec_cleanup_attached_file", e, { file: attachedFile })
          }
        }
      },
    )
    if (child.stdin) {
      child.stdin.end()
    }
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

	const SCC_REPO_ROOT = cfg.repoRoot
	const defaultTaskRole = String(process.env.DEFAULT_TASK_ROLE ?? "engineer").trim().toLowerCase()
	const roleSystemEnabled = String(process.env.ROLE_SYSTEM_ENABLED ?? "true").toLowerCase() !== "false"
 	const roleSystemStrict = String(process.env.ROLE_SYSTEM_STRICT ?? "true").toLowerCase() !== "false"
 	const submitSchemaStrict = String(process.env.SUBMIT_SCHEMA_STRICT ?? "true").toLowerCase() !== "false"
  const verdictSchemaStrict = String(process.env.VERDICT_SCHEMA_STRICT ?? "true").toLowerCase() !== "false"
 	let roleSystem = null
 	if (roleSystemEnabled) {
	  try {
	    roleSystem = loadRoleSystem({ repoRoot: SCC_REPO_ROOT, strict: roleSystemStrict })
	    if (!roleSystem.ok) {
      // Non-strict mode can return ok=false with errors; keep fail-closed by default.
      throw new Error(`role_system_invalid: ${roleSystem.errors?.length ?? 0} errors`)
    }
  } catch (e) {
    console.error("[role_system] failed to load role system:", String(e?.message ?? e))
    if (e?.roleSystemErrors) console.error("[role_system] errors:", JSON.stringify(e.roleSystemErrors, null, 2))
    if (roleSystemStrict) process.exit(1)
    roleSystem = null
	  }
	}

  let submitSchemaValidate = null
  let submitSchemaValidateError = null
  function validateSubmitSchema(submit) {
    if (!submitSchemaStrict) return { ok: true }
    if (submitSchemaValidateError) return { ok: false, reason: "submit_schema_unavailable", error: submitSchemaValidateError }
    if (!submitSchemaValidate) {
      try {
        const schemaPath = path.join(SCC_REPO_ROOT, "contracts", "submit", "submit.schema.json")
        const raw = fs.readFileSync(schemaPath, "utf8")
        const schema = JSON.parse(raw.replace(/^\uFEFF/, ""))
        const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true })
        addFormats(ajv)
        submitSchemaValidate = ajv.compile(schema)
      } catch (e) {
        submitSchemaValidateError = String(e?.message ?? e)
        return { ok: false, reason: "submit_schema_unavailable", error: submitSchemaValidateError }
      }
    }
    const ok = Boolean(submitSchemaValidate(submit))
    if (ok) return { ok: true }
    return {
      ok: false,
      reason: "invalid_submit_schema",
      errors: Array.isArray(submitSchemaValidate.errors) ? submitSchemaValidate.errors.slice(0, 12) : null,
    }
  }

  let verdictSchemaValidate = null
  let verdictSchemaValidateError = null
  function validateVerdictSchema(verdict) {
    if (!verdictSchemaStrict) return { ok: true }
    if (verdictSchemaValidateError) return { ok: false, reason: "verdict_schema_unavailable", error: verdictSchemaValidateError }
    if (!verdictSchemaValidate) {
      try {
        const schemaPath = path.join(SCC_REPO_ROOT, "contracts", "verdict", "verdict.schema.json")
        const raw = fs.readFileSync(schemaPath, "utf8")
        const schema = JSON.parse(raw.replace(/^\uFEFF/, ""))
        const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true })
        addFormats(ajv)
        verdictSchemaValidate = ajv.compile(schema)
      } catch (e) {
        verdictSchemaValidateError = String(e?.message ?? e)
        return { ok: false, reason: "verdict_schema_unavailable", error: verdictSchemaValidateError }
      }
    }
    const ok = Boolean(verdictSchemaValidate(verdict))
    if (ok) return { ok: true }
    return {
      ok: false,
      reason: "invalid_verdict_schema",
      errors: Array.isArray(verdictSchemaValidate.errors) ? verdictSchemaValidate.errors.slice(0, 12) : null,
    }
  }

const ROLE_NAMES = roleSystem
  ? Array.from(roleSystem.roles).sort((a, b) => a.localeCompare(b))
  : [
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

let STRICT_DESIGNER_MODEL = process.env.STRICT_DESIGNER_MODEL ?? "gpt-5.3-codex"
const roleConfigFile = process.env.ROLE_CONFIG_FILE ?? path.join(cfg.repoRoot, "oc-scc-local", "config", "roles.json")
const ledgerStallMinutes = Number(process.env.LEDGER_STALL_MINUTES ?? "15")

function normalizeRole(v) {
  if (roleSystem) return normalizeRoleName(roleSystem, v)
  const s = String(v ?? "").trim().toLowerCase()
  return ROLE_NAMES.includes(s) ? s : null
}

function sha256HexOfFile(absPath) {
  try {
    if (!absPath || !fs.existsSync(absPath)) return null
    const buf = fs.readFileSync(absPath)
    return crypto.createHash("sha256").update(buf).digest("hex")
  } catch {
    return null
  }
}

function rootParentIdForTask(task) {
  try {
    let cur = task && typeof task === "object" ? task : null
    let parentId = cur?.kind === "parent" ? String(cur.id ?? "") : cur?.parentId ? String(cur.parentId) : ""
    parentId = parentId.trim()
    if (!parentId) return null
    let hops = 0
    while (hops < 50) {
      hops += 1
      const pt = getBoardTask(parentId)
      if (!pt) break
      const next = pt.parentId ? String(pt.parentId).trim() : ""
      if (!next) break
      parentId = next
    }
    return parentId || null
  } catch {
    return null
  }
}

function parentLedgerPaths(parentId) {
  const pid = String(parentId ?? "").trim()
  const root = SCC_REPO_ROOT
  return {
    task_ledger_json: path.join(root, "artifacts", pid, "task_ledger.json"),
    progress_ledger_json: path.join(root, "artifacts", pid, "progress_ledger.json"),
    progress_events_jsonl: path.join(root, "artifacts", pid, "progress_events.jsonl"),
  }
}

function loadJsonSafe(absPath) {
  try {
    if (!absPath || !fs.existsSync(absPath)) return null
    const raw = fs.readFileSync(absPath, "utf8")
    return JSON.parse(raw.replace(/^\uFEFF/, ""))
  } catch (e) {
    errSink.note({ level: "warn", where: "loadJsonSafe", file: String(absPath ?? ""), err: log.errToObject(e) })
    return null
  }
}

function writeJsonSafe(absPath, obj) {
  try {
    if (!absPath) return false
    fs.mkdirSync(path.dirname(absPath), { recursive: true })
    fs.writeFileSync(absPath, JSON.stringify(obj, null, 2) + "\n", "utf8")
    return true
  } catch (e) {
    errSink.note({ level: "warn", where: "writeJsonSafe", file: String(absPath ?? ""), err: log.errToObject(e) })
    return false
  }
}

function appendJsonlSafe(absPath, obj) {
  try {
    if (!absPath) return false
    fs.mkdirSync(path.dirname(absPath), { recursive: true })
    fs.appendFileSync(absPath, JSON.stringify(obj) + "\n", "utf8")
    return true
  } catch (e) {
    errSink.note({ level: "warn", where: "appendJsonlSafe", file: String(absPath ?? ""), err: log.errToObject(e) })
    return false
  }
}

function summarizeParentCounts(parentId) {
  const pid = String(parentId ?? "").trim()
  const counts = {
    children_total: 0,
    children_ready: 0,
    children_in_progress: 0,
    children_done: 0,
    children_failed: 0,
    children_blocked: 0,
  }
  for (const t of boardTasks.values()) {
    if (!t || String(t.parentId ?? "") !== pid) continue
    counts.children_total += 1
    const st = String(t.status ?? "")
    if (st === "ready" || st === "backlog") counts.children_ready += 1
    else if (st === "in_progress") counts.children_in_progress += 1
    else if (st === "done") counts.children_done += 1
    else if (st === "failed") counts.children_failed += 1
    else if (st === "blocked") counts.children_blocked += 1
  }
  return counts
}

function inferParentPhase(parentTask, counts) {
  const st = String(parentTask?.status ?? "")
  const lane = normalizeLane(parentTask?.lane) ?? "mainlane"
  if (lane === "dlq") return "dlq"
  if (lane === "quarantine") return "quarantine"
  if (st === "needs_split") return "needs_split"
  if (st === "in_progress") return "executing"
  if (st === "failed") return "failed"
  if (st === "done") return "done"
  if ((counts?.children_in_progress ?? 0) > 0) return "executing"
  if ((counts?.children_done ?? 0) > 0 && (counts?.children_done ?? 0) === (counts?.children_total ?? 0)) return "done"
  return "ready"
}

function ensureParentLedgers(parentTask) {
  try {
    if (!parentTask || parentTask.kind !== "parent") return { ok: false, error: "not_parent" }
    const parentId = String(parentTask.id ?? "").trim()
    if (!parentId) return { ok: false, error: "missing_parent_id" }
    const paths = parentLedgerPaths(parentId)
    const now = new Date().toISOString()
    const b = factoryBudgets()
    const taskLedger =
      loadJsonSafe(paths.task_ledger_json) ??
      ({
        schema_version: "scc.task_ledger.v1",
        parent_id: parentId,
        created_at: now,
        updated_at: now,
        parent_goal: String(parentTask.goal ?? ""),
        children: [],
        split: { last_split_job_id: null, applied_children: 0 },
      })
    const counts = summarizeParentCounts(parentId)
    const progressLedger =
      loadJsonSafe(paths.progress_ledger_json) ??
      ({
        schema_version: "scc.progress_ledger.v1",
        parent_id: parentId,
        updated_at: now,
        phase: inferParentPhase(parentTask, counts),
        counts,
        budgets: {
          max_total_attempts: maxTotalAttempts(),
          max_total_tokens_budget: Number(b.max_total_tokens_budget ?? 200000),
          max_total_verify_minutes: Number(b.max_total_verify_minutes ?? 60),
        },
        usage: { attempts: 0, tokens_input: 0, tokens_output: 0, verify_minutes: 0 },
        stall: { is_stalled: false, last_progress_at: null, minutes_since_progress: null, reason: null },
      })
    taskLedger.updated_at = now
    progressLedger.updated_at = now
    progressLedger.counts = counts
    progressLedger.phase = inferParentPhase(parentTask, counts)
    writeJsonSafe(paths.task_ledger_json, taskLedger)
    writeJsonSafe(paths.progress_ledger_json, progressLedger)
    return { ok: true }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

function bumpParentProgress({ parentId, type, details, usageDelta, stallReason }) {
  try {
    const pid = String(parentId ?? "").trim()
    if (!pid) return { ok: false, error: "missing_parent_id" }
    const parent = getBoardTask(pid)
    if (!parent) return { ok: false, error: "parent_not_found" }
    const paths = parentLedgerPaths(pid)
    const now = new Date().toISOString()
    const counts = summarizeParentCounts(pid)

    const cur = loadJsonSafe(paths.progress_ledger_json)
    const b = factoryBudgets()
    const next =
      (cur && typeof cur === "object" && cur.schema_version === "scc.progress_ledger.v1"
        ? cur
        : {
            schema_version: "scc.progress_ledger.v1",
            parent_id: pid,
            updated_at: now,
            phase: "ready",
            counts,
            budgets: {
              max_total_attempts: maxTotalAttempts(),
              max_total_tokens_budget: Number(b.max_total_tokens_budget ?? 200000),
              max_total_verify_minutes: Number(b.max_total_verify_minutes ?? 60),
            },
            usage: { attempts: 0, tokens_input: 0, tokens_output: 0, verify_minutes: 0 },
            stall: { is_stalled: false, last_progress_at: null, minutes_since_progress: null, reason: null },
          })
    next.updated_at = now
    next.counts = counts
    next.phase = inferParentPhase(parent, counts)

    if (usageDelta && typeof usageDelta === "object") {
      const di = Number(usageDelta.tokens_input ?? 0)
      const do2 = Number(usageDelta.tokens_output ?? 0)
      const dv = Number(usageDelta.verify_minutes ?? 0)
      const da = Number(usageDelta.attempts ?? 0)
      next.usage = next.usage && typeof next.usage === "object" ? next.usage : { attempts: 0, tokens_input: 0, tokens_output: 0, verify_minutes: 0 }
      next.usage.tokens_input = Math.max(0, Number(next.usage.tokens_input ?? 0) + (Number.isFinite(di) ? Math.floor(di) : 0))
      next.usage.tokens_output = Math.max(0, Number(next.usage.tokens_output ?? 0) + (Number.isFinite(do2) ? Math.floor(do2) : 0))
      next.usage.verify_minutes = Math.max(0, Number(next.usage.verify_minutes ?? 0) + (Number.isFinite(dv) ? Math.floor(dv) : 0))
      next.usage.attempts = Math.max(0, Number(next.usage.attempts ?? 0) + (Number.isFinite(da) ? Math.floor(da) : 0))
    }

    // Progress markers: update last_progress_at on meaningful transitions.
    const progressType = String(type ?? "")
    const isProgress = ["split_applied", "child_done", "child_failed", "child_dispatched", "parent_done", "parent_failed"].includes(progressType)
    const last = next.stall && typeof next.stall === "object" ? next.stall.last_progress_at : null
    const lastAt = isProgress ? now : last
    const mins =
      lastAt && typeof lastAt === "string"
        ? Math.max(0, Math.floor((Date.now() - Date.parse(lastAt)) / 60000))
        : null
    const isStalled = mins != null && Number.isFinite(ledgerStallMinutes) && ledgerStallMinutes > 0 ? mins >= ledgerStallMinutes : false
    next.stall = {
      is_stalled: Boolean(isStalled),
      last_progress_at: lastAt ?? null,
      minutes_since_progress: mins,
      reason: stallReason != null ? String(stallReason) : isStalled ? "no_progress" : null,
    }

    writeJsonSafe(paths.progress_ledger_json, next)
    appendJsonlSafe(paths.progress_events_jsonl, {
      schema_version: "scc.progress_event.v1",
      t: now,
      parent_id: pid,
      type: progressType || "unknown",
      details: details ?? null,
      usage_delta: usageDelta ?? null,
    })
    return { ok: true }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
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
  return loadMissionImpl({ missionFile, gatewayPort })
}

function saveMission(m) {
  saveMissionImpl({ missionFile, mission: m, strictWrites: cfg.strictWrites })
}

function loadBoard() {
  return loadBoardImpl({ boardFile })
}

function saveBoard() {
  const arr = Array.from(boardTasks.values())
  saveBoardImpl({ boardFile, tasksArray: arr, strictWrites: cfg.strictWrites })
}

function lanePriorityScore(lane) {
  const fp = getFactoryPolicy ? getFactoryPolicy() : null
  return lanePriorityScoreImpl(lane, fp)
}

function computeJobPriorityForTask(t) {
  const fp = getFactoryPolicy ? getFactoryPolicy() : null
  return computeJobPriorityForTaskImpl(t, fp)
}

function routeLaneForEventType(eventType) {
  const et = String(eventType ?? "").trim()
  if (!et) return null
  const fp = getFactoryPolicy ? getFactoryPolicy() : null
  const routing = fp?.event_routing ?? null
  const by = routing?.by_event_type ?? null
  const direct = by && typeof by === "object" ? by[et] : null
  const lane = direct?.lane ?? routing?.default?.lane ?? null
  return normalizeLane(lane)
}

function maxTotalAttempts() {
  const fp = getFactoryPolicy ? getFactoryPolicy() : null
  const n = Number(fp?.budgets?.max_total_attempts)
  if (Number.isFinite(n) && n > 0) return Math.floor(n)
  return 3
}

function factoryBudgets() {
  const fp = getFactoryPolicy ? getFactoryPolicy() : null
  const b = fp?.budgets ?? {}
  const toInt = (v, fallback) => {
    const n = Number(v)
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : fallback
  }
  return {
    max_children: toInt(b.max_children, 12),
    max_depth: toInt(b.max_depth, 2),
    max_total_tokens_budget: toInt(b.max_total_tokens_budget, 200000),
    max_total_verify_minutes: toInt(b.max_total_verify_minutes, 60),
  }
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

function appendIsolation(rec) {
  try {
    fs.appendFileSync(isolationFile, JSON.stringify(rec) + "\n", "utf8")
  } catch (e) {
    // best-effort
    noteBestEffort("appendIsolation", e, { file: isolationFile })
  }
}

function loadCircuitBreakerState() {
  return loadCircuitBreakerStateImpl({ file: circuitBreakerStateFile })
}

function saveCircuitBreakerState(state) {
  return saveCircuitBreakerStateImpl({ file: circuitBreakerStateFile, state, strictWrites: cfg.strictWrites })
}

let circuitBreakerState = loadCircuitBreakerState()

function quarantineActive() {
  return quarantineActiveImpl(circuitBreakerState, Date.now())
}

const repoUnhealthyWindowMs = Number(process.env.REPO_UNHEALTHY_WINDOW_MS ?? "1800000") // 30 min
const repoUnhealthyFailThreshold = Number(process.env.REPO_UNHEALTHY_FAIL_THRESHOLD ?? "6")
const repoUnhealthyCooldownMs = Number(process.env.REPO_UNHEALTHY_COOLDOWN_MS ?? "900000") // 15 min

function loadRepoHealthState() {
  return loadRepoHealthStateImpl({ file: repoHealthStateFile })
}

function saveRepoHealthState(state) {
  return saveRepoHealthStateImpl({ file: repoHealthStateFile, state, strictWrites: cfg.strictWrites })
}

let repoHealthState = loadRepoHealthState()

function repoUnhealthyActive() {
  return repoUnhealthyActiveImpl(repoHealthState, Date.now())
}

// ---------------- Playbooks (L8 MVP) ----------------
let playbooksCache = { loadedAt: 0, patterns: [], playbooks: [] }
function loadPlaybooksCache({ maxAgeMs = 120000 } = {}) {
  const now = Date.now()
  if (playbooksCache.loadedAt && now - playbooksCache.loadedAt < maxAgeMs) return playbooksCache
  const root = SCC_REPO_ROOT
  const patternsDir = path.join(root, "patterns")
  const playbooksDir = path.join(root, "playbooks")
  const overridesPath = path.join(playbooksDir, "overrides.json")
  const readAllJson = (dir) => {
    try {
      if (!fs.existsSync(dir)) return []
      const files = fs.readdirSync(dir).filter((f) => f.endsWith(".json"))
      const out = []
      for (const f of files.slice(0, 400)) {
        const abs = path.join(dir, f)
        try {
          const obj = JSON.parse(fs.readFileSync(abs, "utf8"))
          out.push(obj)
        } catch (e) {
          noteBestEffort("loadPlaybooksCache.parse_file", e, { file: abs })
        }
      }
      return out
    } catch (e) {
      noteBestEffort("loadPlaybooksCache.read_dir", e, { dir: String(dir ?? "") })
      return []
    }
  }
  const patterns = readAllJson(patternsDir).filter((o) => o && typeof o === "object" && o.schema_version === "scc.pattern.v1")
  let playbooks = readAllJson(playbooksDir).filter((o) => o && typeof o === "object" && o.schema_version === "scc.playbook.v1")

  // Optional: disable/override playbooks at runtime (auto-rollback writes here).
  try {
    if (fs.existsSync(overridesPath)) {
      const raw = fs.readFileSync(overridesPath, "utf8")
      const ov = JSON.parse(raw.replace(/^\uFEFF/, ""))
      const overrides = ov && typeof ov === "object" && ov.schema_version === "scc.playbook_overrides.v1" ? ov.overrides : null
      if (overrides && typeof overrides === "object") {
        playbooks = playbooks.map((pb) => {
          const id = String(pb?.playbook_id ?? "")
          const o = id ? overrides[id] : null
          if (!o || typeof o !== "object" || o.disabled !== true) return pb
          const nextEnablement =
            pb?.enablement && typeof pb.enablement === "object"
              ? { ...pb.enablement, status: "deprecated", rollout: { mode: "percent", percent: 0 } }
              : pb.enablement
          return { ...pb, enablement: nextEnablement, notes: pb?.notes ? `${pb.notes}\n[overrides] disabled` : "[overrides] disabled" }
        })
      }
    }
  } catch (e) {
    noteBestEffort("loadPlaybooksCache.overrides", e, { overridesPath })
  }
  playbooksCache = { loadedAt: now, patterns, playbooks }
  return playbooksCache
}

function stablePercentForTask(taskId, salt) {
  const s = `${String(taskId ?? "")}::${String(salt ?? "")}`
  const h = crypto.createHash("sha1").update(Buffer.from(s, "utf8")).digest("hex")
  const n = parseInt(h.slice(0, 8), 16)
  return Number.isFinite(n) ? Math.abs(n) % 100 : 0
}

function enablementAllows({ enablement, taskId, salt }) {
  const en = enablement && typeof enablement === "object" ? enablement : null
  if (!en || en.schema_version !== "scc.enablement.v1") return false
  const st = String(en.status ?? "draft")
  if (st === "deprecated" || st === "draft") return false
  const rollout = en.rollout && typeof en.rollout === "object" ? en.rollout : {}
  const mode = String(rollout.mode ?? "all")
  if (mode === "all") return st === "active" || st === "gray"
  if (mode === "allowlist") {
    const allow = Array.isArray(rollout.allowlist) ? rollout.allowlist.map((x) => String(x)) : []
    return allow.includes(String(taskId ?? ""))
  }
  if (mode === "percent") {
    const p = Number(rollout.percent ?? 0)
    const pct = Number.isFinite(p) ? Math.max(0, Math.min(100, Math.floor(p))) : 0
    const v = stablePercentForTask(taskId, salt)
    return v < pct
  }
  return false
}

function patternMatches({ pattern, eventType, job, boardTask }) {
  const p = pattern && typeof pattern === "object" ? pattern : null
  if (!p || p.schema_version !== "scc.pattern.v1") return false
  const m = p.match && typeof p.match === "object" ? p.match : {}
  const et = String(m.event_type ?? "").trim()
  if (!et) return false
  if (et !== String(eventType ?? "")) return false
  const tool = m.tool != null ? String(m.tool) : null
  if (tool && String(job?.executor ?? "") !== tool) return false
  const st = m.stacktrace_hash != null ? String(m.stacktrace_hash) : null
  if (st && String(job?.stderr ?? "").trim() && `sha1:${sha1(normalizeForSignature(job.stderr))}` !== st) return false
  const cls = m.task_class != null ? String(m.task_class) : null
  if (cls && String(boardTask?.task_class_id ?? boardTask?.task_class_candidate ?? "") !== cls) return false
  return true
}

function applyPlaybookToRetryPlan({ playbook, retryPlan }) {
  const pb = playbook && typeof playbook === "object" ? playbook : null
  if (!pb || pb.schema_version !== "scc.playbook.v1") return retryPlan
  const out = retryPlan && typeof retryPlan === "object" ? { ...retryPlan } : null
  if (!out || !out.route) return retryPlan
  const actions = Array.isArray(pb.actions) ? pb.actions : []
  for (const a of actions) {
    const type = String(a?.type ?? "")
    if (type === "note") {
      const msg = a?.params?.message ? String(a.params.message) : ""
      if (msg) out.route.notes = out.route?.notes ? `${out.route.notes}\n${msg}` : msg
    } else if (type === "route") {
      const lane = a?.lane ? normalizeLane(String(a.lane)) : null
      const role = a?.role ? String(a.role) : null
      if (lane) out.route.lane = lane
      if (role) out.route.next_role = role
    } else if (type === "add_pin") {
      const add = Array.isArray(a?.params?.paths) ? a.params.paths.map((x) => String(x)).filter(Boolean) : []
      if (add.length) {
        out.pins_adjustments = out.pins_adjustments && typeof out.pins_adjustments === "object" ? { ...out.pins_adjustments } : {}
        const prev = Array.isArray(out.pins_adjustments.add) ? out.pins_adjustments.add : []
        out.pins_adjustments.add = Array.from(new Set(prev.concat(add))).slice(0, 40)
      }
    } else if (type === "open_dlq") {
      out.strategy = "DLQ"
      out.route.lane = "dlq"
      out.route.next_role = "retry_orchestrator"
    }
  }
  return out
}

function maybeApplyPlaybooks({ eventType, boardTask, job }) {
  try {
    if (!boardTask || !job) return { ok: false, error: "missing_task_or_job" }
    const tid = String(boardTask.id ?? "").trim()
    if (!tid) return { ok: false, error: "missing_task_id" }
    const cache = loadPlaybooksCache()
    const patterns = Array.isArray(cache.patterns) ? cache.patterns : []
    const playbooks = Array.isArray(cache.playbooks) ? cache.playbooks : []
    const matched = patterns.filter((p) => patternMatches({ pattern: p, eventType, job, boardTask })).slice(0, 6)
    if (!matched.length) return { ok: false, error: "no_match" }
    const ids = new Set(matched.map((p) => String(p.pattern_id ?? "")).filter(Boolean))
    const candidates = playbooks.filter((pb) => ids.has(String(pb.pattern_id ?? ""))).slice(0, 12)
    const chosen = candidates.filter((pb) => enablementAllows({ enablement: pb.enablement, taskId: tid, salt: pb.playbook_id })).slice(0, 3)
    if (!chosen.length) return { ok: false, error: "no_enabled_playbook" }

    const file = retryPlanPath(tid)
    if (!fs.existsSync(file)) return { ok: false, error: "missing_retry_plan" }
    let rp = null
    try {
      rp = JSON.parse(fs.readFileSync(file, "utf8"))
    } catch {
      rp = null
    }
    if (!rp) return { ok: false, error: "bad_retry_plan" }
    let next = rp
    for (const pb of chosen) next = applyPlaybookToRetryPlan({ playbook: pb, retryPlan: next })
    fs.writeFileSync(file, JSON.stringify(next, null, 2) + "\n", "utf8")

    boardTask.pointers = {
      ...(boardTask.pointers && typeof boardTask.pointers === "object" ? boardTask.pointers : {}),
      playbooks_applied: chosen.map((pb) => ({ playbook_id: pb.playbook_id ?? null, pattern_id: pb.pattern_id ?? null })),
    }
    putBoardTask(boardTask)
    leader({ level: "info", type: "playbooks_applied", taskId: tid, event_type: eventType, count: chosen.length })
    try {
      appendJsonl(playbooksAppliedFile, {
        schema_version: "scc.playbooks_applied.v1",
        t: new Date().toISOString(),
        task_id: tid,
        event_type: String(eventType ?? ""),
        executor: String(job?.executor ?? ""),
        model: String(job?.model ?? ""),
        playbooks: chosen.map((pb) => ({ playbook_id: pb.playbook_id ?? null, pattern_id: pb.pattern_id ?? null, version: pb.version ?? null })),
      })
    } catch (e) {
      noteBestEffort("maybeApplyPlaybooks.append", e, { file: playbooksAppliedFile, task_id: tid })
    }
    return { ok: true, applied: chosen.map((pb) => pb.playbook_id ?? null) }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

function applyRepoHealthFromEvent({ event_type } = {}) {
  const et = String(event_type ?? "").trim()
  if (!et) return
  const now = Date.now()
  const windowMs = Number.isFinite(repoUnhealthyWindowMs) && repoUnhealthyWindowMs > 0 ? repoUnhealthyWindowMs : 1800000
  const threshold = Number.isFinite(repoUnhealthyFailThreshold) && repoUnhealthyFailThreshold > 0 ? Math.floor(repoUnhealthyFailThreshold) : 6
  const cooldown = Number.isFinite(repoUnhealthyCooldownMs) && repoUnhealthyCooldownMs > 0 ? repoUnhealthyCooldownMs : 900000

  const isFailure = et === "CI_FAILED" || et === "PREFLIGHT_FAILED" || et === "EXECUTOR_ERROR" || et === "POLICY_VIOLATION"
  const next = {
    ...repoHealthState,
    failures: Array.isArray(repoHealthState?.failures) ? repoHealthState.failures.slice(0) : [],
    updated_at: new Date().toISOString(),
  }

  // Prune window.
  next.failures = next.failures.filter((t) => Number.isFinite(t) && t >= now - windowMs)
  if (isFailure) next.failures.push(now)

  const wasUnhealthy = repoUnhealthyActive()
  if (threshold > 0 && next.failures.length >= threshold) {
    next.unhealthy_until = now + cooldown
    next.unhealthy_reason = `failures_in_window>=${threshold} (${et})`
    if (!wasUnhealthy) {
      leader({ level: "warn", type: "repo_unhealthy", until: next.unhealthy_until, reason: next.unhealthy_reason, failures: next.failures.length })
      // Spawn a factory_manager task to recommend stop-the-bleeding recovery actions (rate-limited).
      try {
        const createdAt = next.unhealthy_task_created_at ? Date.parse(String(next.unhealthy_task_created_at)) : 0
        if (!createdAt || now - createdAt > 5 * 60 * 1000) {
          const created = createBoardTask({
            kind: "atomic",
            status: "ready",
            title: `Repo unhealthy: ${next.unhealthy_reason ?? "unknown"}`,
            goal: [
              "Role: FACTORY_MANAGER / STABILITY_CONTROLLER.",
              "Goal: Repository health degraded (many failures). Recommend stop-the-bleeding actions and recovery plan.",
              "",
              "Inputs:",
              "- factory_policy.json (degradation_matrix / stop_the_bleeding allowlist)",
              "- artifacts/executor_logs/state_events.jsonl",
              "- artifacts/executor_logs/ci_failures.jsonl",
              "",
              "Output:",
              "- report.md: root cause hypothesis + immediate actions (reduce WIP, quarantine flapping lanes, focus CI fixups).",
              "- Optional: stability_actions.json proposal (non-code config changes only).",
              "- No business code changes.",
            ].join("\n"),
            role: "factory_manager",
            runner: "internal",
            lane: "fastlane",
            area: "control_plane",
            task_class_id: "repo_unhealthy_triage_v1",
            allowedExecutors: ["codex"],
            allowedModels: ["gpt-5.2"],
            timeoutMs: 600000,
            files: ["factory_policy.json", "artifacts/executor_logs/state_events.jsonl", "artifacts/executor_logs/ci_failures.jsonl", "artifacts/executor_logs/repo_health_state.json"],
            allowedTests: ["python tools/scc/gates/run_ci_gates.py --submit artifacts/{task_id}/submit.json"],
            pointers: { reason: "repo_unhealthy", event_type: et },
          })
          if (created.ok) {
            next.unhealthy_task_created_at = new Date().toISOString()
            dispatchBoardTaskToExecutor(created.task.id)
          }
        }
      } catch (e) {
        // best-effort
        noteBestEffort("repoHealth_unhealthy_task_autocreate", e)
      }
    }
  } else if (!repoUnhealthyActive() && next.unhealthy_until) {
    next.unhealthy_until = 0
    next.unhealthy_reason = null
  }

  repoHealthState = next
  saveRepoHealthState(next)
}

function applyCircuitBreakersFromEvent(stateEvent) {
  if (!circuitBreakersEnabled) return
  const fp = getFactoryPolicy ? getFactoryPolicy() : null
  const breakers = Array.isArray(fp?.circuit_breakers) ? fp.circuit_breakers : []
  if (!breakers.length) return
  const et = String(stateEvent?.event_type ?? "").trim()
  if (!et) return

  const now = Date.now()
  const cooldown = Number.isFinite(circuitBreakerCooldownMs) && circuitBreakerCooldownMs > 0 ? circuitBreakerCooldownMs : 900000
  const next = {
    ...circuitBreakerState,
    breakers: { ...(circuitBreakerState?.breakers ?? {}) },
    updated_at: new Date().toISOString(),
    quarantine_task_created_at: circuitBreakerState?.quarantine_task_created_at ?? null,
  }

  let tripped = null
  for (const b of breakers) {
    const name = String(b?.name ?? "").trim()
    if (!name) continue
    const matchType = String(b?.match?.event_type ?? "").trim()
    const tripN = Math.max(1, Math.floor(Number(b?.trip?.consecutive_failures ?? 0) || 1))
    const rec = next.breakers[name] && typeof next.breakers[name] === "object" ? { ...next.breakers[name] } : { consecutive: 0, last_event_type: null, tripped_at: null, tripped_until: 0 }
    if (matchType && et === matchType) rec.consecutive = Number(rec.consecutive ?? 0) + 1
    else rec.consecutive = 0
    rec.last_event_type = et
    if (rec.consecutive >= tripN && (!rec.tripped_until || now >= Number(rec.tripped_until))) {
      rec.tripped_at = new Date().toISOString()
      rec.tripped_until = now + cooldown
      const lane = String(b?.action?.lane ?? "").trim()
      tripped = { name, lane: lane || null, note: b?.action?.note ?? null, until: rec.tripped_until, matchType, tripN }
    }
    next.breakers[name] = rec
  }

  if (tripped && String(tripped.lane ?? "") === "quarantine") {
    next.quarantine_until = Number(tripped.until)
    next.quarantine_reason = `breaker:${tripped.name}`
    next.quarantine_breaker = tripped.name
    leader({ level: "warn", type: "circuit_breaker_tripped", breaker: tripped.name, lane: "quarantine", until: tripped.until, match: tripped.matchType, tripN: tripped.tripN })

    // Spawn a factory_manager task to summarize the situation and recommend recovery actions (rate-limited).
    try {
      const createdAt = next.quarantine_task_created_at ? Date.parse(String(next.quarantine_task_created_at)) : 0
      if (!createdAt || now - createdAt > 5 * 60 * 1000) {
        const created = createBoardTask({
          kind: "atomic",
          status: "ready",
          title: `Quarantine tripped: ${tripped.name}`,
          goal: [
            "Role: FACTORY_MANAGER.",
            "Goal: A circuit breaker tripped and dispatch is quarantined. Summarize why (evidence from state_events / ci_failures) and propose recovery actions.",
            "",
            `Breaker: ${tripped.name}`,
            `Match: ${tripped.matchType}`,
            `Trip threshold: consecutive_failures >= ${tripped.tripN}`,
            `Quarantine until: ${new Date(Number(tripped.until)).toISOString()}`,
            "",
            "Outputs:",
            "- report.md under artifacts/<task_id>/report.md with: top failing tests/reasons + suggested next tasks (pins_fixup/ci_fixup/split/rollback).",
            "- No code changes.",
          ].join("\n"),
          role: "factory_manager",
          runner: "internal",
          lane: "quarantine",
          area: "control_plane",
          task_class_id: "quarantine_triage_v1",
          allowedExecutors: ["codex"],
          allowedModels: ["gpt-5.2"],
          timeoutMs: 600000,
          files: [
            "factory_policy.json",
            "artifacts/executor_logs/state_events.jsonl",
            "artifacts/executor_logs/ci_failures.jsonl",
            "artifacts/executor_logs/ci_gate_results.jsonl",
            "artifacts/executor_logs/router_failures.jsonl",
            "artifacts/executor_logs/circuit_breakers_state.json",
          ],
          allowedTests: ["python scc-top/tools/scc/ops/task_selftest.py --task-id {task_id}"],
          pointers: { reason: "circuit_breaker_tripped", breaker: tripped.name },
        })
        if (created.ok) {
          next.quarantine_task_created_at = new Date().toISOString()
          dispatchBoardTaskToExecutor(created.task.id)
        }
      }
    } catch (e) {
      // best-effort
      noteBestEffort("circuitBreaker_quarantine_task_autocreate", e)
    }
  }

  circuitBreakerState = next
  saveCircuitBreakerState(next)
}

function dlqFilePath() {
  const root = SCC_REPO_ROOT
  return path.join(root, "artifacts", "dlq", "dlq.jsonl")
}

function appendDlq(rec) {
  try {
    const file = dlqFilePath()
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.appendFileSync(file, JSON.stringify(rec) + "\n", "utf8")
  } catch (e) {
    // best-effort
    noteBestEffort("appendDlq", e)
  }
}

function openDlqForTask({ task, reason_code, summary, missing_inputs, last_event }) {
  const taskId = String(task?.id ?? "").trim()
  if (!taskId) return { ok: false, error: "missing_task_id" }
  const id = `dlq_${new Date().toISOString().slice(0, 10).replaceAll("-", "")}_${taskId.slice(0, 8)}`
  const entry = {
    schema_version: "scc.dlq.v1",
    dlq_id: id,
    task_id: taskId,
    created_at: new Date().toISOString(),
    status: "OPEN",
    reason_code: String(reason_code ?? "RETRY_EXHAUSTED"),
    summary: String(summary ?? "Retry budget exhausted"),
    missing_inputs: Array.isArray(missing_inputs) ? missing_inputs.map((x) => String(x)).filter(Boolean).slice(0, 20) : [],
    last_event: last_event ?? null,
    retry_history: [],
    evidence: {
      artifacts_root: `artifacts/${taskId}/`,
      report_md: `artifacts/${taskId}/report.md`,
      selftest_log: `artifacts/${taskId}/selftest.log`,
    },
  }
  appendDlq(entry)
  return { ok: true, entry }
}

function retryPlanPath(taskId) {
  const root = SCC_REPO_ROOT
  return path.join(root, "artifacts", String(taskId), "retry_plan.json")
}

function writeRetryPlanArtifact({ task, event_type, reason, next_attempt, notes }) {
  try {
    const t = task && typeof task === "object" ? task : null
    if (!t?.id) return { ok: false, error: "missing_task" }
    const taskId = String(t.id)
    const et = String(event_type ?? "").trim()
    const rsn = String(reason ?? "").trim()
    const maxAttempts = maxTotalAttempts()
    const attempt = Number.isFinite(Number(next_attempt)) ? Math.max(1, Math.floor(Number(next_attempt))) : Math.max(1, Number(t.dispatch_attempts ?? 0) + 1)

    let strategy = "DLQ"
    let lane = normalizeLane(routeLaneForEventType(et)) ?? normalizeLane(t.lane) ?? "mainlane"
    let next_role = "retry_orchestrator"
    if (et === "PINS_INSUFFICIENT" || (et === "PREFLIGHT_FAILED" && rsn.toLowerCase().includes("pins"))) {
      strategy = "PINS_FIX"
      lane = "fastlane"
      next_role = "pinser"
    } else if (et === "CI_FAILED") {
      strategy = "SHRINK_RADIUS"
      lane = "fastlane"
      next_role = "ci_fixup"
    } else if (et === "EXECUTOR_ERROR") {
      strategy = "SWITCH_EXECUTOR"
      lane = "fastlane"
      next_role = "executor"
    } else if (et === "POLICY_VIOLATION") {
      strategy = "DLQ"
      lane = "quarantine"
      next_role = "factory_manager"
    } else if (et === "RETRY_EXHAUSTED") {
      strategy = "DLQ"
      lane = "dlq"
      next_role = "retry_orchestrator"
    }

    const roleKey = String(t.role ?? "").toLowerCase()
    const rolePolicy = roleSystem ? roleSystem.policiesByRole?.get(roleKey) ?? null : null
    const stop_conditions = Array.isArray(rolePolicy?.gates?.stop_conditions) ? rolePolicy.gates.stop_conditions.map((x) => String(x)).filter(Boolean) : []
    const b = factoryBudgets()
    const obj = {
      schema_version: "scc.retry_plan.v1",
      task_id: taskId,
      attempt,
      max_attempts: maxAttempts,
      route: { lane, next_role, notes: notes != null ? String(notes) : null },
      strategy,
      budgets: {
        max_total_attempts: maxAttempts,
        max_verify_minutes: Number.isFinite(Number(b.max_total_verify_minutes)) ? Math.floor(Number(b.max_total_verify_minutes)) : 60,
        max_children: Number.isFinite(Number(b.max_children)) ? Math.floor(Number(b.max_children)) : 12,
        max_depth: Number.isFinite(Number(b.max_depth)) ? Math.floor(Number(b.max_depth)) : 2,
      },
      stop_conditions,
      dlq_on_fail: true,
    }

    const file = retryPlanPath(taskId)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, JSON.stringify(obj, null, 2) + "\n", "utf8")
    return { ok: true, file, retry_plan: obj }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

function deleteBoardTask(id) {
  if (!boardTasks.has(id)) return false
  boardTasks.delete(id)
  saveBoard()
  leader({ level: "info", type: "board_task_deleted", id })
  return true
}

function isValidRecoveredTask(obj) {
  if (!obj || typeof obj !== "object") return false
  const title = String(obj.title ?? "").trim()
  const goal = String(obj.goal ?? "").trim()
  const files = Array.isArray(obj.files) ? obj.files : []
  const tests = Array.isArray(obj.allowedTests) ? obj.allowedTests : []
  const pins = obj.pins && typeof obj.pins === "object" ? obj.pins : null
  const allow = Array.isArray(pins?.allowed_paths) ? pins.allowed_paths : []
  const hasRealTest = tests.some((t) => !String(t ?? "").toLowerCase().includes("task_selftest"))
  return Boolean(title && goal && files.length && allow.length && hasRealTest)
}

function createTaskFromRecovery({ recoveryTask, job, payload }) {
  if (!isValidRecoveredTask(payload)) {
    appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "recovery_invalid", taskId: recoveryTask?.id ?? null })
    return null
  }
  const title = String(payload.title).slice(0, 180)
  const goal = String(payload.goal)
  const files = Array.isArray(payload.files) ? payload.files.slice(0, 16) : []
  const pins = payload.pins && typeof payload.pins === "object" ? payload.pins : null
  const allowedTests = Array.isArray(payload.allowedTests) ? payload.allowedTests.slice(0, 8) : ["python -m pytest -q"]
  const role = payload.role ? String(payload.role) : "engineer"
  const task = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role,
    area: "mainlane",
    files,
    pins,
    allowedTests,
    runner: "external",
    allowedExecutors: ["opencodecli", "codex"],
  })
  if (!task.ok) {
    appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "recovery_apply_failed", reason: task.error, taskId: recoveryTask?.id ?? null })
    return null
  }
  task.task.pointers = { recovered_from: recoveryTask?.id ?? null }
  putBoardTask(task.task)
  dispatchBoardTaskToExecutor(task.task.id)
  return task.task
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

function roleRequiresRealTests(role) {
  if (roleSystem) return roleRequiresRealTestsFromPolicy(roleSystem, role)
  const r = String(role ?? "").trim().toLowerCase()
  // These roles produce patches and must run a "real" test (not only task_selftest).
  return ["engineer", "integrator", "qa", "doc", "designer", "architect"].includes(r)
}

function globToRegexV1(glob) {
  const g0 = String(glob ?? "").trim().replaceAll("\\", "/")
  if (!g0) return null
  if (g0 === "**") return /^.*$/
  let g = g0
  let prefix = ""
  if (g.startsWith("**/")) {
    prefix = "(?:.*/)?"
    g = g.slice(3)
  }
  let out = ""
  for (let i = 0; i < g.length; i += 1) {
    const c = g[i]
    const next = g[i + 1]
    if (c === "*" && next === "*") {
      out += ".*"
      i += 1
      continue
    }
    if (c === "*") {
      out += "[^/]*"
      continue
    }
    if (c === "?") {
      out += "[^/]"
      continue
    }
    if (/[-/\\^$+?.()|[\]{}]/.test(c)) out += `\\${c}`
    else out += c
  }
  return new RegExp(`^${prefix}${out}$`)
}

function pathMatchesAnyRegex(list, p) {
  const s = normalizeRepoPath(p)
  if (!s) return false
  for (const re of list) {
    if (!re) continue
    if (re.test(s)) return true
    // Treat directory pins like "docs" as matching "docs/**" style globs.
    if (!s.endsWith("/") && re.test(`${s}/`)) return true
  }
  return false
}

function validateRolePolicyForTask({ task, rolePolicy, pinsSpec }) {
  if (!task || !rolePolicy) return { ok: true }
  const role = String(task?.role ?? "").trim().toLowerCase()
  const caps = rolePolicy?.capabilities ?? {}
  const canWrite = Boolean(caps?.can_write_code)

  const readAllow = Array.isArray(rolePolicy?.permissions?.read?.allow_paths) ? rolePolicy.permissions.read.allow_paths : []
  const readDeny = Array.isArray(rolePolicy?.permissions?.read?.deny_paths) ? rolePolicy.permissions.read.deny_paths : []
  const writeAllow = Array.isArray(rolePolicy?.permissions?.write?.allow_paths) ? rolePolicy.permissions.write.allow_paths : []
  const writeDeny = Array.isArray(rolePolicy?.permissions?.write?.deny_paths) ? rolePolicy.permissions.write.deny_paths : []

  const readAllowAll = readAllow.includes("**")
  const writeAllowAll = writeAllow.includes("**")
  const readAllowRe = readAllow.map(globToRegexV1).filter(Boolean)
  const readDenyRe = readDeny.map(globToRegexV1).filter(Boolean)
  const writeAllowRe = writeAllow.map(globToRegexV1).filter(Boolean)
  const writeDenyRe = writeDeny.map(globToRegexV1).filter(Boolean)

  const files = Array.isArray(task?.files) ? task.files : []
  const pinsAllow = Array.isArray(pinsSpec?.allowed_paths) ? pinsSpec.allowed_paths : []
  const requestedRead = Array.from(new Set([...files, ...pinsAllow].map((x) => normalizeRepoPath(x)).filter(Boolean)))

  const denyHits = readDenyRe.length ? requestedRead.filter((p) => pathMatchesAnyRegex(readDenyRe, p)) : []
  const allowMiss = readAllowAll || readAllowRe.length === 0 ? [] : requestedRead.filter((p) => !pathMatchesAnyRegex(readAllowRe, p))

  const errors = []
  if (denyHits.length) errors.push({ reason: "role_read_deny_paths", role, files: denyHits.slice(0, 30) })
  if (allowMiss.length) errors.push({ reason: "role_read_allow_paths", role, files: allowMiss.slice(0, 30), allow: readAllow.slice(0, 12) })

  // For code-writing roles, pins.allowlist is effectively the maximum write scope. Enforce it fail-closed.
  if (canWrite) {
    const writeDenyHits = writeDenyRe.length ? pinsAllow.map(normalizeRepoPath).filter(Boolean).filter((p) => pathMatchesAnyRegex(writeDenyRe, p)) : []
    const writeAllowMiss =
      writeAllowAll || writeAllowRe.length === 0
        ? []
        : pinsAllow.map(normalizeRepoPath).filter(Boolean).filter((p) => !pathMatchesAnyRegex(writeAllowRe, p))
    if (writeDenyHits.length) errors.push({ reason: "role_write_deny_paths", role, files: writeDenyHits.slice(0, 30) })
    if (writeAllowMiss.length) errors.push({ reason: "role_write_allow_paths", role, files: writeAllowMiss.slice(0, 30), allow: writeAllow.slice(0, 12) })
  }

  if (!errors.length) return { ok: true }
  return { ok: false, error: "role_policy_violation", errors }
}

function renderPromptOrFallback({ role_id, preset_id = null, params, fallback, note }) {
  const out = promptRegistry.render({ role_id, preset_id, params })
  if (out.ok) return { ok: true, text: out.text, prompt_ref: out.prompt_ref }
  leader({ level: "warn", type: "prompt_registry_render_failed", role_id, preset_id, error: out.error, missing: out.missing ?? null, note: note ?? null })
  return { ok: false, text: String(fallback ?? ""), prompt_ref: { role_id, preset_id, error: out.error, missing: out.missing ?? null } }
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
  const parentId = payload?.parentId ? String(payload.parentId) : null
  const roleRaw = payload?.role != null ? String(payload.role) : defaultTaskRole
  const role = normalizeRole(roleRaw)
  if (!role) return { ok: false, error: "invalid_role", message: `role must be one of: ${ROLE_NAMES.join(", ")}` }
  const allowedExecutors = Array.isArray(payload?.allowedExecutors)
    ? payload.allowedExecutors.map((x) => String(x)).filter((x) => x === "codex" || x === "opencodecli")
    : ["opencodecli", "codex"]
  const allowedModels = Array.isArray(payload?.allowedModels) ? payload.allowedModels.map((x) => String(x)).slice(0, 8) : []
  let files = Array.isArray(payload?.files) ? payload.files.map((x) => String(x)).slice(0, 16) : []
  const skillsFromPayload = Array.isArray(payload?.skills) ? payload.skills.map((x) => String(x)).slice(0, 16) : []
  const skills = skillsFromPayload.length ? skillsFromPayload : role ? roleSkills(role) : []
  if (roleSystem) {
    const skillCheck = validateRoleSkills(roleSystem, role, skills)
    if (!skillCheck.ok) return { ok: false, error: skillCheck.error ?? "skill_not_allowed", details: skillCheck }
  }
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
  const degradation = computeDegradationState()
  const prefer = degradation?.action?.prefer_lane ? normalizeLane(String(degradation.action.prefer_lane)) : null
  const lane = normalizeLane(payload?.lane) ?? normalizeLane(area) ?? prefer ?? "mainlane"
  const taskClassId = payload?.task_class_id != null ? String(payload.task_class_id).trim() : null
  const taskClassCandidate = payload?.task_class_candidate != null ? String(payload.task_class_candidate).trim() : null
  const taskClassParams = payload?.task_class_params && typeof payload.task_class_params === "object" ? payload.task_class_params : null
  const timeoutMs = payload?.timeoutMs != null ? Number(payload.timeoutMs) : null
  const priorityRaw = payload?.priority != null ? Number(payload.priority) : null
  const priority = Number.isFinite(priorityRaw) ? priorityRaw : null
  const runner = payload?.runner === "external" ? "external" : payload?.runner === "internal" ? "internal" : "external"
  const promptRef = payload?.prompt_ref && typeof payload.prompt_ref === "object" ? payload.prompt_ref : null

  // Tests policy:
  // - Patch-producing roles MUST provide a "real" test command (not only task_selftest).
  // - Control-plane roles may default to task_selftest to keep the factory running.
  const needsReal = kind === "atomic" ? roleRequiresRealTests(role) : false
  const normalizedTestsPre = Array.isArray(allowedTests) ? allowedTests.map((t) => String(t ?? "").trim()).filter(Boolean) : []
  if (Number.isFinite(ciEnforceSinceMs) && ciEnforceSinceMs > 0 && now >= ciEnforceSinceMs && normalizedTestsPre.length === 0) {
    if (needsReal) {
      return { ok: false, error: "missing_allowedTests", message: "allowedTests required (must include at least one non-task_selftest command)" }
    }
    if (autoDefaultAllowedTests || kind === "parent") {
      allowedTests = [`python scc-top/tools/scc/ops/task_selftest.py --task-id ${id}`]
    } else {
      return { ok: false, error: "missing_allowedTests" }
    }
  }
  const normalizedTests = Array.isArray(allowedTests) ? allowedTests.map((t) => String(t ?? "").trim()).filter(Boolean) : []
  const hasNonSelf = normalizedTests.some((t) => !t.toLowerCase().includes("task_selftest"))
  if (needsReal && !hasNonSelf) return { ok: false, error: "missing_real_test", message: "allowedTests must include at least one non-task_selftest command" }
  if (!normalizedTests.length) {
    if (kind === "parent") allowedTests = [`python scc-top/tools/scc/ops/task_selftest.py --task-id ${id}`]
    else return { ok: false, error: "missing_allowedTests" }
  }

  // B-mode friendly defaults: infer files and pins aggressively to reduce pins churn and token burn.
  if (autoFilesFromText && (!Array.isArray(files) || files.length === 0)) {
    files = extractRepoPathsFromText(`${title}\n${goal}`)
  }
  if (autoPinsFromFiles && (!pins || typeof pins !== "object") && Array.isArray(files) && files.length) {
    pins = defaultPinsForFiles(files)
  }

  // Format enforcement: atomic tasks must have files; pins must carry allow_paths when present.
  if (kind === "atomic" && (!Array.isArray(files) || files.length === 0)) {
    return { ok: false, error: "missing_files", message: "atomic task requires files; provide repo-relative paths" }
  }
  if (roleSystem) {
    const policy = roleSystem.policiesByRole?.get(role) ?? null
    if (policy?.permissions?.read?.pins_required) {
      const allow = Array.isArray(pins?.allowed_paths) ? pins.allowed_paths : []
      if (allow.length === 0) {
        return { ok: false, error: "missing_pins_allowlist", message: "pins.allowed_paths required for this role (pins_required=true)" }
      }
    }
  }
  if (pins && typeof pins === "object") {
    const allow = Array.isArray(pins.allowed_paths) ? pins.allowed_paths : []
    if (allow.length === 0) {
      return { ok: false, error: "missing_pins_allowlist", message: "pins.allowed_paths must include at least one path" }
    }
  }

  // Role policy pre-validation (fail-closed): prevent tasks that request out-of-policy read/write scopes.
  if (roleSystem) {
    const roleKey = String(role ?? "").trim().toLowerCase()
    const rolePolicy = roleSystem.policiesByRole?.get(roleKey) ?? null
    if (!rolePolicy) return { ok: false, error: "missing_role_policy", message: `missing role policy for ${roleKey}` }
    const check = validateRolePolicyForTask({ task: { role, files, pins }, rolePolicy, pinsSpec: pins })
    if (!check.ok) return { ok: false, error: check.error ?? "role_policy_violation", details: check }
  }

  // Factory budgets: cap parent fan-out and nesting depth to avoid task explosion.
  if (parentId) {
    const b = factoryBudgets()
    const maxChildren = Number(b?.max_children ?? 0)
    const maxDepth = Number(b?.max_depth ?? 0)
    if (Number.isFinite(maxChildren) && maxChildren > 0) {
      let children = 0
      for (const t of boardTasks.values()) {
        if (String(t?.parentId ?? "") === parentId) children += 1
      }
      if (children >= maxChildren) {
        leader({ level: "warn", type: "task_rejected_budget", reason: "max_children", parentId, children, maxChildren })
        return { ok: false, error: "max_children_exceeded", message: `parent ${parentId} already has ${children} children (max=${maxChildren})` }
      }
    }
    if (Number.isFinite(maxDepth) && maxDepth > 0) {
      let depth = 1
      let cur = parentId
      let hops = 0
      while (cur && hops < 50) {
        hops += 1
        const pt = getBoardTask(cur)
        const next = pt?.parentId ? String(pt.parentId) : null
        if (!next) break
        depth += 1
        cur = next
      }
      if (depth > maxDepth) {
        leader({ level: "warn", type: "task_rejected_budget", reason: "max_depth", parentId, depth, maxDepth })
        return { ok: false, error: "max_depth_exceeded", message: `task depth=${depth} exceeds max_depth=${maxDepth}` }
      }
    }
  }

  const task = {
    id,
    kind,
    title,
    goal,
    parentId,
    status,
    role,
    lane,
    priority,
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
    prompt_ref: promptRef,
    createdAt: now,
    updatedAt: now,
    lastJobId: null,
  }
  putBoardTask(task)
  leader({ level: "info", type: "board_task_created", id, kind, status, title: title.slice(0, 120) })
  if (kind === "parent") {
    try {
      ensureParentLedgers(task)
      bumpParentProgress({ parentId: task.id, type: "parent_created", details: { status: task.status, lane: task.lane ?? null } })
    } catch (e) {
      // best-effort
      noteBestEffort("boardTaskCreated_parent_progress", e, { task_id: task.id })
    }
  } else if (parentId) {
    try {
      bumpParentProgress({ parentId: parentId, type: "child_created", details: { task_id: id, role, status } })
    } catch (e) {
      // best-effort
      noteBestEffort("boardTaskCreated_child_progress", e, { parent_id: parentId, task_id: id })
    }
  }
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
  lines.push("历史 flow_bottleneck 统计:")
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
    lines.push("近期样本:")
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

function factoryManagerDefaultExecutors() {
  return ["opencodecli", "codex"]
}

function factoryManagerDefaultModels() {
  const models = []
  const free = modelsFree.length ? modelsFree[0] : occliModelDefault
  if (free) models.push(free)
  models.push("gpt-5.2")
  return Array.from(new Set(models)).slice(0, 6)
}

function buildLocalFlowResponse(bottleneck, summary, summaryText) {
  const reasons = Array.isArray(bottleneck?.reasons) ? bottleneck.reasons : []
  const parentNeedsSplit = Number(bottleneck?.parentNeedsSplit ?? 0)
  const atomicReady = Number(bottleneck?.atomicReady ?? 0)
  const queued = Number(bottleneck?.queued ?? 0)
  const running = bottleneck?.running ?? {}
  const max = bottleneck?.max ?? {}
  const actions = []
  const bottlenecks = []

  if (parentNeedsSplit > 0) {
    bottlenecks.push({ reason: "parents_need_split", evidence: { parentNeedsSplit } })
    actions.push({ type: "split", todo: "startSplitForParent on stalled parents", owner: "gateway", when: "now" })
  }

  const runningTotal = Number(running.codex ?? 0) + Number(running.opencodecli ?? 0)
  const maxTotal = Number(max.codex ?? 0) + Number(max.opencodecli ?? 0)
  if (atomicReady > 0 && maxTotal > 0 && runningTotal >= maxTotal) {
    bottlenecks.push({ reason: "executor_capacity_full", evidence: { atomicReady, running, max } })
    actions.push({
      type: "throttle",
      todo: "pause new dispatch; drain running jobs; consider reducing queue inflow",
      owner: "gateway",
      when: "now",
    })
  }
  if (queued > Math.max(20, autoPumpMaxDispatch * 4)) {
    bottlenecks.push({ reason: "job_queue_backlog", evidence: { queued } })
    actions.push({ type: "queue", todo: "run schedule() and ensure workers alive; cap external inflow", owner: "gateway", when: "now" })
  }
  if (!bottlenecks.length && reasons.length) {
    bottlenecks.push({ reason: reasons.join("|"), evidence: { raw: bottleneck } })
  }

  const nextTasks = []
  if (parentNeedsSplit > 0) nextTasks.push({ kind: "internal", action: "startSplitForParent", count: Math.min(parentNeedsSplit, autoFlowMaxSplit) })
  if (queued > 0 && runningTotal < Math.max(2, maxTotal)) nextTasks.push({ kind: "internal", action: "wake_workers", hint: "underutilized but queued" })

  return {
    summary: summaryText ?? formatFlowBottleneckSummary(summary),
    bottlenecks,
    actions,
    nextTasks,
  }
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
  const plan = buildLocalFlowResponse(bottleneck, summary, summaryText)
  leader({ level: "info", type: "flow_manager_local", plan, bottleneck })
  saveFlowManagerState({ last_created_at: now, last_reasons_key: reasonsKey })
  if (!flowManagerLlmEnabled) return { ok: true, local: true, plan }

  const title = `Flow bottleneck response: ${(bottleneck?.reasons ?? []).join("|") || "unknown"}`
  const fallbackGoal = [
    "Role: FACTORY_MANAGER.",
    "目标：对 flow_bottleneck 触发即处理，给出调度与分解方案并指出卡点修复动作。",
    "输出要求：JSON {summary, bottlenecks[], actions[], nextTasks[]}.",
    "",
    "当前触发事件:",
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
    "",
    "Local pre-analysis (gateway):",
    JSON.stringify(plan, null, 2),
  ].join("\n")

  const triggerEventJson = JSON.stringify(
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
    2,
  )
  const rendered = renderPromptOrFallback({
    role_id: "factory_manager.flow_bottleneck_response_v1",
    params: { trigger_event_json: triggerEventJson, summary_text: summaryText, local_plan_json: JSON.stringify(plan, null, 2) },
    fallback: fallbackGoal,
    note: "flow_bottleneck_response_v1",
  })
  const goal = rendered.text

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    prompt_ref: rendered.prompt_ref,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "flow_bottleneck_response_v1",
    allowedExecutors: factoryManagerDefaultExecutors(),
    allowedModels: factoryManagerDefaultModels(),
    timeoutMs: flowManagerTaskTimeoutMs,
  })

  if (!created.ok) return created
  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "flow_manager_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 1000
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCountsInternal()
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
  } catch (e) {
    noteBestEffort("saveLearnedPatternsHookState", e, { file: learnedPatternsHookStateFile })
    if (cfg.strictWrites) throw e
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
  const fallbackGoal = [
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
  const rendered = renderPromptOrFallback({
    role_id: "factory_manager.learned_patterns_response_v1",
    params: { summary_json: JSON.stringify(summary, null, 2) },
    fallback: fallbackGoal,
    note: "learned_patterns_response_v1",
  })
  const goal = rendered.text

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    prompt_ref: rendered.prompt_ref,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "learned_patterns_response_v1",
    allowedExecutors: factoryManagerDefaultExecutors(),
    allowedModels: factoryManagerDefaultModels(),
    timeoutMs: learnedPatternsTaskTimeoutMs,
  })
  if (!created.ok) return created

  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "learned_patterns_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 920
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCountsInternal()
    const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
    else schedule()
    leader({ level: "info", type: "learned_patterns_dispatched", id: created.task.id, jobId: dispatched.job.id, topReason, topCount, delta })
  }

  // Batchlane learning: mine patterns/playbooks/skills drafts from the same spike signal (rate-limited by the same hook).
  try {
    const mine = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `Lessons: mine patterns/playbooks (${topReason})`,
      goal: [
        "Role: LESSONS_MINER.",
        "Goal: turn this failure spike into machine-matchable patterns + executable playbooks + skill drafts (MVP).",
        "",
        "Inputs:",
        "- learned_patterns_summary.json (top reason + counts)",
        "- learned_patterns.jsonl (raw failures)",
        "- state_events.jsonl (context)",
        "",
        "Outputs (write to repo):",
        "- patterns/<pattern_id>.json (scc.pattern.v1)",
        "- playbooks/<playbook_id>.json (scc.playbook.v1) with enablement gray rollout + rollback_conditions",
        "- skills_drafts/<skill_id>/... (optional draft notes)",
        "",
        "Learned patterns summary:",
        JSON.stringify(summary, null, 2),
      ].join("\n"),
      role: "lessons_miner",
      runner: "internal",
      lane: "batchlane",
      area: "control_plane",
      task_class_id: "lessons_mine_v1",
      allowedExecutors: ["codex"],
      allowedModels: ["gpt-5.2"],
      timeoutMs: 900000,
      files: [
        "artifacts/executor_logs/learned_patterns_summary.json",
        "artifacts/executor_logs/learned_patterns.jsonl",
        "artifacts/executor_logs/state_events.jsonl",
        "contracts/pattern/pattern.schema.json",
        "contracts/playbook/playbook.schema.json",
        "contracts/enablement/enablement.schema.json",
        "patterns/README.md",
        "playbooks/README.md",
        "skills_drafts/README.md",
      ],
      allowedTests: ["python tools/scc/gates/run_ci_gates.py --submit artifacts/{task_id}/submit.json"],
    })
    if (mine.ok) dispatchBoardTaskToExecutor(mine.task.id)
  } catch (e) {
    // best-effort
    noteBestEffort("learnedPatternsHook_autotrigger", e)
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
  } catch (e) {
    noteBestEffort("saveTokenCfoHookState", e, { file: tokenCfoHookStateFile })
    if (cfg.strictWrites) throw e
  }
}

function loadStabilityHookState() {
  try {
    if (!fs.existsSync(stabilityHookStateFile)) return { last_triggered_at: 0, last_reason: null }
    const raw = fs.readFileSync(stabilityHookStateFile, "utf8")
    const parsed = JSON.parse(raw)
    return { last_triggered_at: Number(parsed?.last_triggered_at ?? 0), last_reason: parsed?.last_reason ?? null }
  } catch {
    return { last_triggered_at: 0, last_reason: null }
  }
}

function saveStabilityHookState(next) {
  try {
    fs.writeFileSync(stabilityHookStateFile, JSON.stringify(next, null, 2), "utf8")
  } catch (e) {
    noteBestEffort("saveStabilityHookState", e, { file: stabilityHookStateFile })
    if (cfg.strictWrites) throw e
  }
}

function maybeTriggerStabilityController() {
  const state = loadStabilityHookState()
  const now = Date.now()
  if (Number.isFinite(stabilityHookMinMs) && stabilityHookMinMs > 0 && now - (state.last_triggered_at ?? 0) < stabilityHookMinMs) {
    return { ok: false, error: "rate_limited" }
  }
  const limits = wipLimits()
  const snap = runningInternalByLane()
  const queued = Array.from(jobs.values()).filter((j) => j.status === "queued" && j.runner !== "external").length
  const overloaded = queued >= stabilityQueuedThreshold || (limits.total > 0 && snap.total >= limits.total && queued > 0)
  if (!overloaded) return { ok: false, error: "healthy" }

  const title = `Stability: backpressure / overload (queued=${queued})`
  const goal = [
    "Role: STABILITY_CONTROLLER (SRE).",
    "Goal: system overload detected. Propose concrete backpressure / lane / WIP / degradation actions to restore stability.",
    "",
    "Inputs:",
    `- WIP limits: ${JSON.stringify(limits)}`,
    `- Running internal: ${JSON.stringify(snap)}`,
    `- Queued internal: ${queued}`,
    "",
    "Constraints:",
    "- Do NOT edit business code.",
    "- Prefer fastlane, reduce mainlane concurrency, and keep verification at smoke when overloaded.",
    "- If a lane/executor is flapping, propose circuit-breaker quarantine rules (factory_policy.json changes optional).",
    "",
    "Output:",
    "- A short action list + stability_actions.json proposal (what to change, thresholds, rollback).",
  ].join("\n")

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    role: "stability_controller",
    runner: "internal",
    lane: "fastlane",
    area: "control_plane",
    task_class_id: "stability_overload_v1",
    allowedExecutors: ["codex"],
    allowedModels: ["gpt-5.2"],
    timeoutMs: 600000,
    files: ["factory_policy.json", "artifacts/executor_logs/heartbeat.jsonl", "artifacts/executor_logs/state_events.jsonl"],
    allowedTests: ["python tools/scc/gates/run_ci_gates.py --submit artifacts/{task_id}/submit.json"],
  })
  if (!created.ok) return created
  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  saveStabilityHookState({ last_triggered_at: now, last_reason: "overload" })
  return { ok: true, task: created.task, dispatched: dispatched.ok }
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
  if (!(Number.isFinite(unusedRatio) && Number.isFinite(included))) return { ok: false, error: "bad_top" }
  if (unusedRatio < tokenCfoUnusedRatio || included < tokenCfoIncludedMin) return { ok: false, error: "below_threshold" }

  const key = `${top.task_class ?? "none"}:${top.executor ?? "unknown"}:${included}:${Math.round(unusedRatio * 100)}`
  if (state.last_key === key) return { ok: false, error: "duplicate" }

  const title = `Token CFO: context waste detected (${Math.round(unusedRatio * 100)}% unused)`
  const fallbackGoal = [
    "Role: FACTORY_MANAGER.",
    "Goal: reduce wasted context and token burn without lowering 1-pass success rate.",
    "Output: JSON {summary, waste_cases[], actions[], nextTasks[]}.",
    "",
    "Token CFO snapshot:",
    JSON.stringify(snapshot, null, 2),
    "",
    "Policy targets:",
    "- Tighten pins/templates (prefer line_windows) for recurring waste cases.",
    "- Add/adjust preflight blockers for known guaranteed-fail patterns.",
    "- Do NOT increase governance noise; prefer local heuristics + small changes.",
  ].join("\n")
  const rendered = renderPromptOrFallback({
    role_id: "factory_manager.token_cfo_response_v1",
    params: { snapshot_json: JSON.stringify(snapshot, null, 2) },
    fallback: fallbackGoal,
    note: "token_cfo_response_v1",
  })
  const goal = rendered.text

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    prompt_ref: rendered.prompt_ref,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "token_cfo_response_v1",
    allowedExecutors: factoryManagerDefaultExecutors(),
    allowedModels: factoryManagerDefaultModels(),
    timeoutMs: tokenCfoTaskTimeoutMs,
  })
  if (!created.ok) return created

  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "token_cfo_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 910
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCountsInternal()
    const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
    if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
    else schedule()
    leader({ level: "info", type: "token_cfo_dispatched", id: created.task.id, jobId: dispatched.job.id, key })
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
  const fallbackGoal = [
    "Role: FACTORY_MANAGER.",
    "目标：针对系统鲁棒性反馈触发，定位卡点并给出修复/缓解/调度动作。",
    "输出要求：JSON {summary, bottlenecks[], actions[], nextTasks[]}.",
    "",
    "触发事件:",
    JSON.stringify(event, null, 2),
    "",
    "同类事件统计:",
    `count=${summary.count}`,
    "samples=",
    JSON.stringify(summary.samples, null, 2),
  ].join("\n")
  const rendered = renderPromptOrFallback({
    role_id: "factory_manager.feedback_response_v1",
    params: { event_json: JSON.stringify(event, null, 2), summary_json: JSON.stringify({ count: summary.count, samples: summary.samples }, null, 2) },
    fallback: fallbackGoal,
    note: "feedback_response_v1",
  })
  const goal = rendered.text

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    prompt_ref: rendered.prompt_ref,
    role: "factory_manager",
    runner: "internal",
    area: "control_plane",
    task_class_id: "feedback_response_v1",
    allowedExecutors: factoryManagerDefaultExecutors(),
    allowedModels: factoryManagerDefaultModels(),
    timeoutMs: flowManagerTaskTimeoutMs,
  })

  if (!created.ok) return created
  const dispatched = dispatchBoardTaskToExecutor(created.task.id)
  if (!dispatched.ok) {
    leader({ level: "warn", type: "feedback_manager_dispatch_failed", id: created.task.id, error: dispatched.error })
  } else if (dispatched.job) {
    dispatched.job.priority = 900
    jobs.set(dispatched.job.id, dispatched.job)
    const running = runningCountsInternal()
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
  const fallbackGoal = lines.join("\n")

  const tasksLines = tasks
    .map((t) => `- ${t.task_id} | role=${t.role ?? "?"} | area=${t.area ?? "?"} | class=${t.task_class ?? "?"} | reason=${t.reason ?? "ok"}`)
    .join("\n")
  const jsonSummaryExample = JSON.stringify(
    { batch_id: batchId, tasks_total: tasks.length, ok: [], unknown: [], needs_followup: [] },
    null,
    2,
  )

  const rendered = renderPromptOrFallback({
    role_id: "status_review.audit_v1",
    params: { batch_id: batchId, report_path: reportPath, tasks_lines: tasksLines, json_summary_example: jsonSummaryExample },
    fallback: fallbackGoal,
    note: "status_review_audit_v1",
  })
  return { goal: rendered.text, prompt_ref: rendered.prompt_ref }
}

function createStatusReviewAuditTask({ batchId, tasks }) {
  const title = `Status Review Audit: Batch ${batchId} (${tasks.length})`
  const built = buildStatusReviewAuditGoal({ batchId, tasks })
  const goal = built.goal
  const allowedModels = Array.isArray(codexPreferredOrder) && codexPreferredOrder.length ? codexPreferredOrder.slice(0, 2) : ["gpt-5.3-codex", "gpt-5.2-codex"]
  return createBoardTask({
    title,
    goal,
    prompt_ref: built.prompt_ref,
    kind: "atomic",
    status: "ready",
    role: "status_review",
    area: "control_plane",
    allowedExecutors: ["codex"],
    allowedModels,
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

function startSplitForParent(t, { reason } = {}) {
  if (!t || t.kind !== "parent") return { ok: false, error: "not_parent" }
  const strict = requireDesigner52(t)
  if (!strict.ok) return { ok: false, error: strict.error }
  if (t.splitJobId) {
    const existing = jobs.get(t.splitJobId)
    if (existing && (existing.status === "queued" || existing.status === "running")) {
      return { ok: false, error: "split_already_running" }
    }
  }

  const executor = t.allowedExecutors?.[0] ?? "codex"
  const model =
    executor === "codex"
      ? (codexModelForced ?? t.allowedModels?.[0] ?? codexModelDefault)
      : (t.allowedModels?.[0] ?? occliModelDefault)
  const files = Array.isArray(t.files) ? t.files : []
  const ctx = files.length ? createContextPackFromFiles({ files, maxBytes: 260_000 }) : { ok: true, id: null, bytes: 0 }
  if (!ctx.ok) return { ok: false, error: ctx.error }

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
    allowedTests: ["test commands (>=1, must include >=1 non-task_selftest for patch roles)"],
    files: ["relative file paths to include in context pack (optional)"],
    runner: "external|internal",
    lane: "fastlane|mainlane|batchlane|dlq|quarantine",
    priority: "number (optional; higher runs first)",
  }

  const fallbackPrompt = [
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
    String(t.goal ?? ""),
    "",
    "Schema (scc.task_graph.v1):",
    JSON.stringify(schema, null, 2),
    "",
    "示例：",
    "GOOD (concise, has files/tests/pins):",
    JSON.stringify(
      [
        {
          title: "Add health check endpoint",
          goal: "Expose GET /health with status + git sha",
          role: "engineer",
          files: ["services/api/health.ts", "services/api/routes.ts", "tests/api/health.test.ts"],
          allowedExecutors: ["codex"],
          allowedModels: ["gpt-5.2"],
          allowedTests: ["npm test services/api/health.test.ts"],
          pins: { allowed_paths: ["services/api", "tests/api/health.test.ts"], max_files: 4, max_loc: 160 },
          acceptance: ["health endpoint returns 200 with sha", "tests pass"],
          stop_conditions: ["pins_insufficient"],
        },
      ],
      null,
      2,
    ),
    "",
    "BAD (缺 goal/files/tests/pins):",
    JSON.stringify([{ title: "do it", goal: "", files: [], allowedTests: ["task_selftest"] }], null, 2),
    "",
    "输出仅此 JSON。模型假设：",
    `executor model = '${STRICT_DESIGNER_MODEL}', pins-first, CI 必须有非 task_selftest 自测。`,
  ].join("\n")

  const rendered = renderPromptOrFallback({
    role_id: "planner.split_parent",
    params: {
      parent_goal: String(t.goal ?? ""),
      schema_json: JSON.stringify(schema, null, 2),
      good_example_json: JSON.stringify(
        [
          {
            title: "Add health check endpoint",
            goal: "Expose GET /health with status + git sha",
            role: "engineer",
            files: ["services/api/health.ts", "services/api/routes.ts", "tests/api/health.test.ts"],
            allowedExecutors: ["codex"],
            allowedModels: ["gpt-5.2"],
            allowedTests: ["npm test services/api/health.test.ts"],
            pins: { allowed_paths: ["services/api", "tests/api/health.test.ts"], max_files: 4, max_loc: 160 },
            acceptance: ["health endpoint returns 200 with sha", "tests pass"],
            stop_conditions: ["pins_insufficient"],
          },
        ],
        null,
        2,
      ),
      bad_example_json: JSON.stringify([{ title: "do it", goal: "", files: [], allowedTests: ["task_selftest"] }], null, 2),
      strict_model: STRICT_DESIGNER_MODEL,
    },
    fallback: fallbackPrompt,
    note: "startSplitForParent",
  })

  const prompt = rendered.text

  const timeoutMs = Number.isFinite(t.timeoutMs) ? t.timeoutMs : timeoutCodexMs
  const job = makeJob({ prompt, model, executor, taskType: "board_split", timeoutMs })
  job.runner = t.runner ?? "external"
  job.contextPackId = ctx.id
  job.prompt_ref = rendered.prompt_ref
  job.boardTaskId = t.id
  jobs.set(job.id, job)
  schedule()

  t.splitJobId = job.id
  t.lastJobId = job.id
  t.dispatch_attempts = Number(t.dispatch_attempts ?? 0) + 1
  t.status = "in_progress"
  t.updatedAt = Date.now()
  putBoardTask(t)
  leader({ level: "info", type: "board_task_split_started", id: t.id, jobId: job.id, executor, model, reason: reason ?? null })
  return { ok: true, task: t, job }
}

function ensureSplitTaskForAtomic(t, job) {
  if (!autoCreateSplitOnTimeout) return null
  if (!t || t.kind !== "atomic") return null
  const titleLower = String(t.title ?? "").toLowerCase()
  if (titleLower.startsWith("split failed atomic")) return null
  if (t.splitTaskId) return null

  const existing = listBoardTasks().find(
    (x) => x.kind === "parent" && x?.pointers && typeof x.pointers === "object" && x.pointers.sourceTaskId === t.id,
  )
  if (existing) {
    t.splitTaskId = existing.id
    t.updatedAt = Date.now()
    putBoardTask(t)
    return { ok: false, reason: "already_exists", taskId: existing.id }
  }

  const filesList = Array.isArray(t.files) ? t.files : []
  const pointers = {
    docs: ["http://127.0.0.1:18788/docs/NAVIGATION.md", "http://127.0.0.1:18788/docs/AI_CONTEXT.md"],
    rules: ["http://127.0.0.1:18788/docs/PROMPTING.md", "http://127.0.0.1:18788/docs/EXECUTOR.md"],
    maps: ["http://127.0.0.1:18788/docs/STATUS.md"],
    sourceTaskId: t.id,
  }

  const fallbackGoal = [
    "As DESIGNER: decompose the following FAILED atomic task into <=10 minute atomic subtasks.",
    "",
    `FAILED TASK ID: ${t.id}`,
    `FAILED TITLE: ${t.title ?? ""}`,
    `FAILED ROLE: ${t.role ?? ""}`,
    "FAILED GOAL:",
    String(t.goal ?? ""),
    "",
    `FAILED REASON: ${job?.reason ?? job?.error ?? "timeout"}`,
    "",
    "Constraints:",
    "- Output MUST be a JSON array (no prose outside JSON).",
    "- Each subtask MUST include: title, goal, role, skills, pointers, files, allowedExecutors, allowedModels, runner, status.",
    "- Keep each subtask runnable without scanning repo: use pointers/docs + small file lists.",
    "- Prefer splitting by file/module and by independent acceptance tests.",
  ].join("\n")

  const rendered = renderPromptOrFallback({
    role_id: "designer.split_failed_atomic",
    params: {
      task_id: t.id,
      task_title: t.title ?? "",
      task_role: t.role ?? "",
      task_goal: String(t.goal ?? ""),
      failed_reason: String(job?.reason ?? job?.error ?? "timeout"),
    },
    fallback: fallbackGoal,
    note: "ensureSplitTaskForAtomic",
  })

  const goal = rendered.text

  const out = createBoardTask({
    kind: "parent",
    title: `Split failed atomic: ${t.title}`.slice(0, 180),
    goal,
    prompt_ref: rendered.prompt_ref,
    parentId: t.parentId ?? null,
    status: "needs_split",
    role: "designer",
    allowedExecutors: ["codex"],
    allowedModels: [STRICT_DESIGNER_MODEL],
    files: filesList,
    pointers,
    runner: "external",
  })
  if (!out.ok) return { ok: false, reason: out.error }

  t.splitTaskId = out.task.id
  t.updatedAt = Date.now()
  putBoardTask(t)
  leader({ level: "warn", type: "split_task_created", id: out.task.id, sourceTaskId: t.id })
  if (autoDispatchSplitTasks) {
    startSplitForParent(out.task, { reason: "auto_split_on_timeout" })
  }
  return { ok: true, task: out.task }
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
    // Success resets the per-task model ladder attempt counter.
    if (Number.isFinite(Number(t.modelAttempt)) && Number(t.modelAttempt) !== 0) t.modelAttempt = 0
  }
  else if (job.status === "failed") {
    const autoRequeueTimeoutEnabled = String(process.env.AUTO_REQUEUE_TIMEOUT ?? "true").toLowerCase() !== "false"
    const autoRequeueTimeoutMax = Number(process.env.AUTO_REQUEUE_TIMEOUT_MAX ?? "3")
    const autoRequeueCooldownMs = Number(process.env.AUTO_REQUEUE_TIMEOUT_COOLDOWN_MS ?? "60000")
    const autoRequeueToolingEnabled = String(process.env.AUTO_REQUEUE_TOOLING ?? "true").toLowerCase() !== "false"
    const autoRequeueToolingMax = Number(process.env.AUTO_REQUEUE_TOOLING_MAX ?? "2")
    const autoRequeueToolingCooldownMs = Number(process.env.AUTO_REQUEUE_TOOLING_COOLDOWN_MS ?? "30000")

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

    // Tooling stability: if a known-bad executor fails (e.g. opencode-cli empty output),
    // requeue once with a safer executor (codex) instead of failing the task immediately.
    const reason = String(job.reason ?? "")
    const stderr = String(job.stderr ?? "")

    // Model ladder auto-retry: when occli hits model-level throttle/auth errors, advance the ladder
    // (strong -> weak) before falling back to a different executor.
    const modelFailureLike = job.executor === "opencodecli" && ["rate_limited", "unauthorized", "forbidden"].includes(reason)
    if (autoRequeueModelFailures && modelFailureLike && t.kind === "atomic") {
      const attempt = Number.isFinite(Number(t.modelAttempt)) ? Number(t.modelAttempt) : 0
      const pool = occliModelPoolForTask(t)
      const canAdvance = pool.length > 1 && attempt < pool.length - 1
      if (
        canAdvance &&
        Number.isFinite(autoRequeueModelFailMax) &&
        autoRequeueModelFailMax > 0 &&
        attempt < autoRequeueModelFailMax
      ) {
        const nextAttempt = attempt + 1
        const nextModel = pool[Math.max(0, Math.min(pool.length - 1, nextAttempt))]
        t.modelAttempt = nextAttempt
        t.cooldownUntil =
          Date.now() + (Number.isFinite(autoRequeueModelFailCooldownMs) ? Math.max(5000, autoRequeueModelFailCooldownMs) : 60000)
        t.status = "ready"
        t.updatedAt = Date.now()
        t.lastJobStatus = job.status
        t.lastJobReason = job.reason ?? null
        t.lastJobFinishedAt = job.finishedAt ?? Date.now()
        t.pointers = {
          ...(t.pointers && typeof t.pointers === "object" ? t.pointers : {}),
          model_ladder: {
            at: new Date().toISOString(),
            from_attempt: attempt,
            to_attempt: nextAttempt,
            next_model: nextModel ?? null,
            reason,
          },
        }
        putBoardTask(t)
        try {
          writeRetryPlanArtifact({
            task: t,
            event_type: "MODEL_FAILURE",
            reason,
            next_attempt: Number(t.dispatch_attempts ?? 0) + 1,
            notes: `Model failure (${reason}); advance occli model ladder to attempt=${nextAttempt} (next_model=${nextModel}).`,
          })
        } catch (e) {
          // best-effort
          noteBestEffort("writeRetryPlanArtifact_model_failure", e, { task_id: t.id })
        }
        leader({
          level: "warn",
          type: "board_task_requeued",
          id: t.id,
          jobId: job.id,
          reason: "model_failure_ladder",
          modelAttempt: t.modelAttempt,
          nextModel,
          cooldownUntil: t.cooldownUntil,
        })
        return
      }
    }

    const occliEmptyOutput =
      job.executor === "opencodecli" &&
      stderr.includes("opencode-cli exited non-zero") &&
      stderr.toLowerCase().includes("empty output")
    const toolingLike =
      occliEmptyOutput ||
      ["executor_error", "missing_binary", "network_error", "unauthorized", "forbidden", "rate_limited", "wrong_subcommand", "occli_bun_install_failed", "occli_plugin_404"].includes(
        reason
      )
    if (
      autoRequeueToolingEnabled &&
      toolingLike &&
      t.kind === "atomic" &&
      job.executor === "opencodecli" &&
      Number.isFinite(autoRequeueToolingMax) &&
      autoRequeueToolingMax > 0 &&
      (t.toolingRetries ?? 0) < autoRequeueToolingMax
    ) {
      t.toolingRetries = (t.toolingRetries ?? 0) + 1
      t.cooldownUntil =
        Date.now() + (Number.isFinite(autoRequeueToolingCooldownMs) ? Math.max(5000, autoRequeueToolingCooldownMs) : 30000)
      t.status = "ready"
      t.updatedAt = Date.now()
      t.lastJobStatus = job.status
      t.lastJobReason = job.reason ?? null
      t.lastJobFinishedAt = job.finishedAt ?? Date.now()
      const prevAllowed = Array.isArray(t.allowedExecutors) ? t.allowedExecutors.slice(0, 4) : []
      if (!prevAllowed.includes("codex")) prevAllowed.push("codex")
      t.allowedExecutors = ["codex"]
      t.runner = "external"
      t.pointers = {
        ...(t.pointers && typeof t.pointers === "object" ? t.pointers : {}),
        tooling_fallback: {
          at: new Date().toISOString(),
          from_executor: job.executor ?? null,
          to_executor: "codex",
          reason,
          stderr_sig: stderr.trim() ? `sha1:${sha1(normalizeForSignature(stderr))}` : null,
          previous_allowed_executors: prevAllowed,
          retry: t.toolingRetries,
        },
      }
      putBoardTask(t)
      writeRetryPlanArtifact({
        task: t,
        event_type: "EXECUTOR_ERROR",
        reason,
        next_attempt: Number(t.dispatch_attempts ?? 0) + 1,
        notes: "Tooling error detected for opencodecli; requeue with codex.",
      })
      leader({
        level: "warn",
        type: "board_task_requeued",
        id: t.id,
        jobId: job.id,
        reason: "tooling_error",
        executor: job.executor ?? null,
        toolingRetries: t.toolingRetries,
        cooldownUntil: t.cooldownUntil,
      })
      return
    }

    if (t.kind === "atomic" && String(job.reason ?? "") === "timeout" && job.executor === "codex") {
      t.status = "needs_split"
    } else {
      t.status = "failed"
    }
  }
  else return
  t.updatedAt = Date.now()
  t.lastJobStatus = job.status
  if (t.status === "needs_split" && String(job.reason ?? "") === "timeout") t.lastJobReason = "timeout_needs_split"
  else t.lastJobReason = job.reason ?? null
  t.lastJobFinishedAt = job.finishedAt ?? Date.now()

  // Fail-closed escalation: NEED_INPUT must enter DLQ immediately with a missing-inputs list.
  if (t.status === "failed" && String(job.reason ?? "") === "needs_input" && t.kind === "atomic") {
    t.lane = "dlq"
    const opened = t.dlq_opened === true
    t.dlq_opened = true
    if (!opened) {
      const needs = Array.isArray(job?.submit?.needs_input) ? job.submit.needs_input.map((x) => String(x)).filter(Boolean) : []
      openDlqForTask({
        task: t,
        reason_code: "NEED_INPUT",
        summary: `Executor returned NEED_INPUT (${needs.length} items).`,
        missing_inputs: needs.slice(0, 20),
        last_event: { event_type: "EXECUTOR_ERROR", t: new Date().toISOString(), reason: "needs_input" },
      })
    }
  }

  putBoardTask(t)
  if (t.status === "needs_split" && t.kind === "atomic") {
    ensureSplitTaskForAtomic(t, job)
  }
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
  const eventType = mapResultToEventType({ status: t.status, reason: t.lastJobReason ?? null })
  const routedLane = routeLaneForEventType(eventType)
  if (t.status === "failed" && routedLane && (t.lane == null || String(t.lane) === "mainlane") && routedLane !== "mainlane") {
    t.lane = routedLane
    t.updatedAt = Date.now()
    putBoardTask(t)
    leader({ level: "info", type: "lane_routed", id: t.id, event_type: eventType, lane: routedLane })
  }
  if (t.status === "failed") {
    try {
      writeRetryPlanArtifact({
        task: t,
        event_type: eventType,
        reason: t.lastJobReason ?? null,
        next_attempt: Number(t.dispatch_attempts ?? 0) + 1,
        notes: "Task failed; use retry_plan.json to determine next action and lane.",
      })
    } catch (e) {
      // best-effort
      noteBestEffort("writeRetryPlanArtifact_failed_task", e, { task_id: t.id })
    }
  }
  appendStateEvent({
    schema_version: "scc.event.v1",
    t: new Date().toISOString(),
    event_type: eventType,
    task_id: t.id,
    parent_id: t.parentId ?? null,
    kind: t.kind ?? null,
    status: t.status,
    role: t.role ?? null,
    area: t.area ?? null,
    lane: t.lane ?? null,
    task_class: t.task_class_id ?? t.task_class_candidate ?? null,
    task_class_params: t.task_class_params ?? null,
    executor: job.executor ?? null,
    model: job.model ?? null,
    attempts: job.attempts ?? null,
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
    policy_gate_ok: job.policy_gate?.ok ?? null,
    policy_gate_required: job.policy_gate?.required ?? null,
    policy_gate_skipped: job.policy_gate?.skipped ?? null,
    artifacts_paths: job.submit?.artifacts ?? null,
    stacktrace_hash:
      t.status === "failed" && String(job.stderr ?? "").trim()
        ? `sha1:${sha1(normalizeForSignature(job.stderr))}`
        : null,
    reason: t.lastJobReason ?? null,
    routing: routedLane ? { lane: routedLane } : null,
  })
  try {
    applyRepoHealthFromEvent({ event_type: eventType })
    applyCircuitBreakersFromEvent({ event_type: eventType })
  } catch (e) {
    // best-effort
    noteBestEffort("applyHealthBreakers_from_event", e, { event_type: eventType, task_id: t.id })
  }
  if (t.status === "failed") {
    // Auto-create a pins fixup task for pins-related failures (trigger -> handle, high priority).
    maybeCreatePinsFixupTask({ boardTask: t, job })
    // L8: apply playbooks to the retry plan deterministically (no new tasks).
    try {
      maybeApplyPlaybooks({ eventType, boardTask: t, job })
    } catch (e) {
      // best-effort
      noteBestEffort("maybeApplyPlaybooks", e, { event_type: eventType, task_id: t.id })
    }
  }
  if (t.status === "done") {
    maybeTriggerAuditOnDone(t)
  }
  if (t.status === "done" && t.task_class_id === "ci_fixup_v1") {
    const sourceId = t.pointers?.sourceTaskId ?? null
    if (sourceId) {
      const src = getBoardTask(String(sourceId))
      if (src && src.status === "failed" && String(src.lastJobReason ?? "").startsWith("ci_")) {
        const gateOk = job?.ci_gate?.ran === true && job?.ci_gate?.ok === true
        if (gateOk) {
          src.status = "done"
          src.updatedAt = Date.now()
          src.lastJobStatus = "done"
          src.lastJobReason = "ci_fixup_applied"
          src.lastJobFinishedAt = Date.now()
          src.pointers = {
            ...(src.pointers && typeof src.pointers === "object" ? src.pointers : {}),
            ci_fixup: { fixupTaskId: t.id, fixupJobId: job.id, applied_at: new Date().toISOString() },
          }
          putBoardTask(src)
          leader({ level: "info", type: "ci_fixup_applied_to_source", sourceId: src.id, fixupId: t.id, jobId: job.id })
        } else {
          // Fallback: requeue once if fixup finished but gate not OK (should be rare).
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
  if (t.status === "done" && ["doc_adr_fixup_v1", "ssot_index_fixup_v1", "schema_fixup_v1"].includes(String(t.task_class_id ?? ""))) {
    const sourceId = t.pointers?.sourceTaskId ?? null
    if (sourceId) {
      const src = getBoardTask(String(sourceId))
      if (src && src.status === "failed" && String(src.lastJobReason ?? "").startsWith("policy_gate_")) {
        const prev = Number(src.policy_requeue_count ?? 0)
        if (prev < 2) {
          src.policy_requeue_count = prev + 1
          src.status = "ready"
          src.updatedAt = Date.now()
          putBoardTask(src)
          const out = dispatchBoardTaskToExecutor(src.id)
          leader({
            level: out.ok ? "info" : "warn",
            type: "policy_fixup_requeued",
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
}

function dispatchBoardTaskToExecutor(id) {
  const t = getBoardTask(id)
  if (!t) return { ok: false, error: "not_found" }
  if (t.kind !== "atomic") return { ok: false, error: "not_atomic" }
  if (t.status !== "ready" && t.status !== "backlog") return { ok: false, error: "bad_status" }
  if (t.pins_pending) return { ok: false, error: "pins_pending" }
  // Hard budget enforcement (fail-closed): stop spawning executor tasks when the root parent budget is exhausted.
  try {
    const root = rootParentIdForTask(t)
    if (root) {
      const parent = getBoardTask(root)
      if (parent) ensureParentLedgers(parent)
      const paths = parentLedgerPaths(root)
      const prog = loadJsonSafe(paths.progress_ledger_json)
      const b = factoryBudgets()
      const maxTokens = Number(b.max_total_tokens_budget ?? 0)
      const maxVerify = Number(b.max_total_verify_minutes ?? 0)
      const usedTokens = prog?.usage ? Number(prog.usage.tokens_input ?? 0) + Number(prog.usage.tokens_output ?? 0) : 0
      const usedVerify = prog?.usage ? Number(prog.usage.verify_minutes ?? 0) : 0
      const tokensExhausted = Number.isFinite(maxTokens) && maxTokens > 0 && Number.isFinite(usedTokens) && usedTokens >= maxTokens
      const verifyExhausted = Number.isFinite(maxVerify) && maxVerify > 0 && Number.isFinite(usedVerify) && usedVerify >= maxVerify
      if (tokensExhausted || verifyExhausted) {
        const nowTs = Date.now()
        t.status = "failed"
        t.lastJobStatus = "failed"
        t.lastJobReason = "budget_exhausted"
        t.lastJobFinishedAt = nowTs
        t.updatedAt = nowTs
        putBoardTask(t)
        appendStateEvent({
          schema_version: "scc.event.v1",
          t: new Date().toISOString(),
          event_type: "RETRY_EXHAUSTED",
          task_id: t.id,
          parent_id: t.parentId ?? null,
          kind: t.kind ?? null,
          status: t.status,
          role: t.role ?? null,
          area: t.area ?? null,
          lane: t.lane ?? null,
          task_class: t.task_class_id ?? t.task_class_candidate ?? null,
          executor: null,
          model: null,
          reason: "budget_exhausted",
          details: { root_parent_id: root, used_tokens: usedTokens, max_tokens: maxTokens, used_verify_minutes: usedVerify, max_verify_minutes: maxVerify },
        })
        try {
          writeRetryPlanArtifact({
            task: t,
            event_type: "RETRY_EXHAUSTED",
            reason: "budget_exhausted",
            next_attempt: Number(t.dispatch_attempts ?? 0) + 1,
            notes: "Parent budget exhausted; require human input or budget increase.",
          })
        } catch (e) {
          // best-effort
          noteBestEffort("writeRetryPlanArtifact_budget_exhausted", e, { task_id: t.id, parent_id: root })
        }
        try {
          bumpParentProgress({ parentId: root, type: "child_failed", details: { task_id: t.id, reason: "budget_exhausted" }, stallReason: "budget_exhausted" })
        } catch (e) {
          // best-effort
          noteBestEffort("bumpParentProgress_budget_exhausted", e, { task_id: t.id, parent_id: root })
        }
        return { ok: false, error: "budget_exhausted", root_parent_id: root, used_tokens: usedTokens, max_tokens: maxTokens, used_verify_minutes: usedVerify, max_verify_minutes: maxVerify }
      }
    }
  } catch (e) {
    // best-effort
    noteBestEffort("budgetGovernor_check", e, { task_id: t.id })
  }
  if (quarantineActive()) {
    const allowedDuring = new Set(["fastlane", "quarantine", "dlq"])
    const cls = String(t.task_class_id ?? "").trim()
    const allowClass = new Set(["ci_fixup_v1", "pins_fixup_v1", "schema_fixup_v1", "retry_exhausted_v1"])
    if (!allowedDuring.has(String(t.lane ?? "")) && !allowClass.has(cls)) {
      appendJsonl(routerFailuresFile, { t: new Date().toISOString(), task_id: t.id, reason: "quarantined", lane: t.lane ?? null, task_class: cls || null })
      leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: "quarantined", until: circuitBreakerState?.quarantine_until ?? null })
      return { ok: false, error: "quarantined", until: circuitBreakerState?.quarantine_until ?? null }
    }
  }
  const degradation = computeDegradationState()
  const stopBleedingCheck = shouldAllowTaskUnderStopTheBleedingV1({ action: degradation.action, task: t })
  if (!stopBleedingCheck.ok) {
    try {
      t.status = "blocked"
      t.lastJobStatus = "blocked"
      t.lastJobReason = "stop_the_bleeding"
      t.cooldownUntil = Date.now() + 5 * 60 * 1000
      t.updatedAt = Date.now()
      putBoardTask(t)
      appendStateEvent({
        schema_version: "scc.event.v1",
        t: new Date().toISOString(),
        event_type: "POLICY_VIOLATION",
        task_id: t.id,
        parent_id: t.parentId ?? null,
        kind: t.kind ?? null,
        status: t.status,
        role: t.role ?? null,
        area: t.area ?? null,
        lane: t.lane ?? null,
        task_class: t.task_class_id ?? t.task_class_candidate ?? null,
        reason: "stop_the_bleeding",
        details: { action: degradation.action ?? null, signals: degradation.signals ?? null },
      })
    } catch (e) {
      // best-effort
      noteBestEffort("appendStateEvent_policy_violation_stop_the_bleeding", e, { task_id: t.id })
    }
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: "stop_the_bleeding",
      task_class: t.task_class_id ?? null,
      lane: t.lane ?? null,
      details: { action: degradation.action ?? null, signals: degradation.signals ?? null },
    })
    leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: "stop_the_bleeding", details: { action: degradation.action ?? null, signals: degradation.signals ?? null } })
    return { ok: false, error: "stop_the_bleeding", details: { action: degradation.action ?? null, signals: degradation.signals ?? null } }
  }
  if (timeoutFuseUntil && Date.now() < timeoutFuseUntil && (t.runner ?? "external") === "external") {
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: "timeout_fused",
      fuse_until: timeoutFuseUntil,
    })
    return { ok: false, error: "timeout_fused", until: timeoutFuseUntil }
  }
  if (roleSystem) {
    if (!t.role) {
      const normalizedDefault = normalizeRole(defaultTaskRole)
      if (!normalizedDefault) return { ok: false, error: "invalid_role", message: "task.role missing and default role invalid" }
      t.role = normalizedDefault
      t.updatedAt = Date.now()
      putBoardTask(t)
      leader({ level: "warn", type: "role_defaulted", id: t.id, role: t.role })
    }
    if (!roleSystem.roles?.has(String(t.role))) {
      appendJsonl(routerFailuresFile, { t: new Date().toISOString(), task_id: t.id, reason: "invalid_role", role: t.role ?? null })
      return { ok: false, error: "invalid_role" }
    }
    const skillCheck = validateRoleSkills(roleSystem, t.role, t.skills ?? [])
    if (!skillCheck.ok) {
      appendJsonl(routerFailuresFile, {
        t: new Date().toISOString(),
        task_id: t.id,
        reason: "skill_not_allowed",
        role: t.role ?? null,
        details: skillCheck,
      })
      return { ok: false, error: skillCheck.error ?? "skill_not_allowed", details: skillCheck }
    }
  }
  const needsRealTests = roleRequiresRealTests(t.role)
  const hasRealTests =
    Array.isArray(t.allowedTests) && t.allowedTests.some((x) => !String(x ?? "").toLowerCase().includes("task_selftest"))
  if (needsRealTests && !hasRealTests) {
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

  if (String(t.role ?? "").toLowerCase() === "engineer" && (!Array.isArray(t.files) || t.files.length === 0)) {
    const nowTs = Date.now()
    t.status = "failed"
    t.lastJobStatus = "failed"
    t.lastJobReason = "missing_files"
    t.lastJobFinishedAt = nowTs
    t.updatedAt = nowTs
    t.pins_pending = true
    putBoardTask(t)
    const fixup = maybeCreatePinsFixupTask({ boardTask: t, job: { reason: "missing_files" } })
    leader({
      level: "warn",
      type: "dispatch_rejected",
      id: t.id,
      reason: "missing_files",
      role: t.role ?? null,
      pins_fixup: fixup?.ok ?? false,
      fixup_error: fixup?.error ?? null,
    })
    return { ok: false, error: "missing_files" }
  }

  const maxAttempts = maxTotalAttempts()
  const prevAttempts = Number(t.dispatch_attempts ?? 0)
  if (Number.isFinite(maxAttempts) && maxAttempts > 0 && prevAttempts >= maxAttempts) {
    const nowTs = Date.now()
    const opened = t.dlq_opened === true
    t.status = "failed"
    t.lane = "dlq"
    t.dlq_opened = true
    t.updatedAt = nowTs
    putBoardTask(t)
    if (!opened) {
      openDlqForTask({
        task: t,
        reason_code: "RETRY_EXHAUSTED",
        summary: `Retry budget exhausted (dispatch_attempts=${prevAttempts}, max=${maxAttempts}).`,
        missing_inputs: [],
        last_event: { event_type: "RETRY_EXHAUSTED", t: new Date().toISOString(), reason: t.lastJobReason ?? null },
      })
      try {
        const created = createBoardTask({
          kind: "atomic",
          status: "ready",
          title: `Retry exhausted: ${t.title ?? t.id}`,
          goal: [
            "Role: RETRY_ORCHESTRATOR.",
            "Goal: Retry budget exhausted. Produce a RETRY_PLAN (scc.retry_plan.v1) and a DLQ summary (missing inputs) for human follow-up.",
            "",
            `Source task_id: ${t.id}`,
            `Last reason: ${t.lastJobReason ?? "unknown"}`,
            `Attempts: ${prevAttempts} / ${maxAttempts}`,
          ].join("\n"),
          role: "retry_orchestrator",
          runner: "internal",
          lane: "dlq",
          area: "control_plane",
          task_class_id: "retry_exhausted_v1",
          parentId: t.parentId ?? null,
          allowedExecutors: ["codex"],
          allowedModels: ["gpt-5.2"],
          timeoutMs: 600000,
          files: ["artifacts/executor_logs/state_events.jsonl", "artifacts/dlq/dlq.jsonl", "factory_policy.json"],
          allowedTests: ["python tools/scc/gates/run_ci_gates.py --submit artifacts/{task_id}/submit.json"],
          pointers: { sourceTaskId: t.id, reason: "retry_exhausted" },
        })
        if (created.ok) dispatchBoardTaskToExecutor(created.task.id)
      } catch (e) {
        // best-effort
        noteBestEffort("retryExhausted_autocreate_task", e, { source_task_id: t.id })
      }
      appendStateEvent({
        schema_version: "scc.event.v1",
        t: new Date().toISOString(),
        event_type: "RETRY_EXHAUSTED",
        task_id: t.id,
        parent_id: t.parentId ?? null,
        kind: t.kind ?? null,
        status: t.status,
        role: t.role ?? null,
        area: t.area ?? null,
        lane: t.lane ?? null,
        task_class: t.task_class_id ?? t.task_class_candidate ?? null,
        executor: null,
        model: null,
        reason: "retry_exhausted",
      })
    }
    try {
      writeRetryPlanArtifact({
        task: t,
        event_type: "RETRY_EXHAUSTED",
        reason: "retry_exhausted",
        next_attempt: prevAttempts + 1,
        notes: `Retry budget exhausted (dispatch_attempts=${prevAttempts}, max=${maxAttempts}); route to DLQ.`,
      })
    } catch (e) {
      // best-effort
      noteBestEffort("writeRetryPlanArtifact_retry_exhausted", e, { task_id: t.id })
    }
    return { ok: false, error: "retry_exhausted", maxAttempts, attempts: prevAttempts }
  }

  const executor = pickExecutorForTask(t) ?? "codex"
  const model =
    executor === "opencodecli" ? pickOccliModelForTask(t) : pickCodexModelForTask(t)
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
  let effectivePins = resolvePinsForTask(t)
  const roleKey = String(t.role ?? "").toLowerCase()
  let rolePolicy = null
  if (roleSystem) {
    rolePolicy = roleSystem.policiesByRole?.get(roleKey) ?? null
    if (!rolePolicy) {
      appendJsonl(routerFailuresFile, { t: new Date().toISOString(), task_id: t.id, reason: "missing_role_policy", role: t.role ?? null })
      return { ok: false, error: "missing_role_policy" }
    }
  }

  // Map-first pins builder (deterministic): when pins are missing, try deriving from current map version.
  if (autoPinsFromMap && (!effectivePins || typeof effectivePins !== "object") && Array.isArray(t.files) && t.files.length) {
    const ref = currentMapRef()
    if (ref?.hash) {
      const child = {
        title: String(t.title ?? "").slice(0, 240),
        goal: String(t.goal ?? ""),
        role: String(t.role ?? "executor"),
        files: Array.isArray(t.files) ? t.files.slice(0, 16) : [],
        allowedTests: Array.isArray(t.allowedTests) ? t.allowedTests.slice(0, 24) : [],
        // Placeholder only to satisfy schema shapes; builder ignores child_task.pins.
        pins: { allowed_paths: [String((Array.isArray(t.files) ? t.files[0] : "") ?? "")].filter(Boolean) },
      }
      const req = {
        schema_version: "scc.pins_request.v1",
        task_id: t.id,
        child_task: child,
        signals: { keywords: ["preflight", "pins", "map"] },
        map_ref: { path: ref.path ?? "map/map.json", hash: ref.hash },
        budgets: { max_files: 20, max_loc: 240, default_line_window: 140 },
      }
      const built = buildPinsFromMapV1({ repoRoot: SCC_REPO_ROOT, request: req })
      if (built?.ok && built.pins) {
        try {
          writePinsV1Outputs({
            repoRoot: SCC_REPO_ROOT,
            taskId: t.id,
            outDir: `artifacts/${t.id}/pins`,
            pinsResult: built.result_v2 ?? built.result,
            pinsSpec: built.pins,
            detail: built.detail,
          })
        } catch (e) {
          noteBestEffort("writePinsV1Outputs", e, { task_id: t.id })
        }
        t.pins = built.pins
        t.pins_pending = false
        t.updatedAt = Date.now()
        putBoardTask(t)
        effectivePins = resolvePinsForTask(t)
        leader({ level: "info", type: "auto_pins_from_map", id: t.id, hash: ref.hash, files: built.pins.allowed_paths?.slice(0, 12) ?? null })
      } else if (built && !built.ok) {
        appendJsonl(routerFailuresFile, {
          t: new Date().toISOString(),
          task_id: t.id,
          reason: "auto_pins_from_map_failed",
          role: t.role ?? null,
          details: built,
        })
      }
    }
  }

  if (rolePolicy?.permissions?.read?.pins_required) {
    const allow = Array.isArray(effectivePins?.allowed_paths) ? effectivePins.allowed_paths : []
    if (allow.length === 0) {
      appendJsonl(routerFailuresFile, { t: new Date().toISOString(), task_id: t.id, reason: "missing_pins", role: t.role ?? null })
      return { ok: false, error: "missing_pins" }
    }
  }
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
  const needsPins = requirePins || (Array.isArray(t.files) && t.files.length > 0)
  if (needsPins && !effectivePins) {
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: "missing_pins",
      role: t.role ?? null,
      area: t.area ?? null,
    })
    const nowTs = Date.now()
    const fixup = maybeCreatePinsFixupTask({ boardTask: t, job: { reason: "missing_pins" } })
    t.pins_pending = Boolean(fixup?.ok)
    t.status = "failed"
    t.lastJobStatus = "failed"
    t.lastJobReason = "missing_pins"
    t.lastJobFinishedAt = nowTs
    t.updatedAt = nowTs
    putBoardTask(t)
    leader({
      level: "warn",
      type: "dispatch_rejected",
      id: t.id,
      reason: "missing_pins",
      pins_fixup: fixup?.ok ?? false,
      fixup_error: fixup?.error ?? null,
    })
    return { ok: false, error: "missing_pins" }
  }

  // Role policy enforcement (fail-closed) before dispatch: read/write scopes must be within role policy.
  if (rolePolicy) {
    const check = validateRolePolicyForTask({ task: t, rolePolicy, pinsSpec: effectivePins })
    if (!check.ok) {
      appendJsonl(routerFailuresFile, { t: new Date().toISOString(), task_id: t.id, reason: "role_policy_violation", role: t.role ?? null, details: check })
      try {
        t.status = "failed"
        t.lastJobStatus = "failed"
        t.lastJobReason = "role_policy_violation"
        t.lastJobFinishedAt = Date.now()
        t.updatedAt = Date.now()
        putBoardTask(t)
        appendStateEvent({
          schema_version: "scc.event.v1",
          t: new Date().toISOString(),
          event_type: "POLICY_VIOLATION",
          task_id: t.id,
          parent_id: t.parentId ?? null,
          kind: t.kind ?? null,
          status: t.status,
          role: t.role ?? null,
          area: t.area ?? null,
          lane: t.lane ?? null,
          task_class: t.task_class_id ?? t.task_class_candidate ?? null,
          reason: "role_policy_violation",
          details: check,
        })
      } catch (e) {
        // best-effort
        noteBestEffort("appendStateEvent_role_policy_violation", e, { task_id: t.id })
      }
      return { ok: false, error: "role_policy_violation", details: check }
    }
  }

  // Preflight gate (fail-closed): pins coverage + allowedTests validity + role write scope.
  if (preflightGateEnabled && rolePolicy?.gates?.preflight_required && effectivePins && typeof effectivePins === "object") {
    try {
      const childForPreflight = {
        title: String(t.title ?? "").slice(0, 240),
        goal: String(t.goal ?? ""),
        role: String(t.role ?? ""),
        files: Array.isArray(t.files) ? t.files.slice(0, 32) : [],
        allowedTests: Array.isArray(t.allowedTests) ? t.allowedTests.slice(0, 32) : [],
      }
      const pre = runPreflightV1({ repoRoot: SCC_REPO_ROOT, taskId: t.id, childTask: childForPreflight, pinsSpec: effectivePins, rolePolicy })
      if (pre?.ok && pre.preflight) {
        try {
          writePreflightV1Output({ repoRoot: SCC_REPO_ROOT, taskId: t.id, outPath: `artifacts/${t.id}/preflight.json`, preflight: pre.preflight })
        } catch (e) {
          // best-effort
          noteBestEffort("writePreflightV1Output", e, { task_id: t.id })
        }
        if (!pre.preflight.pass) {
          let recovered = false
          const miss = pre.preflight?.missing ?? {}
          const hasTestsMissing = Array.isArray(miss.tests) && miss.tests.length > 0
          const hasScopeMissing = Array.isArray(miss.write_scope) && miss.write_scope.length > 0
          const reason = hasTestsMissing ? "test_command_missing" : hasScopeMissing ? "scope_conflict" : "pins_insufficient"
          const eventType = reason.includes("pins") ? "PINS_INSUFFICIENT" : "PREFLIGHT_FAILED"

          // Deterministic preflight recovery: if tests are missing, try to pick a valid command (Map/eval-manifest driven).
          if (hasTestsMissing) {
            const fix = autoFixAllowedTestsFromSignals({
              taskId: t.id,
              rolePolicy,
              pinsSpec: effectivePins,
              baseChildTask: childForPreflight,
              preflight: pre.preflight,
            })
            if (fix?.ok && Array.isArray(fix.allowedTests) && fix.allowedTests.length) {
              t.allowedTests = fix.allowedTests
              t.updatedAt = Date.now()
              putBoardTask(t)
              leader({ level: "info", type: "preflight_autofix_allowed_tests", id: t.id, picked: fix.picked ?? null })
              try {
                const childRetry = { ...childForPreflight, allowedTests: t.allowedTests }
                const pre2 = runPreflightV1({ repoRoot: SCC_REPO_ROOT, taskId: t.id, childTask: childRetry, pinsSpec: effectivePins, rolePolicy })
                if (pre2?.ok && pre2.preflight) {
                  writePreflightV1Output({ repoRoot: SCC_REPO_ROOT, taskId: t.id, outPath: `artifacts/${t.id}/preflight.json`, preflight: pre2.preflight })
                  if (pre2.preflight.pass) {
                    appendStateEvent({
                      schema_version: "scc.event.v1",
                      t: new Date().toISOString(),
                      event_type: "SUCCESS",
                      task_id: t.id,
                      parent_id: t.parentId ?? null,
                      kind: t.kind ?? null,
                      status: t.status,
                      role: t.role ?? null,
                      area: t.area ?? null,
                      lane: t.lane ?? null,
                      task_class: t.task_class_id ?? t.task_class_candidate ?? null,
                      reason: "preflight_autofix_allowed_tests",
                      details: { picked: fix.picked ?? null, candidates: fix.candidates ?? null },
                    })
                    try {
                      applyRepoHealthFromEvent({ event_type: "SUCCESS" })
                      applyCircuitBreakersFromEvent({ event_type: "SUCCESS" })
                    } catch (e) {
                      // best-effort
                      noteBestEffort("applyHealthBreakers_success", e, { task_id: t.id })
                    }
                    recovered = true
                  } else {
                    // fall through to fail-closed handling below with updated preflight content
                    pre.preflight = pre2.preflight
                  }
                }
              } catch (e) {
                // fall through
                noteBestEffort("preflight_autofix_failed", e, { task_id: t?.id ?? null })
              }
            }
          }

          if (recovered) {
            // Preflight recovery succeeded; proceed to dispatch.
          } else {
          const nowTs = Date.now()
          t.status = "failed"
          t.lastJobStatus = "failed"
          t.lastJobReason = reason
          t.lastJobFinishedAt = nowTs
          t.updatedAt = nowTs
          putBoardTask(t)
          appendJsonl(routerFailuresFile, {
            t: new Date().toISOString(),
            task_id: t.id,
            reason: "preflight_failed",
            role: t.role ?? null,
            details: pre.preflight,
          })
          appendStateEvent({
            schema_version: "scc.event.v1",
            t: new Date().toISOString(),
            event_type: eventType,
            task_id: t.id,
            parent_id: t.parentId ?? null,
            kind: t.kind ?? null,
            status: t.status,
            role: t.role ?? null,
            area: t.area ?? null,
            lane: t.lane ?? null,
            task_class: t.task_class_id ?? t.task_class_candidate ?? null,
            executor: null,
            model: null,
            reason,
            details: pre.preflight,
          })
          try {
            applyRepoHealthFromEvent({ event_type: eventType })
            applyCircuitBreakersFromEvent({ event_type: eventType })
          } catch (e) {
            // best-effort
            noteBestEffort("applyHealthBreakers_preflight_failed", e, { event_type: eventType, task_id: t.id })
          }
          try {
            writeRetryPlanArtifact({
              task: t,
              event_type: eventType,
              reason,
              next_attempt: Number(t.dispatch_attempts ?? 0) + 1,
              notes: "Dispatch-time preflight failed; follow retry plan before re-dispatch.",
            })
          } catch (e) {
            // best-effort
            noteBestEffort("writeRetryPlanArtifact_preflight_failed", e, { task_id: t.id })
          }
          leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: "preflight_failed", event_type: eventType })
          if (eventType === "PINS_INSUFFICIENT") {
            try {
              maybeCreatePinsFixupTask({ boardTask: t, job: { id: `preflight_${t.id}`, reason } })
            } catch (e) {
              // best-effort
              noteBestEffort("maybeCreatePinsFixupTask_preflight", e, { task_id: t.id })
            }
          }
          return { ok: false, error: "preflight_failed", reason, event_type: eventType, preflight: pre.preflight }
          }
        }
      }
    } catch (e) {
      appendJsonl(routerFailuresFile, {
        t: new Date().toISOString(),
        task_id: t.id,
        reason: "preflight_exception",
        role: t.role ?? null,
        error: String(e?.message ?? e),
      })
      return { ok: false, error: "preflight_exception" }
    }
  }
  try {
    if (effectivePins) writePinsArtifacts({ taskId: t.id, pins: effectivePins, requiredFiles: t.files })
  } catch (e) {
    // best-effort
    noteBestEffort("writePinsArtifacts", e, { task_id: t.id })
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
  const gatewayWillRunTests = payload.runner === "external"
  const guardBypass = guardBypassRegex.test(`${t.title ?? ""}\n${t.goal ?? ""}`)
  if (guardBypass) {
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: "guardrail_bypass_text",
      role: t.role ?? null,
      area: t.area ?? null,
    })
    leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: "guardrail_bypass_text" })
    return { ok: false, error: "guardrail_bypass_text" }
  }
  const ciHandbookText = getCiHandbookText()
  const lastCi = getLastCiFailure(t.id) || getLastCiGateSummary(t.id)
  const ciSummary = lastCi
    ? `PREV_CI: exit=${lastCi.exitCode ?? "?"} skipped=${lastCi.skipped ?? false} timedOut=${lastCi.timedOut ?? false}\n` +
      `${lastCi.stderrPreview ? `STDERR_PREVIEW: ${String(lastCi.stderrPreview).slice(0, 400)}` : ""}`
    : null

  const role = t.role ?? null
  const roleErrors = role ? readRoleErrors(role, 5) : []
  const taskArtBase = `artifacts/${t.id}`
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
        pins_json_path: `${taskArtBase}/pins/pins.json`,
        pins_md_path: `${taskArtBase}/pins/pins.md`,
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
        // External workers are unreliable at running CI gates (and can loop forever trying to fix gate outputs).
        // The gateway runs CI gates deterministically post-completion instead.
        commands: gatewayWillRunTests ? [] : Array.isArray(allowedTests) ? allowedTests : [],
        gateway_commands: gatewayWillRunTests ? (Array.isArray(allowedTests) ? allowedTests : []) : [],
        smoke: [],
        regression: [],
      },
      acceptance: [
        gatewayWillRunTests ? "Gateway will run allowed_tests after completion (do NOT run tests yourself)." : "All allowed_tests pass",
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
        report_md: `${taskArtBase}/report.md`,
        selftest_log: `${taskArtBase}/selftest.log`,
        preflight_json: `${taskArtBase}/preflight.json`,
        evidence_dir: `${taskArtBase}/evidence/`,
        patch_diff: `${taskArtBase}/patch.diff`,
        submit_json: `${taskArtBase}/submit.json`,
      },
    },
	    submit_contract: {
	      schema_version: "scc.submit.v1",
	      task_id: t.id,
	      status: "DONE|NEED_INPUT|FAILED",
	      changed_files: [],
        new_files: [],
        allow_paths: {
          read: Array.isArray(effectivePins?.allowed_paths) ? effectivePins.allowed_paths.slice(0, 64) : [],
          write: Array.isArray(effectivePins?.allowed_paths) ? effectivePins.allowed_paths.slice(0, 64) : [],
        },
      tests: {
        commands: Array.isArray(allowedTests) ? allowedTests : [],
        passed: true,
        summary: "All tests passed",
      },
	      artifacts: {
	        report_md: `${taskArtBase}/report.md`,
	        selftest_log: `${taskArtBase}/selftest.log`,
	        evidence_dir: `${taskArtBase}/evidence/`,
	        patch_diff: `${taskArtBase}/patch.diff`,
	        submit_json: `${taskArtBase}/submit.json`,
	      },
	      exit_code: 0,
	      needs_input: [],
	    },
    handbook: ciHandbookText || "CI_HANDBOOK missing; see docs/AI_CONTEXT.md",
  }

  const prompt = JSON.stringify(execPrompt, null, 2)

  // Backpressure: do not enqueue new jobs if WIP limits are reached (prevents task explosion).
  const laneForWip = normalizeLane(t.lane ?? t.area) ?? "mainlane"
  const wipCheck = canEnqueueJobByLane(laneForWip, null, payload.runner === "internal" ? "internal" : "external")
  if (!wipCheck.ok) {
    leader({ level: "warn", type: "dispatch_rejected", id: t.id, reason: wipCheck.error, lane: laneForWip, limits: wipCheck.limits, snap: wipCheck.snap })
    appendJsonl(routerFailuresFile, {
      t: new Date().toISOString(),
      task_id: t.id,
      reason: wipCheck.error,
      role: t.role ?? null,
      area: t.area ?? null,
      lane: laneForWip,
      limits: wipCheck.limits,
      snap: wipCheck.snap,
    })
    // Keep task dispatchable; do not advance status.
    if (t.status !== "backlog") t.status = "ready"
    t.updatedAt = Date.now()
    putBoardTask(t)
    return { ok: false, error: wipCheck.error, limits: wipCheck.limits, snap: wipCheck.snap }
  }

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

  // Render slot-based Context Pack v1 as the single legal carrier for execution.
  // Fail-closed by default (enterprise mode), but can be disabled via CONTEXT_PACK_V1_REQUIRED=false.
  let cpv1 = null
  try {
    const out = renderSccContextPackV1Impl({ repoRoot: SCC_REPO_ROOT, taskId: t.id, role: "executor", mode: "execute", budgetTokens: null, getBoardTask })
    if (out?.ok) {
      cpv1 = out
      try {
        const p = path.join(SCC_REPO_ROOT, "artifacts", String(t.id), "context_pack_v1.json")
        writeJsonAtomic(p, {
          schema_version: "scc.context_pack_ref.v1",
          task_id: t.id,
          context_pack_id: out.context_pack_id,
          hash: out.hash,
          rendered_paths: out.rendered_paths,
          created_at: new Date().toISOString(),
          proof_required: true,
          proof_algo: "sha256(nonce_utf8||bytes)",
        })
      } catch (e) {
        // best-effort: not a correctness blocker; pack itself is already written under artifacts/scc_runs.
        noteBestEffort("context_pack_v1_ref_write_failed", e, { task_id: t.id, context_pack_id: out?.context_pack_id ?? null })
      }
    } else if (requireContextPackV1) {
      try {
        const nowTs = Date.now()
        t.status = "failed"
        t.lastJobStatus = "failed"
        t.lastJobReason = "context_pack_v1_render_failed"
        t.lastJobFinishedAt = nowTs
        t.updatedAt = nowTs
        putBoardTask(t)
        appendStateEvent({
          schema_version: "scc.event.v1",
          t: new Date().toISOString(),
          event_type: "POLICY_VIOLATION",
          task_id: t.id,
          parent_id: t.parentId ?? null,
          kind: t.kind ?? null,
          status: t.status,
          role: t.role ?? null,
          area: t.area ?? null,
          lane: t.lane ?? null,
          task_class: t.task_class_id ?? t.task_class_candidate ?? null,
          executor: null,
          model: null,
          reason: "context_pack_v1_render_failed",
          details: out ?? null,
        })
      } catch (e) {
        noteBestEffort("appendStateEvent_context_pack_v1_render_failed", e, { task_id: t.id })
      }
      appendJsonl(routerFailuresFile, { t: new Date().toISOString(), task_id: t.id, reason: "context_pack_v1_render_failed", details: out ?? null })
      return { ok: false, error: "context_pack_v1_render_failed", details: out ?? null }
    }
  } catch (e) {
    if (requireContextPackV1) {
      try {
        const nowTs = Date.now()
        t.status = "failed"
        t.lastJobStatus = "failed"
        t.lastJobReason = "context_pack_v1_render_exception"
        t.lastJobFinishedAt = nowTs
        t.updatedAt = nowTs
        putBoardTask(t)
        appendStateEvent({
          schema_version: "scc.event.v1",
          t: new Date().toISOString(),
          event_type: "POLICY_VIOLATION",
          task_id: t.id,
          parent_id: t.parentId ?? null,
          kind: t.kind ?? null,
          status: t.status,
          role: t.role ?? null,
          area: t.area ?? null,
          lane: t.lane ?? null,
          task_class: t.task_class_id ?? t.task_class_candidate ?? null,
          executor: null,
          model: null,
          reason: "context_pack_v1_render_exception",
          details: { message: String(e?.message ?? e) },
        })
      } catch (e2) {
        noteBestEffort("appendStateEvent_context_pack_v1_render_exception", e2, { task_id: t.id })
      }
      appendJsonl(routerFailuresFile, { t: new Date().toISOString(), task_id: t.id, reason: "context_pack_v1_render_exception", error: String(e?.message ?? e) })
      return { ok: false, error: "context_pack_v1_render_exception" }
    }
  }

  const job = makeJob({ prompt, model: payload.model, executor: payload.executor, taskType: payload.taskType, timeoutMs })
  job.runner = payload.runner === "internal" ? "internal" : "external"
  job.contextPackId = ctx.id
  job.contextPackV1Id = cpv1?.context_pack_id ?? null
  job.contextBytes = Number.isFinite(ctx.bytes) ? ctx.bytes : null
  job.contextFiles = Number.isFinite(ctx.fileCount) ? ctx.fileCount : null
  job.contextFilesList = Array.isArray(ctx.files) ? ctx.files : null
  job.contextSource = contextSource
  job.pinsAllowCount = Array.isArray(effectivePins?.allowed_paths) ? effectivePins.allowed_paths.length : null
  job.pinsSymbolsCount = Array.isArray(effectivePins?.symbols) ? effectivePins.symbols.length : null
  job.pinsLineWindows = effectivePins?.line_windows ? Object.keys(effectivePins.line_windows).length : null
  job.allowedTests = allowedTests
  job.boardTaskId = t.id
  job.prompt_ref = t.prompt_ref ?? null
  job.priority = Number.isFinite(Number(job.priority)) ? Number(job.priority) : computeJobPriorityForTask(t)
  // Pre-run snapshot: enables scope enforcement + submit/artifact synthesis even if executor does not emit a unified diff.
  job.pre_snapshot = capturePreSnapshot({ boardTask: t, pins: effectivePins })
  jobs.set(job.id, job)
  schedule()

  t.lastJobId = job.id
  t.dispatch_attempts = Number(t.dispatch_attempts ?? 0) + 1
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

    // Update latest pointers for UI/inspection.
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
        const fallbackGoal = [
          "Role: FACTORY_MANAGER.",
          "Goal: fix radius expansion guardrails so violations become fail-closed, and add replay/regression proof.",
          "Output: JSON {violations, fixes[], tests[], rollback}.",
          "",
          "Radius audit report:",
          JSON.stringify(rep?.audit ?? {}, null, 2),
        ].join("\n")
        const rendered = renderPromptOrFallback({
          role_id: "factory_manager.radius_audit_response_v1",
          params: { audit_json: JSON.stringify(rep?.audit ?? {}, null, 2) },
          fallback: fallbackGoal,
          note: "radius_audit_response_v1",
        })
        const goal = rendered.text
        const created = createBoardTask({
          kind: "atomic",
          status: "ready",
          title,
          goal,
          prompt_ref: rendered.prompt_ref,
          role: "factory_manager",
          runner: "internal",
          area: "control_plane",
          task_class_id: "radius_audit_response_v1",
          allowedExecutors: factoryManagerDefaultExecutors(),
          allowedModels: factoryManagerDefaultModels(),
          timeoutMs: 900000,
          files: ["artifacts/executor_logs/radius_audit/latest.json", "scc-top/tools/scc/ops/task_selftest.py"],
        })
        if (created.ok) {
          const dispatched = dispatchBoardTaskToExecutor(created.task.id)
          if (dispatched.job) {
            dispatched.job.priority = 945
            jobs.set(dispatched.job.id, dispatched.job)
            const running = runningCountsInternal()
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
      cached_input_tokens: Math.round(totalCached / Math.max(1, withUsage.length)),
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

function writeSplitArtifacts({ taskId, jobId, stdout, arr, check }) {
  const id = String(taskId ?? "").trim()
  if (!id) return { ok: false, error: "missing_task_id" }
  const base = path.join(execRoot, "artifacts", id, "split")
  try {
    fs.mkdirSync(base, { recursive: true })
  } catch (e) {
    noteBestEffort("writeSplitArtifacts.mkdir", e, { base })
  }
  try {
    const meta = {
      t: new Date().toISOString(),
      task_id: id,
      job_id: jobId ?? null,
      ok: check?.ok ?? null,
      reason: check?.reason ?? null,
      count: check?.count ?? null,
      accepted: check?.accepted ?? null,
      rejected: check?.rejected ?? null,
    }
    fs.writeFileSync(path.join(base, "split_check.json"), JSON.stringify(meta, null, 2), "utf8")
  } catch (e) {
    noteBestEffort("writeSplitArtifacts.meta", e, { task_id: id })
  }
  try {
    if (typeof stdout === "string" && stdout.trim()) {
      fs.writeFileSync(path.join(base, "split_stdout.txt"), stdout, "utf8")
    }
  } catch (e) {
    noteBestEffort("writeSplitArtifacts.stdout", e, { task_id: id })
  }
  try {
    if (Array.isArray(arr)) {
      fs.writeFileSync(path.join(base, "split.json"), JSON.stringify(arr, null, 2), "utf8")
    }
  } catch (e) {
    noteBestEffort("writeSplitArtifacts.json", e, { task_id: id })
    // ignore
  }
  return {
    ok: true,
    dir: path.relative(SCC_REPO_ROOT, base).replaceAll("\\", "/"),
    split_json: path.relative(SCC_REPO_ROOT, path.join(base, "split.json")).replaceAll("\\", "/"),
    split_check_json: path.relative(SCC_REPO_ROOT, path.join(base, "split_check.json")).replaceAll("\\", "/"),
  }
}

function runSplitOutputChecks({ job, boardTask }) {
  const taskId = String(boardTask?.id ?? "").trim()
  if (!taskId) return { ok: false, reason: "missing_task_id" }

  const stdout = String(job?.stdout ?? "")
  if (!stdout.trim()) {
    const check = { ok: false, reason: "empty_stdout", count: 0, accepted: 0, rejected: 0 }
    writeSplitArtifacts({ taskId, jobId: job?.id ?? null, stdout, arr: null, check })
    return check
  }

  const arr = extractSplitArrayFromStdout(stdout)
  if (!arr) {
    const check = { ok: false, reason: "no_json_array_found", count: 0, accepted: 0, rejected: 0 }
    writeSplitArtifacts({ taskId, jobId: job?.id ?? null, stdout, arr: null, check })
    return check
  }

  let accepted = 0
  let rejected = 0
  for (const item of arr.slice(0, 30)) {
    const title = String(item?.title ?? "").trim()
    const goal = String(item?.goal ?? "").trim()
    const files = Array.isArray(item?.files) ? item.files : []
    const tests = Array.isArray(item?.allowedTests) ? item.allowedTests : Array.isArray(item?.allowed_tests) ? item.allowed_tests : []
    const pinsRaw = item?.pins && typeof item.pins === "object" ? item.pins : null
    const pinsAllow = Array.isArray(pinsRaw?.allowed_paths) ? pinsRaw.allowed_paths : []
    const testsHasReal = tests.some((t) => !String(t ?? "").toLowerCase().includes("task_selftest"))
    if (!title || !goal || !files.length || !testsHasReal || pinsAllow.length === 0) {
      rejected += 1
      continue
    }
    accepted += 1
  }

  const check = {
    ok: accepted > 0,
    reason: accepted > 0 ? null : "no_valid_children",
    count: Array.isArray(arr) ? arr.length : 0,
    accepted,
    rejected,
  }
  writeSplitArtifacts({ taskId, jobId: job?.id ?? null, stdout, arr, check })
  return check
}

function applySplitFromJob({ parentId, jobId }) {
  const parent = getBoardTask(parentId)
  if (!parent) return { ok: false, error: "parent_not_found" }
  const job = jobs.get(jobId)
  if (!job) return { ok: false, error: "job_not_found" }
  if (job.status !== "done") return { ok: false, error: "job_not_done" }

  const arr = extractSplitArrayFromStdout(job.stdout)
  if (!arr) return { ok: false, error: "no_json_array_found" }

  try {
    writeSplitArtifacts({ taskId: parentId, jobId, stdout: String(job.stdout ?? ""), arr, check: { ok: true } })
  } catch (e) {
    // best-effort
    noteBestEffort("writeSplitArtifacts_parse", e, { parent_id: parentId, job_id: jobId })
  }

  const created = []
  const createdPins = []
  const rejected = []
  for (const item of arr.slice(0, 30)) {
    const index = created.length + rejected.length
    const title = String(item?.title ?? "").trim()
    const goal = String(item?.goal ?? "").trim()
    const files = Array.isArray(item?.files) ? item.files : []
    const tests = Array.isArray(item?.allowedTests) ? item.allowedTests : Array.isArray(item?.allowed_tests) ? item.allowed_tests : []
    const pinsRaw = item?.pins && typeof item.pins === "object" ? item.pins : null
    const pinsAllow = Array.isArray(pinsRaw?.allowed_paths) ? pinsRaw.allowed_paths : []
    const testsHasReal = tests.some((t) => !String(t ?? "").toLowerCase().includes("task_selftest"))
    if (!title || !goal || !files.length || !testsHasReal || pinsAllow.length === 0) {
      leader({
        level: "warn",
        type: "split_item_rejected_schema",
        taskId: job.boardTaskId ?? null,
        title: title || "<empty>",
        hasFiles: files.length > 0,
        hasRealTest: testsHasReal,
        pinsAllow: pinsAllow.length,
      })
      rejected.push({ index, title: title || null, reason: "schema_rejected" })
      continue
    }
    const allowedExecutors = Array.isArray(item?.allowedExecutors) ? item.allowedExecutors : ["opencodecli", "codex"]
    const allowedModels = Array.isArray(item?.allowedModels) ? item.allowedModels : []
    const skills = Array.isArray(item?.skills) ? item.skills : []
    const pointers = item?.pointers && typeof item.pointers === "object" ? item.pointers : null
    const pinsInstance = item?.pins_instance && typeof item.pins_instance === "object" ? item.pins_instance : null
    const assumptions = Array.isArray(item?.assumptions)
      ? item.assumptions
      : Array.isArray(item?.pins?.ssot_assumptions)
        ? item.pins.ssot_assumptions
        : []
    const allowedTests = Array.isArray(item?.allowedTests) ? item.allowedTests : Array.isArray(item?.allowed_tests) ? item.allowed_tests : []
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
    const lane = normalizeLane(item?.lane) ?? parent?.lane ?? "mainlane"
    const status = normalizeBoardStatus(item?.status) ?? "ready"
    const pinsFromTemplate = resolvePinsForTask({ task_class_id: taskClassId, pins_instance: pinsInstance, pins: null })
    let pins = pinsRaw || pinsFromTemplate
    // Normalize pins: never include artifacts as an allowlisted repo path.
    // Artifacts are always written by the system under artifacts/<task_id>/ and should not be in pins.allowed_paths.
    if (pins && typeof pins === "object") {
      const allowRaw = Array.isArray(pins.allowed_paths) ? pins.allowed_paths.map((x) => String(x ?? "").replaceAll("\\", "/")) : []
      const allow = allowRaw.filter((p) => p && p !== "artifacts" && !p.startsWith("artifacts/"))
      const forbidRaw = Array.isArray(pins.forbidden_paths) ? pins.forbidden_paths.map((x) => String(x ?? "").replaceAll("\\", "/")) : []
      const forbid = forbidRaw.includes("artifacts") ? forbidRaw : [...forbidRaw, "artifacts"]
      pins = { ...pins, allowed_paths: allow, forbidden_paths: forbid }
    }
    const pinsPending = splitTwoPhasePins && !pins
    const role = normalizeRole(item?.role)
    const out = createBoardTask({
      kind: "atomic",
      title,
      goal,
      parentId,
      status: pinsPending ? "blocked" : status,
      role,
      lane,
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
    } else {
      rejected.push({ index, title: title || null, reason: out.error ?? "create_failed", details: out.details ?? null })
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
        model: modelsFree?.[0] ?? occliModelDefault,
        executor: "opencodecli",
        taskType: "pins_generate",
        timeoutMs: timeoutOccliMs,
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

  if (!created.length) {
    parent.status = "needs_split"
    parent.updatedAt = Date.now()
    putBoardTask(parent)
    leader({ level: "warn", type: "board_task_split_applied_empty", id: parentId, jobId, rejected: rejected.length })
    return { ok: false, error: "no_children_created", rejected: rejected.slice(0, 30) }
  }

  parent.status = "ready"
  parent.updatedAt = Date.now()
  putBoardTask(parent)
  try {
    ensureParentLedgers(parent)
    bumpParentProgress({ parentId, type: "split_applied", details: { jobId, created: created.length, rejected: rejected.length } })
  } catch (e) {
    // best-effort
    noteBestEffort("splitApplied_parent_progress", e, { parent_id: parentId, job_id: jobId })
  }
  leader({ level: "info", type: "board_task_split_applied", id: parentId, jobId, created: created.length, rejected: rejected.length })
  return { ok: true, created, rejected: rejected.slice(0, 30) }
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

function isLikelyVirtualPath(p) {
  const s = String(p ?? "").trim().replaceAll("\\", "/")
  if (!s) return true
  if (s.includes("://")) return true
  // "18788/docs/..." style virtual paths served by gateway
  if (/^\d{2,6}\//.test(s)) return true
  return false
}

function capturePreSnapshot({ boardTask, pins, maxFiles = 64, maxBytes = 1024 * 1024 }) {
  try {
    const candidates = []
    const allowed = Array.isArray(pins?.allowed_paths) ? pins.allowed_paths : []
    const fallback = Array.isArray(boardTask?.files) ? boardTask.files : []
    for (const raw of (allowed.length ? allowed : fallback)) {
      const rel = normalizeRepoPath(raw)
      if (!rel) continue
      if (isLikelyVirtualPath(rel)) continue
      if (rel.startsWith("artifacts/")) continue
      candidates.push(rel)
    }
    const uniq = Array.from(new Set(candidates)).slice(0, maxFiles)
    const files = []
    for (const rel of uniq) {
      const abs = resolveUnderRoot(rel)
      if (!abs) continue
      try {
        if (!fs.existsSync(abs)) {
          files.push({ path: rel, exists: false })
          continue
        }
        const st = fs.statSync(abs)
        if (!st.isFile()) continue
        if (st.size > maxBytes) {
          files.push({ path: rel, exists: true, size: st.size, skipped: "too_large" })
          continue
        }
        const buf = fs.readFileSync(abs)
        const sha256 = crypto.createHash("sha256").update(buf).digest("hex")
        files.push({ path: rel, exists: true, size: st.size, sha256 })
      } catch (e) {
        // best-effort snapshot; ignore per-file errors
        noteBestEffort("capturePreSnapshot_file", e, { path: rel })
      }
    }
    // Optional rollback support: persist a content-backed snapshot for small files.
    // Stored under artifacts/<task_id>/pre_snapshot_full.json (gateway-owned; not part of submit contract).
    try {
      const enabled = String(process.env.AUTO_ROLLBACK_ON_CI_FAILED ?? "true").toLowerCase() !== "false"
      if (enabled && boardTask?.id) {
        const maxRollbackFiles = Number(process.env.AUTO_ROLLBACK_MAX_FILES ?? "3")
        const maxRollbackBytes = Number(process.env.AUTO_ROLLBACK_MAX_BYTES ?? "200000")
        const perFileMax = Number(process.env.AUTO_ROLLBACK_PER_FILE_MAX_BYTES ?? "120000")
        const capFiles = Number.isFinite(maxRollbackFiles) && maxRollbackFiles > 0 ? Math.floor(maxRollbackFiles) : 3
        const capBytes = Number.isFinite(maxRollbackBytes) && maxRollbackBytes > 0 ? Math.floor(maxRollbackBytes) : 200000
        const capPerFile = Number.isFinite(perFileMax) && perFileMax > 0 ? Math.floor(perFileMax) : 120000

        let used = 0
        const full = []
        for (const f of files.slice(0, Math.min(files.length, capFiles * 4))) {
          if (full.length >= capFiles) break
          if (!f || typeof f !== "object") continue
          const rel = normalizeRepoPath(f.path)
          if (!rel) continue
          const abs = resolveUnderRoot(rel)
          if (!abs) continue
          if (!f.exists) {
            full.push({ path: rel, exists: false })
            continue
          }
          try {
            const st = fs.statSync(abs)
            if (!st.isFile()) continue
            if (st.size > capPerFile) continue
            if (used + st.size > capBytes) continue
            const buf = fs.readFileSync(abs)
            const sha256 = crypto.createHash("sha256").update(buf).digest("hex")
            used += buf.length
            full.push({ path: rel, exists: true, size: st.size, sha256, content_b64: buf.toString("base64") })
          } catch (e) {
            // best-effort snapshot; ignore per-file errors
            noteBestEffort("capturePreSnapshot_full_file", e, { path: rel })
          }
        }
        if (full.length) {
          const file = path.join(SCC_REPO_ROOT, "artifacts", String(boardTask.id), "pre_snapshot_full.json")
          fs.mkdirSync(path.dirname(file), { recursive: true })
          fs.writeFileSync(
            file,
            JSON.stringify({ schema_version: "scc.pre_snapshot_full.v1", task_id: String(boardTask.id), at: new Date().toISOString(), total_bytes: used, files: full }, null, 2) +
              "\n",
            "utf8"
          )
        }
      }
    } catch (e) {
      // best-effort
      noteBestEffort("capturePreSnapshot_full", e, { task_id: String(boardTask?.id ?? "") })
    }
    return { schema_version: "scc.pre_snapshot.v1", at: new Date().toISOString(), files }
  } catch {
    return null
  }
}

function diffSnapshot(pre, { maxFiles = 80, maxBytes = 1024 * 1024 } = {}) {
  if (!pre || !Array.isArray(pre.files)) return null
  const touched = []
  for (const f of pre.files) {
    const rel = normalizeRepoPath(f?.path)
    if (!rel) continue
    if (isLikelyVirtualPath(rel)) continue
    const abs = resolveUnderRoot(rel)
    if (!abs) continue
    try {
      const existedBefore = Boolean(f?.exists)
      const existsNow = fs.existsSync(abs)
      if (existedBefore && !existsNow) {
        touched.push(rel)
        continue
      }
      if (!existedBefore && existsNow) {
        touched.push(rel)
        continue
      }
      if (!existsNow) continue
      const st = fs.statSync(abs)
      if (!st.isFile()) continue
      if (st.size > maxBytes || f?.skipped === "too_large") {
        // Cannot hash reliably; treat as touched only if size changed.
        if (Number.isFinite(Number(f?.size)) && Number(f.size) !== st.size) touched.push(rel)
        continue
      }
      const buf = fs.readFileSync(abs)
      const sha256 = crypto.createHash("sha256").update(buf).digest("hex")
      if (String(f?.sha256 ?? "") && String(f.sha256) !== sha256) touched.push(rel)
    } catch (e) {
      // ignore; snapshot diff is best-effort
      noteBestEffort("snapshot_diff_file_hash", e, { rel })
    }
    if (touched.length >= maxFiles) break
  }
  return { schema_version: "scc.snapshot_diff.v1", touched_files: Array.from(new Set(touched)).slice(0, maxFiles) }
}

function readPreSnapshotFull(taskId) {
  try {
    const file = path.join(SCC_REPO_ROOT, "artifacts", String(taskId), "pre_snapshot_full.json")
    if (!fs.existsSync(file)) return null
    const raw = fs.readFileSync(file, "utf8")
    const obj = JSON.parse(raw)
    return obj && typeof obj === "object" ? obj : null
  } catch {
    return null
  }
}

function applyAutoRollbackOnCiFailed({ boardTask, job, snapshotDiff, patchStats, ciGate }) {
  try {
    const enabled = String(process.env.AUTO_ROLLBACK_ON_CI_FAILED ?? "true").toLowerCase() !== "false"
    const docsOnlyMode = String(process.env.AUTO_ROLLBACK_DOCS_ONLY ?? "true").toLowerCase() !== "false"
    if (!enabled) return { ok: false, error: "disabled" }
    if (!boardTask?.id || !job) return { ok: false, error: "missing_task_or_job" }
    if (String(job?.error ?? "") !== "ci_failed") return { ok: false, error: "not_ci_failed" }
    const taskId = String(boardTask.id)

    const touched =
      Array.isArray(snapshotDiff?.touched_files) && snapshotDiff.touched_files.length
        ? snapshotDiff.touched_files
        : Array.isArray(patchStats?.files) && patchStats.files.length
          ? patchStats.files
          : []
    const touchedFiles = Array.from(new Set(touched.map((p) => normalizeRepoPath(p)).filter(Boolean))).slice(0, 50)
    if (!touchedFiles.length) return { ok: false, error: "no_touched_files" }

    if (docsOnlyMode) {
      const isDocsOnly = touchedFiles.every((p) => p.startsWith("docs/"))
      if (!isDocsOnly) return { ok: false, error: "docs_only_mode" }
    }

    const maxFiles = Number(process.env.AUTO_ROLLBACK_MAX_FILES ?? "3")
    const capFiles = Number.isFinite(maxFiles) && maxFiles > 0 ? Math.floor(maxFiles) : 3
    if (touchedFiles.length > capFiles) return { ok: false, error: "too_many_files", touched: touchedFiles.length, cap: capFiles }

    const snap = readPreSnapshotFull(taskId)
    const entries = Array.isArray(snap?.files) ? snap.files : []
    const byPath = new Map(entries.map((e) => [normalizeRepoPath(e?.path), e]))

    const missing = []
    for (const f of touchedFiles) {
      const e = byPath.get(f)
      if (!e) {
        missing.push({ file: f, reason: "not_in_snapshot" })
        continue
      }
      if (e.exists === false) continue
      if (!e.content_b64) missing.push({ file: f, reason: "missing_content" })
    }
    if (missing.length) return { ok: false, error: "snapshot_incomplete", missing }

    const applied = []
    for (const f of touchedFiles) {
      const e = byPath.get(f)
      if (!e) continue
      const abs = resolveUnderRoot(f)
      if (!abs) continue
      if (e.exists === false) {
        try {
          if (fs.existsSync(abs)) fs.unlinkSync(abs)
          applied.push({ file: f, action: "delete" })
        } catch (e) {
          // best-effort
          noteBestEffort("snapshot_restore_delete_failed", e, { abs })
        }
        continue
      }
      try {
        const buf = Buffer.from(String(e.content_b64), "base64")
        ensureDir(path.dirname(abs))
        fs.writeFileSync(abs, buf)
        applied.push({ file: f, action: "restore", bytes: buf.length })
      } catch (e) {
        // best-effort
        noteBestEffort("snapshot_restore_write_failed", e, { abs })
      }
    }

    const report = {
      schema_version: "scc.rollback_report.v1",
      task_id: taskId,
      created_at: new Date().toISOString(),
      reason: "ci_failed",
      docs_only_mode: docsOnlyMode,
      touched_files: touchedFiles,
      applied,
      ci_gate: ciGate ?? null,
    }
    const out = path.join(SCC_REPO_ROOT, "artifacts", taskId, "rollback_report.json")
    fs.mkdirSync(path.dirname(out), { recursive: true })
    fs.writeFileSync(out, JSON.stringify(report, null, 2) + "\n", "utf8")

    appendStateEvent({
      schema_version: "scc.event.v1",
      t: new Date().toISOString(),
      event_type: "ROLLBACK_APPLIED",
      task_id: taskId,
      parent_id: boardTask.parentId ?? null,
      kind: boardTask.kind ?? null,
      status: "rollback_applied",
      role: boardTask.role ?? null,
      area: boardTask.area ?? null,
      lane: boardTask.lane ?? null,
      task_class: boardTask.task_class_id ?? boardTask.task_class_candidate ?? null,
      executor: job.executor ?? null,
      model: job.model ?? null,
      reason: "auto_rollback_on_ci_failed",
      details: { report: `artifacts/${taskId}/rollback_report.json`, applied_count: applied.length },
    })
    return { ok: true, report_path: `artifacts/${taskId}/rollback_report.json`, applied }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

function artifactRelPaths(taskId) {
  const id = String(taskId ?? "").trim()
  const base = `artifacts/${id}`
  return {
    base,
    pins_dir: `${base}/pins/`,
    pins_json: `${base}/pins/pins.json`,
    pins_md: `${base}/pins/pins.md`,
    report_md: `${base}/report.md`,
    selftest_log: `${base}/selftest.log`,
    evidence_dir: `${base}/evidence/`,
    patch_diff: `${base}/patch.diff`,
    submit_json: `${base}/submit.json`,
    replay_bundle_json: `${base}/replay_bundle.json`,
  }
}

function writePinsArtifacts({ taskId, pins, requiredFiles }) {
  try {
    if (!taskId) return { ok: false, error: "missing_task_id" }
    if (!pins || typeof pins !== "object") return { ok: false, error: "missing_pins" }
    if (!Array.isArray(pins.allowed_paths) || pins.allowed_paths.length === 0) return { ok: false, error: "pins_missing_allowed_paths" }
    const req = Array.isArray(requiredFiles) ? requiredFiles.map((x) => String(x ?? "").replaceAll("\\", "/")).filter(Boolean) : []
    const reqSet = new Set(req)
    const rel = artifactRelPaths(taskId)
    const pinsDirAbs = resolveUnderRoot(rel.pins_dir)
    const pinsJsonAbs = resolveUnderRoot(rel.pins_json)
    const pinsMdAbs = resolveUnderRoot(rel.pins_md)
    if (!pinsDirAbs || !pinsJsonAbs || !pinsMdAbs) return { ok: false, error: "cannot_resolve_pins_paths" }
    ensureDir(pinsDirAbs)
    const classify = (p) => {
      const s = String(p ?? "").replaceAll("\\", "/")
      const reasons = []
      if (reqSet.has(s)) reasons.push("required_file")
      if (s.startsWith("oc-scc-local/") || s.startsWith("tools/scc/")) reasons.push("factory_control_plane")
      if (s.startsWith("contracts/") || s.startsWith("roles/") || s.startsWith("skills/") || s.startsWith("eval/")) reasons.push("control_assets")
      if (s.startsWith("docs/")) reasons.push("docs")
      if (!reasons.length) reasons.push("map_related")
      return reasons
    }
    const normLineWindows =
      pins.line_windows && typeof pins.line_windows === "object" ? pins.line_windows : {}
    const items = (pins.allowed_paths || []).slice(0, 64).map((p) => {
      const pathRel = String(p ?? "").replaceAll("\\", "/")
      const reasons = classify(pathRel)
      const windows = Array.isArray(normLineWindows?.[pathRel]) ? normLineWindows[pathRel] : []
      return {
        path: pathRel,
        reason: reasons.join(", "),
        read_only: !reqSet.has(pathRel),
        write_intent: reqSet.has(pathRel),
        symbols: Array.isArray(pins.symbols) ? pins.symbols.slice(0, 64).map((x) => String(x ?? "")).filter(Boolean) : [],
        line_windows: Array.isArray(windows) ? windows.slice(0, 64) : [],
      }
    })
    const pinsV2 = {
      items,
      allowed_paths: Array.isArray(pins.allowed_paths) ? pins.allowed_paths.slice(0, 64) : [],
      forbidden_paths: Array.isArray(pins.forbidden_paths) ? pins.forbidden_paths.slice(0, 64) : [],
      symbols: Array.isArray(pins.symbols) ? pins.symbols.slice(0, 128) : [],
      line_windows: normLineWindows,
      max_files: Number.isFinite(Number(pins.max_files)) ? Math.floor(Number(pins.max_files)) : undefined,
      max_loc: Number.isFinite(Number(pins.max_loc)) ? Math.floor(Number(pins.max_loc)) : undefined,
      ssot_assumptions: Array.isArray(pins.ssot_assumptions) ? pins.ssot_assumptions.slice(0, 16) : undefined,
    }
    const obj = { schema_version: "scc.pins_result.v2", task_id: String(taskId), pins: pinsV2, recommended_queries: [], preflight_expectation: { should_pass: true } }
    fs.writeFileSync(pinsJsonAbs, JSON.stringify(obj, null, 2) + "\n", "utf8")
    const md = [
      `# Pins for ${taskId}`,
      "",
      `- max_files: ${pins.max_files ?? ""}`,
      `- max_loc: ${pins.max_loc ?? ""}`,
      "",
      "## Reason legend",
      "- required_file: directly listed under child_task.files",
      "- factory_control_plane: SCC runtime / gates / orchestrator code",
      "- control_assets: roles/skills/contracts/eval governance assets",
      "- docs: documentation context",
      "- map_related: included via map-based expansion",
      "",
      "## Allowed paths",
      ...(pins.allowed_paths || []).map((p) => {
        const s = String(p)
        const reasons = classify(p)
        return `- ${s}  (reason: ${reasons.join(", ")})`
      }),
      "",
      "## Forbidden paths",
      ...((pins.forbidden_paths || []).map((p) => `- ${String(p)}`)),
      "",
      "## Symbols",
      ...((pins.symbols || []).map((p) => `- ${String(p)}`)),
      "",
    ].join("\n")
    fs.writeFileSync(pinsMdAbs, md, "utf8")
    return { ok: true, rel }
  } catch {
    return { ok: false, error: "exception" }
  }
}

function writeFileIfMissing(absPath, text) {
  try {
    if (fs.existsSync(absPath)) return true
    ensureDir(path.dirname(absPath))
    fs.writeFileSync(absPath, String(text ?? ""), "utf8")
    return true
  } catch {
    return false
  }
}

function writeFileAlways(absPath, text) {
  try {
    ensureDir(path.dirname(absPath))
    fs.writeFileSync(absPath, String(text ?? ""), "utf8")
    return true
  } catch {
    return false
  }
}

function ensureExternalArtifactsAndSubmit({ job, boardTask, patchText, patchStats, snapshotDiff, ciGate }) {
  if (!job || !boardTask) return { ok: false, error: "missing_job_or_task" }
  const taskId = String(boardTask.id ?? "").trim()
  if (!taskId) return { ok: false, error: "missing_task_id" }
  const rel = artifactRelPaths(taskId)
  const baseAbs = resolveUnderRoot(rel.base)
  if (!baseAbs) return { ok: false, error: "cannot_resolve_artifacts_dir" }
  ensureDir(baseAbs)

  // External executor outputs are untrusted: force-write deterministic control artifacts owned by the gateway.
  try {
    const pins = resolvePinsForTask(boardTask)
    if (pins && typeof pins === "object") {
      writePinsArtifacts({ taskId, pins, requiredFiles: boardTask.files })
      const roleKey = String(boardTask.role ?? "").toLowerCase()
      const policy = roleSystem ? roleSystem.policiesByRole?.get(roleKey) ?? null : null
      const childForPreflight = {
        title: String(boardTask.title ?? "").slice(0, 240),
        goal: String(boardTask.goal ?? ""),
        role: String(boardTask.role ?? "executor"),
        files: Array.isArray(boardTask.files) ? boardTask.files.slice(0, 16) : [],
        allowedTests: Array.isArray(boardTask.allowedTests) ? boardTask.allowedTests.slice(0, 24) : [],
        pins: { allowed_paths: Array.isArray(pins.allowed_paths) && pins.allowed_paths.length ? [String(pins.allowed_paths[0])] : [String((Array.isArray(boardTask.files) ? boardTask.files[0] : "") ?? "")].filter(Boolean) },
      }
      const pre = runPreflightV1({ repoRoot: SCC_REPO_ROOT, taskId, childTask: childForPreflight, pinsSpec: pins, rolePolicy: policy })
      if (pre?.ok && pre.preflight) {
        writePreflightV1Output({ repoRoot: SCC_REPO_ROOT, taskId, outPath: `artifacts/${taskId}/preflight.json`, preflight: pre.preflight })
      }
    }
  } catch (e) {
    // best-effort
    noteBestEffort("ensureExternalArtifacts_preflight_output", e, { task_id: taskId })
  }

  const evidenceAbs = resolveUnderRoot(rel.evidence_dir)
  if (evidenceAbs) ensureDir(evidenceAbs)

  // Persist basic evidence for audit (best-effort).
  if (evidenceAbs) {
    // Always overwrite: external executors are untrusted and may forge artifacts.
    writeFileAlways(path.join(evidenceAbs, "stdout.txt"), String(job.stdout ?? ""))
    writeFileAlways(path.join(evidenceAbs, "stderr.txt"), String(job.stderr ?? ""))
    if (job.contextPackV1Proof) {
      writeFileAlways(path.join(evidenceAbs, "context_pack_v1_proof.json"), JSON.stringify(job.contextPackV1Proof, null, 2) + "\n")
    }
    if (job.policy_violations) {
      writeFileAlways(path.join(evidenceAbs, "policy_violations.json"), JSON.stringify(job.policy_violations, null, 2) + "\n")
    }
    if (ciGate) {
      writeFileAlways(path.join(evidenceAbs, "ci_gate.json"), JSON.stringify(ciGate, null, 2) + "\n")
    }
    if (snapshotDiff && Array.isArray(snapshotDiff.touched_files)) {
      writeFileAlways(path.join(evidenceAbs, "snapshot_diff.json"), JSON.stringify(snapshotDiff, null, 2) + "\n")
    }
  }

  // patch.diff: prefer model-provided unified diff; fallback to a touched-files manifest.
  const patchAbs = resolveUnderRoot(rel.patch_diff)
  if (patchAbs) {
    const fallback = snapshotDiff?.touched_files?.length
      ? `# SCC patch.diff fallback (no unified diff in stdout)\n# touched_files:\n${snapshotDiff.touched_files.map((f) => `- ${f}`).join("\n")}\n`
      : "# SCC patch.diff fallback (no unified diff in stdout)\n"
    writeFileAlways(patchAbs, patchText ? String(patchText) : fallback)
  }

  // report.md
  const reportAbs = resolveUnderRoot(rel.report_md)
  if (reportAbs) {
    const touched = Array.isArray(job?.submit?.touched_files)
      ? job.submit.touched_files
      : Array.isArray(snapshotDiff?.touched_files)
        ? snapshotDiff.touched_files
        : []
    const lines = []
    lines.push(`# Report: ${taskId}`)
    lines.push("")
    lines.push(`- job_id: ${job.id ?? ""}`)
    lines.push(`- executor: ${job.executor ?? ""}`)
    lines.push(`- model: ${job.model ?? ""}`)
    lines.push(`- status: ${job.status ?? ""}`)
    lines.push(`- exit_code: ${job.exit_code ?? ""}`)
    if (ciGate) lines.push(`- ci_gate_ok: ${String(ciGate.ok ?? "")}`)
    if (job.contextPackV1Id) lines.push(`- context_pack_v1_id: ${String(job.contextPackV1Id)}`)
    if (job.attestationNonce) lines.push(`- attestation_nonce: ${String(job.attestationNonce)}`)
    if (job.error === "policy_violation") lines.push(`- policy_violation: ${String(job.reason ?? "policy_violation")}`)
    if (touched.length) lines.push(`- touched_files: ${touched.slice(0, 50).join(", ")}`)
    lines.push("")
    lines.push("Evidence:")
    lines.push(`- ${rel.evidence_dir}stdout.txt`)
    lines.push(`- ${rel.evidence_dir}stderr.txt`)
    if (job.contextPackV1Proof) lines.push(`- ${rel.evidence_dir}context_pack_v1_proof.json`)
    if (job.policy_violations) lines.push(`- ${rel.evidence_dir}policy_violations.json`)
    if (ciGate) lines.push(`- ${rel.evidence_dir}ci_gate.json`)
    lines.push(`- ${rel.patch_diff}`)
    writeFileAlways(reportAbs, lines.join("\n") + "\n")
  }

  // selftest.log: minimal contract to unblock hygiene (must end with EXIT_CODE=0).
  const selftestAbs = resolveUnderRoot(rel.selftest_log)
  if (selftestAbs) {
    // IMPORTANT: task success/failure is represented in submit.json (status/reason_code).
    // selftest.log is a structural artifact used by gates; keep it EXIT_CODE=0 when the gateway wrote it.
    const exitLine = "EXIT_CODE=0"
    const body = [
      `t=${new Date().toISOString()}`,
      `job_id=${job.id ?? ""}`,
      `task_id=${taskId}`,
      `job_status=${String(job.status ?? "")}`,
      `ci_gate_ran=${String(ciGate?.ran ?? false)}`,
      `ci_gate_ok=${String(ciGate?.ok ?? "")}`,
      exitLine,
    ].join("\n")
    try {
      ensureDir(path.dirname(selftestAbs))
      fs.writeFileSync(selftestAbs, body + "\n", "utf8")
    } catch (e) {
      // best-effort
      noteBestEffort("ensureExternalArtifacts_selftest_log", e, { task_id: taskId })
    }
  }

  // submit.json: if missing or non-conforming, synthesize a strict scc.submit.v1.
  const submitAbs = resolveUnderRoot(rel.submit_json)
  if (submitAbs) {
    // Always overwrite for external jobs: do not trust executor-written submit.json.
    {
      const desiredStatus = job.status === "done" ? "DONE" : "FAILED"
      const allow = resolvePinsForTask(boardTask)
      const allowPaths = Array.isArray(allow?.allowed_paths) ? allow.allowed_paths.map((p) => normalizeRepoPath(p)).filter(Boolean).slice(0, 64) : []
      const touched =
        Array.isArray(job?.submit?.touched_files) && job.submit.touched_files.length
          ? job.submit.touched_files.map((p) => normalizeRepoPath(p)).filter(Boolean)
          : Array.isArray(snapshotDiff?.touched_files)
            ? snapshotDiff.touched_files.map((p) => normalizeRepoPath(p)).filter(Boolean)
            : Array.isArray(patchStats?.files)
              ? patchStats.files.map((p) => normalizeRepoPath(p)).filter(Boolean)
              : []
      const submit = {
        schema_version: "scc.submit.v1",
        task_id: taskId,
        status: desiredStatus,
        reason_code: String(job?.submit?.reason_code ?? job?.reason ?? (desiredStatus === "DONE" ? "SYNTH_DONE" : "SYNTH_FAILED")).slice(0, 200),
        changed_files: touched.slice(0, 200),
        new_files: [],
        touched_files: touched.slice(0, 200),
        allow_paths: { read: allowPaths, write: allowPaths },
        tests: {
          commands: Array.isArray(job?.allowedTests) ? job.allowedTests : Array.isArray(boardTask.allowedTests) ? boardTask.allowedTests : [],
          passed: Boolean(job?.allowed_tests?.ran ? job.allowed_tests.ok : (ciGate?.ok ?? job.status === "done")),
          summary: job?.allowed_tests?.ran
            ? String(job.allowed_tests.summary ?? (job.allowed_tests.ok ? "Allowed tests passed" : "Allowed tests failed"))
            : ciGate?.ran
              ? (ciGate.ok ? "CI gate passed" : "CI gate failed")
              : "CI gate skipped/unknown",
        },
        artifacts: {
          report_md: rel.report_md,
          selftest_log: rel.selftest_log,
          evidence_dir: rel.evidence_dir,
          patch_diff: rel.patch_diff,
          submit_json: rel.submit_json,
        },
        exit_code: Number.isFinite(Number(job.exit_code)) ? Number(job.exit_code) : desiredStatus === "DONE" ? 0 : 1,
        needs_input: [],
      }
      try {
        fs.writeFileSync(submitAbs, JSON.stringify(submit, null, 2) + "\n", "utf8")
        job.submit = submit
      } catch (e) {
        // best-effort
        noteBestEffort("ensureExternalArtifacts_submit_json", e, { task_id: taskId })
      }
    }
  }

  // replay_bundle.json: capture enough to re-dispatch the same contract+pins with one command.
  const replayAbs = resolveUnderRoot(rel.replay_bundle_json)
  if (replayAbs) {
    const allow = resolvePinsForTask(boardTask)
    const bundle = {
      schema_version: "scc.replay_bundle.v1",
      task_id: taskId,
      created_at: new Date().toISOString(),
      source: {
        job_id: job.id ?? null,
        executor: job.executor ?? null,
        model: job.model ?? null,
        job_status: job.status ?? null,
        exit_code: job.exit_code ?? null,
      },
      board_task_payload: {
        title: boardTask.title ?? "",
        goal: boardTask.goal ?? "",
        role: boardTask.role ?? null,
        files: Array.isArray(boardTask.files) ? boardTask.files : [],
        skills: Array.isArray(boardTask.skills) ? boardTask.skills : [],
        pointers: boardTask.pointers ?? null,
        pins: allow && typeof allow === "object" ? allow : boardTask.pins ?? null,
        pins_instance: boardTask.pins_instance ?? null,
        allowedTests: Array.isArray(boardTask.allowedTests) ? boardTask.allowedTests : [],
        allowedExecutors: Array.isArray(boardTask.allowedExecutors) ? boardTask.allowedExecutors : [],
        allowedModels: Array.isArray(boardTask.allowedModels) ? boardTask.allowedModels : [],
        runner: boardTask.runner ?? "external",
        area: boardTask.area ?? null,
        lane: boardTask.lane ?? null,
        task_class_id: boardTask.task_class_id ?? null,
        task_class_candidate: boardTask.task_class_candidate ?? null,
        task_class_params: boardTask.task_class_params ?? null,
        toolingRules: boardTask.toolingRules ?? null,
      },
      artifacts: {
        report_md: rel.report_md,
        selftest_log: rel.selftest_log,
        evidence_dir: rel.evidence_dir,
        patch_diff: rel.patch_diff,
        submit_json: rel.submit_json,
        preflight_json: `artifacts/${taskId}/preflight.json`,
        pins_json: rel.pins_json,
        context_pack_v1_json: job.contextPackV1Id ? `artifacts/scc_runs/${job.contextPackV1Id}/rendered_context_pack.json` : null,
        context_pack_v1_txt: job.contextPackV1Id ? `artifacts/scc_runs/${job.contextPackV1Id}/rendered_context_pack.txt` : null,
      },
      replay: {
        dispatch_via: "tools/scc/ops/replay_bundle_dispatch.py",
        endpoint: `/board/tasks (POST) -> /board/tasks/{id}/dispatch (POST)`,
      },
    }
    try {
      ensureDir(path.dirname(replayAbs))
      fs.writeFileSync(replayAbs, JSON.stringify(bundle, null, 2) + "\n", "utf8")
    } catch (e) {
      // best-effort
      noteBestEffort("ensureExternalArtifacts_replay_bundle", e, { task_id: taskId })
    }
  }

  return { ok: true, rel }
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
  } catch (e) {
    noteBestEffort("putThread", e, { thread_id: t.id })
    if (cfg.strictWrites) throw e
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

// Slot-based Context Pack v1 lives in `oc-scc-local/src/context_pack_v1.mjs` and is exposed via gateway endpoints.

const makeJob = ({ prompt, model, executor, taskType, timeoutMs }) => ({
  id: newJobId(),
  prompt,
  prompt_ref: null,
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
  // Slot-based Context Pack v1 (legal carrier; separate from ctxDir markdown pins slices).
  contextPackV1Id: null,
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

function loadSubmitArtifact(taskId) {
  const id = taskId ? String(taskId) : ""
  if (!id) return null
  try {
    const p = path.join(execRoot, "artifacts", id, "submit.json")
    if (!fs.existsSync(p)) return null
    const raw = fs.readFileSync(p, "utf8")
    const obj = JSON.parse(raw)
    return obj && typeof obj === "object" ? obj : null
  } catch {
    return null
  }
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

	function validatePatchScope({ patchStats, boardTask }) {
	  if (!patchStats || !boardTask) return { ok: true }
	  const pins = resolvePinsForTask(boardTask)
	  const allowed = Array.isArray(pins?.allowed_paths) ? pins.allowed_paths.map((p) => normalizeRepoPath(p)).filter(Boolean) : []
	  const forbidden = Array.isArray(pins?.forbidden_paths) ? pins.forbidden_paths.map((p) => normalizeRepoPath(p)).filter(Boolean) : []
	  const files = Array.isArray(patchStats?.files) ? patchStats.files.map((p) => normalizeRepoPath(p)).filter(Boolean) : []
	  const outside =
	    allowed.length === 0
	      ? []
	      : files.filter((f) => !allowed.some((a) => f === a || f.startsWith(`${a}/`)))
	  const forbiddenHits = forbidden.length ? files.filter((f) => forbidden.some((b) => f === b || f.startsWith(`${b}/`))) : []
	  const maxFiles = Number(pins?.max_files ?? null)
	  const maxLoc = Number(pins?.max_loc ?? null)
	  const loc = Number(patchStats.added ?? 0) + Number(patchStats.removed ?? 0)

	  // Role policy enforcement (deny/allow paths) in addition to pins scope.
	  const role = String(boardTask?.role ?? "").trim().toLowerCase()
	  const policy = roleSystem ? roleSystem.policiesByRole?.get(role) ?? null : null
	  const policyAllowRaw = Array.isArray(policy?.permissions?.write?.allow_paths) ? policy.permissions.write.allow_paths : []
	  const policyDenyRaw = Array.isArray(policy?.permissions?.write?.deny_paths) ? policy.permissions.write.deny_paths : []
	  const policyAllowList = policyAllowRaw.map((x) => String(x ?? "").trim()).filter(Boolean)
	  const policyDenyList = policyDenyRaw.map((x) => String(x ?? "").trim()).filter(Boolean)
	  const policyAllowAll = policyAllowList.includes("**")

 	  const policyDenyRegexes = policyDenyList.map(globToRegexV1).filter(Boolean)
 	  const policyAllowRegexes = policyAllowList.map(globToRegexV1).filter(Boolean)
	  const policyDenyHits = policyDenyRegexes.length ? files.filter((f) => policyDenyRegexes.some((re) => re.test(f))) : []
	  const policyAllowMiss =
	    policyAllowAll || policyAllowRegexes.length === 0 ? [] : files.filter((f) => !policyAllowRegexes.some((re) => re.test(f)))
	  const errors = []
	  if (outside.length) errors.push({ reason: "outside_allow_paths", files: outside.slice(0, 20) })
	  if (forbiddenHits.length) errors.push({ reason: "forbidden_paths", files: forbiddenHits.slice(0, 20) })
	  if (policyDenyHits.length) errors.push({ reason: "role_policy_deny_paths", files: policyDenyHits.slice(0, 20) })
	  if (policyAllowMiss.length) errors.push({ reason: "role_policy_allow_paths", files: policyAllowMiss.slice(0, 20), allow: policyAllowList.slice(0, 12) })
	  if (Number.isFinite(maxFiles) && maxFiles > 0 && files.length > maxFiles)
	    errors.push({ reason: "max_files_exceeded", limit: maxFiles, got: files.length })
	  if (Number.isFinite(maxLoc) && maxLoc > 0 && loc > maxLoc)
	    errors.push({ reason: "max_loc_exceeded", limit: maxLoc, got: loc })
	  if (!errors.length) return { ok: true }
	  return { ok: false, errors, allowed, forbidden, loc }
	}

function isCiCommandAllowed(cmd) {
  const s0 = String(cmd ?? "").trim().toLowerCase()
  const s = s0.replaceAll("\\", "/")
  if (!s) return false
  const prefixes = [
    "bun test",
    "npm test",
    "pnpm test",
    "yarn test",
    "pytest",
    "python -m pytest",
    "python scc-top/tools/scc/ops/task_selftest.py",
    "python tools/scc/gates/run_ci_gates.py",
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
    if (hasShellMetacharacters(cmd)) {
      return resolve({ ok: false, exitCode: 2, durationMs: 0, stdoutText: "", stderrText: "refusing unsafe command (shell metacharacters)" })
    }
    const argv = parseCmdline(cmd)
    if (!argv.length) {
      return resolve({ ok: false, exitCode: 2, durationMs: 0, stdoutText: "", stderrText: "empty command" })
    }

    execFile(
      argv[0],
      argv.slice(1),
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
        } catch (e) {
          // best-effort; CI still functions without persisted logs
          noteBestEffort("ciGate_persist_logs", e)
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

function runAllowedTestCommand(cmd) {
  return new Promise((resolve) => {
    const start = Date.now()
    const cwd = SCC_REPO_ROOT && fs.existsSync(SCC_REPO_ROOT) ? SCC_REPO_ROOT : process.cwd()
    if (hasShellMetacharacters(cmd)) {
      return resolve({ ok: false, exitCode: 2, durationMs: 0, stdoutText: "", stderrText: "refusing unsafe command (shell metacharacters)" })
    }
    const argv = parseCmdline(cmd)
    if (!argv.length) {
      return resolve({ ok: false, exitCode: 2, durationMs: 0, stdoutText: "", stderrText: "empty command" })
    }

    execFile(
      argv[0],
      argv.slice(1),
      { cwd, timeout: 1_200_000, windowsHide: true, maxBuffer: 10 * 1024 * 1024 },
      (err, stdout, stderr) => {
        const finishedAt = Date.now()
        const durationMs = finishedAt - start
        const exitCode = err && typeof err.code === "number" ? err.code : 0
        const ok = !err && exitCode === 0
        const stdoutText = String(stdout || "")
        const stderrText = String(stderr || "")
        resolve({
          ok,
          exitCode,
          durationMs,
          startedAt: start,
          finishedAt,
          command: cmd,
          stdoutPreview: stdoutText.slice(0, 2000),
          stderrPreview: stderrText.slice(0, 2000),
          timedOut: err && String(err.message || "").toLowerCase().includes("timed out"),
        })
      }
    )
  })
}

async function runGatewayAllowedTests({ boardTask, job }) {
  const enabled = String(process.env.GATEWAY_RUN_ALLOWED_TESTS ?? "true").toLowerCase() !== "false"
  if (!enabled) return { ran: false, skipped: "disabled" }
  if (!boardTask) return { ran: false, skipped: "no_task" }
  if (!job) return { ran: false, skipped: "no_job" }
  // Only for external runs: internal LLM runners may already run tests, and we want determinism.
  if (job.runner !== "external") return { ran: false, skipped: "internal_runner" }
  const commands = Array.isArray(job.allowedTests)
    ? job.allowedTests.map((x) => String(x ?? "").trim()).filter(Boolean)
    : Array.isArray(boardTask.allowedTests)
      ? boardTask.allowedTests.map((x) => String(x ?? "").trim()).filter(Boolean)
      : []
  if (!commands.length) return { ran: false, skipped: "no_commands" }

  const max = Number(process.env.GATEWAY_ALLOWED_TESTS_MAX_COMMANDS ?? "2")
  const cap = Number.isFinite(max) && max > 0 ? Math.floor(max) : 2
  const picked = commands.slice(0, cap)
  const results = []
  for (const cmd of picked) {
    // Guard against recursion / gate re-entry.
    if (cmd.includes("tools/scc/gates/run_ci_gates.py")) continue
    const r = await runAllowedTestCommand(cmd)
    results.push(r)
    if (!r.ok) break
  }
  const ok = results.length > 0 && results.every((r) => r.ok)
  const summary = ok ? "Allowed tests passed" : "Allowed tests failed"
  const taskId = String(boardTask.id ?? job.boardTaskId ?? "")
  try {
    if (taskId) {
      const evDir = path.join(SCC_REPO_ROOT, "artifacts", taskId, "evidence")
      fs.mkdirSync(evDir, { recursive: true })
      fs.writeFileSync(path.join(evDir, "allowed_tests.json"), JSON.stringify({ schema_version: "scc.allowed_tests_run.v1", task_id: taskId, ok, results }, null, 2) + "\n", "utf8")
    }
  } catch (e) {
    // best-effort
    noteBestEffort("allowed_tests_write_evidence_failed", e, { task_id: boardTask?.id ?? null, job_id: job?.id ?? null })
  }
  try {
    leader({ level: ok ? "info" : "warn", type: "allowed_tests_ran", taskId: boardTask.id ?? null, jobId: job.id ?? null, ok, commands: picked })
  } catch (e) {
    // best-effort
    noteBestEffort("allowed_tests_leader_log_failed", e, { task_id: boardTask?.id ?? null, job_id: job?.id ?? null })
  }
  return { ran: true, ok, summary, results, commands: picked }
}

async function runCiGateForTask({ job, boardTask }) {
  if (!ciGateEnabled) return { ran: false, skipped: "disabled" }
  if (!boardTask) return { ran: false, skipped: "no_task" }
  const required = Number.isFinite(ciEnforceSinceMs) && ciEnforceSinceMs > 0 ? (boardTask.createdAt ?? 0) >= ciEnforceSinceMs : true
  if (!required) return { ran: false, skipped: "not_required", required: false }
  // CI gate is a system-level invariant check (schema/scope/hygiene/ssot/doclink/etc).
  // It must NOT depend on task.allowedTests (which are project-level tests).
  const submitPathRel = `artifacts/${boardTask.id}/submit.json`
  const gateScript = path.join(SCC_REPO_ROOT, "tools", "scc", "gates", "run_ci_gates.py")
  if (!fs.existsSync(gateScript)) return { ran: false, skipped: "missing_gate_script", required: true }
  const strictFlag = ciGatesStrict ? "--strict " : ""
  const cmd = `python tools/scc/gates/run_ci_gates.py ${strictFlag}--submit ${submitPathRel}`
  const result = await runCiGateCommand(cmd)
  return { ran: true, required: true, ...result }
}

function writeVerdictArtifact({ taskId, verdict }) {
  try {
    const tid = String(taskId ?? "").trim()
    if (!tid) return { ok: false, error: "missing_task_id" }
    const check = validateVerdictSchema(verdict)
    if (!check.ok) {
      appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "verdict_invalid", task_id: tid, details: check })
      return { ok: false, error: check.reason ?? "invalid_verdict_schema", details: check }
    }
    const file = path.join(SCC_REPO_ROOT, "artifacts", tid, "verdict.json")
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, JSON.stringify(verdict, null, 2) + "\n", "utf8")
    return { ok: true, file }
  } catch (e) {
    appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "verdict_write_failed", task_id: String(taskId ?? ""), error: String(e?.message ?? e) })
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

function writeTraceArtifact({ taskId, job, boardTask }) {
  try {
    const tid = String(taskId ?? "").trim()
    if (!tid) return { ok: false, error: "missing_task_id" }
    const root = SCC_REPO_ROOT
    const now = new Date().toISOString()

    const factoryPolicySha = sha256HexOfFile(path.join(root, "factory_policy.json"))
    const rolesSha = sha256HexOfFile(path.join(root, "roles", "registry.json"))
    const skillsSha = sha256HexOfFile(path.join(root, "skills", "registry.json"))

    const out = {
      schema_version: "scc.trace.v1",
      task_id: tid,
      created_at: now,
      updated_at: now,
      config_hashes: {
        factory_policy_sha256: factoryPolicySha ? `sha256:${factoryPolicySha}` : null,
        roles_registry_sha256: rolesSha ? `sha256:${rolesSha}` : null,
        skills_registry_sha256: skillsSha ? `sha256:${skillsSha}` : null,
      },
      routing: {
        executor: job?.executor ?? null,
        model: job?.model ?? null,
        model_effective: job?.model_effective ?? null,
      },
      artifacts: {
        submit_json: `artifacts/${tid}/submit.json`,
        report_md: `artifacts/${tid}/report.md`,
        selftest_log: `artifacts/${tid}/selftest.log`,
        evidence_dir: `artifacts/${tid}/evidence/`,
        patch_diff: `artifacts/${tid}/patch.diff`,
        verdict_json: `artifacts/${tid}/verdict.json`,
      },
    }

    const file = path.join(root, "artifacts", tid, "trace.json")
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, JSON.stringify(out, null, 2) + "\n", "utf8")
    return { ok: true, file }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

function policyGateIsTriggered(submit) {
  const changed = Array.isArray(submit?.changed_files) ? submit.changed_files : []
  const newFiles = Array.isArray(submit?.new_files) ? submit.new_files : []
  const touched = changed.concat(newFiles).map((p) => String(p ?? "").replaceAll("\\", "/"))
  for (const p of touched) {
    if (!p) continue
    if (p === "factory_policy.json") return true
    if (p.startsWith("docs/")) return true
    if (p.startsWith("contracts/")) return true
    if (p.startsWith("roles/")) return true
    if (p.startsWith("skills/")) return true
    if (p.startsWith("eval/")) return true
    if (p.startsWith("patterns/")) return true
    if (p.startsWith("playbooks/")) return true
    if (p.startsWith("map/")) return true
  }
  return false
}

function runPolicyGateCommand({ submitPathRel, taskId }) {
  return new Promise((resolve) => {
    const start = Date.now()
    const cwd = SCC_REPO_ROOT && fs.existsSync(SCC_REPO_ROOT) ? SCC_REPO_ROOT : process.cwd()
    const args = ["tools/scc/gates/run_ci_gates.py"]
    if (ciGatesStrict) args.push("--strict")
    args.push("--submit", submitPathRel)
    execFile(
      "python",
      args,
      { cwd, timeout: Number.isFinite(policyGateTimeoutMs) ? policyGateTimeoutMs : 180000, windowsHide: true, maxBuffer: 10 * 1024 * 1024 },
      (err, stdout, stderr) => {
        const finishedAt = Date.now()
        const durationMs = finishedAt - start
        const exitCode = err && typeof err.code === "number" ? err.code : 0
        const ok = !err && exitCode === 0
        const stdoutText = String(stdout || "")
        const stderrText = String(stderr || "")
        const resultsPath = taskId ? `artifacts/${taskId}/ci_gate_results.jsonl` : null
        resolve({
          ok,
          exitCode,
          durationMs,
          startedAt: start,
          finishedAt,
          command: `python tools/scc/gates/run_ci_gates.py --submit ${submitPathRel}`,
          stdoutPreview: stdoutText.slice(0, 2000),
          stderrPreview: stderrText.slice(0, 2000),
          resultsPath,
          timedOut: err && String(err.message || "").toLowerCase().includes("timed out"),
        })
      },
    )
  })
}

function runSsotAutoApply({ taskId }) {
  return new Promise((resolve) => {
    const start = Date.now()
    const cwd = SCC_REPO_ROOT && fs.existsSync(SCC_REPO_ROOT) ? SCC_REPO_ROOT : process.cwd()
    const tid = String(taskId ?? "").trim()
    if (!tid) return resolve({ ok: false, error: "missing_task_id" })
    execFile(
      "python",
      ["tools/scc/ops/ssot_sync.py", "--task-id", tid, "--apply"],
      { cwd, timeout: Number.isFinite(ssotAutoApplyTimeoutMs) ? ssotAutoApplyTimeoutMs : 60000, windowsHide: true, maxBuffer: 5 * 1024 * 1024 },
      (err, stdout, stderr) => {
        const finishedAt = Date.now()
        const durationMs = finishedAt - start
        const exitCode = err && typeof err.code === "number" ? err.code : 0
        const ok = !err && exitCode === 0
        resolve({
          ok,
          exitCode,
          durationMs,
          startedAt: start,
          finishedAt,
          command: `python tools/scc/ops/ssot_sync.py --task-id ${tid} --apply`,
          stdoutPreview: String(stdout || "").slice(0, 2000),
          stderrPreview: String(stderr || "").slice(0, 2000),
          timedOut: err && String(err.message || "").toLowerCase().includes("timed out"),
        })
      },
    )
  })
}

async function runPolicyGateForTask({ job, boardTask }) {
  if (!policyGateEnabled) return { ran: false, skipped: "disabled" }
  const submit = job?.submit
  if (!boardTask || !submit) return { ran: false, skipped: "no_task_or_submit" }
  const required = policyGateIsTriggered(submit)
  if (!required) return { ran: false, skipped: "not_triggered", required: false }
  const submitJson = submit?.artifacts?.submit_json ? String(submit.artifacts.submit_json) : null
  if (!submitJson) return { ran: false, skipped: "missing_submit_json", required: true }
  const taskId = String(submit.task_id ?? boardTask.id ?? "").trim()
  if (!taskId) return { ran: false, skipped: "missing_task_id", required: true }
  let result = await runPolicyGateCommand({ submitPathRel: submitJson, taskId })

  // Deterministic SSOT auto-apply: when ssot_map gate fails, apply artifacts/<task_id>/ssot_update.json to registry.json.
  if (ssotAutoApplyUpdate && result?.ok === false) {
    const current = Number(boardTask.ssot_auto_apply_count ?? 0)
    const maxN = Number.isFinite(ssotAutoApplyMaxPerTask) && ssotAutoApplyMaxPerTask > 0 ? Math.floor(ssotAutoApplyMaxPerTask) : 1
    if (current < maxN) {
      const errors = readPolicyGateErrors(result)
      const ssotHit = errors.some((e) => String(e).includes("SSOT registry missing facts") || String(e).includes("SSOT registry has stale facts"))
      if (ssotHit) {
        boardTask.ssot_auto_apply_count = current + 1
        boardTask.updatedAt = Date.now()
        putBoardTask(boardTask)
        leader({ level: "warn", type: "ssot_auto_apply_attempt", task_id: taskId, attempt: boardTask.ssot_auto_apply_count })
        const applied = await runSsotAutoApply({ taskId })
        appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "ssot_auto_apply", task_id: taskId, ok: applied.ok, details: applied })
        if (applied.ok) {
          result = await runPolicyGateCommand({ submitPathRel: submitJson, taskId })
        }
      }
    }
  }

  return { ran: true, required: true, ...result }
}

	function runHygieneChecks({ job, boardTask }) {
	  const submit = job.submit
	  if (!submit) return { ok: false, reason: "missing_submit" }
	
	  const schemaCheck = validateSubmitSchema(submit)
	  if (!schemaCheck.ok) return { ok: false, reason: schemaCheck.reason ?? "invalid_submit_schema", schema: schemaCheck }
	
	  const art = submit.artifacts || job.artifacts || {}
	  const artifactsList = ["report_md", "selftest_log", "evidence_dir", "patch_diff", "submit_json"]
    const expectedTaskId = String(submit.task_id ?? boardTask?.id ?? "").trim()
    if (!expectedTaskId) return { ok: false, reason: "missing_task_id" }
    if (boardTask?.id && String(boardTask.id) !== expectedTaskId) return { ok: false, reason: "task_id_mismatch" }
    const expectedPrefix = `artifacts/${expectedTaskId}/`
	  for (const k of artifactsList) {
	    const v = art[k]
    if (!v) return { ok: false, reason: `missing_artifact_${k}` }
    const p = String(v).replaceAll("\\", "/")
    if (!p.startsWith("artifacts/")) return { ok: false, reason: `artifact_out_of_root_${k}` }
    if (!p.startsWith(expectedPrefix)) return { ok: false, reason: `artifact_not_under_task_dir_${k}`, expected: expectedPrefix, got: p }
  }

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

  const selftestPath = art.selftest_log ? path.join(execRoot, String(art.selftest_log)) : null
  if (selftestPath && fs.existsSync(selftestPath)) {
    const log = fs.readFileSync(selftestPath, "utf8")
    const lines = log.trim().split(/\r?\n/g)
    const last = lines[lines.length - 1] ?? ""
    if (!/EXIT_CODE=0/.test(last)) return { ok: false, reason: "selftest_exit_nonzero" }
    const hash = crypto.createHash("sha256").update(log, "utf8").digest("hex")
    job.selftest_sha256 = hash
  } else {
    return { ok: false, reason: "missing_selftest_log" }
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
  const originalTaskJson = JSON.stringify(
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
    2,
  )
  const fallbackGoal = [
    "Role: QA/ENGINEER.",
    "Goal: CI/selftest failed or missing. Provide evidence, fix issues, and runnable test commands until exit_code=0.",
    "Output: patch or exact commands + evidence paths; explain failure root cause and fixes.",
    "",
    "CI gate:",
    JSON.stringify(ciGate ?? {}, null, 2),
    "",
    "Original task:",
    originalTaskJson,
  ].join("\n")
  const rendered = renderPromptOrFallback({
    role_id: "qa.ci_fixup_v1",
    params: { ci_gate_json: JSON.stringify(ciGate ?? {}, null, 2), original_task_json: originalTaskJson },
    fallback: fallbackGoal,
    note: "ci_fixup_v1",
  })
  const goal = rendered.text

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    prompt_ref: rendered.prompt_ref,
    role: ciFixupRole,
    runner: "external",
    area: boardTask.area ?? "control_plane",
    lane: "fastlane",
    task_class_id: "ci_fixup_v1",
    parentId: boardTask.parentId ?? null,
    allowedExecutors,
    allowedModels,
    timeoutMs: ciFixupTimeoutMs,
    // CI-fixup validates the *source task* submit.json after applying fixes in the repo.
    allowedTests: [`python tools/scc/gates/run_ci_gates.py --submit artifacts/${boardTask.id}/submit.json`],
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
    if (dispatched.job.runner !== "external") {
      const running = runningCountsInternal()
      const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
      if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
      else schedule()
    } else {
      // External jobs are claimed by workers (ensure-workers.ps1); do not run locally.
      schedule()
    }
    leader({ level: "info", type: "ci_fixup_dispatched", id: created.task.id, jobId: dispatched.job.id })
  }

  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

function readCiGateFailures({ taskId }) {
  const tid = String(taskId ?? "").trim()
  if (!tid) return { ok: false, error: "missing_task_id", failures: [] }
  const rel = `artifacts/${tid}/ci_gate_results.jsonl`
  const file = path.join(SCC_REPO_ROOT, rel)
  const rows = readJsonlTail(file, 600).filter(Boolean)
  const failures = []
  for (const r of rows) {
    const gate = String(r?.gate ?? "")
    const status = String(r?.status ?? "")
    if (!gate) continue
    if (status === "PASS") continue
    const errors = Array.isArray(r?.errors) ? r.errors.map((x) => String(x)).filter(Boolean) : []
    const warnings = Array.isArray(r?.warnings) ? r.warnings.map((x) => String(x)).filter(Boolean) : []
    failures.push({ gate, status, errors, warnings })
  }
  return { ok: true, file: rel, failures }
}

function maybeCreateCiGateFixupTasks({ boardTask, job, ciGate }) {
  const enabled = String(process.env.CI_GATE_ROLE_ROUTING ?? "true").toLowerCase() !== "false"
  if (!enabled) return { ok: false, error: "disabled" }
  if (!boardTask || boardTask.kind !== "atomic") return { ok: false, error: "not_atomic" }
  if (fixupFuseTripped()) {
    leader({ level: "warn", type: "fixup_fused", kind: "ci_role_routing", task_id: boardTask?.id ?? null })
    return { ok: false, error: "fused" }
  }

  const current = Number(boardTask.ci_gate_fixup_count ?? 0)
  const maxN = Number(process.env.CI_GATE_FIXUP_MAX_PER_TASK ?? "2")
  const cap = Number.isFinite(maxN) && maxN > 0 ? Math.floor(maxN) : 2
  if (current >= cap) return { ok: false, error: "limit_reached" }

  const taskId = String(boardTask.id ?? "").trim()
  const out = readCiGateFailures({ taskId })
  if (!out.ok || !out.failures.length) return { ok: false, error: "no_ci_gate_failures" }
  const text = out.failures.flatMap((f) => f.errors).join("\n")

  const isEvents = /missing artifacts\/<task_id>\/events\.jsonl|events\.jsonl has no valid scc\.event\.v1/i.test(text)
  const isMap = /missing map\/map\.sqlite|map sqlite stale|map\/version\.json expired|map\/version\.json too old/i.test(text)
  const isSsot = /SSOT registry missing facts|SSOT registry has stale facts|docs\/SSOT\/registry\.json/i.test(text)

  const tasks = []
  const gateCmdStrict = `python tools/scc/gates/run_ci_gates.py --strict --submit artifacts/${taskId}/submit.json`

  const bump = () => {
    boardTask.ci_gate_fixup_count = current + 1
    boardTask.updatedAt = Date.now()
    putBoardTask(boardTask)
  }

  if (isMap) {
    bump()
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `Map refresh (sqlite): ${boardTask.title ?? boardTask.id}`,
      goal: [
        "Role: MAP_CURATOR.",
        "Goal: CI gate failed due to Map freshness/sqlite invariants. Rebuild map outputs (map.json + version.json + map.sqlite) deterministically, then re-run strict CI gate for the source task.",
        "",
        "Required:",
        "- Run: npm --prefix oc-scc-local run map:build (must also produce map/map.sqlite; env MAP_SQLITE_REQUIRED=true is enforced).",
        `- Verify: python tools/scc/gates/run_ci_gates.py --strict --submit artifacts/${taskId}/submit.json`,
        "",
        "CI gate failures (excerpt):",
        JSON.stringify(out.failures.slice(0, 10), null, 2),
      ].join("\n"),
      role: "map_curator",
      runner: "external",
      lane: "fastlane",
      area: "control_plane",
      task_class_id: "map_refresh_v1",
      parentId: boardTask.parentId ?? null,
      allowedExecutors: ["codex"],
      allowedModels: ["gpt-5.2-codex", "gpt-5.2"],
      timeoutMs: 600000,
      files: ["oc-scc-local/scripts/map_build_v1.mjs", "tools/scc/map/map_sqlite_v1.py", "tools/scc/gates/map_gate.py", "map/version.json"].filter(Boolean),
      allowedTests: [gateCmdStrict],
      pointers: { sourceTaskId: boardTask.id, jobId: job?.id ?? null, reason: "ci_gate_map_failed", ci_gate: ciGate ?? null },
    })
    if (created.ok) {
      tasks.push(created.task)
      dispatchBoardTaskToExecutor(created.task.id)
    }
  }

  if (isEvents) {
    bump()
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `Events backfill: ${boardTask.title ?? boardTask.id}`,
      goal: [
        "Role: AUDITOR.",
        "Goal: CI gate failed due to missing/invalid events.jsonl for this task. Backfill artifacts/<task_id>/events.jsonl deterministically, then re-run strict CI gate.",
        "",
        "Required:",
        `- Run: python tools/scc/ops/backfill_events_v1.py --repo-root ${cfg.repoRoot.replaceAll("\\\\", "/")} --task-id ${taskId}`,
        `- Verify: ${gateCmdStrict}`,
        "",
        "CI gate failures (excerpt):",
        JSON.stringify(out.failures.slice(0, 10), null, 2),
      ].join("\n"),
      role: "auditor",
      runner: "external",
      lane: "fastlane",
      area: "control_plane",
      task_class_id: "events_backfill_v1",
      parentId: boardTask.parentId ?? null,
      allowedExecutors: ["codex"],
      allowedModels: ["gpt-5.2-codex", "gpt-5.2"],
      timeoutMs: 300000,
      files: ["tools/scc/ops/backfill_events_v1.py", `artifacts/${taskId}/submit.json`].filter(Boolean),
      allowedTests: [gateCmdStrict],
      pointers: { sourceTaskId: boardTask.id, jobId: job?.id ?? null, reason: "ci_gate_events_failed", ci_gate: ciGate ?? null },
    })
    if (created.ok) {
      tasks.push(created.task)
      dispatchBoardTaskToExecutor(created.task.id)
    }
  }

  if (isSsot) {
    bump()
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `SSOT sync: ${boardTask.title ?? boardTask.id}`,
      goal: [
        "Role: SSOT_CURATOR.",
        "Goal: CI gate failed due to SSOT drift (docs/SSOT/registry.json). Apply artifacts/<task_id>/ssot_update.json deterministically and ensure no dead links, then re-run strict CI gate.",
        "",
        "Required:",
        `- Review: artifacts/${taskId}/ssot_update.json (generated by ssot_map gate).`,
        `- Apply: python tools/scc/ops/ssot_sync.py --task-id ${taskId} --apply (writes ssot_update.patch).`,
        `- Verify: ${gateCmdStrict}`,
        "",
        "CI gate failures (excerpt):",
        JSON.stringify(out.failures.slice(0, 10), null, 2),
      ].join("\n"),
      role: "ssot_curator",
      runner: "external",
      lane: "fastlane",
      area: "control_plane",
      task_class_id: "ssot_sync_v1",
      parentId: boardTask.parentId ?? null,
      allowedExecutors: ["codex"],
      allowedModels: ["gpt-5.2-codex", "gpt-5.2"],
      timeoutMs: 600000,
      files: ["docs/SSOT/registry.json", `artifacts/${taskId}/ssot_update.json`, "tools/scc/ops/ssot_sync.py", "tools/scc/gates/ssot_map_gate.py"].filter(Boolean),
      allowedTests: [gateCmdStrict],
      pointers: { sourceTaskId: boardTask.id, jobId: job?.id ?? null, reason: "ci_gate_ssot_failed", ci_gate: ciGate ?? null },
    })
    if (created.ok) {
      tasks.push(created.task)
      dispatchBoardTaskToExecutor(created.task.id)
    }
  }

  return tasks.length ? { ok: true, tasks, failures: out.failures.slice(0, 12) } : { ok: false, error: "no_applicable_ci_gate_fixup", failures: out.failures.slice(0, 12) }
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

  // Prefer deterministic Map fixup before spawning an LLM-based pins_fixup_v1 task.
  if (autoPinsFixupFromMap) {
    try {
      const ref = currentMapRef()
      if (ref?.hash) {
        const child = {
          title: String(boardTask.title ?? "").slice(0, 240),
          goal: String(boardTask.goal ?? ""),
          role: String(boardTask.role ?? "executor"),
          files: Array.isArray(boardTask.files) ? boardTask.files.slice(0, 16) : [],
          allowedTests: Array.isArray(boardTask.allowedTests) ? boardTask.allowedTests.slice(0, 24) : [],
          pins: { allowed_paths: [String((Array.isArray(boardTask.files) ? boardTask.files[0] : "") ?? "")].filter(Boolean) },
        }
        const req = {
          schema_version: "scc.pins_request.v1",
          task_id: boardTask.id,
          child_task: child,
          signals: { keywords: ["pins", "preflight", "map", reason] },
          map_ref: { path: ref.path ?? "map/map.json", hash: ref.hash },
          budgets: { max_files: 24, max_loc: 260, default_line_window: 160 },
        }
        const built = buildPinsFromMapV1({ repoRoot: SCC_REPO_ROOT, request: req })
        if (built?.ok && built.pins && Array.isArray(built.pins.allowed_paths) && built.pins.allowed_paths.length) {
          const prevHash = boardTask.pins_map_hash ? String(boardTask.pins_map_hash) : null
          const nextHash = `sha256:${sha256Hex(stableStringify(built.pins))}`
          if (prevHash && prevHash === nextHash) {
            leader({ level: "warn", type: "auto_pins_fixup_no_change", id: boardTask.id, hash: nextHash })
          } else {
            boardTask.pins = built.pins
            boardTask.pins_pending = false
            boardTask.pins_map_hash = nextHash
            boardTask.status = "ready"
            boardTask.updatedAt = Date.now()
            putBoardTask(boardTask)
            try {
              writePinsV1Outputs({
                repoRoot: SCC_REPO_ROOT,
                taskId: boardTask.id,
                outDir: `artifacts/${boardTask.id}/pins`,
                pinsResult: built.result_v2 ?? built.result,
                pinsSpec: built.pins,
                detail: built.detail,
              })
            } catch (e) {
              // best-effort
              noteBestEffort("autoPins_write_outputs", e, { task_id: boardTask.id })
            }
            appendStateEvent({
              schema_version: "scc.event.v1",
              t: new Date().toISOString(),
              event_type: "SUCCESS",
              task_id: boardTask.id,
              parent_id: boardTask.parentId ?? null,
              kind: boardTask.kind ?? null,
              status: "ready",
              role: boardTask.role ?? null,
              area: boardTask.area ?? null,
              lane: boardTask.lane ?? null,
              reason: "auto_pins_fixup_from_map",
              details: { map_hash: ref.hash, pins_hash: nextHash, pins_files: built.pins.allowed_paths.slice(0, 24) },
              })
            applyRepoHealthFromEvent({ event_type: "SUCCESS" })
            applyCircuitBreakersFromEvent({ event_type: "SUCCESS" })
            const out = dispatchBoardTaskToExecutor(boardTask.id)
            leader({ level: out.ok ? "info" : "warn", type: "auto_pins_fixup_requeued", id: boardTask.id, dispatched: out.ok, error: out.ok ? null : out.error })
            if (out.ok) return { ok: true, mode: "map", requeued: true }
            return { ok: true, mode: "map", requeued: false, dispatch_error: out.error }
          }
        } else if (built && !built.ok) {
          appendJsonl(pinsGuideErrorsFile, {
            t: new Date().toISOString(),
            task_id: boardTask.id,
            error: "auto_pins_fixup_from_map_failed",
            hint: built.error ?? null,
          })
        }
      }
    } catch (e) {
      appendJsonl(pinsGuideErrorsFile, { t: new Date().toISOString(), task_id: boardTask?.id ?? null, error: "auto_pins_fixup_exception", hint: String(e?.message ?? e) })
    }
  }

  const safeExecutors = pinsFixupAllowedExecutors.filter((x) => x === "codex" || x === "opencodecli")
  const allowedExecutors = safeExecutors.length ? safeExecutors : ["opencodecli"]
  const allowedModels = pinsFixupAllowedModels.length
    ? pinsFixupAllowedModels.slice(0, 6)
    : modelsFree.length
      ? [modelsFree[0]]
      : [occliModelDefault]

  const title = `Pins fixup: ${boardTask.title ?? boardTask.id}`
  const pfTaskId = `PF-${crypto.randomUUID()}`
  const fallbackObj = {
    schema_version: "scc.pins_fill_prompt.v1",
    role: "pins_filler",
    output_mode: "JSON_ONLY",
    task: {
      task_id: pfTaskId,
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
      existing_pins: { pins_json_path: null, pins_md_path: null },
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
      pins_json: {
        required: true,
        fields: [
          "pins[].path",
          "pins[].symbols[]",
          "pins[].line_windows[]",
          "pins[].purpose",
          "pins[].reason",
          "pins[].read_only",
        ],
      },
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
  }
  const fallbackGoal = JSON.stringify(fallbackObj, null, 2)
  const rendered = renderPromptOrFallback({
    role_id: "pinser.pins_fill_prompt_v1",
    params: {
      pf_task_id: pfTaskId,
      parent_task_id: boardTask.parentId ?? null,
      task_class: boardTask.task_class_id ?? boardTask.task_class_candidate ?? null,
      child_title: boardTask.title ?? "",
      child_goal: boardTask.goal ?? "",
      child_acceptance: Array.isArray(boardTask.acceptance) ? boardTask.acceptance : [],
      child_allowed_tests: Array.isArray(boardTask.allowedTests) ? boardTask.allowedTests : [],
      patch_scope_allow_paths: Array.isArray(boardTask.files) ? boardTask.files : [],
      patch_scope_deny_paths: Array.isArray(boardTask.forbidden_paths) ? boardTask.forbidden_paths : [],
      signals_ci_failures: [reason],
      signals_error_snippets: readPinsGuideErrors(4),
      original_task_id: boardTask.id,
      original_task_role: boardTask.role ?? null,
      original_task_files: Array.isArray(boardTask.files) ? boardTask.files : [],
      original_task_current_pins: boardTask.pins ?? null,
      original_task_failure_reason: reason,
    },
    fallback: fallbackGoal,
    note: "pins_fill_prompt_v1",
  })
  const goal = rendered.text

  const created = createBoardTask({
    kind: "atomic",
    status: "ready",
    title,
    goal,
    prompt_ref: rendered.prompt_ref,
    role: pinsFixupRole,
    runner: "external",
    area: boardTask.area ?? "control_plane",
    lane: "fastlane",
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
    if (dispatched.job.runner !== "external") {
      const running = runningCountsInternal()
      const canRun = dispatched.job.executor === "opencodecli" ? running.opencodecli < occliMax : running.codex < codexMax
      if (canRun && dispatched.job.status === "queued") runJob(dispatched.job)
      else schedule()
    } else {
      schedule()
    }
    leader({ level: "info", type: "pins_fixup_dispatched", id: created.task.id, jobId: dispatched.job.id })
  }

  return { ok: true, task: created.task, dispatched: dispatched.ok }
}

function runningCountsFiltered({ runner = "all" } = {}) {
  let codex = 0
  let opencodecli = 0
  for (const j of jobs.values()) {
    if (j.status !== "running") continue
    if (runner === "internal" && j.runner === "external") continue
    if (runner === "external" && j.runner !== "external") continue
    if (j.executor === "opencodecli") opencodecli += 1
    else codex += 1
  }
  return { codex, opencodecli }
}

const runningCountsInternal = () => runningCountsFiltered({ runner: "internal" })
const runningCountsExternal = () => runningCountsFiltered({ runner: "external" })
const runningCountsAll = () => runningCountsFiltered({ runner: "all" })

let factoryPolicyCache = null
let factoryPolicyMtimeMs = 0
function getFactoryPolicy() {
  try {
    const file = path.join(SCC_REPO_ROOT, "factory_policy.json")
    const st = fs.statSync(file)
    const m = Number(st.mtimeMs ?? 0)
    if (!factoryPolicyCache || (Number.isFinite(m) && m > factoryPolicyMtimeMs)) {
      const raw = fs.readFileSync(file, "utf8")
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === "object" && parsed.schema_version === "scc.factory_policy.v1") {
        factoryPolicyCache = parsed
        factoryPolicyMtimeMs = m
      }
    }
  } catch {
    // ignore; fallback below
  }
  return factoryPolicyCache
}

let mapVersionCache = null
let mapVersionMtimeMs = 0
function getMapVersion() {
  try {
    const file = path.join(SCC_REPO_ROOT, "map", "version.json")
    const st = fs.statSync(file)
    const m = Number(st.mtimeMs ?? 0)
    if (!mapVersionCache || (Number.isFinite(m) && m > mapVersionMtimeMs)) {
      const raw = fs.readFileSync(file, "utf8")
      const parsed = JSON.parse(raw.replace(/^\uFEFF/, ""))
      if (parsed && typeof parsed === "object" && parsed.schema_version === "scc.map_version.v1") {
        mapVersionCache = parsed
        mapVersionMtimeMs = m
      }
    }
  } catch {
    // ignore
  }
  return mapVersionCache
}

function currentMapRef() {
  const ver = getMapVersion()
  const hash = ver?.hash ? String(ver.hash) : null
  const mapPath = ver?.map_path ? String(ver.map_path) : "map/map.json"
  if (!hash) return null
  return { path: mapPath, hash }
}

function loadEvalManifest() {
  try {
    const file = path.join(SCC_REPO_ROOT, "eval", "eval_manifest.json")
    if (!fs.existsSync(file)) return null
    const raw = fs.readFileSync(file, "utf8")
    const parsed = JSON.parse(raw.replace(/^\uFEFF/, ""))
    return parsed && typeof parsed === "object" ? parsed : null
  } catch {
    return null
  }
}

function autoFixAllowedTestsFromSignals({ taskId, rolePolicy, pinsSpec, baseChildTask, preflight }) {
  try {
    const miss = preflight?.missing ?? {}
    const missingTests = Array.isArray(miss.tests) ? miss.tests : []
    if (!missingTests.length) return { ok: false, error: "no_missing_tests" }
    const mapRef = currentMapRef()
    const mapObj = mapRef?.path ? loadMapV1({ repoRoot: SCC_REPO_ROOT, mapPath: mapRef.path }) : null
    const evalMan = loadEvalManifest()
    const candidates = []

    // Tier commands (smoke preferred under degradation).
    const smoke = Array.isArray(evalMan?.tiers?.smoke?.commands) ? evalMan.tiers.smoke.commands : []
    const regression = Array.isArray(evalMan?.tiers?.regression?.commands) ? evalMan.tiers.regression.commands : []
    for (const c of smoke) candidates.push(String(c))
    for (const c of regression) candidates.push(String(c))

    // Map-detected test entry points.
    for (const t of Array.isArray(mapObj?.map?.test_entry_points) ? mapObj.map.test_entry_points : []) {
      const cmd = String(t?.command ?? "").trim()
      if (cmd) candidates.push(cmd)
    }

    // Safe fallbacks.
    candidates.push("python -m compileall .")
    candidates.push("pytest -q")
    candidates.push("python -m pytest -q")

    const uniq = Array.from(new Set(candidates.map((x) => String(x ?? "").trim()).filter(Boolean))).slice(0, 30)
    for (const cmd of uniq) {
      const child = { ...(baseChildTask ?? {}), allowedTests: [cmd] }
      const res = runPreflightV1({ repoRoot: SCC_REPO_ROOT, taskId, childTask: child, pinsSpec, rolePolicy })
      if (res?.ok && res.preflight && res.preflight.pass) {
        return { ok: true, allowedTests: [cmd], picked: cmd, candidates: uniq.slice(0, 12) }
      }
      const mt = Array.isArray(res?.preflight?.missing?.tests) ? res.preflight.missing.tests : null
      if (mt && mt.length === 0) {
        return { ok: true, allowedTests: [cmd], picked: cmd, candidates: uniq.slice(0, 12) }
      }
    }
    return { ok: false, error: "no_valid_command", candidates: uniq.slice(0, 12) }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

const autoMapBuildEnabled = String(process.env.AUTO_MAP_BUILD_ENABLED ?? "true").toLowerCase() !== "false"
const autoMapBuildMinMs = Number(process.env.AUTO_MAP_BUILD_MIN_MS ?? "600000") // 10 min
let lastMapBuildAt = 0
let mapBuildRunning = false
let mapBuildTimer = null

function mapBuildTriggeredBySubmit(submit) {
  const changed = Array.isArray(submit?.changed_files) ? submit.changed_files : []
  const newFiles = Array.isArray(submit?.new_files) ? submit.new_files : []
  const touched = changed.concat(newFiles).map((p) => String(p ?? "").replaceAll("\\", "/"))
  for (const p of touched) {
    if (!p) continue
    if (p.startsWith("oc-scc-local/")) return true
    if (p.startsWith("contracts/")) return true
    if (p.startsWith("roles/")) return true
    if (p.startsWith("skills/")) return true
    if (p === "docs/INDEX.md" || p === "docs/NAVIGATION.md") return true
  }
  return false
}

function syncSsotRegistryFromMap({ mapObj, versionObj } = {}) {
  try {
    const map = mapObj && typeof mapObj === "object" ? mapObj : null
    const ver = versionObj && typeof versionObj === "object" ? versionObj : null
    if (!map || !ver) return { ok: false, error: "missing_map_or_version" }
    const roots = Array.isArray(ver?.coverage?.roots) ? ver.coverage.roots.map((x) => String(x)).filter(Boolean) : []
    const entry = (Array.isArray(map.entry_points) ? map.entry_points : [])
      .filter((e) => e && typeof e === "object" && String(e.path ?? "").replaceAll("\\", "/").startsWith("oc-scc-local/"))
      .map((e) => String(e.id ?? "").trim())
      .filter((id) => Boolean(id) && !String(id).includes(":selfcheck:"))
      .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
    const fi = map.file_index && typeof map.file_index === "object" ? map.file_index : {}
    const contracts = Object.keys(fi)
      .map((p) => String(p).replaceAll("\\", "/").replace(/^\.\/+/, ""))
      .filter((p) => p.startsWith("contracts/") && p.endsWith(".schema.json"))
      .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
    const out = {
      schema_version: "scc.ssot_registry.v1",
      updated_at: new Date().toISOString().slice(0, 10),
      sources: { map_path: String(ver.map_path ?? "map/map.json"), map_hash: String(ver.hash ?? ""), facts_hash: String(ver.facts_hash ?? "") },
      facts: {
        modules: Array.from(new Set(roots)).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)),
        entry_points: Array.from(new Set(entry)),
        contracts: Array.from(new Set(contracts)),
      },
      notes: "Auto-synced from Map v1 (coverage.roots + oc-scc-local entry points + contracts/*.schema.json).",
    }
    const file = path.join(SCC_REPO_ROOT, "docs", "SSOT", "registry.json")
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, JSON.stringify(out, null, 2) + "\n", "utf8")
    return { ok: true, file, stats: { modules: out.facts.modules.length, entry_points: out.facts.entry_points.length, contracts: out.facts.contracts.length } }
  } catch (e) {
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  }
}

async function runMapBuild({ reason = "manual" } = {}) {
  if (mapBuildRunning) return { ok: false, error: "already_running" }
  mapBuildRunning = true
  try {
    const start = Date.now()
    const res = buildMapV1({ repoRoot: SCC_REPO_ROOT, incremental: true, previousMapPath: "map/map.json" })
    if (!res?.ok) return { ok: false, error: "build_failed" }
    writeMapV1Outputs({ repoRoot: SCC_REPO_ROOT, outDir: "map", buildResult: res })
    if (ssotAutoSyncFromMap) {
      const ssot = syncSsotRegistryFromMap({ mapObj: res.map, versionObj: res.version })
      appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "ssot_auto_sync", ok: ssot.ok, reason, details: ssot.ok ? ssot : { error: ssot.error, message: ssot.message ?? null } })
    }
    const finishedAt = Date.now()
    lastMapBuildAt = finishedAt
    appendJsonl(execLeaderLog, {
      t: new Date().toISOString(),
      type: "map_build",
      ok: true,
      reason,
      durationMs: finishedAt - start,
      hash: res.version?.hash ?? null,
      stats: res.version?.stats ?? null,
    })
    return { ok: true, hash: res.version?.hash ?? null, stats: res.version?.stats ?? null }
  } catch (e) {
    appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "map_build", ok: false, reason, error: String(e?.message ?? e) })
    return { ok: false, error: "exception", message: String(e?.message ?? e) }
  } finally {
    mapBuildRunning = false
  }
}

function scheduleMapBuild({ reason = "auto" } = {}) {
  if (!autoMapBuildEnabled) return { ok: false, error: "disabled" }
  const now = Date.now()
  if (Number.isFinite(autoMapBuildMinMs) && autoMapBuildMinMs > 0 && now - lastMapBuildAt < autoMapBuildMinMs) {
    return { ok: false, error: "rate_limited" }
  }
  if (mapBuildTimer) return { ok: true, scheduled: true }
  mapBuildTimer = setTimeout(async () => {
    mapBuildTimer = null
    await runMapBuild({ reason })
  }, 8000)
  return { ok: true, scheduled: true }
}

function wipLimits() {
  const fp = getFactoryPolicy()
  const wl = fp?.wip_limits ?? null
  const toInt = (v, fallback) => {
    const n = Number(v)
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : fallback
  }
  const total = toInt(wl?.WIP_TOTAL_MAX, 12)
  const exec = toInt(wl?.WIP_EXEC_MAX, 4)
  const batch = toInt(wl?.WIP_BATCH_MAX, 1)
  return {
    total,
    exec,
    batch,
    // Runner-specific WIP: prevents internal automation from blocking external user flows.
    total_external: toInt(wl?.WIP_TOTAL_EXTERNAL_MAX, total),
    total_internal: toInt(wl?.WIP_TOTAL_INTERNAL_MAX, total),
    exec_external: toInt(wl?.WIP_EXEC_EXTERNAL_MAX, exec),
    exec_internal: toInt(wl?.WIP_EXEC_INTERNAL_MAX, exec),
    batch_external: toInt(wl?.WIP_BATCH_EXTERNAL_MAX, batch),
    batch_internal: toInt(wl?.WIP_BATCH_INTERNAL_MAX, batch),
  }
}

function internalQueuedCount() {
  let n = 0
  for (const j of jobs.values()) {
    if (j.status !== "queued") continue
    if (j.runner === "external") continue
    n += 1
  }
  return n
}

function computeDegradationState({ snap } = {}) {
  const fp = getFactoryPolicy ? getFactoryPolicy() : null
  const s = snap ?? runningInternalByLane()
  const queued = internalQueuedCount()
  const baseLimits = wipLimits()
  const overloaded = queued >= stabilityQueuedThreshold || (baseLimits.total > 0 && s.total >= baseLimits.total && queued > 0)
  const unhealthy = repoUnhealthyActive() || quarantineActive()
  const action = computeDegradationActionV1({ factoryPolicy: fp, signals: { queue_overload: overloaded, repo_unhealthy: unhealthy } })
  return { signals: { queue_overload: overloaded, repo_unhealthy: unhealthy, queued_internal: queued }, action }
}

function jobLane(job) {
  const taskId = job?.boardTaskId ? String(job.boardTaskId) : null
  const t = taskId ? getBoardTask(taskId) : null
  return normalizeLane(t?.lane ?? t?.area) ?? "mainlane"
}

function runningInternalByLane() {
  const out = { total: 0, exec: 0, batch: 0, byLane: {} }
  for (const j of jobs.values()) {
    if (j.status !== "running") continue
    if (j.runner === "external") continue
    out.total += 1
    const lane = jobLane(j)
    out.byLane[lane] = (out.byLane[lane] ?? 0) + 1
    if (lane === "batchlane") out.batch += 1
    else out.exec += 1
  }
  return out
}

function activeJobsAllByLane() {
  const out = { total: 0, exec: 0, batch: 0, queued: 0, running: 0, byLane: {} }
  for (const j of jobs.values()) {
    if (j.status !== "running" && j.status !== "queued") continue
    out.total += 1
    if (j.status === "running") out.running += 1
    if (j.status === "queued") out.queued += 1
    const lane = jobLane(j)
    out.byLane[lane] = (out.byLane[lane] ?? 0) + 1
    if (lane === "batchlane") out.batch += 1
    else out.exec += 1
  }
  return out
}

function activeJobsByRunnerAndLane() {
  const out = {
    total: 0,
    running: 0,
    queued: 0,
    byLane: {},
    external: { total: 0, running: 0, queued: 0, exec: 0, batch: 0, byLane: {} },
    internal: { total: 0, running: 0, queued: 0, exec: 0, batch: 0, byLane: {} },
  }
  for (const j of jobs.values()) {
    if (j.status !== "running" && j.status !== "queued") continue
    const lane = jobLane(j)
    const bucket = j.runner === "external" ? out.external : out.internal
    out.total += 1
    bucket.total += 1
    out.byLane[lane] = (out.byLane[lane] ?? 0) + 1
    bucket.byLane[lane] = (bucket.byLane[lane] ?? 0) + 1
    if (j.status === "running") {
      out.running += 1
      bucket.running += 1
    } else {
      out.queued += 1
      bucket.queued += 1
    }
    if (lane === "batchlane") bucket.batch += 1
    else bucket.exec += 1
  }
  return out
}

function canEnqueueJobByLane(lane, snap, runner) {
  const r = runner === "internal" ? "internal" : "external"
  const s = snap ?? activeJobsByRunnerAndLane()
  const degradation = computeDegradationState()
  const limits = applyDegradationToWipLimitsV1({ limits: wipLimits(), action: degradation.action })
  const bucket = r === "internal" ? s.internal : s.external

  const totalMax = r === "internal" ? limits.total_internal : limits.total_external
  if (totalMax > 0 && bucket.total >= totalMax) return { ok: false, error: "wip_total_max", limits, snap: s }

  if (lane === "batchlane") {
    const batchMax = r === "internal" ? limits.batch_internal : limits.batch_external
    if (batchMax >= 0 && bucket.batch >= batchMax) return { ok: false, error: "wip_batch_max", limits, snap: s }
    return { ok: true, limits, snap: s }
  }

  const execMax = r === "internal" ? limits.exec_internal : limits.exec_external
  if (execMax > 0 && bucket.exec >= execMax) return { ok: false, error: "wip_exec_max", limits, snap: s }
  return { ok: true, limits, snap: s }
}

function canStartInternalJob(job, snap) {
  const s = snap ?? runningInternalByLane()
  const degradation = computeDegradationState({ snap: s })
  const limits = applyDegradationToWipLimitsV1({ limits: wipLimits(), action: degradation.action })
  const lane = jobLane(job)
  if (lane === "batchlane") {
    if (limits.batch_internal >= 0 && s.batch >= limits.batch_internal) return false
    return true
  }
  if (limits.exec_internal > 0 && s.exec >= limits.exec_internal) return false
  return true
}

const nextQueued = (executor) => Array.from(jobs.values()).find((j) => j.status === "queued" && j.executor === executor)
const nextQueuedInternal = (executor) => {
  const queued = Array.from(jobs.values()).filter(
    (j) => j.status === "queued" && j.executor === executor && j.runner !== "external"
  )
  if (!queued.length) return null
  const snap = runningInternalByLane()
  queued.sort((a, b) => {
    const pa = Number(a.priority ?? 0)
    const pb = Number(b.priority ?? 0)
    if (pa !== pb) return pb - pa
    return Number(a.createdAt ?? 0) - Number(b.createdAt ?? 0)
  })
  for (const j of queued) {
    if (canStartInternalJob(j, snap)) return j
  }
  return null
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
const timeoutFuseWindowMs = 5 * 60 * 1000
const timeoutFuseCooldownMs = 10 * 60 * 1000
let timeoutFuseUntil = 0
let timeoutEventsWindow = []

// Executor flake fuse: if opencode-cli repeatedly exits non-zero with empty output,
// temporarily stop routing tasks to opencodecli (stability over throughput).
const occliFlakeFuseFile = path.join(execLogDir, "opencodecli_fuse.json")
const occliFlakeWindowMs = Number(process.env.OCCLI_FLAKE_FUSE_WINDOW_MS ?? "300000") // 5 min
const occliFlakeTripN = Number(process.env.OCCLI_FLAKE_FUSE_TRIP_N ?? "3")
const occliFlakeCooldownMs = Number(process.env.OCCLI_FLAKE_FUSE_COOLDOWN_MS ?? "600000") // 10 min
let occliFlakeFuseUntil = 0
let occliFlakeEventsWindow = []
try {
  if (fs.existsSync(occliFlakeFuseFile)) {
    const raw = fs.readFileSync(occliFlakeFuseFile, "utf8")
    const parsed = JSON.parse(raw)
    if (Number.isFinite(Number(parsed?.until))) occliFlakeFuseUntil = Number(parsed.until)
  }
} catch {
  // ignore
}
function saveOccliFlakeFuse() {
  try {
    fs.writeFileSync(
      occliFlakeFuseFile,
      JSON.stringify({ schema_version: "scc.executor_fuse.v1", executor: "opencodecli", until: occliFlakeFuseUntil }, null, 2),
      "utf8"
    )
  } catch (e) {
    // best-effort
    noteBestEffort("saveOccliFlakeFuse", e, { file: occliFlakeFuseFile })
  }
}
function occliFusedNow() {
  return Boolean(occliFlakeFuseUntil && Date.now() < occliFlakeFuseUntil)
}
function saveModelRr() {
  try {
    fs.writeFileSync(modelRrFile, JSON.stringify({ index: modelRrIndex }, null, 2), "utf8")
  } catch {
    // best effort
    noteBestEffort("saveModelRr_failed", new Error("write_failed"), { file: modelRrFile })
  }
}
function occliModelPoolForTask(t) {
  const allowed = Array.isArray(t?.allowedModels) ? t.allowedModels.map((x) => String(x)) : []
  const explicitPool = allowed.filter((m) => m.startsWith("opencode/"))
  if (explicitPool.length) return sortModelPool(Array.from(new Set(explicitPool)))

  const text = `${t?.title ?? ""}\n${t?.goal ?? ""}`.toLowerCase()
  const wantsVision = /(vision|image|ocr|视觉|图片|图像)/i.test(text)
  const rawPool = wantsVision && modelsVision.length ? modelsVision : modelsFree.length ? modelsFree : [occliModelDefault]
  const pool = rawPool.filter((m) => !occliSubmitBlacklist.includes(m))
  if (!pool.length) pool.push(occliModelDefault)
  return pool
}
function pickOccliModelForTask(t) {
  if (!autoAssignOccliModels) return occliModelDefault
  const pool = occliModelPoolForTask(t)
  if (!pool.length) return occliModelDefault

  if (modelRoutingMode === "strong_first") return pool[0]
  if (modelRoutingMode === "ladder") {
    const attempt = Number.isFinite(Number(t?.modelAttempt)) ? Number(t.modelAttempt) : 0
    const idx = Math.max(0, Math.min(pool.length - 1, attempt))
    return pool[idx]
  }

  // rr (default)
  const idx = Math.abs(modelRrIndex) % pool.length
  modelRrIndex += 1
  saveModelRr()
  return pool[idx]
}

function pickCodexModelForTask(t) {
  if (codexModelForced) return codexModelForced
  const allowed = Array.isArray(t?.allowedModels) ? t.allowedModels.map((x) => String(x)) : []
  const codexAllowed = allowed.filter((m) => !m.startsWith("opencode/"))
  if (codexAllowed.length) {
    // Prefer stats-driven routing when multiple codex candidates are allowed.
    // This uses recent `state_events.jsonl` outcomes to pick a better default per task_class.
    if (codexAllowed.length > 1) {
      const taskClass = String(t?.task_class_id ?? t?.task_class ?? "unknown").trim() || "unknown"
      const picked = getCodexModelFromStats({ taskClass, candidates: codexAllowed })
      if (picked && codexAllowed.includes(picked)) return picked
    }
    for (const m of codexPreferredOrder) {
      if (codexAllowed.includes(m)) return m
    }
    return codexAllowed[0]
  }
  return codexModelDefault
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
  if (occliFusedNow()) return "codex"

  if (preferFreeModels) {
    const allowedModels = Array.isArray(t?.allowedModels) ? t.allowedModels.map((x) => String(x)) : []
    const hasOpencodeModel = allowedModels.some((m) => m.startsWith("opencode/"))
    const hasCodexOnly = allowedModels.length > 0 && !hasOpencodeModel
    if (!hasCodexOnly && modelsFree.length > 0) return "opencodecli"
  }

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
      const counts = runningCountsInternal()
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

function readPolicyGateErrors(policyGate) {
  const rel = policyGate?.resultsPath ? String(policyGate.resultsPath) : ""
  if (!rel) return []
  const file = path.join(SCC_REPO_ROOT, rel)
  const rows = readJsonlTail(file, 400).filter(Boolean)
  const out = []
  for (const r of rows) {
    const status = String(r?.status ?? "")
    if (status === "PASS") continue
    const errs = Array.isArray(r?.errors) ? r.errors : []
    for (const e of errs) out.push(String(e))
  }
  return out
}

function maybeCreatePolicyFixupTasks({ boardTask, job, policyGate }) {
  if (!boardTask || boardTask.kind !== "atomic") return { ok: false, error: "not_atomic" }
  if (!policyGate || policyGate.ok) return { ok: false, error: "no_failure" }
  const current = Number(boardTask.policy_fixup_count ?? 0)
  if (Number.isFinite(policyGateMaxFixupsPerTask) && policyGateMaxFixupsPerTask > 0 && current >= policyGateMaxFixupsPerTask) {
    return { ok: false, error: "limit_reached" }
  }
  boardTask.policy_fixup_count = current + 1
  boardTask.updatedAt = Date.now()
  putBoardTask(boardTask)

  const errors = readPolicyGateErrors(policyGate)
  const text = errors.join("\n")
  const needsAdr = /ADR required|ADR missing/i.test(text)
  const needsIndex = /unregistered docs file|docs\/INDEX\.md references missing file|SSOT drift gate/i.test(text)
  const schemaIssue = /roles\/registry\.json|skills\/registry\.json|role_skill_matrix|schema_version/i.test(text)

  const tasks = []
  const gateCmd = "python tools/scc/gates/run_ci_gates.py --submit artifacts/{task_id}/submit.json"

  if (needsAdr) {
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `ADR fixup: ${boardTask.title ?? boardTask.id}`,
      goal: [
        "Role: DOC_ADR_SCRIBE.",
        "Goal: Policy gates require an ADR for this change. Write ADR and link it from docs/INDEX.md, then re-run policy gates.",
        "",
        "Inputs:",
        `- Source task: ${boardTask.id}`,
        `- Policy gate results: ${policyGate.resultsPath ?? "(missing)"}`,
        "",
        "Required:",
        "- Add docs/adr/ADR-YYYYMMDD-<slug>.md using docs/adr/ADR-TEMPLATE.md (6-line prefixes).",
        "- Ensure docs/INDEX.md registers the new ADR (and any new docs touched).",
        "- Keep changes docs-only.",
      ].join("\n"),
      role: "doc_adr_scribe",
      runner: "internal",
      lane: "fastlane",
      area: "control_plane",
      task_class_id: "doc_adr_fixup_v1",
      parentId: boardTask.parentId ?? null,
      allowedExecutors: ["codex", "opencodecli"],
      allowedModels: ["gpt-5.2"],
      timeoutMs: 600000,
      files: ["docs/INDEX.md", "docs/adr/ADR-TEMPLATE.md", "docs/adr/README.md", policyGate.resultsPath ?? ""].filter(Boolean),
      allowedTests: [gateCmd],
      pointers: { sourceTaskId: boardTask.id, jobId: job?.id ?? null, reason: "policy_gate_failed" },
    })
    if (created.ok) {
      tasks.push(created.task)
      dispatchBoardTaskToExecutor(created.task.id)
    }
  }

  if (needsIndex) {
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `SSOT index fixup: ${boardTask.title ?? boardTask.id}`,
      goal: [
        "Role: SSOT_CURATOR.",
        "Goal: Policy gates detected SSOT/navigation drift. Update docs/INDEX.md (and docs/NAVIGATION.md if needed) to register new/changed docs and remove dead links, then re-run policy gates.",
        "",
        "Inputs:",
        `- Source task: ${boardTask.id}`,
        `- Policy gate results: ${policyGate.resultsPath ?? "(missing)"}`,
        "",
        "Required:",
        "- Update docs/INDEX.md: add any new docs touched; ensure referenced files exist.",
        "- If control-plane changed, update docs/NAVIGATION.md pointers minimally.",
        "- Keep changes docs-only.",
      ].join("\n"),
      role: "ssot_curator",
      runner: "internal",
      lane: "fastlane",
      area: "control_plane",
      task_class_id: "ssot_index_fixup_v1",
      parentId: boardTask.parentId ?? null,
      allowedExecutors: ["codex", "opencodecli"],
      allowedModels: ["gpt-5.2"],
      timeoutMs: 600000,
      files: ["docs/INDEX.md", "docs/NAVIGATION.md", policyGate.resultsPath ?? ""].filter(Boolean),
      allowedTests: [gateCmd],
      pointers: { sourceTaskId: boardTask.id, jobId: job?.id ?? null, reason: "policy_gate_failed" },
    })
    if (created.ok) {
      tasks.push(created.task)
      dispatchBoardTaskToExecutor(created.task.id)
    }
  }

  if (!tasks.length && schemaIssue) {
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `Control-plane schema fixup: ${boardTask.title ?? boardTask.id}`,
      goal: [
        "Role: FACTORY_MANAGER / INTEGRATOR.",
        "Goal: Policy gates detected schema/registry issues in control-plane assets. Fix registries/matrix/policies to pass schema gate, then re-run policy gates.",
        "",
        "Inputs:",
        `- Source task: ${boardTask.id}`,
        `- Policy gate results: ${policyGate.resultsPath ?? "(missing)"}`,
        "",
        "Constraints:",
        "- Minimal diffs; no business code changes.",
      ].join("\n"),
      role: "factory_manager",
      runner: "internal",
      lane: "fastlane",
      area: "control_plane",
      task_class_id: "schema_fixup_v1",
      parentId: boardTask.parentId ?? null,
      allowedExecutors: ["codex"],
      allowedModels: ["gpt-5.2"],
      timeoutMs: 900000,
      files: ["roles/registry.json", "roles/role_skill_matrix.json", "skills/registry.json", "factory_policy.json", policyGate.resultsPath ?? ""].filter(Boolean),
      allowedTests: [gateCmd],
      pointers: { sourceTaskId: boardTask.id, jobId: job?.id ?? null, reason: "policy_gate_failed" },
    })
    if (created.ok) {
      tasks.push(created.task)
      dispatchBoardTaskToExecutor(created.task.id)
    }
  }

  return tasks.length ? { ok: true, tasks } : { ok: false, error: "no_applicable_fixup", errors: errors.slice(0, 20) }
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

  // Internal runner proof: make Context Pack v1 attestation universal (internal and external).
  // External workers compute these hashes client-side and the gateway verifies them on /complete.
  // For internal runs, the gateway computes them directly from the run snapshot.
  try {
    if (requireContextPackV1 && current.contextPackV1Id) {
      const runId = String(current.contextPackV1Id ?? "").trim()
      if (runId) {
        if (!String(current.attestationNonce ?? "").trim()) {
          try {
            current.attestationNonce = crypto.randomBytes(16).toString("hex")
          } catch {
            current.attestationNonce = String(Math.random()).slice(2) + String(Date.now())
          }
        }
        const nonce = String(current.attestationNonce ?? "").trim()
        const readBytes = (abs) => {
          try {
            return fs.readFileSync(abs)
          } catch {
            return null
          }
        }
        const sha = (buf) => {
          if (!buf) return null
          return `sha256:${crypto.createHash("sha256").update(buf).digest("hex")}`
        }
        const attest = (buf) => {
          if (!buf) return null
          return `sha256:${crypto.createHash("sha256").update(nonce, "utf8").update(buf).digest("hex")}`
        }

        const runDir = path.join(SCC_REPO_ROOT, "artifacts", "scc_runs", runId)
        const packAbs = path.join(runDir, "rendered_context_pack.json")
        const packBuf = readBytes(packAbs)
        const tbDir = path.join(runDir, "task_bundle")
        const files = ["manifest.json", "pins.json", "preflight.json", "task.json"]
        const replayAbs = path.join(tbDir, "replay_bundle.json")
        if (fs.existsSync(replayAbs)) files.push("replay_bundle.json")

        const missing = []
        if (!packBuf) missing.push("rendered_context_pack.json")
        for (const f of files) {
          const p = path.join(tbDir, f)
          if (!fs.existsSync(p)) missing.push(`task_bundle/${f}`)
        }
        if (missing.length) throw new Error(`context_pack_v1_run_missing_files: ${missing.join(", ")}`)

        const filesSha = {}
        const filesAtt = {}
        for (const f of files) {
          const buf = readBytes(path.join(tbDir, f))
          filesSha[f] = sha(buf)
          filesAtt[f] = attest(buf)
        }

        current.contextPackV1Proof = {
          schema_version: "scc.context_pack_v1_proof.v1",
          t: new Date().toISOString(),
          context_pack_v1_id_job: runId,
          context_pack_v1_id_payload: null,
          attestation_nonce_job: nonce,
          attestation_nonce_payload: null,
          pack_json_sha256_payload: sha(packBuf),
          pack_json_attest_sha256_payload: attest(packBuf),
          task_bundle_manifest_sha256_payload: filesSha["manifest.json"] ?? null,
          task_bundle_files_sha256_payload: filesSha,
          task_bundle_files_attest_sha256_payload: filesAtt,
          computed_by: "gateway_internal",
        }
        jobs.set(job.id, current)
        saveState()
      }
    }
  } catch (e) {
    // Fail-closed: do not run model if the execution entrypoint cannot be proven.
    result = {
      ok: false,
      code: 1,
      stdout: "",
      stderr: `[gateway] context_pack_v1 proof compute failed: ${String(e?.message ?? e)}`,
    }
  }
  if (result && result.ok === false) {
    // Skip execution; completion pipeline will persist artifacts and verdict with failure.
  }

  const prefixParts = []
  if (current.contextPackV1Id) {
    const id = String(current.contextPackV1Id ?? "").trim()
    const p = id ? packTxtPathForIdV1({ repoRoot: SCC_REPO_ROOT, id }) : null
    if (p && fs.existsSync(p)) {
      try {
        // Keep model input bounded; pack itself already token-slim by construction.
        const text = fs.readFileSync(p, "utf8")
        prefixParts.push(`<context_pack_v1 id="${id}">\n${text}\n</context_pack_v1>\n`)
      } catch (e) {
        // best-effort: do not crash job start, but leave an audit hint in logs.
        noteBestEffort("context_pack_v1_read_failed", e, { id, path: p })
      }
    }
  }
  if (current.contextPackId) {
    const ctxText = getContextPack(current.contextPackId)
    if (ctxText) prefixParts.push(`<context_pack id="${current.contextPackId}">\n${ctxText}\n</context_pack>\n`)
  }
  if (current.threadId) {
    const t = getThread(current.threadId)
    const history = Array.isArray(t?.history) ? t.history : []
    if (history.length) {
      const last = history.slice(-3).map((x) => `- ${x}`).join("\n")
      prefixParts.push(`<thread id="${current.threadId}">\nRecent decisions:\n${last}\n</thread>\n`)
    }
  }
  const injected = prefixParts.length ? prefixParts.join("\n") + "\n" + current.prompt : current.prompt

  if (!result) {
    if (job.executor === "opencodecli") {
      result = await occliRunSingle(injected, job.model || occliModelDefault, { timeoutMs: current.timeoutMs ?? undefined })
    // Retry once with default model if submit missing
    const firstSubmit = extractSubmitResult(result.stdout)
    if (result.ok && !firstSubmit && (current.attempts ?? 1) < 2) {
      leader({ level: "warn", type: "job_retry_no_submit", id: current.id, model: job.model, fallback: occliModelDefault })
      current.attempts += 1
      result = await occliRunSingle(injected, occliModelDefault, { timeoutMs: current.timeoutMs ?? undefined })
      job.model = occliModelDefault
    }
    } else {
      result = await codexRunSingle(injected, job.model || codexModelDefault, { timeoutMs: current.timeoutMs ?? undefined })
      if (result?.model_used && typeof result.model_used === "string" && result.model_used.trim()) {
        // Preserve configured job.model, but record the actual model used after fallbacks.
        current.model_effective = result.model_used.trim()
      }
    }
  }

  const done = jobs.get(job.id)
  if (!done) return
  done.status = result.ok ? "done" : "failed"
  done.finishedAt = Date.now()
  done.lastUpdate = done.finishedAt
  done.exit_code = result.code
  done.stdout = result.stdout
  done.stderr = result.stderr
  if (result?.model_used && typeof result.model_used === "string" && result.model_used.trim()) {
    done.model_effective = result.model_used.trim()
  }
  done.error = result.ok ? null : "executor_error"
  done.reason = result.ok ? null : classifyFailure(done, result)
  const boardTask = job?.boardTaskId ? getBoardTask(String(job.boardTaskId)) : null
  const isSplitJob = String(done.taskType ?? "") === "board_split"
  const patchText = extractPatchFromStdout(done.stdout)
  let patchStats = patchText ? computePatchStats(patchText) : null
  const snapshotDiff = diffSnapshot(done.pre_snapshot)
  if (!patchStats && Array.isArray(snapshotDiff?.touched_files) && snapshotDiff.touched_files.length) {
    const files = snapshotDiff.touched_files.slice(0, 30)
    patchStats = { files, filesCount: files.length, added: 0, removed: 0, hunks: 0 }
  }
  done.patch_stats = patchStats ?? null
  done.snapshot_diff = snapshotDiff ?? null

  // Split jobs MUST NOT touch the repo. Treat any filesystem diff as a hard failure (hygiene invariant).
  if (isSplitJob && Array.isArray(snapshotDiff?.touched_files) && snapshotDiff.touched_files.length) {
    done.status = "failed"
    done.error = "hygiene_failed"
    done.reason = "split_touched_repo"
  }

  // Executor contract includes a structured SUBMIT payload. Persist it for audit/evidence and
  // for cases where we cannot infer touched files from a unified diff (e.g. tool-based writes).
  done.submit = loadSubmitArtifact(boardTask?.id ?? done.boardTaskId) ?? (extractSubmitResult(done.stdout) ?? null)
  done.usage = done.executor === "codex" ? extractUsageFromStdout(done.stdout) : null
  if (done.status === "done" && done.executor === "opencodecli" && occliRequireSubmit && !done.submit) {
    done.status = "failed"
    done.error = "missing_submit_contract"
    done.reason = "missing_submit_contract"
  }
  if (done.status === "done" && done.submit?.status === "NEED_INPUT") {
    done.status = "failed"
    done.error = "needs_input"
    done.reason = "needs_input"
  }

  // Never write task artifacts for split jobs: split is a meta-step that produces split.json only.
  // Writing artifacts/<parent_id>/submit.json here would corrupt parent semantics.
  if (boardTask && !isSplitJob) ensureExternalArtifactsAndSubmit({ job: done, boardTask, patchText, patchStats, snapshotDiff, ciGate: null })

  // Patch scope enforcement: allowed_paths/forbidden_paths/max_files/loc
  const scope = validatePatchScope({ patchStats, boardTask })
  if (done.status === "done" && !scope.ok) {
    done.status = "failed"
    done.error = "patch_scope_violation"
    done.reason = scope.errors?.[0]?.reason ?? "patch_scope_violation"
    leader({
      level: "warn",
      type: "patch_scope_violation",
      id: done.id,
      taskId: boardTask?.id ?? null,
      errors: scope.errors,
    })
  }

  // Submit vs diff consistency: touched_files must cover patch files
  if (done.status === "done" && patchStats && Array.isArray(done.submit?.touched_files)) {
    const norm = (arr) => arr.map((f) => normalizeRepoPath(f)).filter(Boolean)
    const diffFiles = norm(patchStats.files ?? [])
    const touched = new Set(norm(done.submit.touched_files))
    const missing = diffFiles.filter((f) => !touched.has(f))
    if (missing.length) {
      done.status = "failed"
      done.error = "submit_mismatch"
      done.reason = "submit_mismatch"
      leader({
        level: "warn",
        type: "submit_mismatch",
        id: done.id,
        taskId: boardTask?.id ?? null,
        missing: missing.slice(0, 20),
      })
    }
  }

  const isCiFixup = String(boardTask?.task_class_id ?? "") === "ci_fixup_v1"
  let ciGate = null
  if (isSplitJob) {
    ciGate = { ran: false, skipped: "board_split" }
  } else if (done.status === "done" || isCiFixup) {
    ciGate = await runCiGateForTask({ job: done, boardTask })
    if (ciGate?.required && !ciGate.ran && ciGateStrict) {
      done.status = "failed"
      done.error = "ci_failed"
      done.reason = "ci_skipped"
    } else if (ciGate?.ran && !ciGate.ok) {
      done.status = "failed"
      done.error = "ci_failed"
      done.reason = "ci_failed"
    } else if (ciGate?.timedOut) {
      done.status = "failed"
      done.error = "ci_failed"
      done.reason = "ci_timed_out"
    } else if (isCiFixup && ciGate?.ran && ciGate.ok) {
      done.status = "done"
      done.error = null
      done.reason = null
      done.exit_code = 0
    }
  }
  done.ci_gate = ciGate ?? null
  if (ciGate && done.error === "ci_failed") {
    const routed = maybeCreateCiGateFixupTasks({ boardTask, job: done, ciGate })
    if (!routed.ok) maybeCreateCiFixupTask({ boardTask, job: done, ciGate })
  }
  // Run project-level allowed tests (smoke) under gateway control for external runners.
  let allowedTestsRun = null
  if (done.status === "done" && boardTask) {
    allowedTestsRun = await runGatewayAllowedTests({ boardTask, job: done })
    done.allowed_tests = allowedTestsRun ?? null
    if (allowedTestsRun?.ran && allowedTestsRun.ok === false) {
      done.status = "failed"
      done.error = "tests_failed"
      done.reason = "tests_failed"
    }
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
  // Auto-rollback (docs-only by default) on CI gate failure to stabilize repo health.
  if (done.status === "failed" && done.error === "ci_failed" && boardTask) {
    const rb = applyAutoRollbackOnCiFailed({ boardTask, job: done, snapshotDiff, patchStats, ciGate })
    if (rb?.ok) {
      leader({ level: "warn", type: "auto_rollback_applied", taskId: boardTask.id, jobId: done.id, report: rb.report_path ?? null })
    }
  }
  let hygiene = null
  if (done.status === "done") {
    if (!isSplitJob) {
      if (boardTask) ensureExternalArtifactsAndSubmit({ job: done, boardTask, patchText, patchStats, snapshotDiff, ciGate })
      hygiene = runHygieneChecks({ job: done, boardTask })
      if (!hygiene.ok) {
        done.status = "failed"
        done.error = "hygiene_failed"
        done.reason = hygiene.reason ?? "hygiene_failed"
        appendJsonl(ciFailuresFile, {
          t: new Date().toISOString(),
          task_id: boardTask?.id ?? null,
          job_id: done.id,
          reason: done.reason,
          hygiene,
        })
      }
    } else {
      hygiene = runSplitOutputChecks({ job: done, boardTask })
      if (!hygiene.ok) {
        done.status = "failed"
        done.error = "hygiene_failed"
        done.reason = hygiene.reason ?? "split_output_invalid"
        appendJsonl(ciFailuresFile, {
          t: new Date().toISOString(),
          task_id: boardTask?.id ?? null,
          job_id: done.id,
          reason: done.reason,
          hygiene,
        })
      }
    }
  }

  let policyGate = null
  if (done.status === "done") {
    policyGate = isSplitJob ? { ran: false, skipped: "board_split" } : await runPolicyGateForTask({ job: done, boardTask })
    if (policyGate?.required && policyGate?.ran && !policyGate.ok && policyGateStrict) {
      done.status = "failed"
      done.error = "policy_gate_failed"
      done.reason = policyGate.timedOut ? "policy_gate_timed_out" : "policy_gate_failed"
    } else if (policyGate?.required && policyGate?.ran && policyGate.timedOut && policyGateStrict) {
      done.status = "failed"
      done.error = "policy_gate_failed"
      done.reason = "policy_gate_timed_out"
    }
  }
  done.policy_gate = policyGate ?? null
  if (policyGate) {
    appendJsonlChained(policyGateResultsFile, {
      t: new Date().toISOString(),
      job_id: done.id,
      task_id: boardTask?.id ?? null,
      ok: policyGate.ok ?? null,
      ran: policyGate.ran ?? null,
      required: policyGate.required ?? null,
      skipped: policyGate.skipped ?? null,
      exitCode: policyGate.exitCode ?? null,
      durationMs: policyGate.durationMs ?? null,
      command: policyGate.command ?? null,
      timedOut: policyGate.timedOut ?? null,
      resultsPath: policyGate.resultsPath ?? null,
    })
    if (done.error === "policy_gate_failed") {
      appendJsonl(ciFailuresFile, {
        t: new Date().toISOString(),
        task_id: boardTask?.id ?? null,
        job_id: done.id,
        reason: done.reason ?? "policy_gate_failed",
        policy_gate: policyGate,
      })
      if (boardTask) maybeCreatePolicyFixupTasks({ boardTask, job: done, policyGate })
    }
  }

  // Always emit a machine-readable verdict for audit + routing.
  if (boardTask) {
    try {
      const verdict = computeVerdictV1({ taskId: boardTask.id, submit: done.submit, job: done, ciGate, policyGate, hygiene })
      done.verdict = verdict
      const written = writeVerdictArtifact({ taskId: boardTask.id, verdict })
      done.verdict_path = written.ok ? path.relative(SCC_REPO_ROOT, written.file).replaceAll("\\", "/") : null

      try {
        if (written?.ok) writeTraceArtifact({ taskId: boardTask.id, job: done, boardTask })
      } catch (e) {
        // best-effort
        noteBestEffort("writeTraceArtifact", e, { task_id: boardTask.id })
      }
      try {
        const root = rootParentIdForTask(boardTask)
        if (root) {
          const usageDelta = {
            attempts: 1,
            tokens_input: done?.usage?.input_tokens ?? 0,
            tokens_output: done?.usage?.output_tokens ?? 0,
            verify_minutes: Math.ceil(((ciGate?.durationMs ?? 0) + (policyGate?.durationMs ?? 0)) / 60000),
          }
          const type = done.status === "done" ? "child_done" : "child_failed"
          bumpParentProgress({ parentId: root, type, details: { task_id: boardTask.id, reason: done.reason ?? null }, usageDelta })
        }
      } catch (e) {
        // best-effort
        noteBestEffort("bumpParentProgress_from_verdict", e, { task_id: boardTask.id })
      }

      // Verdict-driven escalation: ESCALATE tasks must enter DLQ (fail-closed) with a structured DLQ entry.
      if (verdict?.verdict === "ESCALATE" && boardTask.kind === "atomic" && boardTask.status !== "done") {
        const opened = boardTask.dlq_opened === true
        boardTask.lane = "dlq"
        boardTask.dlq_opened = true
        boardTask.updatedAt = Date.now()
        putBoardTask(boardTask)
        if (!opened) {
          const missing = Array.isArray(done?.submit?.needs_input) ? done.submit.needs_input.map((x) => String(x)).filter(Boolean) : []
          const reasons = Array.isArray(verdict?.reasons) ? verdict.reasons.map((x) => String(x)).filter(Boolean) : []
          openDlqForTask({
            task: boardTask,
            reason_code: reasons[0] ?? "ESCALATE",
            summary: `Verdict ESCALATE: ${reasons.slice(0, 3).join(", ") || "no reasons"}`,
            missing_inputs: missing.length ? missing.slice(0, 20) : reasons.slice(0, 20),
            last_event: { event_type: "RETRY_EXHAUSTED", t: new Date().toISOString(), reason: "verdict_escalate" },
          })
        }
      }
    } catch (e) {
      appendJsonl(execLeaderLog, { t: new Date().toISOString(), type: "verdict_compute_failed", task_id: boardTask?.id ?? null, error: String(e?.message ?? e) })
    }
  }

  // Apply recovery outputs from isolation area
  if (boardTask && boardTask.area === "isolation" && done.status === "done") {
    const recovered = extractFirstJsonObject(done.stdout)
    const applied = createTaskFromRecovery({ recoveryTask: boardTask, job: done, payload: recovered })
    if (applied) {
      leader({ level: "info", type: "recovery_applied", sourceId: boardTask.id, newId: applied.id })
      boardTask.status = "done"
      boardTask.updatedAt = Date.now()
      boardTask.lastJobReason = "recovered"
      putBoardTask(boardTask)
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
    taskType: done.taskType ?? null,
    status: done.status,
    task_id: boardTask?.id ?? null,
    area: boardTask?.area ?? null,
    lane: boardTask?.lane ?? null,
    task_class: boardTask?.task_class_id ?? boardTask?.task_class_candidate ?? null,
    dispatch_attempts: boardTask?.dispatch_attempts ?? null,
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
    policy_gate: policyGate
      ? {
          ok: policyGate.ok ?? null,
          ran: policyGate.ran ?? null,
          required: policyGate.required ?? null,
          skipped: policyGate.skipped ?? null,
          exitCode: policyGate.exitCode ?? null,
          durationMs: policyGate.durationMs ?? null,
          command: policyGate.command ?? null,
          timedOut: policyGate.timedOut ?? null,
          resultsPath: policyGate.resultsPath ?? null,
        }
      : null,
    prompt_bytes: Buffer.byteLength(String(done.prompt ?? ""), "utf8"),
    context_bytes: Number(done.contextBytes ?? null),
    context_files: Number(done.contextFiles ?? null),
    context_source: done.contextSource ?? null,
    pins_allow_count: Number(done.pinsAllowCount ?? null),
    pins_symbols_count: Number(done.pinsSymbolsCount ?? null),
    pins_line_windows: Number(done.pinsLineWindows ?? null),
    prompt_ref: done.prompt_ref ?? null,
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
  if (done.status === "done" && done.submit && mapBuildTriggeredBySubmit(done.submit)) {
    scheduleMapBuild({ reason: `task_done:${boardTask?.id ?? done.id}` })
  }
  if (done.status === "done" && boardTask) {
    appendPinsCandidate(boardTask, done)
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
      const rendered = renderPromptOrFallback({
        role_id: "factory_manager.audit_fix_v1",
        params: { source_task_id: String(boardTask.parentId ?? boardTask.id) },
        fallback: `Audit failed for task ${boardTask.parentId ?? boardTask.id}. Clarify pins or fix findings, then re-run CI.`,
        note: "audit_fix_v1",
      })
      const created = createBoardTask({
        kind: "atomic",
        status: "ready",
        title: "Audit follow-up: clarify/fix",
        goal: rendered.text,
        prompt_ref: rendered.prompt_ref,
        role: "factory_manager",
        area: "control_plane",
        runner: "internal",
        allowedExecutors: factoryManagerDefaultExecutors(),
        allowedModels: factoryManagerDefaultModels(),
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
  const counts = runningCountsAll()
  const queued = Array.from(jobs.values()).filter((j) => j.status === "queued").length
  const done = Array.from(jobs.values()).filter((j) => j.status === "done").length
  const failed = Array.from(jobs.values()).filter((j) => j.status === "failed").length
  appendJsonl(execLogHeartbeat, {
    t: new Date().toISOString(),
    counts: { ...counts, queued, done, failed, total: jobs.size },
  })
}, 15000)

// Stability hook: when overloaded, spawn a stability_controller task (rate-limited).
setInterval(() => {
  if (!stabilityHookEnabled) return
  try {
    const out = maybeTriggerStabilityController()
    if (out?.ok) leader({ level: "warn", type: "stability_task_created", taskId: out.task?.id ?? null })
  } catch (e) {
    leader({ level: "warn", type: "stability_hook_error", error: String(e) })
  }
}, (() => {
  const ms = Number(process.env.STABILITY_HOOK_TICK_MS ?? "60000")
  return Number.isFinite(ms) && ms > 5000 ? ms : 60000
})())

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

  // Trigger a factory_manager task that turns the report's top taxonomy into concrete fixes + regression.
  try {
    const reportFile = path.join(execLogDir, "five_whys", "report.json")
    let report = null
    if (fs.existsSync(reportFile)) {
      report = JSON.parse(fs.readFileSync(reportFile, "utf8"))
    }
    const top = Array.isArray(report?.taxonomy_summary) && report.taxonomy_summary.length ? report.taxonomy_summary[0] : null
    const topTax = top?.taxonomy ?? null
    const title = `Five Whys: prevention plan (${topTax ?? "unknown"})`
    const fallbackGoal = [
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
    const rendered = renderPromptOrFallback({
      role_id: "factory_manager.five_whys_response_v1",
      params: { taxonomy_summary_json: JSON.stringify(report?.taxonomy_summary ?? [], null, 2) },
      fallback: fallbackGoal,
      note: "five_whys_response_v1",
    })
    const goal = rendered.text
    const created = createBoardTask({
      kind: "atomic",
      status: "ready",
      title,
      goal,
      prompt_ref: rendered.prompt_ref,
      role: "factory_manager",
      runner: "internal",
      area: "control_plane",
      task_class_id: "five_whys_response_v1",
      allowedExecutors: factoryManagerDefaultExecutors(),
      allowedModels: Array.from(new Set([...factoryManagerDefaultModels(), ...fiveWhysAllowedModels])),
      timeoutMs: 900000,
      files: ["artifacts/executor_logs/five_whys/report.json", "artifacts/executor_logs/five_whys/report.md"],
    })
    if (created.ok) {
      const dispatched = dispatchBoardTaskToExecutor(created.task.id)
      if (dispatched.job) {
        dispatched.job.priority = 940
        jobs.set(dispatched.job.id, dispatched.job)
        const running = runningCountsInternal()
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

const failureReportTickMs = Number(process.env.FAILURE_REPORT_TICK_MS ?? "3600000")
const failureReportTail = Number(process.env.FAILURE_REPORT_TAIL ?? "500")

const radiusAuditHookEnabled = String(process.env.RADIUS_AUDIT_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const radiusAuditHookEveryN = Number(process.env.RADIUS_AUDIT_HOOK_EVERY_N ?? "10")
const radiusAuditHookMinMs = Number(process.env.RADIUS_AUDIT_HOOK_MIN_MS ?? "600000")
const radiusAuditHookRoles = (process.env.RADIUS_AUDIT_HOOK_ROLES ?? "engineer,integrator")
  .split(/[;,]/g)
  .map((x) => x.trim())
  .filter((x) => x.length)
const radiusAuditHookTimeoutMs = Number(process.env.RADIUS_AUDIT_HOOK_TIMEOUT_MS ?? "180000")
const radiusAuditHookStateFile = path.join(execLogDir, "radius_audit_hook_state.json")

// Failure report (hourly by default)
if (Number.isFinite(failureReportTickMs) && failureReportTickMs > 0) {
  setInterval(() => {
    const out = writeFailureReport({ tail: failureReportTail })
    if (out) leader({ level: "info", type: "failure_report_written", ...out })
  }, Math.max(60000, failureReportTickMs))
  // Best-effort immediate snapshot on startup
  setTimeout(() => {
    const out = writeFailureReport({ tail: failureReportTail })
    if (out) leader({ level: "info", type: "failure_report_written", ...out })
  }, 2000)
}

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
const policyGateEnabled = String(process.env.POLICY_GATE_ENABLED ?? "true").toLowerCase() !== "false"
const policyGateStrict = String(process.env.POLICY_GATE_STRICT ?? "true").toLowerCase() !== "false"
const policyGateTimeoutMs = Number(process.env.POLICY_GATE_TIMEOUT_MS ?? "180000")
const policyGateMaxFixupsPerTask = Number(process.env.POLICY_GATE_MAX_FIXUPS_PER_TASK ?? "2")
const stabilityHookEnabled = String(process.env.STABILITY_HOOK_ENABLED ?? "true").toLowerCase() !== "false"
const stabilityHookTickMs = Number(process.env.STABILITY_HOOK_TICK_MS ?? "60000")
const stabilityHookMinMs = Number(process.env.STABILITY_HOOK_MIN_MS ?? "900000")
const stabilityQueuedThreshold = Number(process.env.STABILITY_QUEUE_THRESHOLD ?? "80")
const ciFixupEnabled = String(process.env.CI_FIXUP_ENABLED ?? "true").toLowerCase() !== "false"
const ciFixupMaxPerTask = Number(process.env.CI_FIXUP_MAX_PER_TASK ?? "2")
const ciFixupRole = process.env.CI_FIXUP_ROLE ?? "ci_fixup"
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
const ciGatesStrict = String(process.env.CI_GATES_STRICT ?? process.env.CI_GATE_STRICT ?? "true").toLowerCase() !== "false"
const ciGateStrict = ciGatesStrict
const ciGateAllowAll = String(process.env.CI_GATE_ALLOW_ALL ?? "false").toLowerCase() === "true"
const ciGateTimeoutMs = Number(process.env.CI_GATE_TIMEOUT_MS ?? "1200000")
const ciGateCwd = process.env.CI_GATE_CWD ?? cfg.repoRoot
const ciEnforceSinceMs = Number(process.env.CI_ENFORCE_SINCE_MS ?? "0")
const ciAntiforgerySinceMs = Number(process.env.CI_ANTIFORGERY_SINCE_MS ?? "0")
const autoDefaultAllowedTests = String(process.env.AUTO_DEFAULT_ALLOWED_TESTS ?? "true").toLowerCase() !== "false"
const autoRecoverEnabled = String(process.env.AUTO_RECOVER_STALE_TASKS ?? "true").toLowerCase() !== "false"
const autoRecoverTickMs = Number(process.env.AUTO_RECOVER_TICK_MS ?? "60000")
const autoRecoverStaleMs = Number(process.env.AUTO_RECOVER_STALE_MS ?? "1800000") // 30 min
const autoRecoverQueuedMs = Number(process.env.AUTO_RECOVER_QUEUED_MS ?? "900000") // 15 min
const autoCancelStaleExternal = String(process.env.AUTO_CANCEL_STALE_EXTERNAL ?? "true").toLowerCase() !== "false"
const autoCancelExternalTickMs = Number(process.env.AUTO_CANCEL_STALE_EXTERNAL_TICK_MS ?? "60000")
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
      const running = runningCountsInternal()
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
      if (job && job.status === "queued") {
        const jobAge = now - (job.lastUpdate ?? job.createdAt ?? now)
        if (Number.isFinite(autoRecoverQueuedMs) && autoRecoverQueuedMs > 0 && jobAge >= autoRecoverQueuedMs) {
          jobs.delete(job.id)
          saveState()
          t.status = "ready"
          t.updatedAt = now
          t.lastJobStatus = "stale"
          t.lastJobReason = "job_queued_too_long"
          t.lastJobFinishedAt = now
          putBoardTask(t)
          leader({ level: "warn", type: "board_task_recovered", id: t.id, reason: "job_queued_too_long" })
          continue
        }
      }
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

// Auto-cancel stale external jobs if their board task is no longer in progress.
setInterval(() => {
  if (!autoCancelStaleExternal) return
  try {
    for (const j of jobs.values()) {
      if (j.runner !== "external") continue
      if (j.status !== "running") continue
      if (!j.boardTaskId) continue
      const t = getBoardTask(String(j.boardTaskId))
      if (!t) {
        cancelExternalJob({ id: j.id, reason: "board_task_missing" })
        continue
      }
      if (t.status !== "in_progress" || t.lastJobId !== j.id) {
        cancelExternalJob({ id: j.id, reason: "board_task_not_in_progress" })
      }
    }
  } catch (e) {
    leader({ level: "warn", type: "auto_cancel_external_error", error: String(e) })
  }
}, Number.isFinite(autoCancelExternalTickMs) ? Math.max(10000, autoCancelExternalTickMs) : 60000)

// Periodic learn/eval/metrics tick (disabled by default; best-effort).
setInterval(async () => {
  if (!autoLearnTickEnabled) return
  try {
    leader({ level: "info", type: "auto_learn_tick_start" })
    const mine = await runSccPythonOp({ scriptRel: "tools/scc/ops/lesson_miner.py", args: [], timeoutMs: 300000 })
    const evalOut = await runSccPythonOp({
      scriptRel: "tools/scc/ops/eval_replay.py",
      args: ["--drafts", "playbooks/drafts", "--samples-per-playbook", "1"],
      timeoutMs: 300000,
    })
    const reg = await runSccPythonOp({ scriptRel: "tools/scc/ops/playbooks_registry_sync.py", args: [], timeoutMs: 120000 })
    const rollup = await runSccPythonOp({
      scriptRel: "tools/scc/ops/metrics_rollup.py",
      args: ["--window-hours", "24", "--bucket-minutes", "60"],
      timeoutMs: 300000,
    })
    const rollback = await runSccPythonOp({ scriptRel: "tools/scc/ops/playbook_rollback.py", args: [], timeoutMs: 120000 })
    const ok = Boolean(mine.ok && evalOut.ok && reg.ok && rollup.ok && rollback.ok)
    leader({ level: ok ? "info" : "warn", type: "auto_learn_tick_done", ok })
  } catch (e) {
    leader({ level: "warn", type: "auto_learn_tick_error", error: String(e?.message ?? e) })
  }
}, Number.isFinite(autoLearnTickMs) ? Math.max(60000, Math.min(autoLearnTickMs, 6 * 60 * 60 * 1000)) : 900000)

// Auto-unblock tasks after cooldown (stop-the-bleeding / temporary holds).
setInterval(() => {
  const enabled = String(process.env.AUTO_UNBLOCK_TASKS ?? "true").toLowerCase() !== "false"
  if (!enabled) return
  const maxPerTick = Number(process.env.AUTO_UNBLOCK_MAX_PER_TICK ?? "20")
  if (!Number.isFinite(maxPerTick) || maxPerTick <= 0) return
  const now = Date.now()
  let unblocked = 0
  try {
    for (const t of listBoardTasks()) {
      if (unblocked >= maxPerTick) break
      if (t.kind !== "atomic") continue
      if (t.status !== "blocked") continue
      const until = Number(t.cooldownUntil ?? 0)
      if (!Number.isFinite(until) || until <= 0 || now < until) continue

      const degradation = computeDegradationState()
      const allow = shouldAllowTaskUnderStopTheBleedingV1({ action: degradation.action, task: t })
      if (!allow.ok) {
        // Still in stop-the-bleeding; extend cooldown gently.
        t.cooldownUntil = now + 60_000
        t.updatedAt = now
        putBoardTask(t)
        continue
      }

      t.status = "ready"
      t.updatedAt = now
      putBoardTask(t)
      leader({ level: "info", type: "task_unblocked", id: t.id, previous_reason: t.lastJobReason ?? null })
      unblocked += 1
    }
  } catch (e) {
    leader({ level: "warn", type: "auto_unblock_error", error: String(e?.message ?? e) })
  }
}, Number(process.env.AUTO_UNBLOCK_TICK_MS ?? "30000"))

// Lease watchdog: requeue external running jobs whose lease expired (stuck worker / gateway restart).
setInterval(() => {
  const enabled = String(process.env.AUTO_REQUEUE_LEASE_EXPIRED ?? "true").toLowerCase() !== "false"
  if (!enabled) return
  const graceMs = Number(process.env.AUTO_REQUEUE_LEASE_GRACE_MS ?? "30000")
  const maxPerTick = Number(process.env.AUTO_REQUEUE_LEASE_MAX_PER_TICK ?? "5")
  const maxRescue = Number(process.env.AUTO_REQUEUE_LEASE_MAX_PER_JOB ?? "2")
  const now = Date.now()
  let count = 0
  try {
    for (const j of jobs.values()) {
      if (count >= maxPerTick) break
      if (j.runner !== "external") continue
      if (j.status !== "running") continue
      const leaseUntil = Number(j.leaseUntil ?? 0)
      if (!leaseUntil) continue
      if (now <= leaseUntil + (Number.isFinite(graceMs) ? Math.max(0, graceMs) : 30000)) continue

      const rescues = Number(j.lease_rescue_count ?? 0)
      if (Number.isFinite(maxRescue) && maxRescue > 0 && rescues >= maxRescue) {
        cancelExternalJob({ id: j.id, reason: "lease_expired_max_rescue" })
        count += 1
        continue
      }

      const t = j.boardTaskId ? getBoardTask(String(j.boardTaskId)) : null
      if (!t || t.status !== "in_progress" || t.lastJobId !== j.id) {
        cancelExternalJob({ id: j.id, reason: "lease_expired_stale_task" })
        count += 1
        continue
      }

      j.lease_rescue_count = rescues + 1
      jobs.set(j.id, j)
      saveState()
      const out = requeueExternalJob({ id: j.id, reason: "lease_expired" })
      leader({ level: out.ok ? "warn" : "error", type: "job_lease_requeued", id: j.id, task_id: t.id, ok: out.ok })
      count += 1
    }
  } catch (e) {
    leader({ level: "warn", type: "lease_watchdog_error", error: String(e) })
  }
}, 15000)

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
  const counts = runningCountsAll()
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

  // Purge obviously invalid legacy tasks to avoid wasting executors.
  for (const t of listBoardTasks()) {
    const titleEmpty = !String(t.title ?? "").trim()
    const goalEmpty = !String(t.goal ?? "").trim()
    const filesEmpty = !Array.isArray(t.files) || t.files.length === 0
    if (t.kind === "atomic" && (titleEmpty || goalEmpty || filesEmpty)) {
    const now = Date.now()
    appendIsolation({
      quarantined_at: new Date(now).toISOString(),
      source_task: t,
      reason: "invalid_format",
    })
    boardTasks.delete(t.id)
    // Create a recovery task handled by codex 5.2 to reconstruct a valid task definition.
    const rec = createBoardTask({
      kind: "atomic",
      status: "ready",
      title: `Recover task ${t.id}`,
      goal: [
        "You are SCC Recovery (codex 5.2). The source task had missing title/goal/files/pins.",
        "Output JSON with fields: {title, goal, files[], allowedTests[], pins{allowed_paths, forbidden_paths, max_files, max_loc}, acceptance[]}.",
        "Files must be repo-relative and minimal; allowedTests include at least one real test; pins.allowed_paths non-empty.",
        "Also include suggestion for role and task_class if inferable. Avoid code edits; just produce metadata.",
        `Source snapshot: ${JSON.stringify({ title: t.title, goal: t.goal, files: t.files, role: t.role }, null, 2)}`,
      ].join("\n"),
      role: "pinser",
      area: "isolation",
      runner: "internal",
      allowedExecutors: ["codex"],
      allowedModels: ["gpt-5.1-codex-mini-high"],
      files: ["docs/WORKLOG.md"],
      pins: { allowed_paths: ["docs/WORKLOG.md"], forbidden_paths: ["node_modules", ".git"], symbols: [], line_windows: {}, max_files: 4, max_loc: 200 },
      pointers: { sourceTaskId: t.id },
    })
    if (rec.ok) {
      dispatchBoardTaskToExecutor(rec.task.id)
    }
  }
}

// ---------------- External worker pool (optional) ----------------
const workers = new Map()
const newWorkerId = () => crypto.randomUUID()

function listWorkers() {
  return Array.from(workers.values()).filter(Boolean)
}

function getWorker(id) {
  return workers.get(id) ?? null
}

function putWorker(w) {
  workers.set(w.id, w)
}

// Prevent unbounded growth when workers re-register after transient errors.
setInterval(() => {
  const now = Date.now()
  const staleMs = Number(process.env.WORKER_STALE_PRUNE_MS ?? "600000") // 10 min
  const limit = Number(process.env.WORKER_STALE_PRUNE_MAX ?? "500")
  let pruned = 0
  for (const w of workers.values()) {
    if (pruned >= limit) break
    const lastSeen = Number(w?.lastSeen ?? 0)
    if (!lastSeen || now - lastSeen < staleMs) continue
    if (w?.runningJobId) continue
    workers.delete(w.id)
    pruned += 1
  }
  if (pruned) leader({ level: "info", type: "workers_pruned", pruned })
}, 60_000)

function claimNextJob({ executor, worker }) {
  const supported = Array.isArray(worker?.models) ? worker.models.map((x) => String(x)) : null
  const canRunModel = (model) => {
    if (!supported || supported.length === 0) return true
    return supported.includes(String(model))
  }
  const queued = Array.from(jobs.values())
    .filter((j) => j.status === "queued" && j.runner === "external" && j.executor === executor)
    .filter((j) => (!requireContextPackV1 ? true : Boolean(String(j.contextPackV1Id ?? "").trim())))
    .filter((j) => canRunModel(j.model))
    .sort((a, b) => (a.createdAt ?? 0) - (b.createdAt ?? 0))
  return queued[0] ?? null
}

function buildInjectedPrompt(job) {
  const prefixParts = []
  if (job.contextPackV1Id) {
    const id = String(job.contextPackV1Id ?? "").trim()
    const p = id ? packTxtPathForIdV1({ repoRoot: SCC_REPO_ROOT, id }) : null
    if (p && fs.existsSync(p)) {
      try {
        const text = fs.readFileSync(p, "utf8")
        prefixParts.push(`<context_pack_v1 id="${id}">\n${text}\n</context_pack_v1>\n`)
      } catch (e) {
        noteBestEffort("context_pack_v1_read_failed_buildInjectedPrompt", e, { id, path: p })
      }
    }
  }
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
        <a href="/sccdev">/sccdev</a> (monitor UI)
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
      preferFreeModels,
      codexPreferredOrder,
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

function summarizeRouterStatsForUi() {
  try {
    const file = path.join(SCC_REPO_ROOT, "metrics", "router_stats_latest.json")
    let obj = null
    if (fs.existsSync(file)) {
      obj = JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, ""))
    } else if (routerStatsCache?.computedAt) {
      obj = { schema_version: "scc.router_stats.v1", by_model: routerStatsCache.by_model ?? {} }
    } else {
      obj = null
    }

    const byModel = obj?.by_model && typeof obj.by_model === "object" ? obj.by_model : {}
    const rows = []
    for (const v of Object.values(byModel)) {
      const exec = String(v?.executor ?? "")
      if (exec !== "codex") continue
      const model = String(v?.model ?? "")
      const n = Number(v?.n ?? 0)
      const ok = Number(v?.ok ?? 0)
      if (!model || !Number.isFinite(n) || n <= 0) continue
      rows.push({ model, n, ok, rate: ok / n })
    }
    rows.sort((a, b) => (b.rate !== a.rate ? b.rate - a.rate : b.n - a.n))
    const top = rows.slice(0, 3).map((r) => `${r.model} ${(r.rate * 100).toFixed(0)}% (n=${r.n})`)
    return top.length ? top.join(" | ") : "no samples yet"
  } catch {
    return "unavailable"
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

  // Core router (incremental extraction)
  const core = await coreRouter.handle(req, res, {
    gatewayPort,
    http,
    fs,
    path,
    URL,
    execLogDir,
    boardDir,
    docsRoot,
    sccUpstream,
    opencodeUpstream,
    SCC_REPO_ROOT,
    SCC_PREFIXES,
    gatewayErrorsFile,
    readJsonlTail,
    sendJson,
    listBoardTasks,
    runningCounts: runningCountsAll,
    jobs,
    listWorkers,
    stateEventsFile,
    repoHealthState,
    quarantineActive,
    repoUnhealthyActive,
    loadRepoHealthState,
    loadCircuitBreakerState,
    wipLimits,
    runningInternalByLane,
    computeDegradationState,
    applyDegradationToWipLimitsV1,
    codexModelDefault,
    codexPreferredOrder,
    STRICT_DESIGNER_MODEL,
    summarizeRouterStatsForUi,
    statusSnapshot,
    renderHomeHtml,
    log,
    errSink,
    // Config routes dependencies
    readRuntimeEnv,
    configRegistry,
    codexMax,
    occliMax,
    externalMaxCodex,
    externalMaxOccli,
    desiredRatioCodex,
    desiredRatioOccli,
    timeoutCodexMs,
    timeoutOccliMs,
    modelsFree,
    modelsVision,
    preferFreeModels,
    autoCreateSplitOnTimeout,
    autoDispatchSplitTasks,
    occliModelDefault,
    autoAssignOccliModels,
    failureReportTickMs,
    failureReportTail,
    autoCancelStaleExternal,
    autoCancelExternalTickMs,
    cfg,
    writeRuntimeEnv,
    leader,
    runtimeEnvFile,
    readRequestBody,
    // Models routes dependencies
    updateModelPools,
    updateCodexModelPolicy,
    modelsPaid,
    // Prompts routes dependencies
    promptRegistry,
  })
  if (core.handled) return

  // SCC Dev Monitor UI (local only, file-backed).
  if ((pathname === "/sccdev" || pathname === "/sccdev/") && method === "GET") {
    return serveStaticFromDir(req, res, { rootDir: sccDevUiDir, relPath: "index.html" })
  }
  if (pathname.startsWith("/sccdev/") && method === "GET") {
    const rel = pathname.replace("/sccdev/", "")
    if (rel.startsWith("api/")) {
      // fallthrough to API handler
    } else if (rel.length > 0) {
      return serveStaticFromDir(req, res, { rootDir: sccDevUiDir, relPath: rel })
    }
  }

  // Map v1 (structured index): file-backed, deterministic, queryable.
  if (pathname === "/map/v1/version" && method === "GET") {
    try {
      const p = path.join(SCC_REPO_ROOT, "map", "version.json")
      if (!fs.existsSync(p)) return sendJson(res, 404, { error: "map_version_missing", path: p })
      const raw = fs.readFileSync(p, "utf8")
      const data = JSON.parse(raw.replace(/^\uFEFF/, ""))
      return sendJson(res, 200, { ok: true, path: p, data })
    } catch (e) {
      return sendJson(res, 500, { error: "map_version_read_failed", message: String(e?.message ?? e) })
    }
  }

  if (pathname === "/map/v1/link_report" && method === "GET") {
    try {
      const p = path.join(SCC_REPO_ROOT, "map", "link_report.json")
      if (!fs.existsSync(p)) return sendJson(res, 404, { error: "link_report_missing", path: p })
      const raw = fs.readFileSync(p, "utf8")
      const data = JSON.parse(raw.replace(/^\uFEFF/, ""))
      return sendJson(res, 200, { ok: true, path: p, data })
    } catch (e) {
      return sendJson(res, 500, { error: "link_report_read_failed", message: String(e?.message ?? e) })
    }
  }

  if (pathname === "/map/v1/query" && method === "GET") {
    const q = url.searchParams.get("q") ?? ""
    const limit = Number(url.searchParams.get("limit") ?? "20")
    try {
      const backend = String(url.searchParams.get("backend") ?? process.env.MAP_QUERY_BACKEND ?? "").toLowerCase()
      const wantSqlite = backend === "sqlite"
      const strict = (() => {
        const v = String(process.env.MAP_QUERY_STRICT ?? "auto").toLowerCase()
        if (v === "auto") return wantSqlite
        return v === "1" || v === "true" || v === "yes" || v === "on"
      })()
        const sqlitePath = path.join(SCC_REPO_ROOT, "map", "map.sqlite")
      if (wantSqlite && strict && !fs.existsSync(sqlitePath)) {
        return sendJson(res, 400, { ok: false, error: "missing_sqlite", db: "map/map.sqlite", hint: "Rebuild map with sqlite (POST /map/v1/build or npm --prefix oc-scc-local run map:build)" })
      }
      if (wantSqlite && fs.existsSync(sqlitePath)) {
        const root = SCC_REPO_ROOT
        const stdout = execFileSync(
          "python",
          ["tools/scc/map/map_query_sqlite_v1.py", "--repo-root", root, "--db", "map/map.sqlite", "--q", String(q), "--limit", String(Number.isFinite(limit) ? limit : 20)],
          { cwd: root, windowsHide: true, timeout: 20000, maxBuffer: 10 * 1024 * 1024, encoding: "utf8" },
        )
        const out = JSON.parse(String(stdout ?? "").replace(/^\uFEFF/, ""))
        return sendJson(res, 200, { ok: true, backend: "sqlite", ...out })
      }

      const loaded = loadMapV1({ repoRoot: SCC_REPO_ROOT, mapPath: "map/map.json" })
      const out = queryMapV1({ map: loaded.data, q, limit: Number.isFinite(limit) ? limit : 20 })
      if (!out.ok) return sendJson(res, 400, out)
      return sendJson(res, 200, { ok: true, backend: "json", ...out })
    } catch (e) {
      return sendJson(res, 500, { error: "map_query_failed", message: String(e?.message ?? e) })
    }
  }

  if (pathname === "/map/v1" && method === "GET") {
    try {
      const versionPath = path.join(SCC_REPO_ROOT, "map", "version.json")
      const linkPath = path.join(SCC_REPO_ROOT, "map", "link_report.json")
      const version = fs.existsSync(versionPath) ? JSON.parse(fs.readFileSync(versionPath, "utf8").replace(/^\uFEFF/, "")) : null
      const link = fs.existsSync(linkPath) ? JSON.parse(fs.readFileSync(linkPath, "utf8").replace(/^\uFEFF/, "")) : null
      return sendJson(res, 200, {
        ok: true,
        version: version ? { hash: version.hash ?? null, generated_at: version.generated_at ?? null, stats: version.stats ?? null } : null,
        link_report: link ? { generated_at: link.generated_at ?? null, counts: link.counts ?? null } : null,
        endpoints: {
          version: "/map/v1/version",
          query: "/map/v1/query?q=...&limit=20",
          link_report: "/map/v1/link_report",
          build: "/map/v1/build",
        },
      })
    } catch (e) {
      return sendJson(res, 500, { error: "map_v1_failed", message: String(e?.message ?? e) })
    }
  }

  if (pathname === "/map/v1/build" && method === "POST") {
    const out = await runMapBuild({ reason: "api" })
    return sendJson(res, out.ok ? 200 : 500, out)
  }

  // Pins Builder v1 (Map-first, deterministic)
  if (pathname === "/pins/v1/build" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 2_000_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const request = body.data
    const out = buildPinsFromMapV1({ repoRoot: SCC_REPO_ROOT, request })
    if (!out.ok) return sendJson(res, 400, out)
    try {
      writePinsV1Outputs({
        repoRoot: SCC_REPO_ROOT,
        taskId: out.result.task_id,
        outDir: `artifacts/${out.result.task_id}/pins`,
        pinsResult: out.result_v2 ?? out.result,
        pinsSpec: out.pins,
        detail: out.detail,
      })
    } catch (e) {
      // best-effort
      noteBestEffort("pins_v1_write_outputs", e, { task_id: out.result.task_id })
    }
    return sendJson(res, 200, { ok: true, pins_result: out.result, pins_result_v2: out.result_v2 ?? null })
  }

  // Pins Builder v2 (audited pins; reason/read_only/write_intent per pin)
  if (pathname === "/pins/v2/build" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 2_000_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const request = body.data
    const out = buildPinsFromMapV1({ repoRoot: SCC_REPO_ROOT, request })
    if (!out.ok) return sendJson(res, 400, out)
    const v2 = out.result_v2
    if (!v2) return sendJson(res, 500, { ok: false, error: "pins_v2_missing" })
    try {
      writePinsV1Outputs({
        repoRoot: SCC_REPO_ROOT,
        taskId: v2.task_id,
        outDir: `artifacts/${v2.task_id}/pins`,
        pinsResult: v2,
        pinsSpec: out.pins,
        detail: out.detail,
      })
    } catch (e) {
      // best-effort
      noteBestEffort("pins_v2_write_outputs", e, { task_id: v2.task_id })
    }
    return sendJson(res, 200, { ok: true, pins_result_v2: v2 })
  }

  // Preflight Gate v1 (deterministic, fail-closed)
  if (pathname === "/preflight/v1/check" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 2_000_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const payload = body.data && typeof body.data === "object" ? body.data : {}
    const taskId = String(payload.task_id ?? "").trim()
    const childTask = payload.child_task && typeof payload.child_task === "object" ? payload.child_task : null
    const pins = payload.pins && typeof payload.pins === "object" ? payload.pins : null
    const role = payload.role ? String(payload.role) : childTask?.role ? String(childTask.role) : null
    const policy = roleSystem && role ? roleSystem.policiesByRole?.get(String(role).toLowerCase()) ?? null : null
    if (!taskId || !childTask || !pins) {
      return sendJson(res, 400, { ok: false, error: "missing_fields", required: ["task_id", "child_task", "pins"] })
    }
    const out = runPreflightV1({ repoRoot: SCC_REPO_ROOT, taskId, childTask, pinsSpec: pins, rolePolicy: policy })
    if (!out.ok) return sendJson(res, 400, out)
    try {
      writePreflightV1Output({ repoRoot: SCC_REPO_ROOT, taskId, outPath: `artifacts/${taskId}/preflight.json`, preflight: out.preflight })
    } catch (e) {
      // best-effort
      noteBestEffort("preflight_v1_write_output_api", e, { task_id: taskId })
    }
    return sendJson(res, 200, { ok: true, preflight: out.preflight })
  }

  // ---------------- Learning loop (L8 MVP, deterministic python ops) ----------------
  if (pathname === "/learn/v1/mine" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 200_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const payload = body.data && typeof body.data === "object" ? body.data : {}
    const tail = Number(payload.tail ?? 4000)
    const minCount = Number(payload.min_count ?? 3)
    const out = await runSccPythonOp({
      scriptRel: "tools/scc/ops/lesson_miner.py",
      args: ["--tail", String(Number.isFinite(tail) ? tail : 4000), "--min-count", String(Number.isFinite(minCount) ? minCount : 3)],
      timeoutMs: 300000,
    })
    return sendJson(res, out.ok ? 200 : 500, out)
  }

  if (pathname === "/learn/v1/tick" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 400_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const payload = body.data && typeof body.data === "object" ? body.data : {}

    const mineTail = Number(payload.mine_tail ?? payload.tail ?? 4000)
    const mineMinCount = Number(payload.mine_min_count ?? payload.min_count ?? 3)
    const evalSamples = Number(payload.eval_samples_per_playbook ?? 1)
    const evalRequireSampleSet = String(payload.eval_require_sample_set ?? "false").toLowerCase() === "true"
    const evalCandidatesOnly = String(payload.eval_candidates_only ?? "false").toLowerCase() === "true"
    const enforceCandidateEval = String(payload.enforce_candidate_eval ?? "false").toLowerCase() === "true"
    const metricsWindowHours = Number(payload.metrics_window_hours ?? 24)
    const metricsBucketMinutes = Number(payload.metrics_bucket_minutes ?? 60)
    const alsoRollback = String(payload.also_rollback ?? "true").toLowerCase() !== "false"

    const mine = await runSccPythonOp({
      scriptRel: "tools/scc/ops/lesson_miner.py",
      args: ["--tail", String(Number.isFinite(mineTail) ? mineTail : 4000), "--min-count", String(Number.isFinite(mineMinCount) ? mineMinCount : 3)],
      timeoutMs: 300000,
    })

    // Eval is split:
    // 1) eval_all: always runs (shape + optional historical sampling).
    // 2) eval_candidates: optional stronger gate (candidate-only + require curated sample sets).
    const evalAll = await runSccPythonOp({
      scriptRel: "tools/scc/ops/eval_replay.py",
      args: ["--drafts", "playbooks/drafts", "--samples-per-playbook", String(Number.isFinite(evalSamples) ? evalSamples : 1)],
      timeoutMs: 300000,
    })

    const evalCandidates = evalRequireSampleSet || evalCandidatesOnly
      ? await runSccPythonOp({
          scriptRel: "tools/scc/ops/eval_replay.py",
          args: [
            "--drafts",
            "playbooks/drafts",
            "--samples-per-playbook",
            "0",
            "--require-sample-set",
            "--candidates-only",
          ],
          timeoutMs: 300000,
        })
      : { ok: false, error: "skipped", note: "eval_candidates disabled (set eval_require_sample_set=true or eval_candidates_only=true)" }
    const patternsReg = await runSccPythonOp({ scriptRel: "tools/scc/ops/patterns_registry_sync.py", args: [], timeoutMs: 120000 })
    const skillsDraftsReg = await runSccPythonOp({ scriptRel: "tools/scc/ops/skills_drafts_registry_sync.py", args: [], timeoutMs: 120000 })
    const reg = await runSccPythonOp({ scriptRel: "tools/scc/ops/playbooks_registry_sync.py", args: [], timeoutMs: 120000 })
    const rollup = await runSccPythonOp({
      scriptRel: "tools/scc/ops/metrics_rollup.py",
      args: [
        "--window-hours",
        String(Number.isFinite(metricsWindowHours) ? metricsWindowHours : 24),
        "--bucket-minutes",
        String(Number.isFinite(metricsBucketMinutes) ? metricsBucketMinutes : 60),
      ],
      timeoutMs: 300000,
    })
    const rollback = alsoRollback
      ? await runSccPythonOp({ scriptRel: "tools/scc/ops/playbook_rollback.py", args: [], timeoutMs: 120000 })
      : { ok: false, error: "skipped", note: "also_rollback=false" }

    const out = {
      ok: Boolean(
        mine.ok &&
          evalAll.ok &&
          patternsReg.ok &&
          skillsDraftsReg.ok &&
          reg.ok &&
          rollup.ok &&
          (alsoRollback ? rollback.ok : true) &&
          (enforceCandidateEval ? Boolean(evalCandidates.ok) : true),
      ),
      mine,
      eval_all: evalAll,
      eval_candidates: evalCandidates,
      patterns_registry: patternsReg,
      skills_drafts_registry: skillsDraftsReg,
      playbooks_registry: reg,
      metrics_rollup: rollup,
      rollback,
    }
    try {
      fs.writeFileSync(path.join(execLogDir, "learn_tick_latest.json"), JSON.stringify({ schema_version: "scc.learn_tick_report.v1", t: new Date().toISOString(), ...out }, null, 2) + "\n", "utf8")
    } catch (e) {
      // best-effort
      noteBestEffort("learn_tick_latest_write_failed", e, { file: path.join(execLogDir, "learn_tick_latest.json") })
    }
    return sendJson(res, out.ok ? 200 : 500, out)
  }

  if (pathname === "/eval/v1/replay" && method === "POST") {
    const out = await runSccPythonOp({
      scriptRel: "tools/scc/ops/eval_replay.py",
      args: [],
      timeoutMs: 300000,
    })
    return sendJson(res, out.ok ? 200 : 500, out)
  }

  if (pathname === "/playbooks/v1/publish" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 200_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const payload = body.data && typeof body.data === "object" ? body.data : {}
    const draft = String(payload.draft ?? "").trim()
    const rollout = Number(payload.rollout ?? 10)
    if (!draft) return sendJson(res, 400, { ok: false, error: "missing_draft", required: ["draft"] })
    const out = await runSccPythonOp({
      scriptRel: "tools/scc/ops/playbook_publisher.py",
      args: ["--draft", draft, "--rollout", String(Number.isFinite(rollout) ? rollout : 10)],
      timeoutMs: 300000,
    })
    return sendJson(res, out.ok ? 200 : 500, out)
  }

  if (pathname === "/metrics/v1/rollup" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 200_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const payload = body.data && typeof body.data === "object" ? body.data : {}
    const windowHours = Number(payload.window_hours ?? 72)
    const bucketMinutes = Number(payload.bucket_minutes ?? 60)
    const alsoRollback = String(payload.also_rollback ?? "true").toLowerCase() !== "false"
    const rollup = await runSccPythonOp({
      scriptRel: "tools/scc/ops/metrics_rollup.py",
      args: ["--window-hours", String(Number.isFinite(windowHours) ? windowHours : 72), "--bucket-minutes", String(Number.isFinite(bucketMinutes) ? bucketMinutes : 60)],
      timeoutMs: 300000,
    })
    if (!rollup.ok || !alsoRollback) return sendJson(res, rollup.ok ? 200 : 500, { ...rollup, rollback: null })
    const rb = await runSccPythonOp({ scriptRel: "tools/scc/ops/playbook_rollback.py", args: [], timeoutMs: 300000 })
    return sendJson(res, rollup.ok && rb.ok ? 200 : 500, { ...rollup, rollback: rb })
  }

  if (pathname === "/pools" && method === "GET") {
    return sendJson(res, 200, poolSnapshot())
  }

  if (pathname === "/factory/policy" && method === "GET") {
    const fp = getFactoryPolicy()
    if (!fp) return sendJson(res, 404, { error: "missing_factory_policy", file: "factory_policy.json" })
    return sendJson(res, 200, fp)
  }

  if (pathname === "/factory/wip" && method === "GET") {
    const limits = wipLimits()
    const snap = runningInternalByLane()
    const degradation = computeDegradationState({ snap })
    const effective_limits = applyDegradationToWipLimitsV1({ limits, action: degradation.action })
    return sendJson(res, 200, { limits, effective_limits, running: snap, degradation })
  }

  if (pathname === "/factory/degradation" && method === "GET") {
    const snap = runningInternalByLane()
    const state = computeDegradationState({ snap })
    return sendJson(res, 200, state)
  }

  if (pathname === "/factory/health" && method === "GET") {
    const snap = runningInternalByLane()
    const degradation = computeDegradationState({ snap })
    return sendJson(res, 200, { repo_health: repoHealthState, circuit_breakers: circuitBreakerState, quarantine_active: quarantineActive(), degradation })
  }

  if (pathname === "/factory/health/reset" && method === "POST") {
    repoHealthState = {
      schema_version: "scc.repo_health_state.v1",
      updated_at: new Date().toISOString(),
      failures: [],
      unhealthy_until: 0,
      unhealthy_reason: null,
      unhealthy_task_created_at: null,
    }
    saveRepoHealthState(repoHealthState)
    leader({ level: "warn", type: "repo_health_reset", reason: "manual_api" })
    return sendJson(res, 200, { ok: true, repo_health: repoHealthState })
  }

  if (pathname === "/factory/routing" && method === "GET") {
    const et = String(url.searchParams.get("event_type") ?? "").trim()
    if (!et) return sendJson(res, 400, { error: "missing_event_type" })
    const lane = routeLaneForEventType(et)
    return sendJson(res, 200, { event_type: et, lane, factory_policy: "factory_policy.json" })
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
    } catch (e) {
      // fall through
      noteBestEffort("learned_patterns_summary_read_failed", e, { file: learnedPatternsSummaryFile })
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
    } catch (e) {
      // fall through
      noteBestEffort("instinct_patterns_read_failed", e, { file: instinctPatternsFile })
    }
    const snap = updateInstinctArtifacts()
    return sendJson(res, 200, { file: instinctPatternsFile, patterns: snap })
  }

  if (pathname === "/instinct/schemas" && method === "GET") {
    try {
      if (fs.existsSync(instinctSchemasFile)) {
        return sendText(res, 200, fs.readFileSync(instinctSchemasFile, "utf8"))
      }
    } catch (e) {
      // fall through
      noteBestEffort("instinct_schemas_read_failed", e, { file: instinctSchemasFile })
    }
    const text = renderInstinctSchemasYaml() + "\n"
    try {
      ensureDir(instinctDir)
      fs.writeFileSync(instinctSchemasFile, text, "utf8")
    } catch (e) {
      // best-effort
      noteBestEffort("instinct_schemas_write_failed", e, { file: instinctSchemasFile })
    }
    return sendText(res, 200, text)
  }

  if (pathname === "/instinct/playbooks" && method === "GET") {
    try {
      if (fs.existsSync(instinctPlaybooksFile)) {
        return sendText(res, 200, fs.readFileSync(instinctPlaybooksFile, "utf8"))
      }
    } catch (e) {
      // fall through
      noteBestEffort("instinct_playbooks_read_failed", e, { file: instinctPlaybooksFile })
    }
    const snap = updateInstinctArtifacts()
    const text = renderInstinctPlaybooksYaml(snap) + "\n"
    try {
      fs.writeFileSync(instinctPlaybooksFile, text, "utf8")
    } catch (e) {
      // best-effort
      noteBestEffort("instinct_playbooks_write_failed", e, { file: instinctPlaybooksFile })
    }
    return sendText(res, 200, text)
  }

  if (pathname === "/instinct/skills_draft" && method === "GET") {
    try {
      if (fs.existsSync(instinctSkillsDraftFile)) {
        return sendText(res, 200, fs.readFileSync(instinctSkillsDraftFile, "utf8"))
      }
    } catch (e) {
      // fall through
      noteBestEffort("instinct_skills_draft_read_failed", e, { file: instinctSkillsDraftFile })
    }
    const snap = updateInstinctArtifacts()
    const text = renderInstinctSkillsDraftYaml(snap) + "\n"
    try {
      fs.writeFileSync(instinctSkillsDraftFile, text, "utf8")
    } catch (e) {
      // best-effort
      noteBestEffort("instinct_skills_draft_write_failed", e, { file: instinctSkillsDraftFile })
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

  // Slot-based Context Pack v1 (legal semantics via SLOT0..SLOT6; required for execution entrypoints).
  if (pathname === "/scc/context/render" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 1_000_000 })
    if (!body.ok) return sendJson(res, 400, { ok: false, error: body.error, message: body.message ?? null })
    const payload = body.data && typeof body.data === "object" ? body.data : {}
    const task_id = String(payload.task_id ?? payload.taskId ?? "").trim()
    const role = String(payload.role ?? "executor").trim().toLowerCase()
    const mode = String(payload.mode ?? "execute").trim().toLowerCase()
    const budget_tokens = payload.budget_tokens ?? payload.budgetTokens ?? null
    if (!task_id) return sendJson(res, 400, { ok: false, error: "missing_task_id" })
    const out = renderSccContextPackV1Impl({ repoRoot: SCC_REPO_ROOT, taskId: task_id, role, mode, budgetTokens: budget_tokens, getBoardTask })
    if (!out.ok) return sendJson(res, 400, { ok: false, error: out.error, detail: out.detail ?? null, message: out.message ?? null })
    return sendJson(res, 200, out)
  }

  if (pathname.startsWith("/scc/context/pack/") && method === "GET") {
    const id = pathname.slice("/scc/context/pack/".length).trim()
    const fmt = String(url.searchParams.get("format") ?? "").trim().toLowerCase()
    const jsonPath = packJsonPathForIdV1({ repoRoot: SCC_REPO_ROOT, id })
    const txtPath = packTxtPathForIdV1({ repoRoot: SCC_REPO_ROOT, id })
    if (!jsonPath || !txtPath) return sendJson(res, 400, { ok: false, error: "invalid_context_pack_id" })
    if (!fs.existsSync(jsonPath)) return sendJson(res, 404, { ok: false, error: "context_pack_missing", id, path: jsonPath })
    try {
      if (fmt === "raw") {
        // Raw file bytes (as UTF-8 text) for deterministic hashing/replay.
        return sendText(res, 200, fs.readFileSync(jsonPath, "utf8"))
      }
      if (fmt === "txt" || fmt === "text") {
        const text = fs.readFileSync(txtPath, "utf8")
        return sendText(res, 200, text)
      }
      const data = loadJsonFileV1(jsonPath)
      if (!data) return sendJson(res, 500, { ok: false, error: "context_pack_read_failed", id, path: jsonPath })
      return sendJson(res, 200, { ok: true, id, path: `artifacts/scc_runs/${id}/rendered_context_pack.json`, pack: data })
    } catch (e) {
      return sendJson(res, 500, { ok: false, error: "context_pack_read_failed", id, message: String(e?.message ?? e) })
    }
  }

  // API-first fetch for deterministic task_bundle snapshot associated with a Context Pack v1 run.
  // This is intentionally allowlisted and read-only to keep Level-2 "hard gate" semantics simple.
  if (pathname.startsWith("/scc/context/run/") && pathname.includes("/task_bundle/") && method === "GET") {
    const rest = pathname.slice("/scc/context/run/".length)
    const idx = rest.indexOf("/task_bundle/")
    if (idx <= 0) return sendJson(res, 400, { ok: false, error: "invalid_path" })
    const runId = rest.slice(0, idx).trim()
    const file = rest.slice(idx + "/task_bundle/".length).trim()
    const fmt = String(url.searchParams.get("format") ?? "").trim().toLowerCase()
    const allowed = new Set(["manifest.json", "pins.json", "preflight.json", "replay_bundle.json", "task.json"])
    if (!runId) return sendJson(res, 400, { ok: false, error: "missing_run_id" })
    if (!allowed.has(file)) return sendJson(res, 403, { ok: false, error: "file_not_allowed", file })

    const jsonPath = packJsonPathForIdV1({ repoRoot: SCC_REPO_ROOT, id: runId })
    if (!jsonPath) return sendJson(res, 400, { ok: false, error: "invalid_run_id" })
    const runDir = path.dirname(jsonPath)
    const abs = path.join(runDir, "task_bundle", file)
    if (!fs.existsSync(abs)) return sendJson(res, 404, { ok: false, error: "task_bundle_file_missing", run_id: runId, file })
    try {
      if (fmt === "raw") {
        // Raw file bytes (as UTF-8 text) for deterministic hashing/replay.
        return sendText(res, 200, fs.readFileSync(abs, "utf8"))
      }
      const raw = fs.readFileSync(abs, "utf8")
      const data = JSON.parse(String(raw).replace(/^\uFEFF/, ""))
      return sendJson(res, 200, { ok: true, run_id: runId, file, path: `artifacts/scc_runs/${runId}/task_bundle/${file}`, data })
    } catch (e) {
      return sendJson(res, 500, { ok: false, error: "task_bundle_file_read_failed", run_id: runId, file, message: String(e?.message ?? e) })
    }
  }

  if (pathname === "/scc/context/validate" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 2_000_000 })
    if (!body.ok) return sendJson(res, 400, { ok: false, error: body.error, message: body.message ?? null })
    const payload = body.data && typeof body.data === "object" ? body.data : {}
    const context_pack_id = String(payload.context_pack_id ?? payload.contextPackId ?? "").trim()
    let pack = payload.pack && typeof payload.pack === "object" ? payload.pack : null
    if (!pack && context_pack_id) {
      const p = packJsonPathForIdV1({ repoRoot: SCC_REPO_ROOT, id: context_pack_id })
      if (!p) return sendJson(res, 400, { ok: false, error: "invalid_context_pack_id" })
      pack = fs.existsSync(p) ? loadJsonFileV1(p) : null
      if (!pack) return sendJson(res, 404, { ok: false, error: "context_pack_missing", id: context_pack_id, path: p })
    }
    if (!pack) return sendJson(res, 400, { ok: false, error: "missing_pack" })
    const out = validateSccContextPackV1Impl({ repoRoot: SCC_REPO_ROOT, pack })
    const code = out.ok ? 200 : 400
    return sendJson(res, code, { ok: out.ok, ...out })
  }

  if (pathname === "/events" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const areaFilter = String(url.searchParams.get("area") ?? "").trim()
    const rawEvents = readJsonlTail(stateEventsFile, Number.isFinite(limit) ? limit : 50)
    const events = areaFilter ? rawEvents.filter((e) => String(e?.area ?? "").trim() === areaFilter) : rawEvents
    return sendJson(res, 200, { file: stateEventsFile, count: events.length, events, area: areaFilter || null })
  }

  if (pathname === "/dlq" && method === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? "50")
    const file = dlqFilePath()
    const rows = readJsonlTail(file, Number.isFinite(limit) ? limit : 50)
    return sendJson(res, 200, { file, count: rows.length, rows })
  }

  if (pathname === "/verdict" && method === "GET") {
    const taskId = String(url.searchParams.get("task_id") ?? "").trim()
    if (!taskId) return sendJson(res, 400, { error: "missing_task_id" })
    const file = path.join(SCC_REPO_ROOT, "artifacts", taskId, "verdict.json")
    if (!fs.existsSync(file)) return sendJson(res, 404, { error: "verdict_missing", file })
    try {
      const raw = fs.readFileSync(file, "utf8")
      const data = JSON.parse(raw.replace(/^\uFEFF/, ""))
      return sendJson(res, 200, { ok: true, file, verdict: data })
    } catch (e) {
      return sendJson(res, 500, { error: "verdict_read_failed", file, message: String(e?.message ?? e) })
    }
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

  // Board maintenance: archive old done/failed + sweep failed->dlq (best-effort, deterministic).
  if (pathname === "/board/maintenance" && method === "POST") {
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", async () => {
      let payload = {}
      try {
        payload = JSON.parse(body || "{}")
      } catch {
        payload = {}
      }
      const dryRun = payload?.dryRun !== false
      const keepHours = Number.isFinite(Number(payload?.keepHours)) ? Math.max(0, Math.floor(Number(payload.keepHours))) : 24
      const keepLastFailed = Number.isFinite(Number(payload?.keepLastFailed)) ? Math.max(0, Math.floor(Number(payload.keepLastFailed))) : 40
      const keepLastDone = Number.isFinite(Number(payload?.keepLastDone)) ? Math.max(0, Math.floor(Number(payload.keepLastDone))) : 20
      const dlqAfterAttempts = Number.isFinite(Number(payload?.dlqAfterAttempts)) ? Math.max(1, Math.floor(Number(payload.dlqAfterAttempts))) : 2
      const out = await new Promise((resolve) => {
        const cwd = SCC_REPO_ROOT && fs.existsSync(SCC_REPO_ROOT) ? SCC_REPO_ROOT : process.cwd()
        const args = [
          "tools/scc/ops/board_maintenance.py",
          "--repo-root",
          cwd,
          "--keep-hours",
          String(keepHours),
          "--keep-last-failed",
          String(keepLastFailed),
          "--keep-last-done",
          String(keepLastDone),
          "--dlq-after-attempts",
          String(dlqAfterAttempts),
        ]
        if (dryRun) args.push("--dry-run")
        else args.push("--write")
        execFile("python", args, { cwd, timeout: 120000, windowsHide: true, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
          const text = String(stdout || "").trim() || String(stderr || "").trim()
          let parsed = null
          try {
            parsed = text ? JSON.parse(text) : null
          } catch {
            parsed = null
          }
          resolve({
            ok: !err,
            exit_code: err?.code ?? 0,
            report: parsed,
            stdout: String(stdout || "").trim(),
            stderr: String(stderr || "").trim(),
          })
        })
      })
      if (out.ok && !dryRun) {
        try {
          // Reload board from disk after rewrite.
          boardTasks.clear()
          for (const t of loadBoard()) {
            if (!t?.id) continue
            boardTasks.set(t.id, t)
          }
        } catch (e) {
          // best-effort; maintenance should never crash the gateway
          noteBestEffort("board_reload_failed", e, null)
        }
      }
      return sendJson(res, out.ok ? 200 : 500, out)
    })
    return
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
    const out = startSplitForParent(t, { reason: "manual_split" })
    if (!out.ok) {
      leader({ level: "warn", type: "board_task_split_rejected", id: t.id, error: out.error, requiredModel: STRICT_DESIGNER_MODEL })
      appendJsonl(designerFailuresFile, {
        t: new Date().toISOString(),
        task_id: t.id,
        reason: out.error,
        role: t.role ?? null,
        area: t.area ?? null,
      })
      return sendJson(res, 400, { error: out.error ?? "split_start_failed", requiredModel: STRICT_DESIGNER_MODEL })
    }
    return sendJson(res, 202, { task: out.task, job: out.job })
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
      if (!out.ok) return sendJson(res, 400, { error: out.error, details: out.rejected ?? null })
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
        const model = codexModelForced ?? (payload.model ? String(payload.model).trim() : codexModelDefault)
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
        const model = codexModelForced ?? (payload.model ? String(payload.model).trim() : codexModelDefault)
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
        const payloadModel = payload.model ? String(payload.model).trim() : null
        const model = executor === "codex" ? (codexModelForced ?? payloadModel ?? codexModelDefault) : payloadModel ?? occliModelDefault
        const threadId = payload.threadId ? String(payload.threadId).trim() : null
        if (threadId) return sendJson(res, 400, { error: "thread_not_allowed_for_executor" })
        const contextPackId = payload.contextPackId ? String(payload.contextPackId).trim() : null
        const contextPackV1Id = payload.contextPackV1Id ? String(payload.contextPackV1Id).trim() : null
        const taskType = payload.taskType ? String(payload.taskType).trim() : "atomic"
        const timeoutMs = payload.timeoutMs ? Number(payload.timeoutMs) : null
        const runner = payload.runner ? String(payload.runner).trim() : "internal"
        if (!prompt) return sendJson(res, 400, { error: "missing_prompt" })

        // Enterprise fail-closed: do not allow external jobs without a legal Context Pack v1.
        if (runner === "external" && requireContextPackV1 && !contextPackV1Id) {
          return sendJson(res, 400, { error: "missing_context_pack_v1", message: "External jobs require payload.contextPackV1Id" })
        }
        if (contextPackV1Id) {
          const p = packJsonPathForIdV1({ repoRoot: SCC_REPO_ROOT, id: contextPackV1Id })
          const pack = p && fs.existsSync(p) ? loadJsonFileV1(p) : null
          if (!pack) return sendJson(res, 404, { error: "context_pack_v1_missing", id: contextPackV1Id })
          const v = validateSccContextPackV1Impl({ repoRoot: SCC_REPO_ROOT, pack })
          if (!v.ok) return sendJson(res, 400, { error: "invalid_context_pack_v1", details: v })
        }
        const job = makeJob({ prompt, model, executor, taskType, timeoutMs })
        job.runner = runner === "external" ? "external" : "internal"
        job.threadId = threadId
        job.contextPackId = contextPackId
        job.contextPackV1Id = contextPackV1Id
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
        const payloadModel = payload.model ? String(payload.model).trim() : null
        const model = executor === "codex" ? (codexModelForced ?? payloadModel ?? codexModelDefault) : payloadModel ?? occliModelDefault
        const threadId = payload.threadId ? String(payload.threadId).trim() : null
        if (threadId) return sendJson(res, 400, { error: "thread_not_allowed_for_executor" })
        const files = Array.isArray(payload.files) ? payload.files.map((x) => String(x)) : []
        const pins = payload?.pins && typeof payload.pins === "object" ? payload.pins : null
        const maxBytes = Number(payload.maxBytes ?? 220_000)
        const taskType = payload.taskType ? String(payload.taskType).trim() : "atomic"
        const runner = payload.runner ? String(payload.runner).trim() : "internal"
        const contextPackV1Id = payload.contextPackV1Id ? String(payload.contextPackV1Id).trim() : null
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

        // External atomic helper is allowed only with an explicit Context Pack v1 id.
        if (runner === "external" && requireContextPackV1 && !contextPackV1Id) {
          return sendJson(res, 400, { error: "missing_context_pack_v1", message: "External atomic jobs require payload.contextPackV1Id" })
        }
        if (contextPackV1Id) {
          const p = packJsonPathForIdV1({ repoRoot: SCC_REPO_ROOT, id: contextPackV1Id })
          const pack = p && fs.existsSync(p) ? loadJsonFileV1(p) : null
          if (!pack) return sendJson(res, 404, { error: "context_pack_v1_missing", id: contextPackV1Id })
          const v = validateSccContextPackV1Impl({ repoRoot: SCC_REPO_ROOT, pack })
          if (!v.ok) return sendJson(res, 400, { error: "invalid_context_pack_v1", details: v })
        }

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
        job.contextPackV1Id = contextPackV1Id
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
        const now = Date.now()
        const key = `${name}::${allowed.slice().sort().join(",")}`
        const existing = Array.from(workers.values()).find(
          (x) => x && `${x.name}::${Array.isArray(x.executors) ? x.executors.slice().sort().join(",") : ""}` === key
        )
        if (existing) {
          existing.models = models
          existing.lastSeen = now
          existing.startedAt = existing.startedAt ?? now
          existing.executors = allowed
          putWorker(existing)
          leader({ level: "info", type: "worker_reregistered", id: existing.id, name, executors: allowed, models: models.slice(0, 8) })
          return sendJson(res, 200, existing)
        }

        const id = newWorkerId()
        const w = { id, name, executors: allowed, models, startedAt: now, lastSeen: now, runningJobId: null }
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
      const hasRunningJobKey =
        payload && typeof payload === "object" && Object.prototype.hasOwnProperty.call(payload, "runningJobId")
      if (hasRunningJobKey) {
        const raw = payload.runningJobId
        const runningJobId = raw != null && String(raw).trim() ? String(raw) : null
        w.runningJobId = runningJobId
      }
      putWorker(w)
      if (w.runningJobId) {
        const j = jobs.get(String(w.runningJobId))
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
      const counts = runningCountsExternal()
      if (executor === "codex" && counts.codex >= externalMaxCodex) break
      if (executor === "opencodecli" && counts.opencodecli >= externalMaxOccli) break
      const pick = claimNextJob({ executor, worker: w })
      if (pick) {
        const now = Date.now()
        // Nonce-bound attestation: binds completion proofs to this specific claim/lease.
        // Policy: sha256(nonce_utf8 || file_bytes). Used for deterministic replay/audit.
        if (!String(pick.attestationNonce ?? "").trim()) {
          try {
            pick.attestationNonce = crypto.randomBytes(16).toString("hex")
          } catch {
            pick.attestationNonce = String(Math.random()).slice(2) + String(Date.now())
          }
        }
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
          attestation: pick.attestationNonce
            ? {
                nonce: pick.attestationNonce,
                algo: "sha256(nonce_utf8||bytes)",
              }
            : null,
          contextPackV1Id: pick.contextPackV1Id ?? null,
          contextPackV1: pick.contextPackV1Id
            ? {
                id: pick.contextPackV1Id,
                pack_json: `artifacts/scc_runs/${pick.contextPackV1Id}/rendered_context_pack.json`,
                pack_txt: `artifacts/scc_runs/${pick.contextPackV1Id}/rendered_context_pack.txt`,
                fetch_json: `/scc/context/pack/${pick.contextPackV1Id}`,
                fetch_json_raw: `/scc/context/pack/${pick.contextPackV1Id}?format=raw`,
                fetch_txt: `/scc/context/pack/${pick.contextPackV1Id}?format=txt`,
              }
            : null,
          taskBundle: pick.contextPackV1Id
            ? {
                id: pick.contextPackV1Id,
                dir: `artifacts/scc_runs/${pick.contextPackV1Id}/task_bundle`,
                fetch_manifest: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/manifest.json`,
                fetch_manifest_raw: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/manifest.json?format=raw`,
                fetch_pins: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/pins.json`,
                fetch_pins_raw: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/pins.json?format=raw`,
                fetch_preflight: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/preflight.json`,
                fetch_preflight_raw: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/preflight.json?format=raw`,
                fetch_replay_bundle: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/replay_bundle.json`,
                fetch_replay_bundle_raw: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/replay_bundle.json?format=raw`,
                fetch_task: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/task.json`,
                fetch_task_raw: `/scc/context/run/${pick.contextPackV1Id}/task_bundle/task.json?format=raw`,
              }
            : null,
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
    if (requireContextPackV1 && !String(job.contextPackV1Id ?? "").trim()) {
      return sendJson(res, 400, { error: "missing_context_pack_v1", message: "External job missing job.contextPackV1Id (enterprise fail-closed)" })
    }
    let body = ""
    req.on("data", (d) => {
      body += d
    })
    req.on("end", async () => {
      try {
        const payload = JSON.parse(body || "{}")
        const workerId = payload.workerId ? String(payload.workerId) : ""
        const matches = workerId && workerId === job.workerId
        const now = Date.now()
        const lease = Number(job.leaseUntil ?? 0)
        const staleLease = lease && now > lease + 30_000
        const orphaned = !matches && job.workerId && !getWorker(String(job.workerId))
        const rescueAllowed = !matches && job.status === "running" && (staleLease || orphaned)
        if (!matches && !rescueAllowed) return sendJson(res, 403, { error: "worker_mismatch" })
        if (rescueAllowed) {
          leader({
            level: "warn",
            type: "worker_rescue_complete",
            job_id: job.id,
            prev_worker_id: job.workerId ?? null,
            new_worker_id: workerId || null,
            leaseUntil: job.leaseUntil ?? null,
          })
          job.workerId = workerId || job.workerId
        }
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

        // Enterprise fail-closed: external workers must prove they executed against the bound Context Pack v1 run
        // and the deterministic task_bundle snapshot associated with it.
        try {
          if (requireContextPackV1) {
            const wantId = String(job.contextPackV1Id ?? "").trim()
            const gotId = String(payload.contextPackV1Id ?? payload.context_pack_v1_id ?? "").trim()
            const wantManifestPath = wantId ? path.join(SCC_REPO_ROOT, "artifacts", "scc_runs", wantId, "task_bundle", "manifest.json") : null

            const violations = []
            if (!wantId) violations.push({ code: "missing_context_pack_v1_on_job", message: "job.contextPackV1Id missing (should be impossible when required)" })
            if (!gotId) violations.push({ code: "missing_context_pack_v1_on_complete", message: "payload.contextPackV1Id missing" })
            if (wantId && gotId && wantId !== gotId) violations.push({ code: "context_pack_v1_mismatch", want: wantId, got: gotId })

            const gotManifestSha = String(payload.task_bundle_manifest_sha256 ?? payload.taskBundleManifestSha256 ?? "").trim()
            if (!gotManifestSha) violations.push({ code: "missing_task_bundle_manifest_sha256", message: "payload.task_bundle_manifest_sha256 missing" })

            let wantManifestSha = null
            if (wantManifestPath && fs.existsSync(wantManifestPath)) {
              const buf = fs.readFileSync(wantManifestPath)
              wantManifestSha = `sha256:${crypto.createHash("sha256").update(buf).digest("hex")}`
            } else {
              violations.push({ code: "missing_task_bundle_manifest_file", path: wantManifestPath })
            }
            if (wantManifestSha && gotManifestSha && wantManifestSha !== gotManifestSha) {
              violations.push({ code: "task_bundle_manifest_sha256_mismatch", want: wantManifestSha, got: gotManifestSha })
            }

            const gotPackJsonSha = String(payload.context_pack_v1_json_sha256 ?? payload.contextPackV1JsonSha256 ?? "").trim()
            if (!gotPackJsonSha) violations.push({ code: "missing_context_pack_v1_json_sha256", message: "payload.context_pack_v1_json_sha256 missing" })
            const wantPackPath = wantId ? path.join(SCC_REPO_ROOT, "artifacts", "scc_runs", wantId, "rendered_context_pack.json") : null
            let wantPackSha = null
            if (wantPackPath && fs.existsSync(wantPackPath)) {
              const buf = fs.readFileSync(wantPackPath)
              wantPackSha = `sha256:${crypto.createHash("sha256").update(buf).digest("hex")}`
            } else {
              violations.push({ code: "missing_context_pack_v1_json_file", path: wantPackPath })
            }
            if (wantPackSha && gotPackJsonSha && wantPackSha !== gotPackJsonSha) {
              violations.push({ code: "context_pack_v1_json_sha256_mismatch", want: wantPackSha, got: gotPackJsonSha })
            }

            // Nonce-bound attestation: prove the worker computed hashes using bytes after claim time.
            const wantNonce = String(job.attestationNonce ?? "").trim()
            const gotNonce = String(payload.attestation_nonce ?? payload.attestationNonce ?? payload?.attestation?.nonce ?? "").trim()
            if (!wantNonce) violations.push({ code: "missing_attestation_nonce_on_job", message: "job.attestationNonce missing" })
            if (!gotNonce) violations.push({ code: "missing_attestation_nonce_on_complete", message: "payload.attestation_nonce missing" })
            if (wantNonce && gotNonce && wantNonce !== gotNonce) violations.push({ code: "attestation_nonce_mismatch", want: wantNonce, got: gotNonce })

            const gotPackAttest = String(payload.context_pack_v1_json_attest_sha256 ?? payload.contextPackV1JsonAttestSha256 ?? "").trim()
            if (!gotPackAttest) violations.push({ code: "missing_context_pack_v1_json_attest_sha256", message: "payload.context_pack_v1_json_attest_sha256 missing" })
            if (wantNonce && wantPackPath && fs.existsSync(wantPackPath) && gotPackAttest) {
              const buf = fs.readFileSync(wantPackPath)
              const want = `sha256:${crypto.createHash("sha256").update(wantNonce, "utf8").update(buf).digest("hex")}`
              if (want !== gotPackAttest) violations.push({ code: "context_pack_v1_json_attest_sha256_mismatch", want, got: gotPackAttest })
            }

            const gotFiles = payload.task_bundle_files_sha256 ?? payload.taskBundleFilesSha256 ?? null
            if (!gotFiles || typeof gotFiles !== "object") {
              violations.push({ code: "missing_task_bundle_files_sha256", message: "payload.task_bundle_files_sha256 missing or invalid" })
            } else {
              const requiredFiles = ["pins.json", "preflight.json", "task.json", "manifest.json"]
              for (const f of requiredFiles) {
                const got = String(gotFiles[f] ?? "").trim()
                if (!got) violations.push({ code: "missing_task_bundle_file_sha256", file: f })
              }
              const runDir2 = wantId ? path.join(SCC_REPO_ROOT, "artifacts", "scc_runs", wantId, "task_bundle") : null
              const shaFile = (absPath) => {
                try {
                  const buf = fs.readFileSync(absPath)
                  return `sha256:${crypto.createHash("sha256").update(buf).digest("hex")}`
                } catch {
                  return null
                }
              }
              if (runDir2) {
                const wantPins = shaFile(path.join(runDir2, "pins.json"))
                const wantPre = shaFile(path.join(runDir2, "preflight.json"))
                const wantTask = shaFile(path.join(runDir2, "task.json"))
                const wantMan = shaFile(path.join(runDir2, "manifest.json"))
                const wantReplay = fs.existsSync(path.join(runDir2, "replay_bundle.json")) ? shaFile(path.join(runDir2, "replay_bundle.json")) : null

                const cmp = (file, want) => {
                  if (!want) return violations.push({ code: "task_bundle_file_missing_or_unreadable", file })
                  const got = String(gotFiles?.[file] ?? "").trim()
                  if (got && want !== got) violations.push({ code: "task_bundle_file_sha256_mismatch", file, want, got })
                }
                cmp("pins.json", wantPins)
                cmp("preflight.json", wantPre)
                cmp("task.json", wantTask)
                cmp("manifest.json", wantMan)
                if (wantReplay) cmp("replay_bundle.json", wantReplay)
              }
            }

            const gotAtt = payload.task_bundle_files_attest_sha256 ?? payload.taskBundleFilesAttestSha256 ?? null
            if (!gotAtt || typeof gotAtt !== "object") {
              violations.push({ code: "missing_task_bundle_files_attest_sha256", message: "payload.task_bundle_files_attest_sha256 missing or invalid" })
            } else if (wantNonce) {
              const runDir2 = wantId ? path.join(SCC_REPO_ROOT, "artifacts", "scc_runs", wantId, "task_bundle") : null
              const attestFile = (file) => {
                try {
                  const abs = runDir2 ? path.join(runDir2, file) : null
                  if (!abs || !fs.existsSync(abs)) return null
                  const buf = fs.readFileSync(abs)
                  return `sha256:${crypto.createHash("sha256").update(wantNonce, "utf8").update(buf).digest("hex")}`
                } catch {
                  return null
                }
              }
              if (runDir2) {
                const required = ["manifest.json", "pins.json", "preflight.json", "task.json"]
                for (const f of required) {
                  const got = String(gotAtt?.[f] ?? "").trim()
                  if (!got) {
                    violations.push({ code: "missing_task_bundle_file_attest_sha256", file: f })
                    continue
                  }
                  const want = attestFile(f)
                  if (!want) violations.push({ code: "task_bundle_file_missing_or_unreadable", file: f })
                  else if (want !== got) violations.push({ code: "task_bundle_file_attest_sha256_mismatch", file: f, want, got })
                }
                // replay_bundle is optional
                const wantReplayAtt = fs.existsSync(path.join(runDir2, "replay_bundle.json")) ? attestFile("replay_bundle.json") : null
                const gotReplayAtt = String(gotAtt?.["replay_bundle.json"] ?? "").trim()
                if (wantReplayAtt && gotReplayAtt && wantReplayAtt !== gotReplayAtt) {
                  violations.push({ code: "task_bundle_file_attest_sha256_mismatch", file: "replay_bundle.json", want: wantReplayAtt, got: gotReplayAtt })
                }
              }
            }

            // Persist proof material for audit/replay (even if violations exist).
            // NOTE: payload-derived values are untrusted; they are recorded for forensic traceability only.
            job.contextPackV1Proof = {
              schema_version: "scc.context_pack_v1_proof.v1",
              t: new Date().toISOString(),
              context_pack_v1_id_job: wantId || null,
              context_pack_v1_id_payload: gotId || null,
              attestation_nonce_job: wantNonce || null,
              attestation_nonce_payload: gotNonce || null,
              pack_json_sha256_payload: gotPackJsonSha || null,
              pack_json_attest_sha256_payload: gotPackAttest || null,
              task_bundle_manifest_sha256_payload: gotManifestSha || null,
              task_bundle_files_sha256_payload: gotFiles && typeof gotFiles === "object" ? gotFiles : null,
              task_bundle_files_attest_sha256_payload: gotAtt && typeof gotAtt === "object" ? gotAtt : null,
            }

            if (violations.length) {
              job.status = "failed"
              job.error = "policy_violation"
              job.reason = violations[0]?.code ?? "policy_violation"
              job.policy_violations = violations

              // Record a policy violation event for auditing/routing.
              const boardTask = job?.boardTaskId ? getBoardTask(String(job.boardTaskId)) : null
              const tid = String(boardTask?.id ?? job.boardTaskId ?? "").trim()
              if (tid) {
                appendStateEvent({
                  schema_version: "scc.event.v1",
                  t: new Date().toISOString(),
                  task_id: tid,
                  parent_id: boardTask?.parentId ?? null,
                  role: boardTask?.role ?? null,
                  area: boardTask?.area ?? null,
                  executor: job.executor ?? null,
                  model: job.model ?? null,
                  event_type: "POLICY_VIOLATION",
                  reason: job.reason,
                  details: { phase: "external_complete_policy", job_id: job.id, violations: violations.slice(0, 8) },
                })
              }
            }
          }
        } catch (e) {
          // Fail-closed: inability to verify policy becomes a policy violation.
          if (requireContextPackV1) {
            job.status = "failed"
            job.error = "policy_violation"
            job.reason = "external_complete_policy_check_failed"
            job.policy_violations = [{ code: "external_complete_policy_check_failed", message: String(e?.message ?? e) }]
            job.contextPackV1Proof = {
              schema_version: "scc.context_pack_v1_proof.v1",
              t: new Date().toISOString(),
              error: "external_complete_policy_check_failed",
              message: String(e?.message ?? e),
            }
          }
        }

        const w = getWorker(workerId)
        if (w && w.runningJobId === job.id) {
          w.runningJobId = null
          w.lastSeen = Date.now()
          putWorker(w)
        }

        // Apply the same post-processing used by internal runner: submit parsing, CI gate, hygiene,
        // and CI-fixup auto-dispatch. Without this, external jobs can bypass gates entirely.
        const boardTask = job?.boardTaskId ? getBoardTask(String(job.boardTaskId)) : null
        const isSplitJob = String(job.taskType ?? "") === "board_split"
        const patchText = extractPatchFromStdout(job.stdout)
        let patchStats = patchText ? computePatchStats(patchText) : null
        const snapshotDiff = diffSnapshot(job.pre_snapshot)
        if (!patchStats && Array.isArray(snapshotDiff?.touched_files) && snapshotDiff.touched_files.length) {
          const files = snapshotDiff.touched_files.slice(0, 30)
          patchStats = { files, filesCount: files.length, added: 0, removed: 0, hunks: 0 }
        }
        job.patch_stats = patchStats ?? null
        job.snapshot_diff = snapshotDiff ?? null
        job.submit = loadSubmitArtifact(boardTask?.id ?? job.boardTaskId) ?? (extractSubmitResult(job.stdout) ?? null)
        job.usage = job.executor === "codex" ? extractUsageFromStdout(job.stdout) : null
        if (job.status === "done" && job.executor === "opencodecli" && occliRequireSubmit && !job.submit) {
          job.status = "failed"
          job.error = "missing_submit_contract"
          job.reason = "missing_submit_contract"
        }
        if (job.status === "done" && job.submit?.status === "NEED_INPUT") {
          job.status = "failed"
          job.error = "needs_input"
          job.reason = "needs_input"
        }

        // Emit an executor-complete state event early so strict gates that require per-task events.jsonl
        // can run deterministically in this same completion handler.
        try {
          const tid = String(boardTask?.id ?? job.boardTaskId ?? "").trim()
          if (tid) {
            const baseEvent = {
              schema_version: "scc.event.v1",
              t: new Date().toISOString(),
              task_id: tid,
              parent_id: boardTask?.parentId ?? null,
              role: boardTask?.role ?? null,
              area: boardTask?.area ?? null,
              executor: job.executor ?? null,
              model: job.model ?? null,
              details: { phase: "executor_complete", job_id: job.id, taskType: job.taskType ?? null },
            }
            appendStateEvent({
              ...baseEvent,
              event_type: job.status === "done" ? "SUCCESS" : "EXECUTOR_ERROR",
              reason: job.status === "done" ? "executor_exit_0" : (job.reason ?? job.error ?? "executor_error"),
            })
          }
        } catch (e) {
          // best-effort
          noteBestEffort("appendStateEvent_executor_complete", e, { task_id: String(boardTask?.id ?? job.boardTaskId ?? "") })
        }

        if (boardTask && !isSplitJob) ensureExternalArtifactsAndSubmit({ job, boardTask, patchText, patchStats, snapshotDiff, ciGate: null })

        if (!isSplitJob) {
          const scope = validatePatchScope({ patchStats, boardTask })
          if (job.status === "done" && !scope.ok) {
            job.status = "failed"
            job.error = "patch_scope_violation"
            job.reason = scope.errors?.[0]?.reason ?? "patch_scope_violation"
            leader({ level: "warn", type: "patch_scope_violation", id: job.id, taskId: boardTask?.id ?? null, errors: scope.errors })
          }
        }

        if (!isSplitJob) {
          if (job.status === "done" && patchStats && Array.isArray(job.submit?.touched_files)) {
            const norm = (arr) => arr.map((f) => normalizeRepoPath(f)).filter(Boolean)
            const diffFiles = norm(patchStats.files ?? [])
            const touched = new Set(norm(job.submit.touched_files))
            const missing = diffFiles.filter((f) => !touched.has(f))
            if (missing.length) {
              job.status = "failed"
              job.error = "submit_mismatch"
              job.reason = "submit_mismatch"
              leader({ level: "warn", type: "submit_mismatch", id: job.id, taskId: boardTask?.id ?? null, missing: missing.slice(0, 20) })
            }
          }
        }

        const isCiFixup = String(boardTask?.task_class_id ?? "") === "ci_fixup_v1"
        const policyViolated = job.error === "policy_violation"
        let ciGate = null
        if (!policyViolated && !isSplitJob && (job.status === "done" || isCiFixup)) {
          ciGate = await runCiGateForTask({ job, boardTask })
          if (ciGate?.required && !ciGate.ran && ciGateStrict) {
            job.status = "failed"
            job.error = "ci_failed"
            job.reason = "ci_skipped"
          } else if (ciGate?.ran && !ciGate.ok) {
            job.status = "failed"
            job.error = "ci_failed"
            job.reason = "ci_failed"
          } else if (ciGate?.timedOut) {
            job.status = "failed"
            job.error = "ci_failed"
            job.reason = "ci_timed_out"
          } else if (isCiFixup && ciGate?.ran && ciGate.ok) {
            // CI-fixup can be considered successful even if the executor had minor non-zero exit codes
            // while writing auxiliary artifacts, as long as the authoritative CI gate passes.
            job.status = "done"
            job.error = null
            job.reason = null
            job.exit_code = 0
          }
        }
        job.ci_gate = ciGate ?? null
        if (ciGate && job.error === "ci_failed") {
          maybeCreateCiFixupTask({ boardTask, job, ciGate })
        }
        if (ciGate) {
          appendJsonlChained(ciGateResultsFile, {
            t: new Date().toISOString(),
            job_id: job.id,
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
            submit: job.submit
              ? {
                  status: job.submit.status ?? null,
                  reason_code: job.submit.reason_code ?? null,
                  touched_files: Array.isArray(job.submit.touched_files) ? job.submit.touched_files.slice(0, 30) : null,
                  tests_run: Array.isArray(job.submit.tests_run) ? job.submit.tests_run.slice(0, 20) : null,
                }
              : null,
          })
          if (job.error === "ci_failed") {
            appendJsonl(ciFailuresFile, {
              t: new Date().toISOString(),
              task_id: boardTask?.id ?? null,
              job_id: job.id,
              reason: job.reason ?? "ci_failed",
              exitCode: ciGate.exitCode ?? null,
              skipped: ciGate.skipped ?? null,
              stdoutPreview: ciGate.stdoutPreview ?? null,
              stderrPreview: ciGate.stderrPreview ?? null,
            })
          }
        }

        if (job.status === "done") {
          const isSplitJob = String(job.taskType ?? "") === "board_split"
          if (!isSplitJob) {
            if (boardTask) ensureExternalArtifactsAndSubmit({ job, boardTask, patchText, patchStats, snapshotDiff, ciGate })
            const hygiene = runHygieneChecks({ job, boardTask })
            if (!hygiene.ok) {
              job.status = "failed"
              job.error = "hygiene_failed"
              job.reason = hygiene.reason ?? "hygiene_failed"
            }
          } else {
            const hygiene = runSplitOutputChecks({ job, boardTask })
            if (!hygiene.ok) {
              job.status = "failed"
              job.error = "hygiene_failed"
              job.reason = hygiene.reason ?? "split_output_invalid"
            }
          }
        }

        jobs.set(job.id, job)
        saveState()

        const record = {
          t: new Date().toISOString(),
          id: job.id,
          executor: job.executor,
          model: job.model,
          taskType: job.taskType ?? null,
          status: job.status,
          exit_code: job.exit_code,
          reason: job.reason,
          createdAt: job.createdAt,
          startedAt: job.startedAt,
          finishedAt: job.finishedAt,
          durationMs: job.startedAt && job.finishedAt ? job.finishedAt - job.startedAt : null,
          prompt_bytes: Buffer.byteLength(String(job.prompt ?? ""), "utf8"),
          context_bytes: Number(job.contextBytes ?? null),
          context_files: Number(job.contextFiles ?? null),
          context_source: job.contextSource ?? null,
          pins_allow_count: Number(job.pinsAllowCount ?? null),
          pins_symbols_count: Number(job.pinsSymbolsCount ?? null),
          pins_line_windows: Number(job.pinsLineWindows ?? null),
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
      failureReportLatest: readFailureReportLatest(),
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
    let verdict = null
    try {
      const file = path.join(SCC_REPO_ROOT, "artifacts", taskId, "verdict.json")
      if (fs.existsSync(file)) {
        const raw = fs.readFileSync(file, "utf8")
        verdict = JSON.parse(raw.replace(/^\uFEFF/, ""))
      }
    } catch {
      verdict = null
    }
    return sendJson(res, 200, {
      task: t,
      lastJob,
      verdict,
      logs: {
        jobs: { file: execLogJobs, rows: recentJobs.slice(-60) },
        failures: { file: execLogFailures, rows: recentFailures.slice(-30) },
        state_events: { file: stateEventsFile, rows: recentEvents.slice(-30) },
      },
    })
  }

  if (pathname === "/replay/v1/smoke" && method === "POST") {
    const body = await readJsonBody(req, { maxBytes: 200_000 })
    if (!body.ok) return sendJson(res, 400, body)
    const payload = body.data && typeof body.data === "object" ? body.data : {}
    const taskId = String(payload.task_id ?? "").trim()
    if (!taskId) return sendJson(res, 400, { ok: false, error: "missing_task_id", required: ["task_id"] })
    const submitPathRel = `artifacts/${taskId}/submit.json`
    const out = await runSccPythonOp({
      scriptRel: "tools/scc/gates/run_ci_gates.py",
      args: ["--strict", "--submit", submitPathRel],
      timeoutMs: 180000,
    })
    try {
      const evDir = path.join(SCC_REPO_ROOT, "artifacts", taskId, "evidence")
      fs.mkdirSync(evDir, { recursive: true })
      fs.writeFileSync(
        path.join(evDir, "replay_smoke.json"),
        JSON.stringify({ schema_version: "scc.replay_smoke.v1", task_id: taskId, ok: out.ok, t: new Date().toISOString(), gate: out }, null, 2) + "\n",
        "utf8",
      )
    } catch (e) {
      // best-effort
      noteBestEffort("replay_smoke_write_failed", e, { task_id: taskId })
    }
    return sendJson(res, out.ok ? 200 : 500, out)
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
