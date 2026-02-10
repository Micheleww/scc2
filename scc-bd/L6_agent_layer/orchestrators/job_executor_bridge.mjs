#!/usr/bin/env node
/**
 * Job Executor Bridge
 * 自动从 Jobs Store 获取 pending 任务并分配给 Executor Role
 * 
 * 职责:
 * 1. 轮询 Jobs Store 中的 pending 任务
 * 2. 根据任务类型选择合适的 Executor Role
 * 3. 创建 executor context 并启动执行
 * 4. 监控执行状态并更新 Jobs Store
 */

import fs from "node:fs"
import path from "node:path"
import process from "node:process"

// 配置
const JOBS_FILE = process.env.JOBS_FILE || "/app/artifacts/executor_logs/exec_state.json"
const ROLE_INBOX_DIR = process.env.ROLE_INBOX_DIR || "/app/artifacts/role_inbox"
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || "3000")
const GATEWAY_URL = process.env.GATEWAY_URL || "http://127.0.0.1:18788"

// 简单的日志函数
function log(level, message) {
  const timestamp = new Date().toISOString()
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`)
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
 * 获取待分配的 pending 任务
 */
function getPendingJobs(state) {
  const jobs = state.jobs || {}
  return Object.values(jobs).filter(job => 
    job.status === "pending" && !job.assignedTo
  )
}

/**
 * 根据任务选择合适的 Role
 */
function selectRoleForJob(job) {
  // 根据 job 属性选择 role
  if (job.role) {
    return job.role
  }
  
  // 默认 role 映射
  const roleMap = {
    "opencodecli": "executor",
    "codex": "executor",
    "trae": "engineer"
  }
  
  return roleMap[job.executor] || "executor"
}

/**
 * 创建 Role Task 并写入 Role Inbox
 */
function assignJobToRole(job, role) {
  try {
    // 确保 role inbox 目录存在
    const roleInboxFile = path.join(ROLE_INBOX_DIR, `${role}_inbox.jsonl`)
    fs.mkdirSync(ROLE_INBOX_DIR, { recursive: true })
    
    // 创建 role task
    const roleTask = {
      type: "role_task",
      role: role,
      jobId: job.id,
      title: job.title,
      goal: job.goal,
      prompt: job.prompt,
      systemPrompt: job.systemPrompt,
      files: job.files || [],
      pins: job.pins || {},
      allowedTests: job.allowedTests || [],
      executor: job.executor,
      model: job.model,
      parentId: job.parentId,
      status: "assigned",
      assignedAt: new Date().toISOString(),
      context: {
        repoRoot: "/app",
        artifactsDir: `/app/artifacts/${job.id}`,
        workingDir: "/app"
      }
    }
    
    // 追加到 role inbox
    const line = JSON.stringify(roleTask) + "\n"
    fs.appendFileSync(roleInboxFile, line, "utf-8")
    
    log("info", `Assigned job ${job.id} to role ${role}`)
    return { ok: true, role, roleTask }
  } catch (e) {
    log("error", `Failed to assign job ${job.id}: ${e.message}`)
    return { ok: false, error: e.message }
  }
}

/**
 * 更新 Job 状态为已分配
 */
function markJobAssigned(jobId, role) {
  try {
    const state = loadJobs()
    if (state.jobs[jobId]) {
      state.jobs[jobId].status = "assigned"
      state.jobs[jobId].assignedTo = role
      state.jobs[jobId].assignedAt = Date.now()
      saveJobs(state)
      log("info", `Marked job ${jobId} as assigned to ${role}`)
    }
  } catch (e) {
    log("error", `Failed to mark job ${jobId} as assigned: ${e.message}`)
  }
}

/**
 * 处理单个 pending job
 */
async function processPendingJob(job) {
  log("info", `Processing pending job: ${job.id} - ${job.title}`)
  
  // 1. 选择合适的 role
  const role = selectRoleForJob(job)
  log("info", `Selected role ${role} for job ${job.id}`)
  
  // 2. 分配任务给 role
  const result = assignJobToRole(job, role)
  
  if (result.ok) {
    // 3. 更新 job 状态
    markJobAssigned(job.id, role)
    return { ok: true, jobId: job.id, role }
  } else {
    log("error", `Failed to process job ${job.id}: ${result.error}`)
    return { ok: false, jobId: job.id, error: result.error }
  }
}

/**
 * 主轮询循环
 */
async function poll() {
  try {
    const state = loadJobs()
    const pendingJobs = getPendingJobs(state)
    
    if (pendingJobs.length > 0) {
      log("info", `Found ${pendingJobs.length} pending jobs to assign`)
      
      for (const job of pendingJobs) {
        await processPendingJob(job)
      }
    }
  } catch (e) {
    log("error", `Poll error: ${e.message}`)
  }
}

/**
 * 启动 bridge
 */
function start() {
  log("info", "==================================")
  log("info", "Job Executor Bridge Started")
  log("info", `Jobs file: ${JOBS_FILE}`)
  log("info", `Role inbox dir: ${ROLE_INBOX_DIR}`)
  log("info", `Gateway URL: ${GATEWAY_URL}`)
  log("info", `Poll interval: ${POLL_INTERVAL_MS}ms`)
  log("info", "==================================")
  log("info", "")
  log("info", "Waiting for pending jobs...")
  log("info", "Jobs will be automatically assigned to appropriate roles")
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

export { start, poll, processPendingJob, assignJobToRole, selectRoleForJob }
