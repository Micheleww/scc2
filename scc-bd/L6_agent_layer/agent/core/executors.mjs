#!/usr/bin/env node
/**
 * Executors - 可插拔执行器系统
 * 
 * 支持：oltcli, codexcli, 以及自定义执行器
 * 特性：统一接口、自动发现、动态加载
 */

import { spawn } from "node:child_process"
import { EventEmitter } from "node:events"

/**
 * Executor 基类
 */
export class Executor extends EventEmitter {
  constructor(name, config = {}) {
    super()
    this.name = name
    this.config = config
    this.type = config.type || "cli" // 'cli' | 'api' | 'function'
    this.status = "idle" // 'idle' | 'running' | 'error'
  }
  
  /**
   * 验证执行器是否可用
   */
  async validate() {
    throw new Error("validate() must be implemented by subclass")
  }
  
  /**
   * 执行任务
   */
  async execute(task, context = {}) {
    throw new Error("execute() must be implemented by subclass")
  }
  
  /**
   * 获取执行器信息
   */
  getInfo() {
    return {
      name: this.name,
      type: this.type,
      status: this.status,
      config: this.config
    }
  }
}

/**
 * CLI 执行器基类
 */
export class CliExecutor extends Executor {
  constructor(name, config) {
    super(name, { ...config, type: "cli" })
    this.command = config.command
    this.args = config.args || []
    this.timeout = config.timeout || 600000 // 10分钟
  }
  
  async validate() {
    try {
      // 检查命令是否存在
      const checkCmd = process.platform === "win32" ? "where" : "which"
      const result = await this.runCommand(checkCmd, [this.command.split(" ")[0]], { timeout: 5000 })
      return result.ok
    } catch (e) {
      return false
    }
  }
  
  async execute(task, context = {}) {
    this.status = "running"
    this.emit("start", { taskId: task.id, executor: this.name })
    
    const startTime = Date.now()
    
    try {
      // 构建参数
      const args = this.buildArgs(task, context)
      
      // 执行
      const result = await this.runCommand(this.command, args, {
        env: this.buildEnv(task, context),
        cwd: context.workingDir,
        timeout: this.timeout
      })
      
      this.status = "idle"
      
      const executionResult = {
        ok: result.ok,
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
        duration: Date.now() - startTime,
        executor: this.name
      }
      
      this.emit("complete", { taskId: task.id, result: executionResult })
      return executionResult
      
    } catch (e) {
      this.status = "error"
      this.emit("error", { taskId: task.id, error: e.message })
      
      return {
        ok: false,
        error: e.message,
        duration: Date.now() - startTime,
        executor: this.name
      }
    }
  }
  
  /**
   * 构建命令参数
   */
  buildArgs(task, context) {
    // 子类可以重写此方法
    return this.args
  }
  
  /**
   * 构建环境变量
   */
  buildEnv(task, context) {
    return {
      ...process.env,
      SCC_TASK_ID: task.id,
      SCC_TASK_TYPE: task.type,
      SCC_TASK_TITLE: task.title,
      SCC_TASK_PROMPT: task.prompt || task.goal || task.title,
      SCC_TASK_ROLE: task.role,
      SCC_TASK_MODEL: task.model,
      SCC_CONTEXT: JSON.stringify(context),
      ...context.env
    }
  }
  
  /**
   * 运行命令
   */
  runCommand(command, args, options = {}) {
    return new Promise((resolve, reject) => {
      let stdout = ""
      let stderr = ""
      
      const child = spawn(command, args, {
        shell: true,
        env: options.env || process.env,
        cwd: options.cwd,
        timeout: options.timeout
      })
      
      child.stdout.on("data", (data) => {
        stdout += data.toString()
        this.emit("stdout", { data: data.toString() })
      })
      
      child.stderr.on("data", (data) => {
        stderr += data.toString()
        this.emit("stderr", { data: data.toString() })
      })
      
      child.on("close", (code) => {
        resolve({
          ok: code === 0,
          exitCode: code,
          stdout,
          stderr
        })
      })
      
      child.on("error", (err) => {
        reject(err)
      })
    })
  }
}

/**
 * Oltcli 执行器
 */
