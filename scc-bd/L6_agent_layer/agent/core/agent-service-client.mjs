#!/usr/bin/env node
/**
 * Agent Service Client
 * 
 * 统一的 Agent Service 客户端
 * 整合 Skills、Context、Roles 等所有服务
 */

const CONFIG = {
  AGENT_SERVICE_URL: process.env.AGENT_SERVICE_URL || "http://localhost:18000"
}

/**
 * Agent Service Client 类
 */
export class AgentServiceClient {
  constructor(baseUrl = CONFIG.AGENT_SERVICE_URL) {
    this.baseUrl = baseUrl
  }
  
  // ==================== Health ====================
  
  async health() {
    const response = await fetch(`${this.baseUrl}/health`)
    return await response.json()
  }
  
  // ==================== Skills API ====================
  
  async searchSkills(query, options = {}) {
    const params = new URLSearchParams({ q: query, ...options })
    const response = await fetch(`${this.baseUrl}/skills/search?${params}`)
    return await response.json()
  }
  
  async findSkillsForTask(task, role, limit = 5) {
    const response = await fetch(`${this.baseUrl}/skills/find-for-task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, role, limit })
    })
    return await response.json()
  }
  
  async getSkill(skillId) {
    const response = await fetch(`${this.baseUrl}/skills/get?id=${skillId}`)
    return await response.json()
  }
  
  async listSkills(options = {}) {
    const params = new URLSearchParams(options)
    const response = await fetch(`${this.baseUrl}/skills/list?${params}`)
    return await response.json()
  }
  
  async getSkillsStats() {
    const response = await fetch(`${this.baseUrl}/skills/stats`)
    return await response.json()
  }
  
  // ==================== Context API ====================
  
  async renderContext(params) {
    const response = await fetch(`${this.baseUrl}/context/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params)
    })
    return await response.json()
  }
  
  async renderContextSlot(slot, params) {
    const response = await fetch(`${this.baseUrl}/context/render/slot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot, params })
    })
    return await response.json()
  }
  
  /**
   * 快速渲染完整上下文（用于 Agent 执行任务）
   */
  async quickRender(task, role, roleConfig, skills = []) {
    return this.renderContext({
      repoRoot: "/app/scc-bd",
      role,
      roleConfig,
      task,
      mode: "execute",
      files: task.files || [],
      skills,
      state: null,
      tools: null
    })
  }
}

export default AgentServiceClient
