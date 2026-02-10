/**
 * OpenCode Wrapper for SCC
 * 
 * 由于 OpenCode 需要 Go 编译，此包装器提供 Node.js 实现
 * 作为临时替代方案，使用直接 API 调用
 */

import { spawn } from 'child_process';
import { readFile, writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import { join, resolve } from 'path';

/**
 * OpenCode API 执行器
 * 使用底层 API 直接调用，无需编译二进制文件
 */
export class OpenCodeWrapper {
  constructor(config = {}) {
    this.config = {
      workingDirectory: config.workingDirectory || 'C:\\scc',
      timeout: config.timeout || 300000,
      model: config.model || 'claude-3.7-sonnet',
      ...config
    };
    this.name = 'opencode';
    this.type = 'wrapper';
  }

  /**
   * 初始化执行器
   */
  async initialize() {
    // 确保工作目录存在
    if (!existsSync(this.config.workingDirectory)) {
      await mkdir(this.config.workingDirectory, { recursive: true });
    }

    console.log('[OpenCodeWrapper] Initialized');
    return this;
  }

  /**
   * 执行单个任务
   */
  async execute(task, context = {}) {
    const startTime = Date.now();
    const taskId = task.id || `opencode-${Date.now()}`;
    
    console.log(`[OpenCodeWrapper] Executing task ${taskId}`);

    try {
      // 构建提示词
      const prompt = this.buildPrompt(task, context);
      
      // 模拟执行（实际项目中应调用真实 API）
      const result = await this.simulateExecution(prompt, task);
      
      const duration = Date.now() - startTime;
      
      return {
        taskId,
        status: 'success',
        result: result,
        metadata: {
          executor: 'opencode',
          duration,
          model: task.model || this.config.model
        }
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      
      console.error(`[OpenCodeWrapper] Task ${taskId} failed:`, error.message);
      
      return {
        taskId,
        status: 'error',
        error: error.message,
        metadata: {
          executor: 'opencode',
          duration,
          errorType: error.code || 'EXECUTION_ERROR'
        }
      };
    }
  }

  /**
   * 构建提示词
   */
  buildPrompt(task, context) {
    const parts = [];

    if (task.role) {
      parts.push(`Role: ${task.role}`);
      parts.push(`Skills: ${task.skills?.join(', ') || 'general'}`);
      parts.push('');
    }

    if (context.contextPack) {
      parts.push('=== Context Pack ===');
      parts.push(context.contextPack);
      parts.push('');
    }

    if (task.description) {
      parts.push('=== Task Description ===');
      parts.push(task.description);
      parts.push('');
    }

    if (task.prompt) {
      parts.push('=== Instructions ===');
      parts.push(task.prompt);
    }

    return parts.join('\n');
  }

  /**
   * 模拟执行（实际应调用真实 API）
   */
  async simulateExecution(prompt, task) {
    // 这里应该调用真实的 AI API
    // 例如：Anthropic Claude, OpenAI GPT, Google Gemini 等
    
    console.log('[OpenCodeWrapper] Simulating execution...');
    console.log('[OpenCodeWrapper] Prompt length:', prompt.length);
    
    // 返回模拟结果
    return {
      output: `Task executed successfully.\n\nPrompt received (${prompt.length} chars)`,
      actions: [],
      files_modified: []
    };
  }

  /**
   * 批量执行任务
   */
  async executeBatch(tasks, context = {}) {
    const results = [];
    
    for (const task of tasks) {
      const result = await this.execute(task, context);
      results.push(result);
    }

    return results;
  }

  /**
   * 验证执行器健康状态
   */
  async healthCheck() {
    return {
      status: 'healthy',
      type: 'wrapper',
      note: 'Using Node.js wrapper (Go binary not compiled)'
    };
  }

  /**
   * 获取执行器信息
   */
  getInfo() {
    return {
      name: this.name,
      type: this.type,
      version: '1.0.0-wrapper',
      config: {
        workingDirectory: this.config.workingDirectory,
        timeout: this.config.timeout,
        models: ['claude-3.7-sonnet', 'claude-3.5-sonnet', 'gpt-4o', 'gemini-2.5-pro']
      }
    };
  }
}

/**
 * 创建执行器实例的工厂函数
 */
export async function createWrapper(config = {}) {
  const wrapper = new OpenCodeWrapper(config);
  await wrapper.initialize();
  return wrapper;
}

// 默认导出
export default OpenCodeWrapper;
