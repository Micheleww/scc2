/**
 * Portal Router - 统一入口路由
 * 
 * 简化版本：只保留 sccdev 作为常驻页面
 * 其他应用通过插件系统接入
 */

import path from "node:path"
import fs from "node:fs"

// 项目配置 - 简化版本
const PROJECTS_CONFIG = [
  // 核心项目 - 后端服务
  {
    id: "quantsys",
    name: "Quantsys 量化系统",
    path: "projects/quantsys",
    type: "backend",
    entry: "src/quantsys/trading_engine/api/server.py",
    port_env: "QUANTSYS_PORT",
    default_port: 18801,
    health_path: "/health",
    description: "量化交易策略引擎与回测系统",
    icon: "🐍",
    category: "core"
  },
  {
    id: "yme",
    name: "YME 数据报表",
    path: "projects/yme/yme_backend",
    type: "backend",
    entry: "api/app.py",
    port_env: "YME_PORT",
    default_port: 18802,
    health_path: "/api/health",
    description: "销售数据分析与报表系统",
    icon: "📈",
    category: "core"
  },
  
  // 服务组件 - 后端服务
  {
    id: "mcp_bus",
    name: "MCP Bus",
    path: "projects/quantsys/services/mcp_bus",
    type: "backend",
    entry: "server/main.py",
    port_env: "MCP_BUS_PORT",
    default_port: 19002,
    health_path: "/health",
    description: "Model Context Protocol 总线服务",
    icon: "🤖",
    category: "service"
  },
  {
    id: "a2a_hub",
    name: "A2A Hub",
    path: "projects/quantsys/services/a2a_hub",
    type: "backend",
    entry: "main.py",
    port_env: "A2A_HUB_PORT",
    default_port: 19003,
    health_path: "/health",
    description: "Agent-to-Agent 通信中心",
    icon: "🔗",
    category: "service"
  },
  {
    id: "exchange_server",
    name: "Exchange Server",
    path: "projects/quantsys/services/exchange_server",
    type: "backend",
    entry: "main.py",
    port_env: "EXCHANGE_PORT",
    default_port: 19004,
    health_path: "/health",
    description: "文件交换服务",
    icon: "📁",
    category: "service"
  },
  
  // 常驻前端页面 - 只保留 sccdev
  {
    id: "sccdev",
    name: "SCC Dev 监控",
    path: "oc-scc-local/ui/sccdev",
    type: "frontend",
    index: "index.html",
    description: "开发监控面板（常驻页面）",
    icon: "📊",
    category: "frontend",
    isResident: true  // 标记为常驻页面
  }
  
  // 注意：VS Code 已下架
  // 注意：其他前端项目（portal, mcp_webviewer）已移除
  // 注意：OpenCode, OpenClaw, LangGraph 等改为插件方式接入
]

// 插件配置 - 通过插件系统动态加载
const PLUGIN_SERVICES = [
  {
    id: "opencode",
    name: "OpenCode",
    type: "proxy",
    port: 18790,
    upstream_env: "OPENCODE_UPSTREAM",
    default_upstream: "http://127.0.0.1:18790",
    description: "OpenCode UI/Server 代理",
    icon: "🌐",
    category: "plugin"
  },
  {
    id: "clawdbot",
    name: "OpenClaw",
    type: "proxy",
    port: 19001,
    upstream_env: "CLAWDBOT_UPSTREAM",
    default_upstream: "http://127.0.0.1:19001",
    description: "OpenClaw Gateway 代理",
    icon: "🦞",
    category: "plugin"
  },
  {
    id: "langgraph",
    name: "LangGraph",
    type: "integration",
    port: 19005,
    description: "LangGraph 工作流编排",
    icon: "📊",
    category: "plugin",
    github: "langchain-ai/langgraph"
  },
  {
    id: "langchain",
    name: "LangChain",
    type: "integration",
    port: 19007,
    description: "LangChain 框架集成",
    icon: "🔗",
    category: "plugin",
    github: "langchain-ai/langchain"
  },
  {
    id: "autogen",
    name: "AutoGen",
    type: "integration",
    port: 19008,
    description: "微软 AutoGen 多代理框架",
    icon: "🤖",
    category: "plugin",
    github: "microsoft/autogen"
  },
  {
    id: "dify",
    name: "Dify",
    type: "integration",
    port: 19009,
    description: "LLM 应用开发平台",
    icon: "💬",
    category: "plugin",
    github: "langgenius/dify"
  }
]

