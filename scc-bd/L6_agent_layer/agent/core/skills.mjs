#!/usr/bin/env node
/**
 * Skills - 可插拔 Skills 系统
 * 
 * 特性：动态挂载、技能组合、技能商店
 */

import fs from "node:fs"
import path from "node:path"
import { EventEmitter } from "node:events"

/**
 * Skill 类
 */
export class Skill {
  constructor(id, config = {}) {
    this.id = id
    this.name = config.name || id
    this.description = config.description || ""
    this.category = config.category || "general"
    
    // 技能内容
    this.prompt = config.prompt || "" // 技能提示词
    this.examples = config.examples || [] // 使用示例
    this.parameters = config.parameters || [] // 参数定义
    
    // 元数据
    this.keywords = config.keywords || []
    this.roles = config.roles || [] // 适用的 roles
    this.dependencies = config.dependencies || [] // 依赖的其他 skills
    
    // 版本
    this.version = config.version || "1.0.0"
    this.author = config.author || ""
  }
  
  /**
   * 渲染技能提示词
   */
  render(context = {}) {
    let rendered = this.prompt
    
    // 替换变量
    for (const [key, value] of Object.entries(context)) {
      rendered = rendered.replace(new RegExp(`{{${key}}}`, 'g'), value)
    }
    
    return rendered
  }
  
  /**
   * 检查是否匹配任务
   */
  matches(task, roleName) {
    let score = 0
    
    const goal = (task.goal || task.title || task.description || "").toLowerCase()
    
    // 关键词匹配
    for (const keyword of this.keywords) {
      if (goal.includes(keyword.toLowerCase())) {
        score += 0.5
      }
    }
    
    // Role 匹配
    if (roleName && this.roles.includes(roleName)) {
      score += 0.3
    }
    
    return Math.min(score, 1.0)
  }
  
  /**
   * 获取技能信息
   */
  getInfo() {
    return {
      id: this.id,
      name: this.name,
      description: this.description,
      category: this.category,
      version: this.version,
      keywords: this.keywords,
      roles: this.roles
    }
  }
}

/**
 * Skill Registry - Skills 注册表
 */
export class SkillRegistry extends EventEmitter {
  constructor(options = {}) {
    super()
    this.skillsDir = options.skillsDir || "/app/scc-bd/L4_prompt_layer/skills"
    this.skills = new Map() // id -> Skill
    this.byCategory = new Map() // category -> Set(skillIds)
    this.byRole = new Map() // role -> Set(skillIds)
  }
  
  /**
   * 初始化并加载所有 Skills
   */
  async init() {
    this.emit("initializing")
    await this.loadFromDirectory()
    this.emit("initialized", { count: this.skills.size })
    return this
  }
  
  /**
   * 从目录加载 Skills
   */
  async loadFromDirectory() {
    try {
      if (!fs.existsSync(this.skillsDir)) {
        console.warn(`[SkillRegistry] Skills directory not found: ${this.skillsDir}`)
        return
      }
      
      const categories = fs.readdirSync(this.skillsDir)
      
      for (const category of categories) {
        const categoryPath = path.join(this.skillsDir, category)
        const stat = fs.statSync(categoryPath)
        
        if (!stat.isDirectory()) continue
        
        const skillDirs = fs.readdirSync(categoryPath)
        
        for (const skillDir of skillDirs) {
          const skillPath = path.join(categoryPath, skillDir, 'skill.json')
          
          if (fs.existsSync(skillPath)) {
            try {
              const content = fs.readFileSync(skillPath, 'utf-8')
              const config = JSON.parse(content)
              const skillId = `${category}.${skillDir}`
              
              const skill = new Skill(skillId, { ...config, category })
              this.register(skill)
            } catch (e) {
              console.error(`[SkillRegistry] Failed to load skill ${skillDir}:`, e.message)
            }
          }
        }
      }
    } catch (e) {
      console.error("[SkillRegistry] Failed to load skills:", e.message)
    }
  }
  
  /**
   * 注册 Skill
   */
  register(skill) {
    this.skills.set(skill.id, skill)
    
    // 更新分类索引
    if (!this.byCategory.has(skill.category)) {
      this.byCategory.set(skill.category, new Set())
    }
    this.byCategory.get(skill.category).add(skill.id)
    
    // 更新 Role 索引
    for (const role of skill.roles) {
      if (!this.byRole.has(role)) {
        this.byRole.set(role, new Set())
      }
      this.byRole.get(role).add(skill.id)
    }
    
    this.emit("registered", { id: skill.id, skill })
    return this
  }
  
  /**
   * 获取 Skill
   */
  get(id) {
    return this.skills.get(id)
  }
  
  /**
   * 为任务查找相关 Skills
   */
  findForTask(task, roleName, options = {}) {
    const matches = []
    
    for (const skill of this.skills.values()) {
      const score = skill.matches(task, roleName)
      if (score > 0) {
        matches.push({ skill, score })
      }
    }
    
    // 按分数排序
    matches.sort((a, b) => b.score - a.score)
    
    // 限制数量
    const limit = options.limit || 5
    return matches.slice(0, limit).map(m => m.skill)
  }
  
  /**
   * 获取 Role 相关的 Skills
   */
  getForRole(roleName) {
    const skillIds = this.byRole.get(roleName)
    if (!skillIds) return []
    
    return Array.from(skillIds).map(id => this.get(id)).filter(Boolean)
  }
  
  /**
   * 获取分类下的 Skills
   */
  getByCategory(category) {
    const skillIds = this.byCategory.get(category)
    if (!skillIds) return []
    
    return Array.from(skillIds).map(id => this.get(id)).filter(Boolean)
  }
  
  /**
   * 组合多个 Skills
   */
  compose(skillIds, options = {}) {
    const skills = skillIds.map(id => this.get(id)).filter(Boolean)
    
    if (skills.length === 0) {
      return null
    }
    
    // 合并提示词
    const combinedPrompt = skills
      .map(s => `## ${s.name}\n${s.prompt}`)
      .join("\n\n")
    
    // 合并示例
    const allExamples = skills.flatMap(s => s.examples)
    
    // 创建组合 Skill
    return new Skill(options.name || `composed_${skillIds.join("_")}`, {
      name: options.name || "Composed Skill",
      description: options.description || `Combined: ${skills.map(s => s.name).join(", ")}`,
      category: options.category || "composed",
      prompt: combinedPrompt,
      examples: allExamples,
      keywords: [...new Set(skills.flatMap(s => s.keywords))]
    })
  }
  
  /**
   * 列出所有 Skills
   */
  list(options = {}) {
    let skills = Array.from(this.skills.values())
    
    if (options.category) {
      skills = skills.filter(s => s.category === options.category)
    }
    
    if (options.role) {
      skills = skills.filter(s => s.roles.includes(options.role))
    }
    
    return skills.map(s => s.getInfo())
  }
  
  /**
   * 获取分类列表
   */
  getCategories() {
    return Array.from(this.byCategory.keys())
  }
  
  /**
   * 渲染技能上下文
   */
  renderContext(skills, context = {}) {
    if (!skills || skills.length === 0) {
      return ""
    }
    
    const rendered = skills.map(skill => {
      if (typeof skill === 'string') {
        skill = this.get(skill)
      }
      if (!skill) return ""
      
      return skill.render(context)
    }).filter(Boolean)
    
    if (rendered.length === 0) {
      return ""
    }
    
    return `\n\n## Skills\n\n${rendered.join("\n\n---\n\n")}`
  }
}

export default SkillRegistry
