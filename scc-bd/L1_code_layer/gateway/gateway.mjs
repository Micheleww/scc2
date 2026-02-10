#!/usr/bin/env node
/**
 * SCC Gateway - 精简模块化版本
 * 基于17层分层架构
 */

import http from "node:http"
import { URL } from "node:url"
import process from "node:process"
import fs from "node:fs"
import path from "node:path"
import { createLogger } from "../../L16_observability_layer/logging/logger.mjs"
import { createJsonlErrorSink } from "../../L16_observability_layer/logging/error_sink.mjs"
import { getConfig } from "../config/config.mjs"
import { loadRoleSystem } from "../../L4_prompt_layer/role_system/role_system.mjs"
import { createPromptRegistry } from "../../L4_prompt_layer/prompt_registry/prompt_registry.mjs"
import { readJson, writeJsonAtomic, updateJsonLocked } from "../../L9_state_layer/state_stores/state_store.mjs"

// Router imports
import { createRouter } from "../../L11_routing_layer/routing/router.mjs"
import { registerCoreRoutes } from "../../L11_routing_layer/routing/router_core.mjs"
import { registerNavRoutes } from "../../L11_routing_layer/routing/router_nav.mjs"
import { registerConfigRoutes } from "../../L11_routing_layer/routing/router_config.mjs"
import { registerModelsRoutes } from "../../L11_routing_layer/routing/router_models.mjs"
import { registerPromptsRoutes } from "../../L11_routing_layer/routing/router_prompts.mjs"
import { registerFactoryRoutes } from "../../L11_routing_layer/routing/router_factory.mjs"
import { registerMapRoutes } from "../../L11_routing_layer/routing/router_map.mjs"
import { registerPortalRoutes } from "../../L11_routing_layer/routing/router_portal.mjs"
import { registerSccDevRoutes } from "../../L11_routing_layer/routing/router_sccdev.mjs"
import { registerBoardRoutes } from "../../L11_routing_layer/routing/router_board.mjs"
import { registerExecutorRoutes } from "../../L11_routing_layer/routing/router_executor.mjs"
import { registerPinsRoutes } from "../../L11_routing_layer/routing/router_pins.mjs"

// Utils
import { sendJson } from "./utils.mjs"

// Config
const gatewayPort = Number(process.env.GATEWAY_PORT ?? "18788")
const cfg = getConfig()
const log = createLogger({ component: "scc.gateway" })
const errSink = createJsonlErrorSink({ file: path.join(cfg.execLogDir, "gateway_errors.jsonl") })

// Initialize role system
const roleSystem = loadRoleSystem({ repoRoot: cfg.repoRoot, strict: false })

// Initialize prompt registry
const promptRegistryRoot = process.env.PROMPT_REGISTRY_ROOT ?? path.join(cfg.repoRoot, "L4_prompt_layer", "prompts")
const promptRegistryFile = process.env.PROMPT_REGISTRY_FILE ?? path.join(promptRegistryRoot, "registry.json")
const promptRegistry = createPromptRegistry({ registryFile: promptRegistryFile, rootDir: promptRegistryRoot })

// Runtime config
const runtimeEnvFile = path.join(cfg.repoRoot, "L1_code_layer", "config", "config", "runtime.env")

// Config registry
const configRegistry = [
  { key: "GATEWAY_PORT", type: "number", desc: "Gateway port" },
  { key: "EXEC_CONCURRENCY_CODEX", type: "number", desc: "Codex concurrency" },
  { key: "EXEC_CONCURRENCY_OPENCODE", type: "number", desc: "OpenCode concurrency" },
  { key: "MODEL_POOL_FREE", type: "string", desc: "Free models" },
  { key: "MODEL_POOL_VISION", type: "string", desc: "Vision models" },
  { key: "PREFER_FREE_MODELS", type: "bool", desc: "Prefer free models" },
]

// State files
const boardFile = path.join(cfg.boardDir, "tasks.json")
const missionFile = path.join(cfg.boardDir, "mission.json")
const execStateFile = path.join(cfg.execLogDir, "exec_state.json")
const gatewayErrorsFile = path.join(cfg.execLogDir, "gateway_errors.jsonl")
const stateEventsFile = path.join(cfg.execLogDir, "state_events.jsonl")

// Ensure directories exist
fs.mkdirSync(cfg.execLogDir, { recursive: true })
fs.mkdirSync(cfg.boardDir, { recursive: true })

// Jobs map
const jobs = new Map()

// Default model configuration (OpenCode free models)
const modelsFree = ["opencode/kimi-k2.5-free", "opencode/minimax-m2.1-free", "opencode/trinity-large-preview-free"]
const modelsVision = ["opencode/kimi-k2.5-free"]
const modelsPaid = []
const occliModelDefault = "opencode/kimi-k2.5-free"
const codexModelDefault = "gpt-4.1-mini"
const codexPreferredOrder = ["gpt-4.1-mini", "gpt-4.1-nano"]
const STRICT_DESIGNER_MODEL = "gpt-4.1"

