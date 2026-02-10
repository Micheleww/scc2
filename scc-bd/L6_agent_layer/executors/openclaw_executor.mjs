/**
 * OpenClaw Executor for SCC System
 * 
 * 将 OpenClaw 作为 SCC 的执行器集成，支持多代理协作和工具调用。
 */

import { spawn } from 'child_process';
import { readFile, writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import { join, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// 配置路径
const PLUGIN_DIR = resolve(__dirname, '../../../plugin/openclaw');
const CONFIG_PATH = resolve(PLUGIN_DIR, 'config/openclaw.config.json');

/**
 * OpenClaw 执行器类
 */
export class OpenClawExecutor {
  constructor(config = {}) {
    this.config = {
      binary: config.binary || 'node',
      scriptPath: config.scriptPath || join(PLUGIN_DIR, 'openclaw.mjs'),
      workingDirectory: config.workingDirectory || 'C:\\scc',
      configPath: config.configPath || join(PLUGIN_DIR, 'config.json'),
      timeout: config.timeout || 600000, // OpenClaw 任务通常需要更长时间
      autoApprove: config.autoApprove !== false,
      outputFormat: config.outputFormat || 'json',
      agent: config.agent || 'default',
      ...config
    };
    this.name = 'openclaw';
    this.type = 'cli';
  }

  /**
   * 初始化执行器
   */
  async initialize() {
    // 确保日志目录存在
    const logDir = join(process.cwd(), 'artifacts/executor_logs/openclaw');
    if (!existsSync(logDir)) {
      await mkdir(logDir, { recursive: true });
    }

    console.log('[OpenClawExecutor] Initialized with config:', {
      binary: this.config.binary,
      scriptPath: this.config.scriptPath,
      workingDirectory: this.config.workingDirectory,
      agent: this.config.agent
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
    const taskId = task.id || `openclaw-${Date.now()}`;
    
    console.log(`[OpenClawExecutor] Executing task ${taskId}:`, task.type || task.prompt?.substring(0, 50));

    try {
      // 构建提示词
      const prompt = this.buildPrompt(task, context);
      
      // 执行 OpenClaw
      const result = await this.runOpenClaw(prompt, task, context);
      
      const duration = Date.now() - startTime;
      
      return {
        taskId,
        status: 'success',
        result: result.output,
        metadata: {
          executor: 'openclaw',
          duration,
          agent: task.agent || this.config.agent,
          tokens: result.tokens,
          toolCalls: result.toolCalls
        }
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      
      console.error(`[OpenClawExecutor] Task ${taskId} failed:`, error.message);
      
      return {
        taskId,
        status: 'error',
        error: error.message,
        metadata: {
          executor: 'openclaw',
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

    // 添加工具配置
    if (task.tools && task.tools.length > 0) {
      parts.push('');
      parts.push('=== Available Tools ===');
      for (const tool of task.tools) {
        parts.push(`- ${tool}`);
      }
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
   * 运行 OpenClaw
   */
  runOpenClaw(prompt, task, context) {
    return new Promise((resolve, reject) => {
      const args = [
        this.config.scriptPath,
        'agent',
        '--prompt', prompt
      ];

      // 添加配置路径
      if (this.config.configPath && existsSync(this.config.configPath)) {
        args.push('--config', this.config.configPath);
      }

      // 设置代理
      if (task.agent || this.config.agent) {
        args.push('--agent', task.agent || this.config.agent);
      }

      // 添加工作目录
      args.push('--cwd', this.config.workingDirectory);

      // 设置环境变量
      const env = { ...process.env };
      
      // OpenClaw 特定的环境变量
      if (process.env.OPENCLAW_API_KEY) {
        env.OPENCLAW_API_KEY = process.env.OPENCLAW_API_KEY;
      }

      console.log(`[OpenClawExecutor] Running: ${this.config.binary} ${args.join(' ')}`);

      const child = spawn(this.config.binary, args, {
        cwd: this.config.workingDirectory,
        env,
        timeout: this.config.timeout
      });

      let stdout = '';
      let stderr = '';
      let toolCalls = [];

      child.stdout.on('data', (data) => {
        const chunk = data.toString();
        stdout += chunk;
        
        // 尝试解析工具调用
        this.parseToolCalls(chunk, toolCalls);
      });

      child.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      child.on('close', (code) => {
        if (code !== 0 && code !== null) {
          reject(new Error(`OpenClaw exited with code ${code}: ${stderr}`));
          return;
        }

        // 解析输出
        let output;
        try {
          // 尝试解析 JSON 输出
          const jsonMatch = stdout.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            output = JSON.parse(jsonMatch[0]);
          } else {
            output = { text: stdout.trim() };
          }
        } catch (e) {
          output = { text: stdout.trim() };
        }

        resolve({
          output,
          tokens: this.extractTokenUsage(stdout),
          toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
          stderr: stderr || null
        });
      });

      child.on('error', (error) => {
        reject(new Error(`Failed to start OpenClaw: ${error.message}`));
      });
    });
  }

  /**
   * 解析工具调用
   */
  parseToolCalls(chunk, toolCalls) {
    // 匹配工具调用模式
    const toolPattern = /Tool:\s*(\w+)\s*\n(?:Input:|Parameters:)\s*(\{[\s\S]*?\})/g;
    let match;
    while ((match = toolPattern.exec(chunk)) !== null) {
      try {
        toolCalls.push({
          tool: match[1],
          input: JSON.parse(match[2])
        });
      } catch (e) {
        toolCalls.push({
          tool: match[1],
          input: match[2]
        });
      }
    }
  }

  /**
   * 提取 Token 使用量
   */
  extractTokenUsage(output) {
    // 尝试从输出中解析 token 使用量
    const tokenMatch = output.match(/Tokens:\s*(\d+)\s*input,\s*(\d+)\s*output/i);
    if (tokenMatch) {
      return {
        input: parseInt(tokenMatch[1], 10),
        output: parseInt(tokenMatch[2], 10),
        total: parseInt(tokenMatch[1], 10) + parseInt(tokenMatch[2], 10)
      };
    }
    
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
   * 执行特定代理任务
   */
  async executeWithAgent(agentName, prompt, options = {}) {
    return this.execute({
      id: options.id || `openclaw-agent-${Date.now()}`,
      agent: agentName,
      prompt,
      ...options
    });
  }

  /**
   * 验证执行器健康状态
   */
  async healthCheck() {
    try {
      // 检查脚本文件是否存在
      const scriptExists = existsSync(this.config.scriptPath);
      if (!scriptExists) {
        return {
          status: 'unhealthy',
          error: `Script not found: ${this.config.scriptPath}`
        };
      }

      // 检查 Node.js 是否可用
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
              scriptPath: this.config.scriptPath,
              nodeVersion: stdout.trim()
            });
          } else {
            resolve({
              status: 'unhealthy',
              error: `Node.js check failed with code ${code}`
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
        scriptPath: this.config.scriptPath,
        workingDirectory: this.config.workingDirectory,
        timeout: this.config.timeout,
        agent: this.config.agent,
        features: ['multi-agent', 'tool-calling', 'session-management']
      }
    };
  }
}

/**
 * 创建执行器实例的工厂函数
 */
export async function createOpenClawExecutor(config = {}) {
  const executor = new OpenClawExecutor(config);
  await executor.initialize();
  return executor;
}

/**
 * 从配置文件加载执行器
 */
export async function loadOpenClawExecutorFromConfig(configPath = CONFIG_PATH) {
  try {
    const configData = await readFile(configPath, 'utf-8');
    const config = JSON.parse(configData);
    return createOpenClawExecutor(config.openclaw || config);
  } catch (error) {
    console.warn(`[OpenClawExecutor] Failed to load config from ${configPath}:`, error.message);
    return createOpenClawExecutor();
  }
}

// 默认导出
export default OpenClawExecutor;
