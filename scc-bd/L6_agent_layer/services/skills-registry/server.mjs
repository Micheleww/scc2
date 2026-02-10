#!/usr/bin/env node
/**
 * Skills Registry Service
 * 
 * 独立的 Skills 注册表服务
 * - 加载和管理所有 skills
 * - 提供查询 API
 * - 支持全文搜索和语义匹配
 */

import http from "node:http"
import fs from "node:fs"
import path from "node:path"
import url from "node:url"

const CONFIG = {
  PORT: process.env.SKILLS_REGISTRY_PORT || 18001,
  SKILLS_DIR: process.env.SKILLS_DIR || "/app/scc-bd/L4_prompt_layer/skills",
  CACHE_ENABLED: process.env.CACHE_ENABLED !== "false",
  MAX_RESULTS: Number(process.env.MAX_RESULTS || "10")
}

// Skills 存储
const skillsDB = new Map()
const index = {
  byCategory: new Map(),
  byRole: new Map(),
  byKeyword: new Map()
}

// 日志
function log(level, message, meta = {}) {
  const timestamp = new Date().toISOString()
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`, meta)
}

/**
 * 加载所有 Skills
 */
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
            
            // 存储 skill
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
            updateIndex(skillId, skill, category)
            count++
          } catch (e) {
            log("error", `Failed to load skill ${skillDir}`, { error: e.message })
          }
        }
      }
    }
    
    log("info", `Loaded ${count} skills in ${Date.now() - startTime}ms`)
  } catch (e) {
    log("error", "Failed to load skills", { error: e.message })
  }
}

/**
 * 更新索引
 */
function updateIndex(skillId, skill, category) {
  // 分类索引
  if (!index.byCategory.has(category)) {
    index.byCategory.set(category, new Set())
  }
  index.byCategory.get(category).add(skillId)
  
  // Role 索引
  for (const role of skill.roles || []) {
    if (!index.byRole.has(role)) {
      index.byRole.set(role, new Set())
    }
    index.byRole.get(role).add(skillId)
  }
  
  // 关键词索引
  for (const keyword of skill.keywords || []) {
    const kw = keyword.toLowerCase()
    if (!index.byKeyword.has(kw)) {
      index.byKeyword.set(kw, new Set())
    }
    index.byKeyword.get(kw).add(skillId)
  }
}

/**
 * 搜索 Skills
 */
function searchSkills(query) {
  const { q, role, category, limit = CONFIG.MAX_RESULTS } = query
  const results = []
  const seen = new Set()
  
  // 1. ID 精确匹配
  if (q && skillsDB.has(q)) {
    results.push(skillsDB.get(q))
    seen.add(q)
  }
  
  // 2. 关键词搜索
  if (q && results.length < limit) {
    const qLower = q.toLowerCase()
    
    // 2.1 关键词索引匹配
    for (const [keyword, skillIds] of index.byKeyword) {
      if (keyword.includes(qLower) || qLower.includes(keyword)) {
        for (const skillId of skillIds) {
          if (!seen.has(skillId) && results.length < limit) {
            results.push(skillsDB.get(skillId))
            seen.add(skillId)
          }
        }
      }
    }
    
    // 2.2 名称和描述匹配
    for (const [skillId, skill] of skillsDB) {
      if (seen.has(skillId) || results.length >= limit) continue
      
      const nameMatch = skill.name.toLowerCase().includes(qLower)
      const descMatch = skill.description.toLowerCase().includes(qLower)
      
      if (nameMatch || descMatch) {
        results.push(skill)
        seen.add(skillId)
      }
    }
  }
  
  // 3. Role 过滤
  if (role && results.length < limit) {
    const roleSkills = index.byRole.get(role) || new Set()
    for (const skillId of roleSkills) {
      if (!seen.has(skillId) && results.length < limit) {
        results.push(skillsDB.get(skillId))
        seen.add(skillId)
      }
    }
  }
  
  // 4. Category 过滤
  if (category && results.length < limit) {
    const catSkills = index.byCategory.get(category) || new Set()
    for (const skillId of catSkills) {
      if (!seen.has(skillId) && results.length < limit) {
        results.push(skillsDB.get(skillId))
        seen.add(skillId)
      }
    }
  }
  
  return results
}

/**
 * 为任务查找相关 Skills
 */
function findRelevantSkills(task, roleName, limit = 5) {
  const goal = (task.goal || task.title || task.description || "").toLowerCase()
  const matches = []
  
  for (const [skillId, skill] of skillsDB) {
    let score = 0
    
    // 关键词匹配
    for (const keyword of skill.keywords) {
      if (goal.includes(keyword.toLowerCase())) {
        score += 0.5
      }
    }
    
    // Role 匹配
    if (roleName && skill.roles.includes(roleName)) {
      score += 0.3
    }
    
    // 名称匹配
    if (goal.includes(skill.name.toLowerCase())) {
      score += 0.2
    }
    
    if (score > 0) {
      matches.push({ skill, score })
    }
  }
  
  // 按分数排序
  matches.sort((a, b) => b.score - a.score)
  
  return matches.slice(0, limit).map(m => m.skill)
}

/**
 * HTTP 请求处理
 */
async function handleRequest(req, res) {
  const parsedUrl = url.parse(req.url, true)
  const pathname = parsedUrl.pathname
  const query = parsedUrl.query
  
  // CORS
  res.setHeader("Access-Control-Allow-Origin", "*")
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
  res.setHeader("Access-Control-Allow-Headers", "Content-Type")
  
  if (req.method === "OPTIONS") {
    res.writeHead(200)
    res.end()
    return
  }
  
  try {
    switch (pathname) {
      case "/health":
        res.writeHead(200, { "Content-Type": "application/json" })
        res.end(JSON.stringify({
          status: "ok",
          skills: skillsDB.size,
          uptime: process.uptime()
        }))
        break
        
      case "/search":
        const searchResults = searchSkills(query)
        res.writeHead(200, { "Content-Type": "application/json" })
        res.end(JSON.stringify({
          query,
          count: searchResults.length,
          results: searchResults
        }))
        break
        
      case "/find-for-task":
        if (req.method !== "POST") {
          res.writeHead(405)
          res.end("Method not allowed")
          return
        }
        
        let body = ""
        req.on("data", chunk => body += chunk)
        req.on("end", () => {
          try {
            const { task, role, limit } = JSON.parse(body)
            const relevant = findRelevantSkills(task, role, limit)
            res.writeHead(200, { "Content-Type": "application/json" })
            res.end(JSON.stringify({
              task: task.title || task.goal,
              role,
              count: relevant.length,
              skills: relevant
            }))
          } catch (e) {
            res.writeHead(400)
            res.end(JSON.stringify({ error: e.message }))
          }
        })
        break
        
      case "/get":
        const skillId = query.id
        const skill = skillsDB.get(skillId)
        if (skill) {
          res.writeHead(200, { "Content-Type": "application/json" })
          res.end(JSON.stringify(skill))
        } else {
          res.writeHead(404)
          res.end(JSON.stringify({ error: "Skill not found" }))
        }
        break
        
      case "/list":
        const category = query.category
        const role = query.role
        let list = Array.from(skillsDB.values())
        
        if (category) {
          list = list.filter(s => s.category === category)
        }
        if (role) {
          list = list.filter(s => s.roles.includes(role))
        }
        
        res.writeHead(200, { "Content-Type": "application/json" })
        res.end(JSON.stringify({
          count: list.length,
          skills: list.map(s => ({ id: s.id, name: s.name, category: s.category }))
        }))
        break
        
      case "/stats":
        res.writeHead(200, { "Content-Type": "application/json" })
        res.end(JSON.stringify({
          total: skillsDB.size,
          categories: Array.from(index.byCategory.keys()),
          roles: Array.from(index.byRole.keys())
        }))
        break
        
      default:
        res.writeHead(404)
        res.end(JSON.stringify({ error: "Not found" }))
    }
  } catch (e) {
    log("error", "Request failed", { error: e.message })
    res.writeHead(500)
    res.end(JSON.stringify({ error: e.message }))
  }
}

/**
 * 启动服务
 */
async function start() {
  await loadSkills()
  
  const server = http.createServer(handleRequest)
  
  server.listen(CONFIG.PORT, () => {
    log("info", `Skills Registry Service started`, { port: CONFIG.PORT })
  })
  
  // 优雅退出
  process.on("SIGINT", () => {
    log("info", "Shutting down...")
    server.close(() => {
      process.exit(0)
    })
  })
}

start()
