/**
 * Plugin Routes for SCC
 * 
 * 提供 WebGPT、OpenCode、OpenClaw 等插件的统一接口
 */

import { loadJobsState, saveJobsState } from "../../L9_state_layer/state_stores/jobs_store.mjs"

// 动态导入执行器
async function getExecutor(name) {
  const { 
    createWebGPTExecutor, 
    createOpenClawExecutor,
    createExecutor 
  } = await import('../../L6_agent_layer/executors/index.mjs')
  
  switch (name) {
    case 'webgpt':
      return createWebGPTExecutor()
    case 'openclaw':
      return createOpenClawExecutor()
    case 'opencode':
      return createExecutor()
    default:
      throw new Error(`Unknown executor: ${name}`)
  }
}

/**
 * 注册插件路由
 */
function registerPluginRoutes({ router }) {
  // ==========================================
  // WebGPT Routes
  // ==========================================
  
  // GET /plugins/webgpt/health
  router.get("/plugins/webgpt/health", async (ctx) => {
    try {
      const executor = await getExecutor('webgpt')
      const health = await executor.healthCheck()
      return { 
        type: "json", 
        status: health.status === 'healthy' ? 200 : 503, 
        body: { 
          ok: health.status === 'healthy', 
          executor: "webgpt", 
          ...health 
        } 
      }
    } catch (error) {
      return { 
        type: "json", 
        status: 503, 
        body: { 
          ok: false, 
          executor: "webgpt", 
          error: error.message 
        } 
      }
    }
  })

  // GET /plugins/webgpt/info
  router.get("/plugins/webgpt/info", async (ctx) => {
    try {
      const executor = await getExecutor('webgpt')
      const info = executor.getInfo()
      return { 
        type: "json", 
        status: 200, 
        body: { 
          ok: true, 
          executor: "webgpt", 
          info 
        } 
      }
    } catch (error) {
      return { 
        type: "json", 
        status: 500, 
        body: { 
          ok: false, 
          error: error.message 
        } 
      }
    }
  })

  // POST /plugins/webgpt/execute
  router.post("/plugins/webgpt/execute", async (ctx) => {
    const { req, readJsonBody } = ctx
    const body = await readJsonBody(req)
    
    if (!body.ok) {
      return { type: "json", status: 400, body }
    }
    
    const { prompt, model, enableSearch, context } = body.data
    
    if (!prompt) {
      return { type: "json", status: 400, body: { ok: false, error: "missing_prompt" } }
    }
    
    try {
      const executor = await getExecutor('webgpt')
      const result = await executor.execute({
        id: `webgpt-${Date.now()}`,
        prompt,
        model,
        enableSearch: enableSearch !== false
      }, { contextPack: context })
      
      return {
        type: "json",
        status: result.status === 'success' ? 200 : 500,
        body: result
      }
    } catch (error) {
      return {
        type: "json",
        status: 500,
        body: { ok: false, error: error.message }
      }
    }
  })

  // ==========================================
  // OpenCode Routes
  // ==========================================
  
  // GET /plugins/opencode/health
  router.get("/plugins/opencode/health", async (ctx) => {
    try {
      const executor = await getExecutor('opencode')
      const health = await executor.healthCheck()
      return { 
        type: "json", 
        status: health.status === 'healthy' ? 200 : 503, 
        body: { 
          ok: health.status === 'healthy', 
          executor: "opencode", 
          ...health 
        } 
      }
    } catch (error) {
      return { 
        type: "json", 
        status: 503, 
        body: { 
          ok: false, 
          executor: "opencode", 
          error: error.message 
        } 
      }
    }
  })

  // GET /plugins/opencode/info
  router.get("/plugins/opencode/info", async (ctx) => {
    try {
      const executor = await getExecutor('opencode')
      const info = executor.getInfo()
      return { 
        type: "json", 
        status: 200, 
        body: { 
          ok: true, 
          executor: "opencode", 
          info 
        } 
      }
    } catch (error) {
      return { 
        type: "json", 
        status: 500, 
        body: { 
          ok: false, 
          error: error.message 
        } 
      }
    }
  })

  // POST /plugins/opencode/execute
  router.post("/plugins/opencode/execute", async (ctx) => {
    const { req, readJsonBody } = ctx
    const body = await readJsonBody(req)
    
    if (!body.ok) {
      return { type: "json", status: 400, body }
    }
    
    const { prompt, model, role, skills, context } = body.data
    
    if (!prompt) {
      return { type: "json", status: 400, body: { ok: false, error: "missing_prompt" } }
    }
    
    try {
      const executor = await getExecutor('opencode')
      const result = await executor.execute({
        id: `opencode-${Date.now()}`,
        prompt,
        model,
        role,
        skills
      }, { contextPack: context })
      
      return {
        type: "json",
        status: result.status === 'success' ? 200 : 500,
        body: result
      }
    } catch (error) {
      return {
        type: "json",
        status: 500,
        body: { ok: false, error: error.message }
      }
    }
  })

  // ==========================================
  // OpenClaw Routes
  // ==========================================
  
  // GET /plugins/openclaw/health
  router.get("/plugins/openclaw/health", async (ctx) => {
    try {
      const executor = await getExecutor('openclaw')
      const health = await executor.healthCheck()
      return { 
        type: "json", 
        status: health.status === 'healthy' ? 200 : 503, 
        body: { 
          ok: health.status === 'healthy', 
          executor: "openclaw", 
          ...health 
        } 
      }
    } catch (error) {
      return { 
        type: "json", 
        status: 503, 
        body: { 
          ok: false, 
          executor: "openclaw", 
          error: error.message 
        } 
      }
    }
  })

  // GET /plugins/openclaw/info
  router.get("/plugins/openclaw/info", async (ctx) => {
    try {
      const executor = await getExecutor('openclaw')
      const info = executor.getInfo()
      return { 
        type: "json", 
        status: 200, 
        body: { 
          ok: true, 
          executor: "openclaw", 
          info 
        } 
      }
    } catch (error) {
      return { 
        type: "json", 
        status: 500, 
        body: { 
          ok: false, 
          error: error.message 
        } 
      }
    }
  })

  // GET /plugins/openclaw/agents
  router.get("/plugins/openclaw/agents", async (ctx) => {
    return { 
      type: "json", 
      status: 200, 
      body: { 
        ok: true, 
        agents: [
          { name: "default", description: "General purpose agent" },
          { name: "coder", description: "Code generation and review" },
          { name: "task", description: "Task planning and execution" },
          { name: "verifier", description: "Code verification and testing" }
        ]
      } 
    }
  })

  // POST /plugins/openclaw/execute
  router.post("/plugins/openclaw/execute", async (ctx) => {
    const { req, readJsonBody } = ctx
    const body = await readJsonBody(req)
    
    if (!body.ok) {
      return { type: "json", status: 400, body }
    }
    
    const { prompt, agent, role, skills, tools, context } = body.data
    
    if (!prompt) {
      return { type: "json", status: 400, body: { ok: false, error: "missing_prompt" } }
    }
    
    try {
      const executor = await getExecutor('openclaw')
      const result = await executor.execute({
        id: `openclaw-${Date.now()}`,
        prompt,
        agent: agent || 'default',
        role,
        skills,
        tools
      }, { contextPack: context })
      
      return {
        type: "json",
        status: result.status === 'success' ? 200 : 500,
        body: result
      }
    } catch (error) {
      return {
        type: "json",
        status: 500,
        body: { ok: false, error: error.message }
      }
    }
  })

  // POST /plugins/openclaw/execute/:agent
  router.post("/plugins/openclaw/execute/*", async (ctx) => {
    const { req, pathname, readJsonBody } = ctx
    const body = await readJsonBody(req)
    
    if (!body.ok) {
      return { type: "json", status: 400, body }
    }
    
    const agent = pathname.split("/").pop()
    const { prompt, role, skills, tools, context } = body.data
    
    if (!prompt) {
      return { type: "json", status: 400, body: { ok: false, error: "missing_prompt" } }
    }
    
    try {
      const executor = await getExecutor('openclaw')
      const result = await executor.executeWithAgent(agent, prompt, {
        id: `openclaw-${agent}-${Date.now()}`,
        role,
        skills,
        tools
      })
      
      return {
        type: "json",
        status: result.status === 'success' ? 200 : 500,
        body: result
      }
    } catch (error) {
      return {
        type: "json",
        status: 500,
        body: { ok: false, error: error.message }
      }
    }
  })

  // ==========================================
  // Unified Plugin Routes
  // ==========================================
  
  // GET /plugins - List all available plugins
  router.get("/plugins", async (ctx) => {
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        plugins: [
          {
            id: "webgpt",
            name: "WebGPT",
            type: "cli",
            description: "Web search and AI chat executor",
            endpoints: {
              health: "/plugins/webgpt/health",
              info: "/plugins/webgpt/info",
              execute: "/plugins/webgpt/execute"
            },
            features: ["web_search", "ai_chat", "real_time_info"]
          },
          {
            id: "opencode",
            name: "OpenCode",
            type: "scc_executor",
            description: "Multi-model AI code executor",
            endpoints: {
              health: "/plugins/opencode/health",
              info: "/plugins/opencode/info",
              execute: "/plugins/opencode/execute"
            },
            features: ["code_generation", "code_review", "multi_model"]
          },
          {
            id: "openclaw",
            name: "OpenClaw",
            type: "cli",
            description: "Multi-agent orchestration executor",
            endpoints: {
              health: "/plugins/openclaw/health",
              info: "/plugins/openclaw/info",
              agents: "/plugins/openclaw/agents",
              execute: "/plugins/openclaw/execute"
            },
            features: ["multi_agent", "tool_calling", "session_management"]
          }
        ]
      }
    }
  })

  // GET /plugins/registry - Get connector registry
  router.get("/plugins/registry", async (ctx) => {
    try {
      const { readFile } = await import('fs/promises')
      const registryPath = ctx.path.join(ctx.cfg.repoRoot, 'plugin', 'connectors', 'registry.json')
      const data = await readFile(registryPath, 'utf-8')
      const registry = JSON.parse(data)
      
      return {
        type: "json",
        status: 200,
        body: {
          ok: true,
          registry
        }
      }
    } catch (error) {
      return {
        type: "json",
        status: 500,
        body: { ok: false, error: error.message }
      }
    }
  })

  // POST /plugins/execute - Universal execution endpoint
  router.post("/plugins/execute", async (ctx) => {
    const { req, readJsonBody } = ctx
    const body = await readJsonBody(req)
    
    if (!body.ok) {
      return { type: "json", status: 400, body }
    }
    
    const { plugin, prompt, ...options } = body.data
    
    if (!plugin) {
      return { type: "json", status: 400, body: { ok: false, error: "missing_plugin" } }
    }
    
    if (!prompt) {
      return { type: "json", status: 400, body: { ok: false, error: "missing_prompt" } }
    }
    
    const validPlugins = ['webgpt', 'opencode', 'openclaw']
    if (!validPlugins.includes(plugin)) {
      return { 
        type: "json", 
        status: 400, 
        body: { 
          ok: false, 
          error: "invalid_plugin",
          validPlugins 
        } 
      }
    }
    
    try {
      const executor = await getExecutor(plugin)
      const result = await executor.execute({
        id: `${plugin}-${Date.now()}`,
        prompt,
        ...options
      })
      
      return {
        type: "json",
        status: result.status === 'success' ? 200 : 500,
        body: result
      }
    } catch (error) {
      return {
        type: "json",
        status: 500,
        body: { ok: false, error: error.message }
      }
    }
  })
}

export { registerPluginRoutes }
