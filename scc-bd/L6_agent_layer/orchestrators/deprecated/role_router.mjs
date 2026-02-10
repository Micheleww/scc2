#!/usr/bin/env node
/**
 * Role Router
 * 自动选择合适的 Role 并调用 CLI 执行任务
 * 
 * 职责:
 * 1. 从 Role Inbox 读取任务
 * 2. 根据任务内容智能选择 Role
 * 3. 调用 OpenCode CLI 执行
 * 4. 监控执行状态并更新结果
 */

import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"
import process from "node:process"

// 配置
const ROLE_INBOX_DIR = process.env.ROLE_INBOX_DIR || "/app/artifacts/role_inbox"
const JOBS_FILE = process.env.JOBS_FILE || "/app/artifacts/executor_logs/exec_state.json"
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || "3000")
const OLTCLI = process.env.OLTCLI_PATH || "node /app/scc-bd/L6_execution_layer/oltcli.mjs"

// Role 到执行器的映射
const ROLE_EXECUTOR_MAP = {
  "executor": "oltcli",
  "engineer": "oltcli",
  "planner": "oltcli",
  "split": "oltcli",
  "auditor": "oltcli",
  "qa": "oltcli",
  "doc": "oltcli",
  "architect": "oltcli",
  "integrator": "oltcli",
  "workspace_janitor": "oltcli"
}

