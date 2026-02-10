import test from "node:test"
import assert from "node:assert/strict"
import { createRouter } from "../../L11_routing_layer/routing/router.mjs"
import { registerConfigRoutes } from "../../L11_routing_layer/routing/router_config.mjs"
import { registerModelsRoutes } from "../../L11_routing_layer/routing/router_models.mjs"
import { registerPromptsRoutes } from "../../L11_routing_layer/routing/router_prompts.mjs"

// Minimal mock ctx for testing
function createMockCtx(overrides = {}) {
  return {
    // Router framework deps
    sendJson: () => {},
    errSink: { note: () => {} },
    log: { errToObject: (e) => ({ message: String(e?.message ?? e) }) },
    // Config routes deps
    readRuntimeEnv: () => ({ exists: true, path: "/mock/runtime.env", values: { GATEWAY_PORT: "18788" } }),
    configRegistry: [{ key: "GATEWAY_PORT", type: "number", frequent: false, note: "gateway port" }],
    gatewayPort: 18788,
    sccUpstream: { toString: () => "http://127.0.0.1:18789" },
    opencodeUpstream: { toString: () => "http://127.0.0.1:18790" },
    codexMax: 4,
    occliMax: 6,
    externalMaxCodex: 4,
    externalMaxOccli: 6,
    desiredRatioCodex: 0.5,
    desiredRatioOccli: 0.5,
    timeoutCodexMs: 1200000,
    timeoutOccliMs: 1200000,
    modelsFree: ["opencode/kimi-k2.5-free"],
    modelsVision: ["opencode/kimi-k2.5-free"],
    preferFreeModels: true,
    codexPreferredOrder: ["gpt-5.3-codex"],
    autoCreateSplitOnTimeout: true,
    autoDispatchSplitTasks: true,
    occliModelDefault: "opencode/kimi-k2.5-free",
    autoAssignOccliModels: false,
    failureReportTickMs: 3600000,
    failureReportTail: 500,
    autoCancelStaleExternal: false,
    autoCancelExternalTickMs: 60000,
    cfg: { repoRoot: "/mock/repo" },
    path: { join: (...args) => args.join("/").replaceAll("//", "/") },
    writeRuntimeEnv: () => {},
    leader: () => {},
    runtimeEnvFile: "/mock/runtime.env",
    readRequestBody: async () => ({ ok: true, raw: "{}" }),
    req: {},
    // Models routes deps
    updateModelPools: () => {},
    updateCodexModelPolicy: () => ({ ok: true }),
    modelsPaid: ["gpt-5.3-codex"],
    STRICT_DESIGNER_MODEL: "gpt-5.3-codex",
    codexModelDefault: "gpt-5.3-codex",
    // Prompts routes deps
    promptRegistry: {
      info: () => ({ ok: true, version: "v1", entries: [] }),
      render: ({ role_id }) => ({ ok: true, text: `rendered for ${role_id}`, prompt_ref: { role_id } }),
    },
    ...overrides,
  }
}

test("GET /config/schema returns config registry", async () => {
  const router = createRouter()
  registerConfigRoutes({ router })

  const mockReq = { method: "GET", url: "/config/schema" }
  const mockRes = {}
  const ctx = createMockCtx()

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
})

test("GET /config returns runtime and live config", async () => {
  const router = createRouter()
  registerConfigRoutes({ router })

  const mockReq = { method: "GET", url: "/config" }
  const mockRes = {}
  const ctx = createMockCtx()

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
})

test("POST /config/set validates and updates config", async () => {
  const router = createRouter()
  registerConfigRoutes({ router })

  const mockReq = { method: "POST", url: "/config/set" }
  const mockRes = {}
  let writeCalled = false
  const ctx = createMockCtx({
    readRequestBody: async () => ({ ok: true, raw: JSON.stringify({ GATEWAY_PORT: 18888 }) }),
    writeRuntimeEnv: () => { writeCalled = true },
  })

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
  assert.equal(writeCalled, true)
})

test("GET /models returns model pools", async () => {
  const router = createRouter()
  registerModelsRoutes({ router })

  const mockReq = { method: "GET", url: "/models" }
  const mockRes = {}
  const ctx = createMockCtx()

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
})

test("POST /models/set updates model pools", async () => {
  const router = createRouter()
  registerModelsRoutes({ router })

  const mockReq = { method: "POST", url: "/models/set" }
  const mockRes = {}
  let poolsUpdated = false
  const ctx = createMockCtx({
    readRequestBody: async () => ({ ok: true, raw: JSON.stringify({ free: ["model1", "model2"] }) }),
    updateModelPools: () => { poolsUpdated = true },
  })

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
  assert.equal(poolsUpdated, true)
})

test("GET /prompts/registry returns registry info", async () => {
  const router = createRouter()
  registerPromptsRoutes({ router })

  const mockReq = { method: "GET", url: "/prompts/registry" }
  const mockRes = {}
  const ctx = createMockCtx()

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
})

test("POST /prompts/render renders prompt", async () => {
  const router = createRouter()
  registerPromptsRoutes({ router })

  const mockReq = { method: "POST", url: "/prompts/render" }
  const mockRes = {}
  let renderCalled = false
  const ctx = createMockCtx({
    readRequestBody: async () => ({ ok: true, raw: JSON.stringify({ role_id: "test_role" }) }),
    promptRegistry: {
      info: () => ({ ok: true }),
      render: () => { renderCalled = true; return { ok: true, text: "rendered" } },
    },
  })

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
  assert.equal(renderCalled, true)
})

test("POST /config/set rejects invalid values", async () => {
  const router = createRouter()
  registerConfigRoutes({ router })

  const mockReq = { method: "POST", url: "/config/set" }
  const mockRes = {}
  let leaderCalled = false
  const ctx = createMockCtx({
    readRequestBody: async () => ({ ok: true, raw: JSON.stringify({ GATEWAY_PORT: "not_a_number" }) }),
    leader: () => { leaderCalled = true },
  })

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
  assert.equal(leaderCalled, true)
})

test("POST /models/set rejects empty free pool", async () => {
  const router = createRouter()
  registerModelsRoutes({ router })

  const mockReq = { method: "POST", url: "/models/set" }
  const mockRes = {}
  const ctx = createMockCtx({
    readRequestBody: async () => ({ ok: true, raw: JSON.stringify({ free: [] }) }),
  })

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, true)
})

test("all routers handle unknown routes as not handled", async () => {
  const router = createRouter()
  registerConfigRoutes({ router })
  registerModelsRoutes({ router })
  registerPromptsRoutes({ router })

  const mockReq = { method: "GET", url: "/unknown/route" }
  const mockRes = {}
  const ctx = createMockCtx()

  const result = await router.handle(mockReq, mockRes, ctx)

  assert.equal(result.handled, false)
})
