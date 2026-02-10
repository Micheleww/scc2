#!/usr/bin/env node
/**
 * Roles - 可插拔 Role 系统
 * 
 * 特性：动态加载、热切换、Role 组合
 */

import fs from "node:fs"
import path from "node:path"
import { EventEmitter } from "node:events"

/**
 * Role 类
 */
export class Role {
  constructor(name, config = {}) {
    this.name = name
    this.config = config
    
    // Role 属性
    this.systemPrompt = config.system_prompt || config.systemPrompt || ""
    this.capabilities = config.capabilities || []
    this.skills = config.skills || [] // Role 默认挂载的 skills
    this.model = config.model || "opencode/kimi-k2.5-free"
    this.executor = config.executor || "oltcli"
    
    // 行为配置
    this.behavior = {
      canDecompose: config.canDecompose || false, // 是否能分解任务
      canExecute: config.canExecute || true,      // 是否能执行任务
      autoRetry: config.autoRetry || 0,           // 自动重试次数
      timeout: config.timeout || 600000           // 超时时间
    }
    
    // Hooks
    this.hooks = config.hooks || {
      beforeExecute: null,
      afterExecute: null,
      onError: null
    }
  }
  
  /**
   * 获取完整的系统提示词
   */
  getSystemPrompt(context = {}) {
    let prompt = this.systemPrompt
    
    // 添加上下文
    if (context.task) {
      prompt += `\n\nCurrent Task: ${context.task.title}`
      if (context.task.description) {
        prompt += `\nDescription: ${context.task.description}`
      }
    }
    
    // 添加能力描述
    if (this.capabilities.length > 0) {
      prompt += `\n\nYour capabilities:\n${this.capabilities.map(c => `- ${c}`).join("\n")}`
    }
    
    // 添加挂载的 skills
    if (this.skills.length > 0) {
      prompt += `\n\nAvailable skills: ${this.skills.join(", ")}`
    }
    
    return prompt
  }
  
  /**
   * 检查是否匹配任务
   */
  matches(task) {
    // 如果任务指定了 role，直接匹配
    if (task.role === this.name) return 1.0
    
    // 根据关键词匹配
    const goal = (task.goal || task.title || task.description || "").toLowerCase()
    const keywords = this.config.keywords || []
    
    let score = 0
    for (const keyword of keywords) {
      if (goal.includes(keyword.toLowerCase())) {
        score += 0.3
      }
    }
    
    return Math.min(score, 0.9) // 最高 0.9，只有明确指定 role 才能得 1.0
  }
  
  /**
   * 序列化
   */
  toJSON() {
    return {
      name: this.name,
      systemPrompt: this.systemPrompt,
      capabilities: this.capabilities,
      skills: this.skills,
      model: this.model,
      executor: this.executor,
      behavior: this.behavior,
      hooks: this.hooks
    }
  }
}

/**
 * Role Registry - Role 注册表
 */
export class RoleRegistry extends EventEmitter {
  constructor(options = {}) {
    super()
    this.rolesDir = options.rolesDir || "/app/scc-bd/L4_prompt_layer/roles"
    this.roles = new Map()
    this.defaultRole = options.defaultRole || "executor"
  }
  
  /**
   * 初始化并加载所有 Role
   */
  async init() {
    this.emit("initializing")
    
    // 加载内置 roles
    this.loadBuiltInRoles()
    
    // 从目录加载自定义 roles
    await this.loadFromDirectory()
    
    this.emit("initialized", { count: this.roles.size })
    return this
  }
  
  /**
   * 加载内置基础 roles
   */
  loadBuiltInRoles() {
    const builtInRoles = {
      executor: new Role("executor", {
        systemPrompt: "You are an executor agent. Your job is to execute tasks efficiently and accurately.",
        capabilities: ["execute", "implement", "code"],
        keywords: ["execute", "implement", "code", "build", "开发", "实现"],
        canExecute: true,
        canDecompose: false
      }),
      
      planner: new Role("planner", {
        systemPrompt: "You are a planner agent. Your job is to break down complex tasks into manageable subtasks.",
        capabilities: ["plan", "decompose", "organize"],
        keywords: ["plan", "decompose", "organize", "规划", "分解", "计划"],
        canExecute: false,
        canDecompose: true
      }),
      
      qa: new Role("qa", {
        systemPrompt: "You are a QA agent. Your job is to verify and validate work.",
        capabilities: ["test", "verify", "validate", "check"],
        keywords: ["test", "verify", "validate", "check", "验证", "检查", "测试"],
        canExecute: true,
        canDecompose: false
      }),
      
      architect: new Role("architect", {
        systemPrompt: "You are an architect agent. Your job is to design systems and make high-level decisions.",
        capabilities: ["design", "architect", "decide"],
        keywords: ["design", "architect", "decide", "架构", "设计"],
        canExecute: false,
        canDecompose: true
      }),
      
      doc: new Role("doc", {
        systemPrompt: "You are a documentation agent. Your job is to create and maintain documentation.",
        capabilities: ["document", "write", "explain"],
        keywords: ["doc", "document", "write", "explain", "文档", "说明"],
        canExecute: true,
        canDecompose: false
      }),
      
      auditor: new Role("auditor", {
        systemPrompt: "You are an auditor agent. Your job is to review and audit code and processes.",
        capabilities: ["audit", "review", "inspect"],
        keywords: ["audit", "review", "inspect", "审计", "审核", "检查"],
        canExecute: true,
        canDecompose: false
      })
    }
    
    for (const [name, role] of Object.entries(builtInRoles)) {
      this.register(role)
    }
  }
  
