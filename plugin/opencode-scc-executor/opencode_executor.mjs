/**
 * OpenCode Executor for SCC System
 * 
 * 将 OpenCode CLI 作为 SCC 的执行器集成，支持任务执行、代码生成和验证。
 */

import { spawn } from 'child_process';
import { readFile, writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import { join, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// 配置路径 - 相对于 plugin 目录
const PLUGIN_DIR = resolve(__dirname);
const CONFIG_PATH = resolve(PLUGIN_DIR, 'config/opencode.config.json');
const OPENCODE_CONFIG_PATH = resolve(PLUGIN_DIR, 'config/.opencode.json');

/**
 * OpenCode 执行器类
 */
export class OpenCodeExecutor {
  constructor(config = {}) {
    this.config = {
      binary: config.binary || 'C:\\scc\\plugin\\opencode\\opencode.exe',
      workingDirectory: config.workingDirectory || 'C:\\scc',
      configPath: config.configPath || OPENCODE_CONFIG_PATH,
      timeout: config.timeout || 300000,
      autoApprove: config.autoApprove !== false,
      outputFormat: config.outputFormat || 'json',
      ...config
    };
    this.name = 'opencode';
    this.type = 'cli';
  }

  /**
   * 初始化执行器
   */
  async initialize() {
    // 确保数据目录存在
    const dataDir = join(process.cwd(), '.opencode');
    if (!existsSync(dataDir)) {
      await mkdir(dataDir, { recursive: true });
    }

    // 确保日志目录存在
    const logDir = join(process.cwd(), 'artifacts/executor_logs/opencode');
    if (!existsSync(logDir)) {
      await mkdir(logDir, { recursive: true });
    }

    console.log('[OpenCodeExecutor] Initialized with config:', {
      binary: this.config.binary,
      workingDirectory: this.config.workingDirectory
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
    const taskId = task.id || `opencode-${Date.now()}`;
    
    console.log(`[OpenCodeExecutor] Executing task ${taskId}:`, task.type || task.prompt?.substring(0, 50));

    try {
      // 构建提示词
      const prompt = this.buildPrompt(task, context);
      
      // 执行 OpenCode
      const result = await this.runOpenCode(prompt, task, context);
      
      const duration = Date.now() - startTime;
      
      return {
        taskId,
        status: 'success',
        result: result.output,
        metadata: {
          executor: 'opencode',
          duration,
          model: task.model || this.config.model,
          tokens: result.tokens
        }
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      
      console.error(`[OpenCodeExecutor] Task ${taskId} failed:`, error.message);
      
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

    // 添加输出格式要求
    if (task.outputFormat) {
      parts.push('');
      parts.push('=== Output Format ===');
      parts.push(task.outputFormat);
    }

    return parts.join('\n');
  }

  /**
   * 运行 OpenCode CLI
   */
  runOpenCode(prompt, task, context) {
    return new Promise((resolve, reject) => {
      const args = [
        '-p', prompt,
        '-f', this.config.outputFormat,
        '-c', this.config.workingDirectory
      ];

      if (this.config.configPath) {
        process.env.OPENCODE_CONFIG = this.config.configPath;
      }

      // 设置模型
      if (task.model) {
        process.env.OPENCODE_MODEL = task.model;
      }

      console.log(`[OpenCodeExecutor] Running: ${this.config.binary} ${args.join(' ')}`);

      const child = spawn(this.config.binary, args, {
        cwd: this.config.workingDirectory,
        env: { ...process.env },
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
          reject(new Error(`OpenCode exited with code ${code}: ${stderr}`));
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
        reject(new Error(`Failed to start OpenCode: ${error.message}`));
      });
    });
  }

  /**
   * 提取 Token 使用量
   */
  extractTokenUsage(output) {
    // 这里可以根据 OpenCode 的输出格式解析 token 使用量
    // 暂时返回估算值
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
      // 检查二进制文件是否存在
      const binaryExists = existsSync(this.config.binary);
      if (!binaryExists) {
        return {
          status: 'unhealthy',
          error: `Binary not found: ${this.config.binary}`
        };
      }

      // 尝试执行简单命令
      const testPrompt = 'echo "health check"';
      await this.runOpenCode(testPrompt, { id: 'health-check' }, {});

      return {
        status: 'healthy',
        binary: this.config.binary,
        version: 'unknown' // 可以通过 --version 获取
      };
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
        models: ['claude-3.7-sonnet', 'claude-3.5-sonnet', 'gpt-4o', 'gemini-2.5-pro']
      }
    };
  }
}

/**
 * 创建执行器实例的工厂函数
 */
export async function createExecutor(config = {}) {
  const executor = new OpenCodeExecutor(config);
  await executor.initialize();
  return executor;
}

/**
 * 从配置文件加载执行器
 */
export async function loadExecutorFromConfig(configPath = CONFIG_PATH) {
  try {
    const configData = await readFile(configPath, 'utf-8');
    const config = JSON.parse(configData);
    return createExecutor(config.opencode || config);
  } catch (error) {
    console.warn(`[OpenCodeExecutor] Failed to load config from ${configPath}:`, error.message);
    return createExecutor();
  }
}

// 默认导出
export default OpenCodeExecutor;
