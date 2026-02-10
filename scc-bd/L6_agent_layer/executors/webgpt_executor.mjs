/**
 * WebGPT Executor for SCC System
 * 
 * 将 WebGPT 作为 SCC 的执行器集成，支持 Web 搜索和 AI 对话功能。
 */

import { spawn } from 'child_process';
import { readFile, writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import { join, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// 配置路径
const PLUGIN_DIR = resolve(__dirname, '../../../plugin/webgpt');
const CONFIG_PATH = resolve(PLUGIN_DIR, 'config/webgpt.config.json');

/**
 * WebGPT 执行器类
 */
export class WebGPTExecutor {
  constructor(config = {}) {
    this.config = {
      binary: config.binary || 'npx',
      scriptPath: config.scriptPath || 'webgpt',
      workingDirectory: config.workingDirectory || 'C:\\scc',
      timeout: config.timeout || 300000,
      autoApprove: config.autoApprove !== false,
      outputFormat: config.outputFormat || 'json',
      apiKey: config.apiKey || process.env.WEBGPT_API_KEY || process.env.OPENAI_API_KEY,
      searchProvider: config.searchProvider || 'brave',
      ...config
    };
    this.name = 'webgpt';
    this.type = 'cli';
  }

  /**
   * 初始化执行器
   */
  async initialize() {
    // 确保日志目录存在
    const logDir = join(process.cwd(), 'artifacts/executor_logs/webgpt');
    if (!existsSync(logDir)) {
      await mkdir(logDir, { recursive: true });
    }

    console.log('[WebGPTExecutor] Initialized with config:', {
      binary: this.config.binary,
      workingDirectory: this.config.workingDirectory,
      searchProvider: this.config.searchProvider
    });

    return this;
  }

  /**
   * 执行单个任务
   * @param {Object} task - 任务定义
   * @param {Object} context - 执行上下文
   * @returns {Promise<Object>} 执行结果
   */
  async execute(task, context = {}) {
    const startTime = Date.now();
    const taskId = task.id || `webgpt-${Date.now()}`;
    
    console.log(`[WebGPTExecutor] Executing task ${taskId}:`, task.type || task.prompt?.substring(0, 50));

    try {
      // 构建提示词
      const prompt = this.buildPrompt(task, context);
      
      // 执行 WebGPT
      const result = await this.runWebGPT(prompt, task, context);
      
      const duration = Date.now() - startTime;
      
      return {
        taskId,
        status: 'success',
        result: result.output,
        metadata: {
          executor: 'webgpt',
          duration,
          model: task.model || this.config.model,
          searchProvider: this.config.searchProvider,
          tokens: result.tokens
        }
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      
      console.error(`[WebGPTExecutor] Task ${taskId} failed:`, error.message);
      
      return {
        taskId,
        status: 'error',
        error: error.message,
        metadata: {
          executor: 'webgpt',
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

    // 添加角色定义
    if (task.role) {
      parts.push(`Role: ${task.role}`);
      parts.push(`Skills: ${task.skills?.join(', ') || 'general'}`);
      parts.push('');
    }

    // 添加上下文包
    if (context.contextPack) {
      parts.push('=== Context Pack ===');
      parts.push(context.contextPack);
      parts.push('');
    }

    // 添加任务描述
    if (task.description) {
      parts.push('=== Task Description ===');
      parts.push(task.description);
      parts.push('');
    }

    // 添加提示词
    if (task.prompt) {
      parts.push('=== Instructions ===');
      parts.push(task.prompt);
    }

    // 添加搜索要求
    if (task.enableSearch !== false) {
      parts.push('');
      parts.push('=== Search Configuration ===');
      parts.push(`Search Provider: ${this.config.searchProvider}`);
      parts.push('Enable web search for up-to-date information');
    }

    // 添加输出格式要求
    if (task.outputFormat) {
      parts.push('');
      parts.push('=== Output Format ===');
      parts.push(task.outputFormat);
    }

    return parts.join('\n');
  }

  /**
   * 运行 WebGPT
   */
  runWebGPT(prompt, task, context) {
    return new Promise((resolve, reject) => {
      const args = [
        this.config.scriptPath,
        '--prompt', prompt,
        '--format', this.config.outputFormat
      ];

      // 添加搜索选项
      if (task.enableSearch !== false) {
        args.push('--search');
        args.push('--search-provider', this.config.searchProvider);
      }

      // 设置模型
      if (task.model) {
        args.push('--model', task.model);
      }

      // 设置 API Key
      const env = { ...process.env };
      if (this.config.apiKey) {
        env.OPENAI_API_KEY = this.config.apiKey;
        env.WEBGPT_API_KEY = this.config.apiKey;
      }

      console.log(`[WebGPTExecutor] Running: ${this.config.binary} ${args.join(' ')}`);

      const child = spawn(this.config.binary, args, {
        cwd: this.config.workingDirectory,
        env,
        timeout: this.config.timeout
      });

      let stdout = '';
      let stderr = '';

      child.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      child.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      child.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`WebGPT exited with code ${code}: ${stderr}`));
          return;
        }

        // 解析输出
        let output;
        try {
          if (this.config.outputFormat === 'json') {
            output = JSON.parse(stdout);
          } else {
            output = stdout;
          }
        } catch (e) {
          output = stdout;
        }

        resolve({
          output,
          tokens: this.extractTokenUsage(stdout),
          stderr: stderr || null
        });
      });

      child.on('error', (error) => {
        reject(new Error(`Failed to start WebGPT: ${error.message}`));
      });
    });
  }

  /**
   * 提取 Token 使用量
   */
  extractTokenUsage(output) {
    return {
      input: Math.ceil(output.length / 4),
      output: Math.ceil(output.length / 4),
      total: Math.ceil(output.length / 2)
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
    try {
      // 检查必要的命令是否可用
      return new Promise((resolve) => {
        const child = spawn(this.config.binary, ['--version'], {
          timeout: 10000
        });

        let stdout = '';
        child.stdout.on('data', (data) => {
          stdout += data.toString();
        });

        child.on('close', (code) => {
          if (code === 0) {
            resolve({
              status: 'healthy',
              binary: this.config.binary,
              version: stdout.trim()
            });
          } else {
            resolve({
              status: 'unhealthy',
              error: `Binary check failed with code ${code}`
            });
          }
        });

        child.on('error', (error) => {
          resolve({
            status: 'unhealthy',
            error: error.message
          });
        });
      });
    } catch (error) {
      return {
        status: 'unhealthy',
        error: error.message
      };
    }
  }

  /**
   * 获取执行器信息
   */
  getInfo() {
    return {
      name: this.name,
      type: this.type,
      version: '1.0.0',
      config: {
        binary: this.config.binary,
        workingDirectory: this.config.workingDirectory,
        timeout: this.config.timeout,
        searchProvider: this.config.searchProvider,
        models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo']
      }
    };
  }
}

/**
 * 创建执行器实例的工厂函数
 */
export async function createWebGPTExecutor(config = {}) {
  const executor = new WebGPTExecutor(config);
  await executor.initialize();
  return executor;
}

/**
 * 从配置文件加载执行器
 */
export async function loadWebGPTExecutorFromConfig(configPath = CONFIG_PATH) {
  try {
    const configData = await readFile(configPath, 'utf-8');
    const config = JSON.parse(configData);
    return createWebGPTExecutor(config.webgpt || config);
  } catch (error) {
    console.warn(`[WebGPTExecutor] Failed to load config from ${configPath}:`, error.message);
    return createWebGPTExecutor();
  }
}

// 默认导出
export default WebGPTExecutor;