// 服务端口分配
const SERVICE_PORTS = {
  // 核心服务
  gateway: 18788,
  scc_server: 18789,
  
  // 项目服务
  quantsys: 18801,
  yme: 18802,
  
  // 内部服务
  mcp_bus: 19002,
  a2a_hub: 19003,
  exchange_server: 19004,
  executor: 19006,
}

// 插件端口分配（动态加载）
const PLUGIN_PORTS = {
  opencode: 18790,
  clawdbot: 19001,
  langgraph: 19005,
  langchain: 19007,
  autogen: 19008,
  dify: 19009,
}

// 分类配置
const CATEGORIES = {
  core: { name: "核心项目", icon: "⭐", color: "#ffd700" },
  service: { name: "服务组件", icon: "⚙️", color: "#58a6ff" },
  frontend: { name: "常驻页面", icon: "🎨", color: "#a371f7" },
  plugin: { name: "插件服务", icon: "🔌", color: "#3fb950" }
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase()
  if (ext === ".html" || ext === ".htm") return "text/html; charset=utf-8"
  if (ext === ".css") return "text/css; charset=utf-8"
  if (ext === ".js" || ext === ".mjs") return "text/javascript; charset=utf-8"
  if (ext === ".json") return "application/json; charset=utf-8"
  if (ext === ".svg") return "image/svg+xml"
  if (ext === ".png") return "image/png"
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg"
  if (ext === ".ico") return "image/x-icon"
  return "application/octet-stream"
}

