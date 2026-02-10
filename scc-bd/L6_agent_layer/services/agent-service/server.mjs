#!/usr/bin/env node
/**
 * SCC Unified Agent Service
 * 
 * 统一的 Agent 服务，整合所有模块化组件：
 * - Skills Registry (skills/*)
 * - Context Renderer (context/*)
 * - Role Registry (roles/*)
 * - Task Management (tasks/*)
 * 
 * 端口: 18000
 */

import http from "node:http"
import url from "node:url"
import fs from "node:fs"
import path from "node:path"

const CONFIG = {
  PORT: process.env.AGENT_SERVICE_PORT || 18000,
  REPO_ROOT: process.env.REPO_ROOT || "/app/scc-bd",
  SKILLS_DIR: process.env.SKILLS_DIR || "/app/scc-bd/L4_prompt_layer/skills",
  ROLES_DIR: process.env.ROLES_DIR || "/app/scc-bd/L4_prompt_layer/roles"
}

// 日志
function log(level, message, meta = {}) {
  const timestamp = new Date().toISOString()
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`, meta)
}

// ==================== Skills Registry ====================

const skillsDB = new Map()
const skillsIndex = {
  byCategory: new Map(),
  byRole: new Map(),
  byKeyword: new Map()
}

async function loadSkills() {
  log("info", "Loading skills...", { dir: CONFIG.SKILLS_DIR })
  const startTime = Date.now()
  let count = 0
  
  try {
    if (!fs.existsSync(CONFIG.SKILLS_DIR)) {
      log("error", "Skills directory not found")
      return
    }
    
    const categories = fs.readdirSync(CONFIG.SKILLS_DIR)
    for (const category of categories) {
      const categoryPath = path.join(CONFIG.SKILLS_DIR, category)
      if (!fs.statSync(categoryPath).isDirectory()) continue
      
      const skillDirs = fs.readdirSync(categoryPath)
      for (const skillDir of skillDirs) {
        const skillPath = path.join(categoryPath, skillDir, "skill.json")
        if (fs.existsSync(skillPath)) {
          try {
            const content = fs.readFileSync(skillPath, "utf-8")
            const skill = JSON.parse(content)
            const skillId = `${category}.${skillDir}`
            
            skillsDB.set(skillId, {
              id: skillId,
              name: skill.name || skillDir,
              description: skill.description || "",
              category,
              prompt: skill.prompt || "",
              examples: skill.examples || [],
              keywords: skill.keywords || [],
              roles: skill.roles || [],
              version: skill.version || "1.0.0"
            })
            
            // 更新索引
            if (!skillsIndex.byCategory.has(category)) {
              skillsIndex.byCategory.set(category, new Set())
            }
            skillsIndex.byCategory.get(category).add(skillId)
            
            for (const role of skill.roles || []) {
              if (!skillsIndex.byRole.has(role)) {
                skillsIndex.byRole.set(role, new Set())
              }
              skillsIndex.byRole.get(role).add(skillId)
            }
            
            for (const keyword of skill.keywords || []) {
              const kw = keyword.toLowerCase()
              if (!skillsIndex.byKeyword.has(kw)) {
                skillsIndex.byKeyword.set(kw, new Set())
              }
              skillsIndex.byKeyword.get(kw).add(skillId)
            }
            
            count++
          } catch (e) {
            // ignore
          }
        }
      }
    }
    
    log("info", `Loaded ${count} skills in ${Date.now() - startTime}ms`)
  } catch (e) {
    log("error", "Failed to load skills", { error: e.message })
  }
}

function searchSkills(query) {
  const { q, role, category, limit = 10 } = query
  const results = []
  const seen = new Set()
  
  if (q && skillsDB.has(q)) {
    results.push(skillsDB.get(q))
    seen.add(q)
  }
  
  if (q && results.length < limit) {
    const qLower = q.toLowerCase()
    for (const [keyword, skillIds] of skillsIndex.byKeyword) {
      if (keyword.includes(qLower) || qLower.includes(keyword)) {
        for (const skillId of skillIds) {
          if (!seen.has(skillId) && results.length < limit) {
            results.push(skillsDB.get(skillId))
            seen.add(skillId)
          }
        }
      }
    }
    
    for (const [skillId, skill] of skillsDB) {
      if (seen.has(skillId) || results.length >= limit) continue
      if (skill.name.toLowerCase().includes(qLower) || 
          skill.description.toLowerCase().includes(qLower)) {
        results.push(skill)
        seen.add(skillId)
      }
    }
  }
  
  if (role && results.length < limit) {
    const roleSkills = skillsIndex.byRole.get(role) || new Set()
    for (const skillId of roleSkills) {
      if (!seen.has(skillId) && results.length < limit) {
        results.push(skillsDB.get(skillId))
        seen.add(skillId)
      }
    }
  }
  
  if (category && results.length < limit) {
    const catSkills = skillsIndex.byCategory.get(category) || new Set()
    for (const skillId of catSkills) {
      if (!seen.has(skillId) && results.length < limit) {
        results.push(skillsDB.get(skillId))
        seen.add(skillId)
      }
    }
  }
  
  return results
}

function findRelevantSkills(task, roleName, limit = 5) {
  const goal = (task.goal || task.title || task.description || "").toLowerCase()
  const matches = []
  
  for (const [skillId, skill] of skillsDB) {
    let score = 0
    for (const keyword of skill.keywords) {
      if (goal.includes(keyword.toLowerCase())) score += 0.5
    }
    if (roleName && skill.roles.includes(roleName)) score += 0.3
    if (goal.includes(skill.name.toLowerCase())) score += 0.2
    
    if (score > 0) matches.push({ skill, score })
  }
  
  matches.sort((a, b) => b.score - a.score)
  return matches.slice(0, limit).map(m => m.skill)
}

// ==================== Context Renderer (7 Slots) ====================

function renderSlot0(params) {
  return { slot: 0, kind: "LEGAL_PREFIX", text: params.customPrefix || "SCC Context Pack v1" }
}

function renderSlot1(params) {
  return {
    slot: 1,
    kind: "BINDING_REFS",
    refs_index: {
      repo_root: params.repoRoot || CONFIG.REPO_ROOT,
      role: params.role || null,
      mode: params.mode || "execute",
      files: (params.files || []).map(f => ({ path: f })),
      generated_at: new Date().toISOString()
    }
  }
}

function renderSlot2(params) {
  return {
    slot: 2,
    kind: "ROLE_CAPSULE",
    capsule: {
      role: params.role || "executor",
      system_prompt: params.roleConfig?.systemPrompt || `You are a ${params.role} agent.`,
      capabilities: params.roleConfig?.capabilities || [],
      model: params.roleConfig?.model || "opencode/kimi-k2.5-free"
    }
  }
}

function renderSlot3(params) {
  return {
    slot: 3,
    kind: "TASK_BUNDLE",
    bundle: {
      task: {
        id: params.task?.id || null,
        title: params.task?.title || "",
        goal: params.task?.goal || "",
        files: params.task?.files || []
      },
      generated_at: new Date().toISOString()
    }
  }
}

function renderSlot4(params) {
  return { slot: 4, kind: "STATE", state: params.state || null }
}

function renderSlot5(params) {
  return {
    slot: 5,
    kind: "TOOLS",
    tools: params.tools || {
      executor: params.executor || "oltcli",
      available: ["read_file", "write_file", "edit_file", "list_dir", "search_files", "run_command"]
    }
  }
}

function renderSlot6(params) {
  return {
    slot: 6,
    kind: "OPTIONAL_CONTEXT",
    optional_context: {
      skills: (params.skills || []).map(s => ({ id: s.id || s, name: s.name || s }))
    }
  }
}

function renderContextPack(params) {
  return {
    schema_version: "scc.context_pack.v1",
    created_at: new Date().toISOString(),
    slots: [
      renderSlot0(params),
      renderSlot1(params),
      renderSlot2(params),
      renderSlot3(params),
      renderSlot4(params),
      renderSlot5(params),
      renderSlot6(params)
    ]
  }
}

// ==================== HTTP Handlers ====================

async function handleRequest(req, res) {
  const parsedUrl = url.parse(req.url, true)
  const pathname = parsedUrl.pathname
  const query = parsedUrl.query
  
  res.setHeader("Access-Control-Allow-Origin", "*")
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
  res.setHeader("Access-Control-Allow-Headers", "Content-Type")
  
  if (req.method === "OPTIONS") {
    res.writeHead(200)
    res.end()
    return
  }
  
  try {
    // Health
    if (pathname === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" })
      res.end(JSON.stringify({
        status: "ok",
        service: "scc-agent-service",
        skills: skillsDB.size,
        uptime: process.uptime()
      }))
      return
    }
    
    // Skills API
    if (pathname === "/skills/search") {
      const results = searchSkills(query)
      res.writeHead(200, { "Content-Type": "application/json" })
      res.end(JSON.stringify({ query, count: results.length, results }))
      return
    }
    
    if (pathname === "/skills/find-for-task" && req.method === "POST") {
      let body = ""
      req.on("data", chunk => body += chunk)
      req.on("end", () => {
        try {
          const { task, role, limit } = JSON.parse(body)
          const skills = findRelevantSkills(task, role, limit)
          res.writeHead(200, { "Content-Type": "application/json" })
          res.end(JSON.stringify({ task: task.title, role, count: skills.length, skills }))
        } catch (e) {
          res.writeHead(400)
          res.end(JSON.stringify({ error: e.message }))
        }
      })
      return
    }
    
    if (pathname === "/skills/get") {
      const skill = skillsDB.get(query.id)
      if (skill) {
        res.writeHead(200, { "Content-Type": "application/json" })
        res.end(JSON.stringify(skill))
      } else {
        res.writeHead(404)
        res.end(JSON.stringify({ error: "Skill not found" }))
      }
      return
    }
    
    if (pathname === "/skills/list") {
      let list = Array.from(skillsDB.values())
      if (query.category) list = list.filter(s => s.category === query.category)
      if (query.role) list = list.filter(s => s.roles.includes(query.role))
      res.writeHead(200, { "Content-Type": "application/json" })
      res.end(JSON.stringify({ count: list.length, skills: list.map(s => ({ id: s.id, name: s.name })) }))
      return
    }
    
    if (pathname === "/skills/stats") {
      res.writeHead(200, { "Content-Type": "application/json" })
      res.end(JSON.stringify({
        total: skillsDB.size,
        categories: Array.from(skillsIndex.byCategory.keys()),
        roles: Array.from(skillsIndex.byRole.keys())
      }))
      return
    }
    
    // Context Renderer API
    if (pathname === "/context/render" && req.method === "POST") {
      let body = ""
      req.on("data", chunk => body += chunk)
      req.on("end", () => {
        try {
          const params = JSON.parse(body)
          const pack = renderContextPack(params)
          res.writeHead(200, { "Content-Type": "application/json" })
          res.end(JSON.stringify({ pack, slots_count: 7 }))
        } catch (e) {
          res.writeHead(400)
          res.end(JSON.stringify({ error: e.message }))
        }
      })
      return
    }
    
    if (pathname === "/context/render/slot" && req.method === "POST") {
      let body = ""
      req.on("data", chunk => body += chunk)
      req.on("end", () => {
        try {
          const { slot, params } = JSON.parse(body)
          const renderers = [renderSlot0, renderSlot1, renderSlot2, renderSlot3, renderSlot4, renderSlot5, renderSlot6]
          if (slot < 0 || slot > 6) {
            res.writeHead(400)
            res.end(JSON.stringify({ error: "Invalid slot number" }))
            return
          }
          res.writeHead(200, { "Content-Type": "application/json" })
          res.end(JSON.stringify(renderers[slot](params)))
        } catch (e) {
          res.writeHead(400)
          res.end(JSON.stringify({ error: e.message }))
        }
      })
      return
    }
    
    res.writeHead(404)
    res.end(JSON.stringify({ error: "Not found" }))
  } catch (e) {
    log("error", "Request failed", { error: e.message })
    res.writeHead(500)
    res.end(JSON.stringify({ error: e.message }))
  }
}

// ==================== Start ====================

async function start() {
  await loadSkills()
  
  const server = http.createServer(handleRequest)
  server.listen(CONFIG.PORT, () => {
    log("info", `SCC Unified Agent Service started`, { port: CONFIG.PORT })
    log("info", `Available endpoints:`)
    log("info", `  GET  /health`)
    log("info", `  GET  /skills/search?q=xxx`)
    log("info", `  POST /skills/find-for-task`)
    log("info", `  GET  /skills/get?id=xxx`)
    log("info", `  GET  /skills/list`)
    log("info", `  GET  /skills/stats`)
    log("info", `  POST /context/render`)
    log("info", `  POST /context/render/slot`)
  })
  
  process.on("SIGINT", () => {
    log("info", "Shutting down...")
    server.close(() => process.exit(0))
  })
}

start()
