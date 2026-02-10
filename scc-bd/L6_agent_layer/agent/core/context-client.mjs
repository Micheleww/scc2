#!/usr/bin/env node
/**
 * Context Renderer Client
 * 
 * 用于 Agent 查询 Context Renderer Service
 * 基于 opencode_executor 的七个 slot 设计
 */

const CONFIG = {
  CONTEXT_RENDERER_URL: process.env.CONTEXT_RENDERER_URL || "http://localhost:18004"
}

/**
 * Context Renderer Client 类
 */
export class ContextRendererClient {
  constructor(baseUrl = CONFIG.CONTEXT_RENDERER_URL) {
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
   * 渲染完整上下文包（七个 slot）
   */
  async render(params) {
    const response = await fetch(`${this.baseUrl}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params)
    })
    return await response.json()
  }
  
  /**
   * 渲染单个 slot
   */
  async renderSlot(slot, params) {
    const response = await fetch(`${this.baseUrl}/render/slot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot, params })
    })
    return await response.json()
  }
  
  /**
   * 渲染为文本格式
   */
  async renderText(params) {
    const response = await fetch(`${this.baseUrl}/render/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params)
    })
    return await response.text()
  }
  
  /**
   * 快速渲染（常用参数）
   */
  async quickRender(task, role, roleConfig, options = {}) {
    return this.render({
      repoRoot: options.repoRoot || "/app/scc-bd",
      role,
      roleConfig,
      task,
      mode: options.mode || "execute",
      files: task.files || [],
      skills: options.skills || [],
      state: options.state || null,
      tools: options.tools || null
    })
  }
}

export default ContextRendererClient
