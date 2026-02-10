import { loadJobsState, saveJobsState } from "../../L9_state_layer/state_stores/jobs_store.mjs"

// OLT CLI 执行器配置（从 oltcli.mjs 迁移）
const DEFAULT_MODEL = "opencode/kimi-k2.5-free"
const OPENCODE_CLI = 'C:\\\\scc\\\\plugin\\\\OpenCode\\\\opencode-cli.exe'

// 模拟 healthCheck 函数
async function healthCheck() {
  return { ok: true, status: "ready", executor: "oltcli", model: DEFAULT_MODEL }
}

// 模拟 createJobExecutor 函数
function createJobExecutor(config = {}) {
  const { model = DEFAULT_MODEL, timeoutMs = 300000 } = config
  return {
    async execute(job, progressCallback) {
      const startTime = Date.now()
      const { prompt, systemPrompt, context } = job
      
      // 这里应该调用 OLT CLI，暂时返回模拟结果
      const result = {
        ok: true,
        result: { text: `Executed with ${model}` },
        metadata: {
          model,
          elapsed: Date.now() - startTime,
          tokens: Math.ceil(prompt.length / 4)
        }
      }
      
      return result
    }
  }
}

// Default configuration
const DEFAULT_CONFIG = {
  defaultModel: DEFAULT_MODEL || "opencode/kimi-k2.5-free",
  freeModels: ["opencode/kimi-k2.5-free", "opencode/minimax-m2.1-free", "opencode/trinity-large-preview-free"],
  visionModels: ["opencode/kimi-k2.5-free"],
  timeoutMs: 300000
}

// Active executors map
const activeExecutors = new Map()

