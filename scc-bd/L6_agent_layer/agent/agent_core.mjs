#!/usr/bin/env node
/**
 * SCC Unified Agent Core
 * 
 * 统一的任务执行平台，整合：
 * - Role 库 (L4_prompt_layer/roles/)
 * - 执行器库 (L6_agent_layer/executors/)
 * - Skills 库 (L4_prompt_layer/skills/)
 * - 任务状态管理
 * 
 * 职责：
 * 1. 统一接收任务（替代 parent_inbox_watcher + job_executor_bridge + role_router）
 * 2. 根据任务选择合适的 Role
 * 3. 调用执行器执行任务
 * 4. 管理任务全生命周期
 */

import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"
import process from "node:process"

// 配置
const CONFIG = {
  TASK_INBOX: process.env.TASK_INBOX || "/app/artifacts/scc_state/parent_inbox.jsonl",
  JOBS_FILE: process.env.JOBS_FILE || "/app/artifacts/executor_logs/exec_state.json",
  ROLE_DIR: process.env.ROLE_DIR || "/app/scc-bd/L4_prompt_layer/roles",
  SKILLS_DIR: process.env.SKILLS_DIR || "/app/scc-bd/L4_prompt_layer/skills",
  EXECUTORS_DIR: process.env.EXECUTORS_DIR || "/app/scc-bd/L6_agent_layer/executors",
  ARTIFACTS_DIR: process.env.ARTIFACTS_DIR || "/app/artifacts",
  POLL_INTERVAL_MS: Number(process.env.POLL_INTERVAL_MS || "3000"),
  OLTCLI_PATH: process.env.OLTCLI_PATH || "node /app/scc-bd/L6_execution_layer/oltcli.mjs"
}

// Agent 状态
const agentState = {
  roles: new Map(),
  skills: new Map(),
  executors: new Map(),
  jobs: new Map(),
  isRunning: false
}