// Concurrency settings
const codexMax = 2
const occliMax = 2
const externalMaxCodex = 5
const externalMaxOccli = 5
const desiredRatioCodex = 0.5
const desiredRatioOccli = 0.5
const timeoutCodexMs = 300000
const timeoutOccliMs = 300000

// Feature flags
const preferFreeModels = true
const autoCreateSplitOnTimeout = false
const autoDispatchSplitTasks = false
const autoAssignOccliModels = true
const failureReportTickMs = 60000
const failureReportTail = 100
const autoCancelStaleExternal = true
const autoCancelExternalTickMs = 300000

// Upstream URLs
const sccUpstream = new URL("http://127.0.0.1:18788")
const opencodeUpstream = new URL("http://127.0.0.1:18080")

// SCC prefixes
const SCC_PREFIXES = ["/scc/", "/scc-v1/"]

// Create router
const router = createRouter()

// Register all routes
registerCoreRoutes({ router })
registerNavRoutes({ router })
registerConfigRoutes({ router })
registerModelsRoutes({ router })
registerPromptsRoutes({ router })
registerFactoryRoutes({ router })
registerMapRoutes({ router })
registerPortalRoutes({ router, repoRoot: cfg.repoRoot, cfg })
registerSccDevRoutes({ router })
registerBoardRoutes({ router })
registerExecutorRoutes({ router })
registerPinsRoutes({ router })

// Helper functions
function readRuntimeEnv() {
  try {
    const content = fs.readFileSync(runtimeEnvFile, "utf8")
    const values = {}
    for (const line of content.split("\n")) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith("#")) continue
      const eq = trimmed.indexOf("=")
      if (eq > 0) {
        const key = trimmed.slice(0, eq).trim()
        const value = trimmed.slice(eq + 1).trim()
        values[key] = value
      }
    }
    return { values }
  } catch {
    return { values: {} }
  }
}

function writeRuntimeEnv(values) {
  const lines = ["# Runtime environment - auto-generated", ""]
  for (const [k, v] of Object.entries(values)) {
    lines.push(`${k}=${v}`)
  }
  fs.mkdirSync(path.dirname(runtimeEnvFile), { recursive: true })
  fs.writeFileSync(runtimeEnvFile, lines.join("\n") + "\n", "utf8")
}

async function readRequestBody(req, { maxBytes = 10 * 1024 * 1024 } = {}) {
  return new Promise((resolve) => {
    let body = ""
    let length = 0
    req.on("data", (chunk) => {
      length += chunk.length
      if (length > maxBytes) {
        resolve({ ok: false, error: "payload_too_large", message: `max ${maxBytes} bytes` })
        req.destroy()
        return
      }
      body += chunk
    })
    req.on("end", () => {
      try {
        const data = JSON.parse(body || "{}")
        resolve({ ok: true, data, raw: body })
      } catch (e) {
        resolve({ ok: false, error: "json_parse_failed", message: String(e?.message ?? e) })
      }
    })
    req.on("error", (e) => resolve({ ok: false, error: "read_failed", message: String(e?.message ?? e) }))
  })
}

// Alias for compatibility with router modules
const readJsonBody = readRequestBody

function listBoardTasks() {
  try {
    const data = readJson(boardFile, [])
    return Array.isArray(data) ? data : []
  } catch {
    return []
  }
}

function runningCounts() {
  return { codex: 0, opencodecli: 0 }
}

function quarantineActive() {
  return false
}

function repoUnhealthyActive() {
  return false
}

function loadRepoHealthState() {
  return { ok: true }
}

function loadCircuitBreakerState() {
  return { ok: true }
}

function poolSnapshot() {
  return { free: modelsFree, vision: modelsVision, paid: modelsPaid }
}

function getFactoryPolicy() {
  return { wipLimits: { fastlane: 5, mainlane: 10, batchlane: 20 } }
}

function wipLimits() {
  return { fastlane: 5, mainlane: 10, batchlane: 20 }
}

function runningInternalByLane() {
  return { fastlane: 0, mainlane: 0, batchlane: 0 }
}

function computeDegradationState({ snap }) {
  return { action: null }
}

function applyDegradationToWipLimitsV1({ limits, action }) {
  return limits
}

function routeLaneForEventType(et) {
  return "mainlane"
}

function updateModelPools({ free, vision, occliDefault }) {
  return { ok: true }
}

function updateCodexModelPolicy({ codexDefault, codexPreferred, paidPool, strictDesignerModel }) {
  return { ok: true }
}

function leader({ level, type, ...rest }) {
  log.info(`[${level}] ${type}`, rest)
}

function noteBestEffort(e) {
  log.error("Best effort error", e)
}

function listWorkers() {
  return []
}

function readJsonlTail(file, limit = 100) {
  try {
    if (!fs.existsSync(file)) return []
    const content = fs.readFileSync(file, "utf8")
    const lines = content.split("\n").filter(Boolean)
    return lines.slice(-limit).map((l) => {
      try {
        return JSON.parse(l)
      } catch {
        return { raw: l }
      }
    })
  } catch {
    return []
  }
}