  /**
   * 从目录加载 Role
   */
  async loadFromDirectory() {
    try {
      if (!fs.existsSync(this.rolesDir)) {
        console.warn(`[RoleRegistry] Roles directory not found: ${this.rolesDir}`)
        return
      }
      
      const files = fs.readdirSync(this.rolesDir)
      const roleFiles = files.filter(f => f.endsWith('.json'))
      
      for (const file of roleFiles) {
        const rolePath = path.join(this.rolesDir, file)
        try {
          const content = fs.readFileSync(rolePath, 'utf-8')
          const config = JSON.parse(content)
          const roleName = path.basename(file, '.json')
          
          const role = new Role(roleName, config)
          this.register(role)
        } catch (e) {
          console.error(`[RoleRegistry] Failed to load role ${file}:`, e.message)
        }
      }
    } catch (e) {
      console.error("[RoleRegistry] Failed to load roles from directory:", e.message)
    }
  }
  
  /**
   * 注册 Role
   */
  register(role) {
    this.roles.set(role.name, role)
    this.emit("registered", { name: role.name, role })
    return this
  }
  
  /**
   * 获取 Role
   */
  get(name) {
    return this.roles.get(name)
  }
  
  /**
   * 获取默认 Role
   */
  getDefault() {
    return this.get(this.defaultRole)
  }
  
  /**
   * 设置默认 Role
   */
  setDefault(name) {
    if (this.roles.has(name)) {
      this.defaultRole = name
    }
    return this
  }
  
  /**
   * 为任务选择最佳 Role
   */
  selectForTask(task) {
    // 如果任务明确指定了 role
    if (task.role && this.roles.has(task.role)) {
      return this.get(task.role)
    }
    
    // 根据任务内容匹配
    let bestRole = null
    let bestScore = 0
    
    for (const role of this.roles.values()) {
      const score = role.matches(task)
      if (score > bestScore) {
        bestScore = score
        bestRole = role
      }
    }
    
    return bestRole || this.getDefault()
  }
  
  /**
   * 列出所有 Roles
   */
  list() {
    return Array.from(this.roles.values()).map(role => ({
      name: role.name,
      capabilities: role.capabilities,
      model: role.model,
      executor: role.executor,
      behavior: role.behavior
    }))
  }
  
  /**
   * 组合多个 Roles
   */
  compose(roleNames, options = {}) {
    const roles = roleNames.map(name => this.get(name)).filter(Boolean)
    
    if (roles.length === 0) {
      return this.getDefault()
    }
    
    if (roles.length === 1) {
      return roles[0]
    }
    
    // 创建组合 Role
    const composedName = options.name || `composed_${roleNames.join("_")}`
    
    // 合并 system prompts
    const combinedPrompt = roles
      .map(r => r.systemPrompt)
      .filter(Boolean)
      .join("\n\n---\n\n")
    
    // 合并 capabilities
    const allCapabilities = [...new Set(roles.flatMap(r => r.capabilities))]
    
    // 合并 skills
    const allSkills = [...new Set(roles.flatMap(r => r.skills))]
    
    // 合并行为配置（取最宽松）
    const combinedBehavior = {
      canDecompose: roles.some(r => r.behavior.canDecompose),
      canExecute: roles.some(r => r.behavior.canExecute),
      autoRetry: Math.max(...roles.map(r => r.behavior.autoRetry)),
      timeout: Math.max(...roles.map(r => r.behavior.timeout))
    }
    
    return new Role(composedName, {
      systemPrompt: combinedPrompt,
      capabilities: allCapabilities,
      skills: allSkills,
      model: options.model || roles[0].model,
      executor: options.executor || roles[0].executor,
      behavior: combinedBehavior
    })
  }
  
  /**
   * 热重载 Role
   */
  async reload(roleName) {
    const rolePath = path.join(this.rolesDir, `${roleName}.json`)
    
    try {
      if (fs.existsSync(rolePath)) {
        const content = fs.readFileSync(rolePath, 'utf-8')
        const config = JSON.parse(content)
        const role = new Role(roleName, config)
        this.register(role)
        this.emit("reloaded", { name: roleName })
        return role
      }
    } catch (e) {
      console.error(`[RoleRegistry] Failed to reload role ${roleName}:`, e.message)
    }
    
    return null
  }
}

export default RoleRegistry
