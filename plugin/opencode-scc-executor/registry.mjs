/**
 * SCC Executor Registry
 * 
 * 管理所有可用的执行器，包括 OpenCode、Codex 等
 */

import { existsSync } from 'fs';
import { OpenCodeExecutor, loadExecutorFromConfig } from './opencode_executor.mjs';
import { OpenCodeWrapper, createWrapper } from './opencode_wrapper.mjs';

/**
 * 执行器注册表类
 */
export class ExecutorRegistry {
  constructor() {
    this.executors = new Map();
    this.configs = new Map();
    this.defaultExecutor = null;
  }

  /**
   * 初始化注册表
   */
  async initialize() {
    console.log('[ExecutorRegistry] Initializing...');

    // 尝试加载 OpenCode 执行器
    const opencodeBinary = 'C:\\scc\\plugin\\opencode\\opencode.exe';
    const binaryExists = existsSync(opencodeBinary);

    if (binaryExists) {
      // 使用原生二进制
      try {
        const opencodeConfig = await this.loadConfig('opencode');
        const { createExecutor } = await import('./opencode_executor.mjs');
        const opencode = await createExecutor(opencodeConfig.opencode || opencodeConfig);
        this.register('opencode', opencode, { priority: 1, type: 'native' });
        console.log('[ExecutorRegistry] OpenCode native executor registered');
      } catch (error) {
        console.warn('[ExecutorRegistry] Failed to load OpenCode native:', error.message);
        await this.loadWrapper();
      }
    } else {
      // 使用包装器
      console.log('[ExecutorRegistry] OpenCode binary not found, using wrapper');
      await this.loadWrapper();
    }

    // 设置默认执行器
    if (this.executors.has('opencode')) {
      this.defaultExecutor = 'opencode';
    }

    console.log(`[ExecutorRegistry] Initialized with ${this.executors.size} executors`);
    return this;
  }

  /**
   * 加载包装器
   */
  async loadWrapper() {
    try {
      const config = await this.loadConfig('opencode');
      const wrapper = await createWrapper(config.opencode || config);
      this.register('opencode', wrapper, { priority: 1, type: 'wrapper' });
      console.log('[ExecutorRegistry] OpenCode wrapper registered');
    } catch (error) {
      console.warn('[ExecutorRegistry] Failed to load OpenCode wrapper:', error.message);
    }
  }

  /**
   * 注册执行器
   */
  register(name, executor, options = {}) {
    this.executors.set(name, {
      instance: executor,
      name,
      priority: options.priority || 0,
      enabled: options.enabled !== false,
      type: options.type || 'unknown',
      config: options.config || {}
    });
  }

  /**
   * 获取执行器
   */
  get(name) {
    const entry = this.executors.get(name);
    return entry?.instance || null;
  }

  /**
   * 获取默认执行器
   */
  getDefault() {
    if (this.defaultExecutor) {
      return this.get(this.defaultExecutor);
    }
    
    // 返回第一个可用的执行器
    for (const [name, entry] of this.executors) {
      if (entry.enabled) {
        return entry.instance;
      }
    }
    
    return null;
  }

  /**
   * 列出所有执行器
   */
  list() {
    const result = [];
    for (const [name, entry] of this.executors) {
      result.push({
        name,
        priority: entry.priority,
        enabled: entry.enabled,
        type: entry.type
      });
    }
    return result.sort((a, b) => b.priority - a.priority);
  }

  /**
   * 执行健康检查
   */
  async healthCheck() {
    const results = {};
    
    for (const [name, entry] of this.executors) {
      if (entry.instance?.healthCheck) {
        try {
          results[name] = await entry.instance.healthCheck();
        } catch (error) {
          results[name] = {
            status: 'error',
            error: error.message
          };
        }
      }
    }
    
    return results;
  }

  /**
   * 加载配置文件
   */
  async loadConfig(name) {
    // 配置文件路径 - 相对于当前目录
    const configPath = new URL(`config/${name}.config.json`, import.meta.url);
    
    try {
      const { readFile } = await import('fs/promises');
      const data = await readFile(configPath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      console.warn(`[ExecutorRegistry] Config not found: ${configPath}`);
      return {};
    }
  }

  /**
   * 根据角色选择执行器
   */
  selectForRole(role) {
    // 角色到执行器的映射
    const roleMapping = {
      'engineer': 'opencode',
      'integrator': 'opencode',
      'designer': 'opencode',
      'auditor': 'opencode',
      'verifier_judge': 'opencode'
    };

    const executorName = roleMapping[role] || this.defaultExecutor;
    return this.get(executorName);
  }

  /**
   * 根据任务类型选择执行器
   */
  selectForTask(task) {
    // 根据任务属性选择执行器
    if (task.executor) {
      return this.get(task.executor);
    }

    if (task.role) {
      return this.selectForRole(task.role);
    }

    // 默认执行器
    return this.getDefault();
  }
}

// 单例实例
let registryInstance = null;

/**
 * 获取注册表单例
 */
export async function getRegistry() {
  if (!registryInstance) {
    registryInstance = new ExecutorRegistry();
    await registryInstance.initialize();
  }
  return registryInstance;
}

/**
 * 重置注册表（用于测试）
 */
export function resetRegistry() {
  registryInstance = null;
}

// 默认导出
export default ExecutorRegistry;
