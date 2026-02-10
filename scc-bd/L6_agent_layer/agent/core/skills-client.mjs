#!/usr/bin/env node
/**
 * Skills Client
 * 
 * 用于 Agent 查询 Skills Registry Service
 * 替代直接加载所有 skills
 */

const CONFIG = {
  SKILLS_REGISTRY_URL: process.env.SKILLS_REGISTRY_URL || "http://localhost:18001"
}

/**
 * Skills Client 类
 */
export class SkillsClient {
  constructor(baseUrl = CONFIG.SKILLS_REGISTRY_URL) {
    this.baseUrl = baseUrl
  }
  
  /**
   * 健康检查
   */
  async health() {
    try {
      const response = await fetch(`${this.baseUrl}/health`)
      return await response.json()
    } catch (e) {
      return { status: "error", error: e.message }
    }
  }
  
  /**
   * 搜索 Skills
   */
  async search(query, options = {}) {
    const params = new URLSearchParams({ q: query, ...options })
    const response = await fetch(`${this.baseUrl}/search?${params}`)
    return await response.json()
  }
  
  /**
   * 为任务查找相关 Skills
   */
  async findForTask(task, role, limit = 5) {
    const response = await fetch(`${this.baseUrl}/find-for-task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, role, limit })
    })
    return await response.json()
  }
  
  /**
   * 获取单个 Skill
   */
  async get(skillId) {
    const response = await fetch(`${this.baseUrl}/get?id=${skillId}`)
    return await response.json()
  }
  
  /**
   * 列出 Skills
   */
  async list(options = {}) {
    const params = new URLSearchParams(options)
    const response = await fetch(`${this.baseUrl}/list?${params}`)
    return await response.json()
  }
  
  /**
   * 获取统计信息
   */
  async stats() {
    const response = await fetch(`${this.baseUrl}/stats`)
    return await response.json()
  }
}

export default SkillsClient
