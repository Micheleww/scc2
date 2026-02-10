import { loadBoard, saveBoard, loadMission, saveMission, BOARD_LANES, BOARD_STATUS } from "../../L9_state_layer/state_stores/board.mjs"
import { loadJobsState, saveJobsState } from "../../L9_state_layer/state_stores/jobs_store.mjs"

// Hook: Auto-execute a single task
async function autoExecuteSingleTask({ task, ctx }) {
  // Only auto-execute if task has executor and prompt
  if (!task.executor || !task.prompt) {
    console.log(`[BoardHook] Task ${task.id} has no executor or prompt, skipping auto-execution`)
    return { ok: false, reason: "no_executor_or_prompt" }
  }

  const { execStateFile, strictWrites, boardFile } = ctx

  console.log(`[BoardHook] Auto-executing task ${task.id} with executor: ${task.executor}`)

  // Load state
  const state = loadJobsState({ file: execStateFile })

  // Create job
  const job = {
    id: `job_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    executor: task.executor,
    model: task.model || "opencode/kimi-k2.5-free",
    prompt: task.prompt,
    taskId: task.id,
    createdAt: Date.now(),
    status: "pending"
  }

  // Save job to state
  if (!state.jobs) state.jobs = {}
  state.jobs[job.id] = job
  saveJobsState({ file: execStateFile, state, strictWrites })

  console.log(`[BoardHook] Created job ${job.id} for task ${task.id}`)

  // Execute job
  try {
    job.status = "running"
    job.startedAt = Date.now()

    // Dynamic import executor
    let executorModule
    try {
      executorModule = await import(`../../L6_execution_layer/executors/${task.executor}_executor.mjs`)
    } catch (e) {
      console.error(`[BoardHook] Failed to load executor: ${task.executor}`, e.message)
      job.status = "failed"
      job.error = `Failed to load executor: ${e.message}`
      job.finishedAt = Date.now()
      saveJobsState({ file: execStateFile, state, strictWrites })
      return { ok: false, error: job.error }
    }

    const { createJobExecutor } = executorModule
    if (!createJobExecutor) {
      console.error(`[BoardHook] Executor ${task.executor} does not export createJobExecutor`)
      job.status = "failed"
      job.error = "Executor does not support job execution"
      job.finishedAt = Date.now()
      saveJobsState({ file: execStateFile, state, strictWrites })
      return { ok: false, error: job.error }
    }

    const executor = createJobExecutor({
      workingDir: process.cwd(),
      timeoutMs: 300000 // 5 minutes
    })

    console.log(`[BoardHook] Executing job ${job.id}...`)
    const result = await executor.execute({
      id: job.id,
      prompt: job.prompt,
      systemPrompt: job.systemPrompt,
      model: job.model,
      onProgress: (data) => {
        console.log(`[BoardHook] Job ${job.id} progress:`, data.type)
      }
    })

    job.status = result.ok ? "completed" : "failed"
    job.result = result
    job.finishedAt = Date.now()
    saveJobsState({ file: execStateFile, state, strictWrites })

    console.log(`[BoardHook] Job ${job.id} completed with status: ${job.status}`)

    // Update task status to done on success
    if (result.ok) {
      const tasks = loadBoard({ boardFile })
      const updatedTask = tasks.find(t => t.id === task.id)
      if (updatedTask) {
        updatedTask.status = "done"
        updatedTask.result = result
        updatedTask.updatedAt = Date.now()
        saveBoard({ boardFile, tasksArray: tasks, strictWrites })
        console.log(`[BoardHook] Task ${task.id} auto-completed`)
      }
    }

    return { ok: result.ok, job, result }

  } catch (error) {
    console.error(`[BoardHook] Job ${job.id} execution failed:`, error)
    job.status = "failed"
    job.error = String(error.message || error)
    job.finishedAt = Date.now()
    saveJobsState({ file: execStateFile, state, strictWrites })
    return { ok: false, error: job.error }
  }
}

// Hook: Auto-execute task and its subtasks when status changes to "in_progress"
async function autoExecuteTask({ task, ctx }) {
  const results = []

  // Execute current task if it has executor and prompt
  if (task.executor && task.prompt) {
    const result = await autoExecuteSingleTask({ task, ctx })
    results.push({ taskId: task.id, ...result })
  }

  // If this is a parent task, find and execute all subtasks
  const { boardFile, strictWrites } = ctx
  const tasks = loadBoard({ boardFile })
  const subtasks = tasks.filter(t => t.parentId === task.id)

  if (subtasks.length > 0) {
    console.log(`[BoardHook] Parent task ${task.id} has ${subtasks.length} subtasks, triggering auto-execution for all...`)

    for (const subtask of subtasks) {
      // Update subtask status to in_progress
      subtask.status = "in_progress"
      subtask.updatedAt = Date.now()
      saveBoard({ boardFile, tasksArray: tasks, strictWrites })

      // Execute subtask
      const result = await autoExecuteSingleTask({ task: subtask, ctx })
      results.push({ taskId: subtask.id, parentTaskId: task.id, ...result })
    }
  }

  return {
    ok: results.every(r => r.ok),
    results,
    executedCount: results.length
  }
}

function registerBoardRoutes({ router }) {
  // GET /board - List all tasks
  router.get("/board", async (ctx) => {
    const { boardFile } = ctx
    const tasks = loadBoard({ boardFile })
    return { type: "json", status: 200, body: { ok: true, tasks, count: tasks.length } }
  })

  // POST /board/clear - Clear all tasks
  router.post("/board/clear", async (ctx) => {
    const { boardFile, strictWrites } = ctx
    saveBoard({ boardFile, tasksArray: [], strictWrites })
    return { type: "json", status: 200, body: { ok: true, message: "Board cleared" } }
  })

  // GET /board/tasks - List tasks with filtering
  router.get("/board/tasks", async (ctx) => {
    const { url, boardFile } = ctx
    const status = url.searchParams.get("status")
    const lane = url.searchParams.get("lane")
    let tasks = loadBoard({ boardFile })
    
    if (status) tasks = tasks.filter(t => t.status === status)
    if (lane) tasks = tasks.filter(t => t.lane === lane)
    
    return { type: "json", status: 200, body: { ok: true, tasks, count: tasks.length } }
  })

  // POST /board/tasks - Create new task
  router.post("/board/tasks", async (ctx) => {
    const { req, boardFile, readJsonBody, strictWrites } = ctx
    const body = await readJsonBody(req)
    if (!body.ok) return { type: "json", status: 400, body }
    
    const task = body.data
    task.id = task.id || `task_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    task.createdAt = Date.now()
    task.status = task.status || "backlog"
    
    const tasks = loadBoard({ boardFile })
    tasks.push(task)
    saveBoard({ boardFile, tasksArray: tasks, strictWrites })
    
    return { type: "json", status: 201, body: { ok: true, task } }
  })

  // GET /board/tasks/* - Get specific task
  router.get("/board/tasks/*", async (ctx) => {
    const { pathname, boardFile } = ctx
    const id = pathname.split("/").pop()
    const tasks = loadBoard({ boardFile })
    const task = tasks.find(t => t.id === id)
    
    if (!task) {
      return { type: "json", status: 404, body: { ok: false, error: "task_not_found" } }
    }
    
    return { type: "json", status: 200, body: { ok: true, task } }
  })

  // POST /board/tasks/*/status - Update task status
  router.post("/board/tasks/*/status", async (ctx) => {
    const { req, pathname, boardFile, readJsonBody, strictWrites, execStateFile } = ctx
    const id = pathname.split("/").slice(-2)[0]
    const body = await readJsonBody(req)
    if (!body.ok) return { type: "json", status: 400, body }

    const { status } = body.data
    if (!BOARD_STATUS.includes(status)) {
      return { type: "json", status: 400, body: { ok: false, error: "invalid_status", valid: BOARD_STATUS } }
    }

    const tasks = loadBoard({ boardFile })
    const task = tasks.find(t => t.id === id)
    if (!task) {
      return { type: "json", status: 404, body: { ok: false, error: "task_not_found" } }
    }

    const oldStatus = task.status
    task.status = status
    task.updatedAt = Date.now()
    saveBoard({ boardFile, tasksArray: tasks, strictWrites })

    // Hook: Auto-execute when status changes to "in_progress"
    let hookResult = null
    if (status === "in_progress" && oldStatus !== "in_progress") {
      console.log(`[Board] Task ${id} status changed to "in_progress", triggering auto-execution...`)
      hookResult = await autoExecuteTask({ task, ctx: { execStateFile, strictWrites, boardFile } })
      console.log(`[Board] Auto-execution result:`, hookResult.ok ? "success" : "failed")
    }

    return { type: "json", status: 200, body: { ok: true, task, hook: hookResult } }
  })

  // GET /mission - Get mission
  router.get("/mission", async (ctx) => {
    const { missionFile, gatewayPort } = ctx
    const mission = loadMission({ missionFile, gatewayPort })
    return { type: "json", status: 200, body: { ok: true, mission } }
  })

  // POST /mission/consume - Update mission
  router.post("/mission/consume", async (ctx) => {
    const { req, missionFile, gatewayPort, readJsonBody, strictWrites } = ctx
    const body = await readJsonBody(req)
    if (!body.ok) return { type: "json", status: 400, body }
    
    const current = loadMission({ missionFile, gatewayPort })
    const updated = { ...current, ...body.data, updatedAt: Date.now() }
    saveMission({ missionFile, mission: updated, strictWrites })
    
    return { type: "json", status: 200, body: { ok: true, mission: updated } }
  })
}

export { registerBoardRoutes }