function registerExecutorRoutes({ router }) {
  // GET /executor/codex/health
  router.get("/executor/codex/health", async (ctx) => {
    return { type: "json", status: 200, body: { ok: true, executor: "codex", status: "ready" } }
  })

  // GET /executor/opencodecli/health
  router.get("/executor/opencodecli/health", async (ctx) => {
    const health = await healthCheck()
    return { type: "json", status: health.ok ? 200 : 503, body: health }
  })

  // GET /executor/opencodecli/models - List available model
  router.get("/executor/opencodecli/models", async (ctx) => {
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        defaultModel: DEFAULT_MODEL,
        models: [{
          id: DEFAULT_MODEL,
          name: DEFAULT_MODEL.split("/").pop(),
          provider: DEFAULT_MODEL.split("/")[0],
          free: true
        }]
      }
    }
  })

  // POST /executor/opencodecli/execute - Execute with OpenCode CLI
  router.post("/executor/opencodecli/execute", async (ctx) => {
    const { req, readJsonBody } = ctx
    const body = await readJsonBody(req)
    
    if (!body.ok) {
      return { type: "json", status: 400, body }
    }
    
    const { prompt, model, systemPrompt, context } = body.data
    
    if (!prompt) {
      return { type: "json", status: 400, body: { ok: false, error: "missing_prompt" } }
    }
    
    // Create executor instance
    const executor = createJobExecutor({
      model: model || DEFAULT_CONFIG.defaultModel,
      timeoutMs: 300000
    })
    
    // Execute job
    const result = await executor.execute({
      prompt,
      systemPrompt,
      context
    }, (progress) => {
      // Progress callback - could be used for streaming updates
      console.log(`[OpenCode CLI] Progress: ${progress.type}, elapsed: ${progress.elapsed}ms`)
    })
    
    return {
      type: "json",
      status: result.ok ? 200 : 500,
      body: result
    }
  })

  // GET /executor/jobs - List all jobs
  router.get("/executor/jobs", async (ctx) => {
    const { execStateFile } = ctx
    const state = loadJobsState({ file: execStateFile })
    return { type: "json", status: 200, body: { ok: true, jobs: state.jobs || {}, count: Object.keys(state.jobs || {}).length } }
  })

  // POST /executor/jobs - Create new job
  router.post("/executor/jobs", async (ctx) => {
    const { req, execStateFile, readJsonBody, strictWrites } = ctx
    const body = await readJsonBody(req)
    if (!body.ok) return { type: "json", status: 400, body }

    const job = body.data
    job.id = job.id || `job_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    job.createdAt = Date.now()
    job.status = job.status || "pending"
    
    // If executor type is opencodecli, validate model
    if (job.executor === "opencodecli") {
      job.model = job.model || DEFAULT_CONFIG.defaultModel
      if (!DEFAULT_CONFIG.freeModels.includes(job.model)) {
        return {
          type: "json",
          status: 400,
          body: {
            ok: false,
            error: "invalid_model",
            message: "Model must be one of the available free models",
            availableModels: DEFAULT_CONFIG.freeModels
          }
        }
      }
    }

    const state = loadJobsState({ file: execStateFile })
    state.jobs = state.jobs || {}
    state.jobs[job.id] = job
    saveJobsState({ file: execStateFile, state, strictWrites })

    return { type: "json", status: 201, body: { ok: true, job } }
  })

  // POST /executor/jobs/:id/run - Run a job
  router.post("/executor/jobs/*/run", async (ctx) => {
    const { req, pathname, execStateFile, readJsonBody, strictWrites } = ctx
    const id = pathname.split("/")[3]
    
    const state = loadJobsState({ file: execStateFile })
    const job = state.jobs?.[id]

    if (!job) {
      return { type: "json", status: 404, body: { ok: false, error: "job_not_found" } }
    }
    
    // Update job status
    job.status = "running"
    job.startedAt = Date.now()
    saveJobsState({ file: execStateFile, state, strictWrites })
    
    // Execute based on executor type
    let result
    if (job.executor === "opencodecli") {
      const executor = createJobExecutor({
        model: job.model || DEFAULT_CONFIG.defaultModel,
        timeoutMs: job.timeout || 300000
      })
      
      result = await executor.execute({
        prompt: job.prompt,
        systemPrompt: job.systemPrompt,
        context: job.context
      })
    } else {
      // Default codex executor (placeholder)
      result = {
        ok: true,
        result: { text: "Codex execution placeholder" },
        metadata: { executor: "codex" }
      }
    }
    
    // Update job with result
    job.status = result.ok ? "completed" : "failed"
    job.finishedAt = Date.now()
    job.result = result
    saveJobsState({ file: execStateFile, state, strictWrites })

    return { type: "json", status: result.ok ? 200 : 500, body: { ok: result.ok, job, result } }
  })

  // GET /executor/workers - List workers
  router.get("/executor/workers", async (ctx) => {
    return { type: "json", status: 200, body: { ok: true, workers: [], count: 0 } }
  })

  // GET /executor/leader - Get leader status
  router.get("/executor/leader", async (ctx) => {
    const { jobs } = ctx
    const jobArray = Array.from(jobs.values())
    const running = jobArray.filter(j => j.status === "running")
    const pending = jobArray.filter(j => j.status === "pending")
    
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        leader: {
          id: "leader_001",
          status: "active",
          uptime: Date.now()
        },
        stats: {
          total: jobArray.length,
          running: running.length,
          pending: pending.length,
          completed: jobArray.filter(j => j.status === "completed").length,
          failed: jobArray.filter(j => j.status === "failed").length
        }
      }
    }
  })

  // GET /executor/jobs/:id - Get job details
  router.get("/executor/jobs/*", async (ctx) => {
    const { pathname, execStateFile } = ctx
    // Skip if this is a sub-route like /run or /cancel
    if (pathname.endsWith('/run') || pathname.endsWith('/cancel')) {
      return { handled: false }
    }
    const id = pathname.split("/").pop()
    const state = loadJobsState({ file: execStateFile })
    const job = state.jobs?.[id]

    if (!job) {
      return { type: "json", status: 404, body: { ok: false, error: "job_not_found" } }
    }

    return { type: "json", status: 200, body: { ok: true, job } }
  })

  // POST /executor/jobs/:id/cancel - Cancel job
  router.post("/executor/jobs/*/cancel", async (ctx) => {
    const { pathname, execStateFile, strictWrites } = ctx
    const id = pathname.split("/")[3]
    const state = loadJobsState({ file: execStateFile })
    const job = state.jobs?.[id]

    if (!job) {
      return { type: "json", status: 404, body: { ok: false, error: "job_not_found" } }
    }

    job.status = "cancelled"
    job.updatedAt = Date.now()
    saveJobsState({ file: execStateFile, state, strictWrites })

    return { type: "json", status: 200, body: { ok: true, job } }
  })
}

export { registerExecutorRoutes }