function serveStaticFromDir(req, res, { rootDir, relPath }) {
  const root = path.resolve(String(rootDir ?? ""))
  const rel = String(relPath ?? "").replaceAll("\\", "/").replace(/^\//, "")
  const target = path.resolve(root, rel)
  
  // 安全检查：防止路径遍历
  if (!target.toLowerCase().startsWith(root.toLowerCase())) {
    return { status: 400, body: { error: "path_outside_root" } }
  }
  
  if (!fs.existsSync(target)) {
    return { status: 404, body: { error: "not_found", path: rel } }
  }
  
  try {
    const buf = fs.readFileSync(target)
    return {
      type: "buffer",
      status: 200,
      contentType: contentTypeFor(target),
      headers: { "cache-control": "no-store" },
      body: buf
    }
  } catch (e) {
    return { status: 500, body: { error: "read_failed", message: String(e?.message ?? e) } }
  }
}

function registerPortalRoutes({ router, repoRoot, cfg }) {
  // 只保留 sccdev 作为常驻页面
  const sccdevPath = path.join(repoRoot, "oc-scc-local", "ui", "sccdev")

  // Portal main page - redirect to sccdev or show portal dashboard
  router.get("/portal", async (ctx) => {
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        service: "SCC Portal",
        version: "1.0.0",
        endpoints: {
          config: "/api/portal/config",
          projects: "/api/portal/projects",
          plugins: "/api/portal/plugins",
          health: "/api/portal/health",
          status: "/api/portal/status"
        }
      }
    }
  })

  // SCC Dev - 常驻页面（作为根路径）
  router.get("/", async (ctx) => {
    const indexPath = path.join(sccdevPath, "index.html")
    if (!fs.existsSync(indexPath)) {
      return { 
        type: "json", 
        status: 503, 
        body: { error: "sccdev_not_installed", path: sccdevPath } 
      }
    }
    
    try {
      const html = fs.readFileSync(indexPath, "utf8")
      return { 
        type: "text", 
        status: 200, 
        contentType: "text/html; charset=utf-8",
        headers: { "cache-control": "no-store" },
        body: html 
      }
    } catch (e) {
      return { 
        type: "json", 
        status: 500, 
        body: { error: "read_failed", message: String(e?.message ?? e) } 
      }
    }
  })

  // SCC Dev 静态资源
  router.get("/sccdev", async (ctx) => {
    const indexPath = path.join(sccdevPath, "index.html")
    if (!fs.existsSync(indexPath)) {
      return { 
        type: "json", 
        status: 503, 
        body: { error: "sccdev_not_installed", path: sccdevPath } 
      }
    }
    
    try {
      const html = fs.readFileSync(indexPath, "utf8")
      return { 
        type: "text", 
        status: 200, 
        contentType: "text/html; charset=utf-8",
        headers: { "cache-control": "no-store" },
        body: html 
      }
    } catch (e) {
      return { 
        type: "json", 
        status: 500, 
        body: { error: "read_failed", message: String(e?.message ?? e) } 
      }
    }
  })

  router.get("/sccdev/*", async (ctx) => {
    const relPath = ctx.url.pathname.replace(/^\/sccdev\//, "")
    return serveStaticFromDir(ctx.req, ctx.res, { rootDir: sccdevPath, relPath })
  })

  // API: 获取项目列表（简化版）
  router.get("/api/portal/projects", async (ctx) => {
    const projects = PROJECTS_CONFIG.map(p => {
      const fullPath = path.join(repoRoot, p.path)
      const exists = fs.existsSync(fullPath)
      const port = SERVICE_PORTS[p.id] || process.env[p.port_env] || p.default_port
      
      return {
        id: p.id,
        name: p.name,
        type: p.type,
        category: p.category,
        path: p.path,
        full_path: fullPath,
        port: port,
        health_path: p.health_path,
        description: p.description,
        icon: p.icon,
        isResident: p.isResident || false,
        exists: exists,
        endpoint: p.type === "backend" ? `http://127.0.0.1:${port}` : null,
        health_url: p.health_path ? `http://127.0.0.1:${port}${p.health_path}` : null
      }
    })
    
    return { type: "json", status: 200, body: { ok: true, projects } }
  })

  // API: 获取插件服务列表
  router.get("/api/portal/plugins", async (ctx) => {
    const plugins = PLUGIN_SERVICES.map(p => {
      const port = PLUGIN_PORTS[p.id] || p.port
      const upstream = process.env[p.upstream_env] || p.default_upstream
      
      return {
        id: p.id,
        name: p.name,
        type: p.type,
        category: p.category,
        port: port,
        upstream: upstream,
        description: p.description,
        icon: p.icon,
        github: p.github,
        endpoint: `http://127.0.0.1:${port}`,
        enabled: true  // 可以通过配置控制
      }
    })
    
    return { type: "json", status: 200, body: { ok: true, plugins } }
  })

  // API: 获取分类项目
  router.get("/api/portal/projects/by-category", async (ctx) => {
    const byCategory = {}
    
    for (const cat of Object.keys(CATEGORIES)) {
      byCategory[cat] = []
    }
    
    // 添加核心项目
    for (const p of PROJECTS_CONFIG) {
      const fullPath = path.join(repoRoot, p.path)
      const exists = fs.existsSync(fullPath)
      const port = SERVICE_PORTS[p.id] || process.env[p.port_env] || p.default_port
      
      if (byCategory[p.category]) {
        byCategory[p.category].push({
          id: p.id,
          name: p.name,
          type: p.type,
          path: p.path,
          port: port,
          description: p.description,
          icon: p.icon,
          isResident: p.isResident || false,
          exists: exists
        })
      }
    }
    
    // 添加插件服务
    for (const p of PLUGIN_SERVICES) {
      const port = PLUGIN_PORTS[p.id] || p.port
      byCategory.plugin.push({
        id: p.id,
        name: p.name,
        type: p.type,
        port: port,
        description: p.description,
        icon: p.icon,
        github: p.github,
        enabled: true
      })
    }
    
    return { 
      type: "json", 
      status: 200, 
      body: { 
        ok: true, 
        categories: CATEGORIES,
        projects: byCategory 
      } 
    }
  })

  // API: 获取服务端口分配
  router.get("/api/portal/ports", async (ctx) => {
    return { 
      type: "json", 
      status: 200, 
      body: { 
        ok: true, 
        services: SERVICE_PORTS,
        plugins: PLUGIN_PORTS,
        range: "18000-19999"
      } 
    }
  })

  // API: 获取统一配置
  router.get("/api/portal/config", async (ctx) => {
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        portal: {
          title: "SCC 统一入口",
          version: "1.0.0",
          entry: "/",
          resident: "sccdev"
        },
        categories: CATEGORIES,
        services: Object.entries(SERVICE_PORTS).map(([name, port]) => ({
          name,
          port,
          endpoint: `http://127.0.0.1:${port}`,
          health: `http://127.0.0.1:${port}/health`
        })),
        plugins: PLUGIN_SERVICES.map(p => ({
          id: p.id,
          name: p.name,
          type: p.type,
          port: PLUGIN_PORTS[p.id] || p.port,
          description: p.description,
          icon: p.icon,
          github: p.github
        })),
        projects: PROJECTS_CONFIG.map(p => ({
          id: p.id,
          name: p.name,
          type: p.type,
          category: p.category,
          path: `/${p.path}`,
          port: SERVICE_PORTS[p.id] || p.default_port,
          description: p.description,
          icon: p.icon,
          isResident: p.isResident || false
        }))
      }
    }
  })

  // API: 获取单个项目详情
  router.get("/api/portal/projects/:projectId", async (ctx) => {
    const projectId = ctx.params.projectId
    const project = PROJECTS_CONFIG.find(p => p.id === projectId)
    
    if (!project) {
      return { type: "json", status: 404, body: { error: "project_not_found", project: projectId } }
    }
    
    const fullPath = path.join(repoRoot, project.path)
    const exists = fs.existsSync(fullPath)
    const port = SERVICE_PORTS[projectId] || process.env[project.port_env] || project.default_port
    
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        project: {
          ...project,
          full_path: fullPath,
          port: port,
          exists: exists,
          endpoint: project.type === "backend" ? `http://127.0.0.1:${port}` : null,
          health_url: project.health_path ? `http://127.0.0.1:${port}${project.health_path}` : null
        }
      }
    }
  })

  // API: 获取插件详情
  router.get("/api/portal/plugins/:pluginId", async (ctx) => {
    const pluginId = ctx.params.pluginId
    const plugin = PLUGIN_SERVICES.find(p => p.id === pluginId)
    
    if (!plugin) {
      return { type: "json", status: 404, body: { error: "plugin_not_found", plugin: pluginId } }
    }
    
    const port = PLUGIN_PORTS[pluginId] || plugin.port
    const upstream = process.env[plugin.upstream_env] || plugin.default_upstream
    
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        plugin: {
          ...plugin,
          port: port,
          upstream: upstream,
          endpoint: `http://127.0.0.1:${port}`,
          enabled: true
        }
      }
    }
  })

  // 项目后端代理
  router.all("/api/projects/:projectId/*", async (ctx) => {
    const { http, URL } = ctx
    const projectId = ctx.params.projectId
    const project = PROJECTS_CONFIG.find(p => p.id === projectId && p.type === "backend")
    
    if (!project) {
      return { type: "json", status: 404, body: { error: "project_not_found", project: projectId } }
    }
    
    const port = SERVICE_PORTS[projectId] || process.env[project.port_env] || project.default_port
    const targetPath = ctx.url.pathname.replace(`/api/projects/${projectId}`, "")
    const targetUrl = new URL(targetPath || "/", `http://127.0.0.1:${port}`)
    targetUrl.search = ctx.url.search
    
    try {
      const response = await new Promise((resolve, reject) => {
        const req2 = http.request(
          targetUrl,
          { 
            method: ctx.req.method,
            timeout: 30000,
            headers: {
              ...ctx.req.headers,
              host: `127.0.0.1:${port}`
            }
          },
          (resp) => {
            let data = ""
            resp.on("data", chunk => data += chunk)
            resp.on("end", () => resolve({ status: resp.statusCode, data, headers: resp.headers }))
          }
        )
        req2.on("timeout", () => req2.destroy(new Error("timeout")))
        req2.on("error", reject)
        
        if (ctx.req.method !== "GET" && ctx.req.method !== "HEAD") {
          let body = ""
          ctx.req.on("data", chunk => body += chunk)
          ctx.req.on("end", () => {
            req2.write(body)
            req2.end()
          })
        } else {
          req2.end()
        }
      })
      
      // 尝试解析 JSON，失败则返回文本
      let body
      try {
        body = JSON.parse(response.data)
      } catch {
        body = response.data
      }
      
      return {
        type: typeof body === "object" ? "json" : "text",
        status: response.status,
        headers: response.headers,
        body: body
      }
    } catch (e) {
      return { 
        type: "json", 
        status: 503, 
        body: { 
          error: "upstream_unreachable", 
          project: projectId,
          port,
          message: String(e?.message ?? e)
        } 
      }
    }
  })

  // 插件代理
  router.all("/api/plugins/:pluginId/*", async (ctx) => {
    const { http, URL } = ctx
    const pluginId = ctx.params.pluginId
    const plugin = PLUGIN_SERVICES.find(p => p.id === pluginId)
    
    if (!plugin) {
      return { type: "json", status: 404, body: { error: "plugin_not_found", plugin: pluginId } }
    }
    
    const port = PLUGIN_PORTS[pluginId] || plugin.port
    const targetPath = ctx.url.pathname.replace(`/api/plugins/${pluginId}`, "")
    const targetUrl = new URL(targetPath || "/", `http://127.0.0.1:${port}`)
    targetUrl.search = ctx.url.search
    
    try {
      const response = await new Promise((resolve, reject) => {
        const req2 = http.request(
          targetUrl,
          { 
            method: ctx.req.method,
            timeout: 30000,
            headers: {
              ...ctx.req.headers,
              host: `127.0.0.1:${port}`
            }
          },
          (resp) => {
            let data = ""
            resp.on("data", chunk => data += chunk)
            resp.on("end", () => resolve({ status: resp.statusCode, data, headers: resp.headers }))
          }
        )
        req2.on("timeout", () => req2.destroy(new Error("timeout")))
        req2.on("error", reject)
        req2.end()
      })
      
      let body
      try {
        body = JSON.parse(response.data)
      } catch {
        body = response.data
      }
      
      return {
        type: typeof body === "object" ? "json" : "text",
        status: response.status,
        headers: response.headers,
        body: body
      }
    } catch (e) {
      return { 
        type: "json", 
        status: 503, 
        body: { 
          error: "plugin_unreachable", 
          plugin: pluginId,
          port,
          message: String(e?.message ?? e)
        } 
      }
    }
  })

  // 健康检查
  router.get("/api/portal/health", async () => {
    return { 
      type: "json", 
      status: 200, 
      body: { 
        ok: true, 
        service: "portal",
        resident: "sccdev",
        projects: PROJECTS_CONFIG.length,
        plugins: PLUGIN_SERVICES.length,
        timestamp: new Date().toISOString()
      } 
    }
  })

  // API: 检查所有服务状态
  router.get("/api/portal/status", async (ctx) => {
    const { http } = ctx
    const results = []
    
    // 检查核心项目
    for (const project of PROJECTS_CONFIG) {
      if (project.type !== "backend" || !project.health_path) {
        results.push({
          id: project.id,
          name: project.name,
          type: project.type,
          category: project.category,
          status: "skipped"
        })
        continue
      }
      
      const port = SERVICE_PORTS[project.id] || process.env[project.port_env] || project.default_port
      const healthUrl = `http://127.0.0.1:${port}${project.health_path}`
      
      try {
        const response = await new Promise((resolve, reject) => {
          const req2 = http.request(
            new URL(healthUrl),
            { method: "GET", timeout: 3000 },
            (resp) => {
              resp.on("data", () => {})
              resp.on("end", () => resolve(resp.statusCode))
            }
          )
          req2.on("timeout", () => req2.destroy(new Error("timeout")))
          req2.on("error", reject)
          req2.end()
        })
        
        results.push({
          id: project.id,
          name: project.name,
          type: "project",
          category: project.category,
          status: response >= 200 && response < 300 ? "online" : "degraded",
          port: port,
          health_url: healthUrl
        })
      } catch (e) {
        results.push({
          id: project.id,
          name: project.name,
          type: "project",
          category: project.category,
          status: "offline",
          port: port,
          health_url: healthUrl,
          error: String(e?.message ?? e)
        })
      }
    }
    
    // 检查插件服务
    for (const plugin of PLUGIN_SERVICES) {
      const port = PLUGIN_PORTS[plugin.id] || plugin.port
      const healthUrl = `http://127.0.0.1:${port}/health`
      
      try {
        const response = await new Promise((resolve, reject) => {
          const req2 = http.request(
            new URL(healthUrl),
            { method: "GET", timeout: 3000 },
            (resp) => {
              resp.on("data", () => {})
              resp.on("end", () => resolve(resp.statusCode))
            }
          )
          req2.on("timeout", () => req2.destroy(new Error("timeout")))
          req2.on("error", reject)
          req2.end()
        })
        
        results.push({
          id: plugin.id,
          name: plugin.name,
          type: "plugin",
          category: "plugin",
          status: response >= 200 && response < 300 ? "online" : "degraded",
          port: port,
          health_url: healthUrl
        })
      } catch (e) {
        results.push({
          id: plugin.id,
          name: plugin.name,
          type: "plugin",
          category: "plugin",
          status: "offline",
          port: port,
          health_url: healthUrl,
          error: String(e?.message ?? e)
        })
      }
    }
    
    const online = results.filter(r => r.status === "online").length
    const offline = results.filter(r => r.status === "offline").length
    
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        summary: {
          total: results.length,
          online,
          offline,
          skipped: results.length - online - offline
        },
        services: results
      }
    }
  })
}

export { registerPortalRoutes, PROJECTS_CONFIG, PLUGIN_SERVICES, SERVICE_PORTS, PLUGIN_PORTS, CATEGORIES }