export class OltcliExecutor extends CliExecutor {
  constructor(config = {}) {
    super("oltcli", {
      command: config.command || "node /app/scc-bd/L6_execution_layer/oltcli.mjs",
      timeout: config.timeout || 600000,
      ...config
    })
  }
  
  buildEnv(task, context) {
    const env = super.buildEnv(task, context)
    
    // Oltcli 特定的环境变量
    env.SCC_SYSTEM_PROMPT = context.systemPrompt || `You are a ${task.role} agent.`
    env.SCC_RELEVANT_SKILLS = JSON.stringify(context.skills || [])
    env.SCC_TASK_FILES = JSON.stringify(task.files || [])
    
    return env
  }
}

/**
 * Codexcli 执行器
 */
export class CodexcliExecutor extends CliExecutor {
  constructor(config = {}) {
    super("codexcli", {
      command: config.command || "codex",
      timeout: config.timeout || 600000,
      ...config
    })
  }
  
  buildArgs(task, context) {
    // Codex CLI 参数格式
    return [
      "--model", task.model || "gpt-4",
      "--prompt", task.prompt || task.goal || task.title
    ]
  }
  
  buildEnv(task, context) {
    const env = super.buildEnv(task, context)
    
    // Codex 特定的环境变量
    env.CODEX_SYSTEM_PROMPT = context.systemPrompt || `You are a ${task.role} agent.`
    env.CODEX_WORKING_DIR = context.workingDir
    
    return env
  }
}

/**
 * Function 执行器（用于自定义函数）
 */
export class FunctionExecutor extends Executor {
  constructor(name, config) {
    super(name, { ...config, type: "function" })
    this.fn = config.function
  }
  
  async validate() {
    return typeof this.fn === "function"
  }
  
  async execute(task, context = {}) {
    this.status = "running"
    this.emit("start", { taskId: task.id, executor: this.name })
    
    const startTime = Date.now()
    
    try {
      const result = await this.fn(task, context)
      
      this.status = "idle"
      
      const executionResult = {
        ok: true,
        result,
        duration: Date.now() - startTime,
        executor: this.name
      }
      
      this.emit("complete", { taskId: task.id, result: executionResult })
      return executionResult
      
    } catch (e) {
      this.status = "error"
      this.emit("error", { taskId: task.id, error: e.message })
      
      return {
        ok: false,
        error: e.message,
        duration: Date.now() - startTime,
        executor: this.name
      }
    }
  }
}

/**
 * Executor Registry - 执行器注册表
 */
export class ExecutorRegistry extends EventEmitter {
  constructor() {
    super()
    this.executors = new Map()
    this.defaultExecutor = null
  }
  
  /**
   * 注册执行器
   */
  register(name, executor) {
    this.executors.set(name, executor)
    this.emit("registered", { name, executor })
    
    // 第一个注册的执行器设为默认
    if (!this.defaultExecutor) {
      this.defaultExecutor = name
    }
    
    return this
  }
  
  /**
   * 获取执行器
   */
  get(name) {
    return this.executors.get(name)
  }
  
  /**
   * 获取默认执行器
   */
  getDefault() {
    return this.get(this.defaultExecutor)
  }
  
  /**
   * 设置默认执行器
   */
  setDefault(name) {
    if (this.executors.has(name)) {
      this.defaultExecutor = name
    }
    return this
  }
  
  /**
   * 列出所有执行器
   */
  list() {
    return Array.from(this.executors.entries()).map(([name, executor]) => ({
      name,
      ...executor.getInfo()
    }))
  }
  
  /**
   * 验证所有执行器
   */
  async validateAll() {
    const results = []
    
    for (const [name, executor] of this.executors) {
      const isValid = await executor.validate()
      results.push({ name, valid: isValid })
    }
    
    return results
  }
  
  /**
   * 创建标准执行器集合
   */
  static createStandard(config = {}) {
    const registry = new ExecutorRegistry()
    
    // 注册 oltcli
    registry.register("oltcli", new OltcliExecutor(config.oltcli))
    
    // 注册 codexcli（如果配置了）
    if (config.codexcli !== false) {
      registry.register("codexcli", new CodexcliExecutor(config.codexcli))
    }
    
    return registry
  }
}

export default ExecutorRegistry