// 日志函数
function log(level, message, meta = {}) {
  const timestamp = new Date().toISOString()
  const metaStr = Object.keys(meta).length ? JSON.stringify(meta) : ""
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message} ${metaStr}`)
}

/**
 * ==================== Role 库管理 ====================
 */

/**
 * 加载所有 Role 配置
 */
async function loadRoles() {
  log("info", "Loading roles from", { dir: CONFIG.ROLE_DIR })
  
  try {
    const files = fs.readdirSync(CONFIG.ROLE_DIR)
    const roleFiles = files.filter(f => f.endsWith('.json') && f !== 'registry.json')
    
    for (const file of roleFiles) {
      const rolePath = path.join(CONFIG.ROLE_DIR, file)
      try {
        const content = fs.readFileSync(rolePath, 'utf-8')
        const role = JSON.parse(content)
        const roleName = path.basename(file, '.json')
        agentState.roles.set(roleName, role)
        log("debug", `Loaded role: ${roleName}`)
      } catch (e) {
        log("error", `Failed to load role ${file}: ${e.message}`)
      }
    }
    
    log("info", `Loaded ${agentState.roles.size} roles`)
  } catch (e) {
    log("error", `Failed to load roles: ${e.message}`)
  }
}

/**
 * 根据任务选择合适的 Role
 */
function selectRole(task) {
  // 如果任务已指定 role，直接使用
  if (task.role && agentState.roles.has(task.role)) {
    return task.role
  }
  
  // 根据任务内容关键词选择
  const goal = (task.goal || task.title || task.description || "").toLowerCase()
  
  const roleKeywords = {
    "qa": ["test", "验证", "检查", "verify", "validate"],
    "doc": ["文档", "doc", "readme", "documentation"],
    "architect": ["架构", "设计", "architect", "design"],
    "auditor": ["审计", "审核", "audit", "review"],
    "planner": ["规划", "计划", "plan", "schedule"],
    "split": ["分解", "拆分", "split", "breakdown"],
    "integrator": ["集成", "整合", "integrat", "merge"],
    "engineer": ["开发", "实现", "code", "implement", "build"]
  }
  
  for (const [role, keywords] of Object.entries(roleKeywords)) {
    if (keywords.some(kw => goal.includes(kw))) {
      return role
    }
  }
  
  // 默认使用 executor
  return "executor"
}

/**
 * 获取 Role 的系统提示词
 */
function getRoleSystemPrompt(roleName, task) {
  const role = agentState.roles.get(roleName)
  if (!role) {
    return `You are a ${roleName} agent. Execute the task following best practices.`
  }
  
  // 组合 role 的 system prompt
  let prompt = role.system_prompt || role.systemPrompt || ""
  
  // 添加 role 的能力描述
  if (role.capabilities) {
    prompt += `\n\nYour capabilities: ${role.capabilities.join(", ")}`
  }
  
  // 添加任务特定的上下文
  if (task.context) {
    prompt += `\n\nTask context: ${JSON.stringify(task.context)}`
  }
  
  return prompt || `You are a ${roleName} agent. Execute the task following best practices.`
}

/**
 * ==================== Skills 库管理 ====================
 */

/**
 * 加载所有 Skills
 */
async function loadSkills() {
  log("info", "Loading skills from", { dir: CONFIG.SKILLS_DIR })
  
  try {
    // Skills 目录结构: skills/category/skill_name/skill.json
    const categories = fs.readdirSync(CONFIG.SKILLS_DIR)
    
    for (const category of categories) {
      const categoryPath = path.join(CONFIG.SKILLS_DIR, category)
      const stat = fs.statSync(categoryPath)
      
      if (!stat.isDirectory()) continue
      
      const skillDirs = fs.readdirSync(categoryPath)
      
      for (const skillDir of skillDirs) {
        const skillPath = path.join(categoryPath, skillDir, 'skill.json')
        
        if (fs.existsSync(skillPath)) {
          try {
            const content = fs.readFileSync(skillPath, 'utf-8')
            const skill = JSON.parse(content)
            const skillId = `${category}.${skillDir}`
            agentState.skills.set(skillId, skill)
          } catch (e) {
            log("error", `Failed to load skill ${skillDir}: ${e.message}`)
          }
        }
      }
    }
    
    log("info", `Loaded ${agentState.skills.size} skills`)
  } catch (e) {
    log("error", `Failed to load skills: ${e.message}`)
  }
}

/**
 * 为任务查找相关的 Skills
 */
function findRelevantSkills(task, roleName) {
  const relevantSkills = []
  const goal = (task.goal || task.title || "").toLowerCase()
  
  for (const [skillId, skill] of agentState.skills) {
    // 根据关键词匹配
    if (skill.keywords) {
      if (skill.keywords.some(kw => goal.includes(kw.toLowerCase()))) {
        relevantSkills.push({ id: skillId, ...skill })
      }
    }
    
    // 根据 role 匹配
    if (skill.roles && skill.roles.includes(roleName)) {
      if (!relevantSkills.find(s => s.id === skillId)) {
        relevantSkills.push({ id: skillId, ...skill })
      }
    }
  }
  
  return relevantSkills.slice(0, 5) // 最多返回 5 个相关 skills
}

/**
 * ==================== 执行器管理 ====================
 */

/**
 * 初始化执行器
 */
async function loadExecutors() {
  log("info", "Initializing executors")
  
  // 目前主要使用 oltcli
  agentState.executors.set("oltcli", {
    name: "oltcli",
    path: CONFIG.OLTCLI_PATH,
    type: "cli"
  })
  
  log("info", `Initialized ${agentState.executors.size} executors`)
}

/**
 * 执行任务
 */
async function executeTask(jobId, task, roleName) {
  log("info", `Executing task ${jobId}`, { role: roleName, title: task.title })
  
  const startTime = Date.now()
  
  // 准备环境变量
  const env = {
    ...process.env,
    SCC_JOB_ID: jobId,
    SCC_ROLE: roleName,
    SCC_TASK_PROMPT: task.prompt || task.goal || task.title,
    SCC_SYSTEM_PROMPT: getRoleSystemPrompt(roleName, task),
    SCC_TASK_MODEL: task.model || "opencode/kimi-k2.5-free"
  }
  
  // 添加相关 skills 到环境变量
  const relevantSkills = findRelevantSkills(task, roleName)
  if (relevantSkills.length > 0) {
    env.SCC_RELEVANT_SKILLS = JSON.stringify(relevantSkills)
  }
  
  // 创建工作目录
  const jobDir = path.join(CONFIG.ARTIFACTS_DIR, jobId)
  fs.mkdirSync(jobDir, { recursive: true })
  
  return new Promise((resolve, reject) => {
    let stdout = ""
    let stderr = ""
    
    const child = spawn(CONFIG.OLTCLI_PATH, [], {
      env,
      timeout: 600000, // 10分钟超时
      shell: true,
      cwd: jobDir
    })
    
    child.stdout.on("data", (data) => {
      stdout += data.toString()
    })
    
    child.stderr.on("data", (data) => {
      stderr += data.toString()
    })
    
    child.on("close", (code) => {
      const duration = Date.now() - startTime
      
      // 保存输出到 artifacts
      fs.writeFileSync(path.join(jobDir, "output.log"), stdout, "utf-8")
      if (stderr) {
        fs.writeFileSync(path.join(jobDir, "error.log"), stderr, "utf-8")
      }
      
      // 保存元数据
      fs.writeFileSync(
        path.join(jobDir, "metadata.json"),
        JSON.stringify({
          jobId,
          role: roleName,
          title: task.title,
          startTime,
          endTime: Date.now(),
          duration,
          exitCode: code
        }, null, 2),
        "utf-8"
      )
      
      if (code === 0) {
        log("info", `Task ${jobId} completed in ${duration}ms`)
        resolve({
          ok: true,
          exitCode: code,
          stdout,
          stderr,
          duration,
          artifactsDir: jobDir
        })
      } else {
        log("error", `Task ${jobId} failed with code ${code}`)
        resolve({
          ok: false,
          exitCode: code,
          stdout,
          stderr,
          duration,
          error: `Process exited with code ${code}`,
          artifactsDir: jobDir
        })
      }
    })
    
    child.on("error", (err) => {
      log("error", `Failed to execute task ${jobId}: ${err.message}`)
      reject(err)
    })
  })
}

/**
 * ==================== 任务状态管理 ====================
 */

/**
 * 加载 Jobs Store
 */
function loadJobs() {
  try {
    if (!fs.existsSync(CONFIG.JOBS_FILE)) {
      return { jobs: {}, updatedAt: Date.now() }
    }
    const content = fs.readFileSync(CONFIG.JOBS_FILE, "utf-8")
    return JSON.parse(content)
  } catch (e) {
    log("error", `Failed to load jobs: ${e.message}`)
    return { jobs: {}, updatedAt: Date.now() }
  }
}

/**
 * 保存 Jobs Store
 */
function saveJobs(state) {
  try {
    state.updatedAt = Date.now()
    fs.mkdirSync(path.dirname(CONFIG.JOBS_FILE), { recursive: true })
    fs.writeFileSync(CONFIG.JOBS_FILE, JSON.stringify(state, null, 2), "utf-8")
  } catch (e) {
    log("error", `Failed to save jobs: ${e.message}`)
  }
}

/**
 * 更新 Job 状态
 */
function updateJobStatus(jobId, status, metadata = {}) {
  try {
    const state = loadJobs()
    if (!state.jobs[jobId]) {
      state.jobs[jobId] = { id: jobId }
    }
    state.jobs[jobId].status = status
    state.jobs[jobId].updatedAt = Date.now()
    Object.assign(state.jobs[jobId], metadata)
    saveJobs(state)
    log("info", `Updated job ${jobId} status to ${status}`)
  } catch (e) {
    log("error", `Failed to update job ${jobId}: ${e.message}`)
  }
}

/**
 * ==================== 任务处理 ====================
 */

/**
 * 读取任务收件箱
 */
function readTaskInbox() {
  try {
    if (!fs.existsSync(CONFIG.TASK_INBOX)) {
      return []
    }
    
    const content = fs.readFileSync(CONFIG.TASK_INBOX, "utf-8")
    const lines = content.split("\n").filter(line => line.trim())
    
    return lines.map((line, index) => {
      try {
        const data = JSON.parse(line)
        return { ...data, _lineIndex: index, _raw: line }
      } catch (e) {
        log("error", `Failed to parse inbox line ${index}: ${e.message}`)
        return null
      }
    }).filter(Boolean)
  } catch (e) {
    log("error", `Failed to read task inbox: ${e.message}`)
    return []
  }
}

/**
 * 处理单个任务
 */
async function processTask(task) {
  const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  
  log("info", `========================================`)
  log("info", `Processing Task: ${jobId}`)
  log("info", `Title: ${task.title || task.description}`)
  log("info", `========================================`)
  
  // 1. 选择 Role
  const roleName = selectRole(task)
  log("info", `Selected role: ${roleName}`)
  
  // 2. 创建 Job
  const job = {
    id: jobId,
    title: task.title || task.description,
    goal: task.description || task.goal,
    role: roleName,
    files: task.files || [],
    executor: "oltcli",
    model: task.model || "opencode/kimi-k2.5-free",
    status: "pending",
    createdAt: Date.now(),
    parentTask: task
  }
  
  // 3. 保存到 Jobs Store
  updateJobStatus(jobId, "pending", job)
  
  // 4. 执行任务
  updateJobStatus(jobId, "running", { startedAt: Date.now() })
  
  try {
    const result = await executeTask(jobId, task, roleName)
    
    if (result.ok) {
      updateJobStatus(jobId, "completed", {
        completedAt: Date.now(),
        duration: result.duration,
        output: result.stdout?.slice(0, 1000),
        artifactsDir: result.artifactsDir
      })
      log("info", `Job ${jobId} completed successfully`)
      return { ok: true, jobId }
    } else {
      updateJobStatus(jobId, "failed", {
        failedAt: Date.now(),
        error: result.error,
        stderr: result.stderr?.slice(0, 1000)
      })
      log("error", `Job ${jobId} failed: ${result.error}`)
      return { ok: false, jobId, error: result.error }
    }
  } catch (e) {
    log("error", `Unexpected error processing job ${jobId}: ${e.message}`)
    updateJobStatus(jobId, "failed", { error: e.message })
    return { ok: false, jobId, error: e.message }
  }
}

/**
 * 轮询任务收件箱
 */
async function poll() {
  const tasks = readTaskInbox()
  
  // 查找待处理的任务
  const pendingTasks = tasks.filter(t => 
    !t.status || t.status === "pending"
  )
  
  if (pendingTasks.length > 0) {
    log("info", `Found ${pendingTasks.length} pending tasks`)
    
    for (const task of pendingTasks) {
      await processTask(task)
    }
  }
}

/**
 * ==================== Agent 生命周期 ====================
 */

/**
 * 初始化 Agent
 */
async function initialize() {
  log("info", "==================================")
  log("info", "SCC Unified Agent Initializing...")
  log("info", "==================================")
  
  // 加载所有资源
  await loadRoles()
  await loadSkills()
  await loadExecutors()
  
  log("info", "==================================")
  log("info", "Agent initialization complete")
  log("info", `Roles: ${agentState.roles.size}`)
  log("info", `Skills: ${agentState.skills.size}`)
  log("info", `Executors: ${agentState.executors.size}`)
  log("info", "==================================")
}

/**
 * 启动 Agent
 */
async function start() {
  if (agentState.isRunning) {
    log("warn", "Agent is already running")
    return
  }
  
  await initialize()
  
  agentState.isRunning = true
  
  log("info", "")
  log("info", "Agent started, waiting for tasks...")
  log("info", "")
  
  // 立即执行一次
  poll()
  
  // 设置定时轮询
  const interval = setInterval(poll, CONFIG.POLL_INTERVAL_MS)
  
  // 优雅退出
  process.on("SIGINT", () => {
    log("info", "Shutting down agent...")
    agentState.isRunning = false
    clearInterval(interval)
    process.exit(0)
  })
  
  process.on("SIGTERM", () => {
    log("info", "Shutting down agent...")
    agentState.isRunning = false
    clearInterval(interval)
    process.exit(0)
  })
}

// 如果直接运行此文件
if (import.meta.url === `file://${process.argv[1]}`) {
  start()
}

export { start, initialize, processTask, selectRole, findRelevantSkills }
