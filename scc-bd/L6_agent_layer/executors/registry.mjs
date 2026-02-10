/**
 * SCC Executor Registry
 * 
 * 管理所有可用的执行器，包括 OpenCode、Codex、WebGPT 等
 */

import { existsSync } from 'fs';
import { OpenCodeExecutor, loadExecutorFromConfig } from './opencode_executor.mjs';
import { OpenCodeWrapper, createWrapper } from './opencode_wrapper.mjs';
import { WebGPTExecutor, loadWebGPTExecutorFromConfig } from './webgpt_executor.mjs';

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
        const opencode = await loadExecutorFromConfig(opencodeConfig);
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

    // 尝试加载 WebGPT 执行器
    await this.loadWebGPT();

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
   * 加载 WebGPT 执行器
   */
  async loadWebGPT() {
    try {
      const webgptConfigPath = 'C:\\scc\\plugin\\webgpt\\config\\webgpt.config.json';
      const configExists = existsSync(webgptConfigPath);
      
      if (!configExists) {
        console.log('[ExecutorRegistry] WebGPT config not found, skipping...');
        return;
      }

      const webgpt = await loadWebGPTExecutorFromConfig(webgptConfigPath);
      this.register('webgpt', webgpt, { 
        priority: 2, 
        type: 'plugin',
        features: ['web_search', 'ai_chat', 'real_time_info']
