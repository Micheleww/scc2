#!/usr/bin/env node
/**
 * Parent Inbox Watcher - Standalone Version
 * 监听 parent_inbox.jsonl，自动分解父任务并提交到 Jobs Store
 */

import fs from "node:fs"
import path from "node:path"
import process from "node:process"

// 简单的日志函数
function log(level, message) {
  const timestamp = new Date().toISOString()
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`)
}

// 配置
const PARENT_INBOX_FILE = process.env.PARENT_INBOX_FILE || "/app/artifacts/scc_state/parent_inbox.jsonl"
const JOBS_FILE = process.env.JOBS_FILE || "/app/artifacts/executor_logs/exec_state.json"
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || "5000")
const GATEWAY_URL = process.env.GATEWAY_URL || "http://127.0.0.1:18788"

// 状态跟踪
let lastProcessedIndex = 0
let isRunning = false

/**
 * 读取 parent_inbox.jsonl 文件
 */
function readParentInbox() {
  try {
    if (!fs.existsSync(PARENT_INBOX_FILE)) {
      return []
    }
    const content = fs.readFileSync(PARENT_INBOX_FILE, "utf-8")
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
    log("error", `Failed to read parent inbox: ${e.message}`)
    return []
  }
}

/**
 * 更新父任务状态
 */
function updateParentStatus(index, newStatus, metadata = {}) {
  try {
    const entries = readParentInbox()
    if (index >= 0 && index < entries.length) {
      entries[index].status = newStatus
      entries[index].updatedAt = new Date().toISOString()
      Object.assign(entries[index], metadata)
      
      // 写回文件
      const lines = entries.map(e => JSON.stringify(e, (key, val) => 
        key.startsWith("_") ? undefined : val
      ))
      fs.writeFileSync(PARENT_INBOX_FILE, lines.join("\n") + "\n", "utf-8")
      log("info", `Updated parent task ${index} status to ${newStatus}`)
      return true
    }
    return false
  } catch (e) {
    log("error", `Failed to update parent status: ${e.message}`)
    return false
  }
}

/**
 * 将父任务分解为子任务
 */
async function decomposeParentTask(parentTask) {
  log("info", `Decomposing parent task: ${parentTask.description || parentTask.title || "unnamed"}`)
  
  const subtasks = []
  
  // 策略1: 如果父任务有明确的步骤，按步骤分解
  if (parentTask.steps && Array.isArray(parentTask.steps)) {
    for (let i = 0; i < parentTask.steps.length; i++) {
      const step = parentTask.steps[i]
      subtasks.push({
        id: `subtask_${Date.now()}_${i}`,
        title: step.title || `Step ${i + 1}`,
        goal: step.description || step.goal || String(step),
        role: step.role || parentTask.role || "workspace_janitor",
        files: step.files || parentTask.files || [],
        allowedTests: step.allowedTests || ["echo 'ok'"],
        pins: {
          allowed_paths: step.allowedPaths || parentTask.allowedPaths || ["**"],
          max_files: step.maxFiles || 10,
          max_loc: step.maxLoc || 500
        },
        parentId: parentTask.id || `parent_${parentTask._index}`,
        executor: step.executor || parentTask.executor || "opencodecli",
        model: step.model || parentTask.model || "opencode/kimi-k2.5-free",
        lane: "fastlane",
        status: "pending",
        createdAt: Date.now()
      })
    }
  }
  
  // 策略2: 如果没有步骤，创建一个原子任务
  if (subtasks.length === 0) {
    subtasks.push({
      id: `subtask_${Date.now()}_0`,
      title: parentTask.title || `Task from: ${parentTask.description?.slice(0, 50) || "unnamed"}`,
      goal: parentTask.description || parentTask.goal || "Execute parent task",
      role: parentTask.role || "workspace_janitor",
      files: parentTask.files || [],
      allowedTests: parentTask.allowedTests || ["echo 'ok'"],
      pins: {
        allowed_paths: parentTask.allowedPaths || ["**"],
        max_files: 10,
        max_loc: 500
      },
      parentId: parentTask.id || `parent_${parentTask._index}`,
      executor: parentTask.executor || "opencodecli",
      model: parentTask.model || "opencode/kimi-k2.5-free",
      lane: "fastlane",
      status: "pending",
      createdAt: Date.now()
    })
  }
  
  log("info", `Decomposed into ${subtasks.length} subtasks`)
  return subtasks
}

/**
 * 直接写入 Jobs 文件
 */
function submitJobDirectly(job) {
  try {
    let state = { jobs: {}, updatedAt: Date.now() }
    if (fs.existsSync(JOBS_FILE)) {
      const content = fs.readFileSync(JOBS_FILE, "utf-8")
      state = JSON.parse(content)
    }
    
    state.jobs = state.jobs || {}
    state.jobs[job.id] = {
      ...job,
      status: "pending",
      prompt: `Task: ${job.title}\nGoal: ${job.goal}\nFiles: ${job.files?.join(", ") || "none"}`,
      systemPrompt: `You are a ${job.role} agent. Execute the task following best practices.`,
      createdAt: Date.now()
    }
    state.updatedAt = Date.now()
    
    fs.writeFileSync(JOBS_FILE, JSON.stringify(state, null, 2), "utf-8")
    log("info", `Directly wrote job ${job.id} to ${JOBS_FILE}`)
    return { ok: true, job: state.jobs[job.id] }
  } catch (e) {
    log("error", `Failed to write job directly: ${e.message}`)
    return { ok: false, error: e.message }
  }
}

/**
 * 提交任务到 Jobs Store (通过 Gateway API)
 */
async function submitJobToStore(job) {
  try {
    const response = await fetch(`${GATEWAY_URL}/executor/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: job.id,
        title: job.title,
        goal: job.goal,
        role: job.role,
        files: job.files,
        allowedTests: job.allowedTests,
        pins: job.pins,
        parentId: job.parentId,
        executor: job.executor,
        model: job.model,
        lane: job.lane,
        status: "pending",
        prompt: `Task: ${job.title}\nGoal: ${job.goal}\nFiles: ${job.files?.join(", ") || "none"}`,
        systemPrompt: `You are a ${job.role} agent. Execute the task following best practices.`,
        createdAt: job.createdAt
      })
    })
    
    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Gateway returned ${response.status}: ${error}`)
    }
    
    const result = await response.json()
    log("info", `Submitted job ${job.id} to store: ${result.ok}`)
    return result
  } catch (e) {
    log("error", `Failed to submit job ${job.id} via API: ${e.message}`)
    // Fallback: 直接写入 jobs 文件
    return submitJobDirectly(job)
  }
}

/**
 * 自动运行 pending 的 job
 */
async function autoRunJob(jobId) {
  try {
    log("info", `Auto-running job ${jobId}`)
    const response = await fetch(`${GATEWAY_URL}/executor/jobs/${jobId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    })
    
    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Run failed: ${response.status}: ${error}`)
    }
    
    const result = await response.json()
    log("info", `Job ${jobId} started: ${result.ok}`)
    return result
  } catch (e) {
    log("error", `Failed to auto-run job ${jobId}: ${e.message}`)
    return { ok: false, error: e.message }
  }
}

/**
 * 处理单个父任务
 */
async function processParentTask(parentTask) {
  const index = parentTask._index
  
  // 标记为处理中
  updateParentStatus(index, "decomposing", { startedAt: new Date().toISOString() })
  
  try {
    // 1. 分解任务
    const subtasks = await decomposeParentTask(parentTask)
    
    // 2. 提交到 Jobs Store
    const submittedJobs = []
    for (const subtask of subtasks) {
      const result = await submitJobToStore(subtask)
      if (result.ok) {
        submittedJobs.push(subtask.id)
        // 3. 自动运行
        await autoRunJob(subtask.id)
      }
    }
    
    // 4. 标记父任务为完成
    updateParentStatus(index, "completed", {
      completedAt: new Date().toISOString(),
      subtaskCount: subtasks.length,
      submittedJobs
    })
    
    log("info", `Parent task ${index} processed successfully with ${submittedJobs.length} jobs`)
    return { ok: true, subtaskCount: subtasks.length, jobs: submittedJobs }
    
  } catch (e) {
    log("error", `Failed to process parent task ${index}: ${e.message}`)
    updateParentStatus(index, "failed", { error: e.message })
    return { ok: false, error: e.message }
  }
}

/**
 * 主轮询循环
 */
async function poll() {
  if (isRunning) return
  isRunning = true
  
  try {
    const entries = readParentInbox()
    
    // 查找 pending 状态的父任务
    const pendingTasks = entries.filter(e => 
      e.status === "pending" && e._index >= lastProcessedIndex
    )
    
    if (pendingTasks.length > 0) {
      log("info", `Found ${pendingTasks.length} pending parent tasks`)
      
      for (const task of pendingTasks) {
        await processParentTask(task)
        lastProcessedIndex = Math.max(lastProcessedIndex, task._index + 1)
      }
    }
  } catch (e) {
    log("error", `Poll error: ${e.message}`)
  } finally {
    isRunning = false
  }
}

/**
 * 启动 watcher
 */
function start() {
  log("info", "==================================")
  log("info", "Parent Inbox Watcher Started")
  log("info", `Inbox file: ${PARENT_INBOX_FILE}`)
  log("info", `Jobs file: ${JOBS_FILE}`)
  log("info", `Gateway URL: ${GATEWAY_URL}`)
  log("info", `Poll interval: ${POLL_INTERVAL_MS}ms`)
  log("info", "==================================")
  
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

export { start, poll, processParentTask, decomposeParentTask }