// 简单的日志函数
function log(level, message) {
  const timestamp = new Date().toISOString()
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`)
}

/**
 * 读取 Role Inbox 文件
 */
function readRoleInbox(role) {
  const inboxFile = path.join(ROLE_INBOX_DIR, `${role}_inbox.jsonl`)
  try {
    if (!fs.existsSync(inboxFile)) {
      return []
    }
    const content = fs.readFileSync(inboxFile, "utf-8")
    const lines = content.split("\n").filter(line => line.trim())
    return lines.map((line, index) => {
      try {
        const data = JSON.parse(line)
        return { ...data, _index: index, _raw: line }
      } catch (e) {
        log("error", `Failed to parse line ${index}: ${e.message}`)
        return null
      }
    }).filter(Boolean)
  } catch (e) {
    log("error", `Failed to read role inbox for ${role}: ${e.message}`)
    return []
  }
}

/**
 * 读取 Jobs Store
 */
function loadJobs() {
  try {
    if (!fs.existsSync(JOBS_FILE)) {
      return { jobs: {}, updatedAt: Date.now() }
    }
    const content = fs.readFileSync(JOBS_FILE, "utf-8")
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
    fs.writeFileSync(JOBS_FILE, JSON.stringify(state, null, 2), "utf-8")
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
    if (state.jobs[jobId]) {
      state.jobs[jobId].status = status
      state.jobs[jobId].updatedAt = Date.now()
      Object.assign(state.jobs[jobId], metadata)
      saveJobs(state)
      log("info", `Updated job ${jobId} status to ${status}`)
    }
  } catch (e) {
    log("error", `Failed to update job ${jobId}: ${e.message}`)
  }
}

/**
 * 智能选择 Role
 * 根据任务内容分析选择最合适的 Role
 */
function selectRole(task) {
  // 如果任务已指定 role，直接使用
  if (task.role && ROLE_EXECUTOR_MAP[task.role]) {
    return task.role
  }
  
  // 根据任务内容关键词选择
  const goal = (task.goal || task.title || "").toLowerCase()
  
  if (goal.includes("test") || goal.includes("验证") || goal.includes("检查")) {
    return "qa"
  }
  if (goal.includes("文档") || goal.includes("doc") || goal.includes("readme")) {
    return "doc"
  }
  if (goal.includes("架构") || goal.includes("设计") || goal.includes("architect")) {
    return "architect"
  }
  if (goal.includes("审计") || goal.includes("审核") || goal.includes("audit")) {
    return "auditor"
  }
  if (goal.includes("规划") || goal.includes("计划") || goal.includes("plan")) {
    return "planner"
  }
  if (goal.includes("分解") || goal.includes("拆分") || goal.includes("split")) {
    return "split"
  }
  if (goal.includes("集成") || goal.includes("整合") || goal.includes("integrat")) {
    return "integrator"
  }
  
  // 默认使用 executor
  return "executor"
}

/**
 * 构建 oltcli 参数
 */
function buildOltcliArgs(task, role) {
  const args = []
  
  // oltcli 通过环境变量接收任务信息
  process.env.SCC_TASK_PROMPT = task.prompt || task.goal || task.title
  process.env.SCC_TASK_ROLE = role
  process.env.SCC_TASK_JOB_ID = task.jobId
  
  if (task.systemPrompt) {
    process.env.SCC_SYSTEM_PROMPT = task.systemPrompt
  }
  
  if (task.model) {
    process.env.SCC_TASK_MODEL = task.model
  }
  
  return args
}

/**
 * 执行 oltcli
 */
async function executeWithOltcli(task, role) {
  return new Promise((resolve, reject) => {
    const args = buildOltcliArgs(task, role)
    
    log("info", `Executing oltcli for job ${task.jobId}`)
    log("info", `Command: ${OLTCLI}`)
    
    const startTime = Date.now()
    let stdout = ""
    let stderr = ""
    
    // 使用 shell 执行 oltcli
    const child = spawn(OLTCLI, args, {
      env: { ...process.env, SCC_ROLE: role, SCC_JOB_ID: task.jobId },
      timeout: 300000, // 5分钟超时
      shell: true
    })
    
    child.stdout.on("data", (data) => {
      stdout += data.toString()
      process.stdout.write(data)
    })
    
    child.stderr.on("data", (data) => {
      stderr += data.toString()
      process.stderr.write(data)
    })
    
    child.on("close", (code) => {
      const duration = Date.now() - startTime
      
      if (code === 0) {
        log("info", `Job ${task.jobId} completed in ${duration}ms`)
        resolve({
          ok: true,
          exitCode: code,
          stdout,
          stderr,
          duration
        })
      } else {
        log("error", `Job ${task.jobId} failed with code ${code}`)
        resolve({
          ok: false,
          exitCode: code,
          stdout,
          stderr,
          duration,
          error: `Process exited with code ${code}`
        })
      }
    })
    
    child.on("error", (err) => {
      log("error", `Failed to spawn oltcli: ${err.message}`)
      reject(err)
    })
  })
}

/**
 * 执行 Fallback（直接调用 Node.js 执行器）
 */
async function executeWithFallback(task, role) {
  log("info", `Using fallback execution for job ${task.jobId}`)
  
  // 导入 opencodecli_executor_v2
  try {
    const executorModule = await import("../../L6_execution_layer/executors/opencodecli_executor_v2.mjs")
    
    if (executorModule.executeMultiRound) {
      const result = await executorModule.executeMultiRound({
        prompt: task.prompt || task.goal,
        systemPrompt: task.systemPrompt,
        model: task.model,
        maxRounds: 10,
        workingDir: task.context?.workingDir
      })
      
      return {
        ok: true,
        result,
        duration: result.duration
      }
    }
  } catch (e) {
    log("error", `Fallback execution failed: ${e.message}`)
  }
  
  return {
    ok: false,
    error: "Both OpenCode CLI and fallback execution failed"
  }
}

/**
 * 处理单个 Role Task
 */
async function processRoleTask(task) {
  const jobId = task.jobId
  
  log("info", `========================================`)
  log("info", `Processing Role Task: ${jobId}`)
  log("info", `Title: ${task.title}`)
  log("info", `Role: ${task.role}`)
  log("info", `========================================`)
  
  // 1. 更新 Job 状态为 running
  updateJobStatus(jobId, "running", { startedAt: Date.now() })
  
  try {
    // 2. 智能选择 Role（如果未指定）
    const selectedRole = selectRole(task)
    if (selectedRole !== task.role) {
      log("info", `Auto-selected role: ${selectedRole} (was: ${task.role})`)
    }
    
    // 3. 执行
    let result
    try {
      result = await executeWithOltcli(task, selectedRole)
    } catch (e) {
      log("warn", `oltcli failed, trying fallback: ${e.message}`)
      result = await executeWithFallback(task, selectedRole)
    }
    
    // 4. 更新结果
    if (result.ok) {
      updateJobStatus(jobId, "completed", {
        completedAt: Date.now(),
        duration: result.duration,
        output: result.stdout?.slice(0, 1000), // 限制输出大小
        role: selectedRole
      })
      
      // 生成 artifacts
      await generateArtifacts(jobId, result)
      
      log("info", `Job ${jobId} completed successfully`)
      return { ok: true, jobId }
    } else {
      updateJobStatus(jobId, "failed", {
        failedAt: Date.now(),
        error: result.error,
        stderr: result.stderr?.slice(0, 1000),
        role: selectedRole
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
 * 生成执行产物
 */
async function generateArtifacts(jobId, result) {
  try {
    const artifactsDir = path.join("/app/artifacts", jobId)
    fs.mkdirSync(artifactsDir, { recursive: true })
    
    // 保存完整输出
    fs.writeFileSync(
      path.join(artifactsDir, "output.log"),
      result.stdout || "No output",
      "utf-8"
    )
    
    // 保存错误输出
    if (result.stderr) {
      fs.writeFileSync(
        path.join(artifactsDir, "error.log"),
        result.stderr,
        "utf-8"
      )
    }
    
    // 保存元数据
    fs.writeFileSync(
      path.join(artifactsDir, "metadata.json"),
      JSON.stringify({
        jobId,
        completedAt: new Date().toISOString(),
        duration: result.duration,
        exitCode: result.exitCode
      }, null, 2),
      "utf-8"
    )
    
    log("info", `Artifacts saved to ${artifactsDir}`)
  } catch (e) {
    log("error", `Failed to generate artifacts: ${e.message}`)
  }
}

/**
 * 轮询所有 Role Inbox
 */
async function poll() {
  const roles = Object.keys(ROLE_EXECUTOR_MAP)
  
  for (const role of roles) {
    const tasks = readRoleInbox(role)
    
    // 查找待处理的任务
    const pendingTasks = tasks.filter(t => 
      t.status === "assigned" || t.status === "pending"
    )
    
    if (pendingTasks.length > 0) {
      log("info", `Found ${pendingTasks.length} pending tasks for role ${role}`)
      
      for (const task of pendingTasks) {
        await processRoleTask(task)
      }
    }
  }
}

/**
 * 启动 Role Router
 */
function start() {
  log("info", "==================================")
  log("info", "Role Router Started")
  log("info", `Role Inbox Dir: ${ROLE_INBOX_DIR}`)
  log("info", `Jobs File: ${JOBS_FILE}`)
  log("info", `OLTCLI: ${OLTCLI}`)
  log("info", `Poll Interval: ${POLL_INTERVAL_MS}ms`)
  log("info", "==================================")
  log("info", "")
  log("info", "Supported Roles:")
  Object.entries(ROLE_EXECUTOR_MAP).forEach(([role, executor]) => {
    log("info", `  - ${role} → ${executor}`)
  })
  log("info", "")
  log("info", "Waiting for role tasks...")
  log("info", "")
  
  // 立即执行一次
  poll()
  
  // 设置定时轮询
  const interval = setInterval(poll, POLL_INTERVAL_MS)
  
  // 优雅退出
  process.on("SIGINT", () => {
    log("info", "Shutting down...")
    clearInterval(interval)
    process.exit(0)
  })
  
  process.on("SIGTERM", () => {
    log("info", "Shutting down...")
    clearInterval(interval)
    process.exit(0)
  })
}

// 如果直接运行此文件
if (import.meta.url === `file://${process.argv[1]}`) {
  start()
}

export { start, poll, processRoleTask, selectRole }
