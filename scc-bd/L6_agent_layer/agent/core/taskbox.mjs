#!/usr/bin/env node
/**
 * TaskBox - 统一任务容器
 * 
 * 支持：父任务、子任务、总任务
 * 特性：可插拔存储后端（文件/数据库/内存）
 */

import fs from "node:fs"
import path from "node:path"
import { EventEmitter } from "node:events"

/**
 * Task 类 - 统一任务对象
 */
export class Task {
  constructor(data = {}) {
    this.id = data.id || `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    this.type = data.type || "task" // 'parent' | 'child' | 'master'
    this.status = data.status || "pending" // 'pending' | 'running' | 'completed' | 'failed' | 'paused'
    
    // 任务内容
    this.title = data.title || ""
    this.description = data.description || ""
    this.goal = data.goal || ""
    this.prompt = data.prompt || ""
    
    // 层级关系
    this.parentId = data.parentId || null
    this.children = data.children || [] // 子任务ID列表
    this.dependencies = data.dependencies || [] // 依赖任务ID列表
    
    // 执行配置
    this.role = data.role || "executor"
    this.executor = data.executor || "oltcli" // 'oltcli' | 'codexcli' | 'custom'
    this.model = data.model || "opencode/kimi-k2.5-free"
    
    // 上下文
    this.files = data.files || []
    this.context = data.context || {}
    this.skills = data.skills || [] // 挂载的 skills
    
    // Hooks
    this.hooks = data.hooks || {
      before: [],
      after: [],
      onError: []
    }
    
    // 元数据
    this.metadata = data.metadata || {}
    this.artifacts = data.artifacts || {}
    
    // 时间戳
    this.createdAt = data.createdAt || Date.now()
    this.updatedAt = data.updatedAt || Date.now()
    this.startedAt = data.startedAt || null
    this.completedAt = data.completedAt || null
  }
  
  /**
   * 更新任务状态
   */
  updateStatus(status, metadata = {}) {
    this.status = status
    this.updatedAt = Date.now()
    
    if (status === "running" && !this.startedAt) {
      this.startedAt = Date.now()
    }
    
    if (["completed", "failed"].includes(status)) {
      this.completedAt = Date.now()
    }
    
    Object.assign(this.metadata, metadata)
    return this
  }
  
  /**
   * 添加子任务
   */
  addChild(childTaskId) {
    if (!this.children.includes(childTaskId)) {
      this.children.push(childTaskId)
      this.updatedAt = Date.now()
    }
    return this
  }
  
  /**
   * 序列化为 JSON
   */
  toJSON() {
    return {
      id: this.id,
      type: this.type,
      status: this.status,
      title: this.title,
      description: this.description,
      goal: this.goal,
      prompt: this.prompt,
      parentId: this.parentId,
      children: this.children,
      dependencies: this.dependencies,
      role: this.role,
      executor: this.executor,
      model: this.model,
      files: this.files,
      context: this.context,
      skills: this.skills,
      hooks: this.hooks,
      metadata: this.metadata,
      artifacts: this.artifacts,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt,
      startedAt: this.startedAt,
      completedAt: this.completedAt
    }
  }
  
  /**
   * 从 JSON 反序列化
   */
  static fromJSON(json) {
    return new Task(json)
  }
}

/**
 * TaskBox 类 - 统一任务容器
 */
export class TaskBox extends EventEmitter {
  constructor(options = {}) {
    super()
    
    this.name = options.name || "default"
    this.storage = options.storage || "file" // 'file' | 'memory' | 'db'
    this.storagePath = options.storagePath || `/app/artifacts/taskbox_${this.name}.jsonl`
    
    // 内存缓存
    this.tasks = new Map()
    this.index = {
      byStatus: new Map(), // status -> Set(taskIds)
      byType: new Map(),   // type -> Set(taskIds)
      byRole: new Map(),   // role -> Set(taskIds)
      byParent: new Map()  // parentId -> Set(taskIds)
    }
    
    this.initialized = false
  }
  
  /**
   * 初始化 TaskBox
   */
  async init() {
    if (this.initialized) return this
    
    // 创建存储目录
    if (this.storage === "file") {
      const dir = path.dirname(this.storagePath)
      fs.mkdirSync(dir, { recursive: true })
      
      // 加载已有任务
      await this.load()
    }
    
    this.initialized = true
    this.emit("initialized", { name: this.name, taskCount: this.tasks.size })
    return this
  }
  
  /**
   * 创建任务
   */
  async create(taskData) {
    const task = new Task(taskData)
    
    // 保存到内存
    this.tasks.set(task.id, task)
    this.updateIndex(task)
    
    // 持久化
    await this.persist(task)
    
    this.emit("task:created", task)
    return task
  }
  
  /**
   * 获取任务
   */
  get(taskId) {
    return this.tasks.get(taskId)
  }
  
  /**
   * 更新任务
   */
  async update(taskId, updates) {
    const task = this.tasks.get(taskId)
    if (!task) return null
    
    // 移除旧索引
    this.removeFromIndex(task)
    
    // 更新任务
    Object.assign(task, updates)
    task.updatedAt = Date.now()
    
    // 更新索引
    this.updateIndex(task)
    
    // 持久化
    await this.persist(task)
    
    this.emit("task:updated", task)
    return task
  }
  
  /**
   * 删除任务
   */
  async delete(taskId) {
    const task = this.tasks.get(taskId)
    if (!task) return false
    
    this.removeFromIndex(task)
    this.tasks.delete(taskId)
    
    this.emit("task:deleted", { taskId })
    return true
  }
  
  /**
   * 查询任务
   */
  query(filters = {}) {
    let results = Array.from(this.tasks.values())
    
    if (filters.status) {
      results = results.filter(t => t.status === filters.status)
    }
    
    if (filters.type) {
      results = results.filter(t => t.type === filters.type)
    }
    
    if (filters.role) {
      results = results.filter(t => t.role === filters.role)
    }
    
    if (filters.parentId !== undefined) {
      results = results.filter(t => t.parentId === filters.parentId)
    }
    
    if (filters.executor) {
      results = results.filter(t => t.executor === filters.executor)
    }
    
    // 排序
    const sortBy = filters.sortBy || "createdAt"
    const sortOrder = filters.sortOrder || "desc"
    results.sort((a, b) => {
      const aVal = a[sortBy] || 0
      const bVal = b[sortBy] || 0
      return sortOrder === "desc" ? bVal - aVal : aVal - bVal
    })
    
    // 分页
    if (filters.limit) {
      const offset = filters.offset || 0
      results = results.slice(offset, offset + filters.limit)
    }
    
    return results
  }
  
  /**
   * 获取待处理任务
   */
  getPending() {
    return this.query({ status: "pending", sortBy: "createdAt", sortOrder: "asc" })
  }
  
  /**
   * 获取可执行的任务（依赖已满足）
   */
  getRunnable() {
    const pending = this.getPending()
    return pending.filter(task => {
      // 检查依赖是否都已完成
      if (!task.dependencies || task.dependencies.length === 0) return true
      return task.dependencies.every(depId => {
        const dep = this.get(depId)
        return dep && dep.status === "completed"
      })
    })
  }
  
  /**
   * 分解父任务为子任务
   */
  async decompose(parentTaskId, subtasksData) {
    const parent = this.get(parentTaskId)
    if (!parent) throw new Error(`Parent task ${parentTaskId} not found`)
    
    const children = []
    
    for (const data of subtasksData) {
      const child = await this.create({
        ...data,
        type: "child",
        parentId: parentTaskId,
        status: "pending"
      })
      
      parent.addChild(child.id)
      children.push(child)
    }
    
    // 更新父任务
    parent.type = "parent"
    await this.update(parentTaskId, { 
      type: "parent",
      children: parent.children 
    })
    
    this.emit("task:decomposed", { parentId: parentTaskId, children: children.map(c => c.id) })
    return children
  }
  
  /**
   * 更新索引
   */
  updateIndex(task) {
    // 状态索引
    if (!this.index.byStatus.has(task.status)) {
      this.index.byStatus.set(task.status, new Set())
    }
    this.index.byStatus.get(task.status).add(task.id)
    
    // 类型索引
    if (!this.index.byType.has(task.type)) {
      this.index.byType.set(task.type, new Set())
    }
    this.index.byType.get(task.type).add(task.id)
    
    // Role 索引
    if (!this.index.byRole.has(task.role)) {
      this.index.byRole.set(task.role, new Set())
    }
    this.index.byRole.get(task.role).add(task.id)
    
    // 父任务索引
    if (task.parentId) {
      if (!this.index.byParent.has(task.parentId)) {
        this.index.byParent.set(task.parentId, new Set())
      }
      this.index.byParent.get(task.parentId).add(task.id)
    }
  }
  
  /**
   * 从索引中移除
   */
  removeFromIndex(task) {
    this.index.byStatus.get(task.status)?.delete(task.id)
    this.index.byType.get(task.type)?.delete(task.id)
    this.index.byRole.get(task.role)?.delete(task.id)
    if (task.parentId) {
      this.index.byParent.get(task.parentId)?.delete(task.id)
    }
  }
  
  /**
   * 持久化任务
   */
  async persist(task) {
    if (this.storage !== "file") return
    
    const line = JSON.stringify(task.toJSON()) + "\n"
    fs.appendFileSync(this.storagePath, line)
  }
  
  /**
   * 加载任务
   */
  async load() {
    if (this.storage !== "file") return
    if (!fs.existsSync(this.storagePath)) return
    
    const content = fs.readFileSync(this.storagePath, "utf-8")
    const lines = content.split("\n").filter(line => line.trim())
    
    for (const line of lines) {
      try {
        const data = JSON.parse(line)
        const task = Task.fromJSON(data)
        this.tasks.set(task.id, task)
        this.updateIndex(task)
      } catch (e) {
        console.error("Failed to parse task:", e.message)
      }
    }
  }
  
  /**
   * 获取统计信息
   */
  getStats() {
    return {
      total: this.tasks.size,
      byStatus: {
        pending: this.index.byStatus.get("pending")?.size || 0,
        running: this.index.byStatus.get("running")?.size || 0,
        completed: this.index.byStatus.get("completed")?.size || 0,
        failed: this.index.byStatus.get("failed")?.size || 0
      },
      byType: {
        master: this.index.byType.get("master")?.size || 0,
        parent: this.index.byType.get("parent")?.size || 0,
        child: this.index.byType.get("child")?.size || 0
      }
    }
  }
}

export default TaskBox
