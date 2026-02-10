#!/usr/bin/env node
/**
 * SCC Unified Agent
 * 
 * 统一任务执行平台，整合：
 * - TaskBox: 统一任务容器（父子任务）
 * - ExecutorRegistry: 可插拔执行器（oltcli/codexcli）
 * - RoleRegistry: 可插拔 Role
 * - SkillRegistry: 可插拔 Skills
 * - ContextRenderer: 上下文渲染
 * - HookSystem: 统一 Hook
 * 
 * 工作流：任务目标 → 父任务Box → Hook → Agent → 分解到子任务Box → Hook → Agent执行
 */

import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

// 导入核心模块
import { TaskBox, Task } from "./core/taskbox.mjs"
import { ExecutorRegistry, OltcliExecutor, CodexcliExecutor } from "./core/executors.mjs"
import { RoleRegistry } from "./core/roles.mjs"
import { SkillRegistry } from "./core/skills.mjs"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/**
 * 上下文渲染器 - 基于现有 opencode_executor 的 buildPrompt
 */
class ContextRenderer {
  constructor(config = {}) {
    this.config = config
  }
  
  /**
   * 渲染完整上下文
   */
  render(task, role, skills, context = {}) {
    const parts = []
    
    // 1. 系统提示词（Role）
    if (role) {
      parts.push("=== System ===")
      parts.push(role.getSystemPrompt({ task }))
      parts.push("")
    }
    
    // 2. Skills 上下文
    if (skills && skills.length > 0) {
      parts.push("=== Skills ===")
      for (const skill of skills) {
        parts.push(`## ${skill.name}`)
        parts.push(skill.render({ task }))
        parts.push("")
      }
      parts.push("")
    }
    
    // 3. 任务上下文包
    if (context.contextPack) {
      parts.push("=== Context ===")
      parts.push(context.contextPack)
      parts.push("")
    }
    
    // 4. 相关文件