function renderHomeHtml(snap) {
  return `<!DOCTYPE html>
<html>
<head><title>SCC Gateway</title></head>
<body>
<h1>SCC Gateway</h1>
<pre>${JSON.stringify(snap, null, 2)}</pre>
</body>
</html>`
}

function summarizeRouterStatsForUi() {
  return { ok: true }
}

function loadMapV1() {
  return { ok: true, data: {} }
}

function queryMapV1(q) {
  return { ok: true, results: [] }
}

function runMapBuild() {
  return { ok: true }
}

// Status snapshot function
async function statusSnapshot() {
  return {
    gateway: { ok: true, port: gatewayPort },
    roleSystem: { ok: roleSystem.ok, roles: roleSystem.roles?.length ?? 0 },
    promptRegistry: promptRegistry.info(),
    timestamp: new Date().toISOString(),
  }
}

// Context for router
function createContext(req, res) {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${gatewayPort}`)
  return {
    req, res, url, pathname: url.pathname,
    gatewayPort,
    fs, path, URL, http,
    sendJson,
    log, errSink,
    cfg,
    promptRegistry,
    roleSystem,
    statusSnapshot,
    // Core
    listBoardTasks,
    runningCounts,
    jobs,
    quarantineActive,
    // Config
    runtimeEnvFile,
    configRegistry,
    readRuntimeEnv,
    writeRuntimeEnv,
    readRequestBody,
    readJsonBody,
    // Upstreams
    sccUpstream,
    opencodeUpstream,
    // Paths
    SCC_REPO_ROOT: cfg.repoRoot,
    execLogDir: cfg.execLogDir,
    boardDir: cfg.boardDir,
    docsRoot: cfg.docsRoot,
    boardFile,
    missionFile,
    execStateFile,
    gatewayErrorsFile,
    stateEventsFile,
    // Models
    modelsFree,
    modelsVision,
    modelsPaid,
    occliModelDefault,
    codexModelDefault,
    codexPreferredOrder,
    STRICT_DESIGNER_MODEL,
    // Concurrency
    codexMax,
    occliMax,
    externalMaxCodex,
    externalMaxOccli,
    desiredRatioCodex,
    desiredRatioOccli,
    timeoutCodexMs,
    timeoutOccliMs,
    // Feature flags
    preferFreeModels,
    autoCreateSplitOnTimeout,
    autoDispatchSplitTasks,
    autoAssignOccliModels,
    failureReportTickMs,
    failureReportTail,
    autoCancelStaleExternal,
    autoCancelExternalTickMs,
    // Nav
    SCC_PREFIXES,
    // Health
    repoUnhealthyActive,
    loadRepoHealthState,
    loadCircuitBreakerState,
    // Factory
    poolSnapshot,
    getFactoryPolicy,
    wipLimits,
    runningInternalByLane,
    computeDegradationState,
    applyDegradationToWipLimitsV1,
    routeLaneForEventType,
    updateModelPools,
    updateCodexModelPolicy,
    leader,
    // Utils
    noteBestEffort,
    listWorkers,
    readJsonlTail,
    renderHomeHtml,
    summarizeRouterStatsForUi,
    // Map
    loadMapV1,
    queryMapV1,
    runMapBuild,
    // State store
    readJson,
    writeJsonAtomic,
    updateJsonLocked,
    // Strict writes
    strictWrites: cfg.strictWrites,
  }
}

// HTTP Server
const server = http.createServer(async (req, res) => {
  try {
    const ctx = createContext(req, res)
    const result = await router.handle(req, res, ctx)
    
    if (result.handled) {
      return
    }
    
    // 404 for unhandled routes
    sendJson(res, 404, { error: "not_found", path: ctx.pathname })
  } catch (e) {
    log.error("Request handling failed", e)
    sendJson(res, 500, { error: "internal_error", message: String(e?.message ?? e) })
  }
})

server.listen(gatewayPort, "127.0.0.1", () => {
  console.log(`[SCC Gateway] listening on http://127.0.0.1:${gatewayPort}`)
  console.log(`[SCC Gateway] Role System: ${roleSystem.ok ? 'OK' : 'Failed'}`)
  console.log(`[SCC Gateway] Prompt Registry: ${promptRegistry.info().ok ? 'OK' : 'Failed'}`)
})

// Global error handlers
process.on('uncaughtException', (err) => {
  console.error('[SCC Gateway] Uncaught Exception:', err)
  errSink?.note?.({ level: "fatal", where: "uncaughtException", err: log?.errToObject ? log.errToObject(err) : String(err?.message ?? err) })
})

process.on('unhandledRejection', (reason, promise) => {
  console.error('[SCC Gateway] Unhandled Rejection at:', promise, 'reason:', reason)
  errSink?.note?.({ level: "fatal", where: "unhandledRejection", reason: String(reason) })
})
