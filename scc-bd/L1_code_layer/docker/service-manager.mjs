#!/usr/bin/env node
/**
 * SCC Service Manager
 * 统一管理和启动所有 SCC 服务
 * 
 * 启动顺序:
 * 1. 基础服务 (日志、状态存储)
 * 2. Gateway (主入口)
 * 3. Parent Inbox Watcher (父任务监听)
 * 4. OLT CLI Server (可选)
 * 5. 健康检查
 */

import { spawn, exec } from 'child_process';
import { promises as fs } from 'fs';
import path from 'path';
import http from 'http';

const SERVICES = {
  // 核心服务
  gateway: {
    name: 'SCC Gateway',
    cmd: 'node',
    args: ['L1_code_layer/gateway/gateway.mjs'],
    port: 18788,
    required: true,
    healthCheck: '/health',
    maxRetries: 5
  },
  
  // 父任务监听服务
  parentWatcher: {
    name: 'Parent Inbox Watcher',
    cmd: 'node',
    args: ['L6_agent_layer/orchestrators/parent_inbox_watcher.mjs'],
    port: null, // 无端口，后台进程
    required: true,
    dependsOn: ['gateway'],
    delay: 3000 // 等待 gateway 启动
  },
  
  // OLT CLI 服务 (可选)
  oltCli: {
    name: 'OLT CLI Server',
    cmd: 'node',
    args: ['L6_execution_layer/oltcli.mjs'],
    port: 3458,
    required: false,
    dependsOn: ['gateway'],
    delay: 5000
  },
  
  // Job Executor Bridge (任务执行桥接)
  jobExecutorBridge: {
    name: 'Job Executor Bridge',
    cmd: 'node',
    args: ['L6_agent_layer/orchestrators/job_executor_bridge.mjs'],
    port: null,
    required: true,
    dependsOn: ['gateway', 'parentWatcher'],
    delay: 2000
  },
  
  // Role Router (角色路由)
  roleRouter: {
    name: 'Role Router',
    cmd: 'node',
    args: ['L6_agent_layer/orchestrators/role_router.mjs'],
    port: null,
    required: true,
    dependsOn: ['gateway', 'oltCli'],
    delay: 3000
  }
};

class ServiceManager {
  constructor() {
    this.processes = new Map();
    this.status = new Map();
    this.logs = [];
  }

  log(level, message, service = 'manager') {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] [${level.toUpperCase()}] [${service}] ${message}`;
    console.log(logEntry);
    this.logs.push(logEntry);
  }

  async start() {
    this.log('info', '==================================');
    this.log('info', 'SCC Service Manager');
    this.log('info', 'Starting all services...');
    this.log('info', '==================================');

    // 1. 预检查
    await this.preCheck();

    // 2. 按顺序启动服务
    for (const [key, config] of Object.entries(SERVICES)) {
      if (config.required || process.env[`ENABLE_${key.toUpperCase()}`] === 'true') {
        await this.startService(key, config);
      }
    }

    // 3. 健康检查
    await this.healthCheckAll();

    // 4. 输出状态
    this.printStatus();

    // 5. 监控服务
    this.monitorServices();

    this.log('info', '==================================');
    this.log('info', 'All services started successfully!');
    this.log('info', '==================================');
  }

  async preCheck() {
    this.log('info', 'Running pre-checks...');

    // 检查必要目录
    const dirs = [
      '/app/artifacts/scc_state',
      '/app/data',
      '/app/logs',
      '/app/state'
    ];

    for (const dir of dirs) {
      try {
        await fs.mkdir(dir, { recursive: true });
        this.log('info', `Directory ready: ${dir}`);
      } catch (err) {
        this.log('error', `Failed to create directory: ${dir} - ${err.message}`);
      }
    }

    // 检查 parent_inbox.jsonl
    const inboxPath = process.env.SCC_PARENT_INBOX || '/app/artifacts/scc_state/parent_inbox.jsonl';
    try {
      await fs.access(inboxPath);
    } catch {
      await fs.writeFile(inboxPath, '');
      this.log('info', `Created parent inbox: ${inboxPath}`);
    }

    // 检查 Node.js 版本
    const nodeVersion = process.version;
    this.log('info', `Node.js version: ${nodeVersion}`);

    this.log('info', 'Pre-checks completed');
  }

  async startService(key, config) {
    this.log('info', `Starting ${config.name}...`, key);

    // 等待依赖服务
    if (config.dependsOn) {
      for (const dep of config.dependsOn) {
        await this.waitForService(dep);
      }
    }

    // 延迟启动
    if (config.delay) {
      this.log('info', `Waiting ${config.delay}ms for dependencies...`, key);
      await this.sleep(config.delay);
    }

    // 启动进程
    return new Promise((resolve, reject) => {
      const proc = spawn(config.cmd, config.args, {
        cwd: '/app',
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, SERVICE_NAME: key }
      });

      this.processes.set(key, proc);
      this.status.set(key, 'starting');

      // 输出日志
      proc.stdout.on('data', (data) => {
        const lines = data.toString().trim().split('\n');
        for (const line of lines) {
          if (line.trim()) {
            this.log('info', line, key);
          }
        }
      });

      proc.stderr.on('data', (data) => {
        const lines = data.toString().trim().split('\n');
        for (const line of lines) {
          if (line.trim()) {
            this.log('error', line, key);
          }
        }
      });

      proc.on('error', (err) => {
        this.log('error', `Failed to start: ${err.message}`, key);
        this.status.set(key, 'failed');
        if (config.required) {
          reject(err);
        } else {
          resolve();
        }
      });

      proc.on('exit', (code) => {
        if (code !== 0) {
          this.log('error', `Exited with code ${code}`, key);
          this.status.set(key, 'crashed');
        }
      });

      // 等待服务就绪
      if (config.port) {
        this.waitForPort(config.port, config.maxRetries || 30)
          .then(() => {
            this.status.set(key, 'running');
            this.log('info', `${config.name} is ready on port ${config.port}`, key);
            resolve();
          })
          .catch((err) => {
            this.status.set(key, 'failed');
            if (config.required) {
              reject(err);
            } else {
              this.log('warn', `Service ${key} failed to start but is optional`, key);
              resolve();
            }
          });
      } else {
        // 无端口服务，直接标记为运行
        setTimeout(() => {
          this.status.set(key, 'running');
          this.log('info', `${config.name} is running`, key);
          resolve();
        }, 2000);
      }
    });
  }

  async waitForService(key) {
    const maxRetries = 30;
    for (let i = 0; i < maxRetries; i++) {
      const status = this.status.get(key);
      if (status === 'running') {
        return;
      }
      await this.sleep(1000);
    }
    throw new Error(`Service ${key} did not start in time`);
  }

  async waitForPort(port, maxRetries = 30) {
    for (let i = 0; i < maxRetries; i++) {
      try {
        await this.checkPort(port);
        return;
      } catch {
        await this.sleep(1000);
      }
    }
    throw new Error(`Port ${port} did not become available`);
  }

  checkPort(port) {
    return new Promise((resolve, reject) => {
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          reject(new Error(`Status: ${res.statusCode}`));
        }
      });
      req.on('error', reject);
      req.setTimeout(5000, () => {
        req.destroy();
        reject(new Error('Timeout'));
      });
    });
  }

  async healthCheckAll() {
    this.log('info', 'Running health checks...');

    for (const [key, config] of Object.entries(SERVICES)) {
      if (config.port && this.status.get(key) === 'running') {
        try {
          await this.checkPort(config.port);
          this.log('info', `Health check passed: ${config.name}`, key);
        } catch (err) {
          this.log('error', `Health check failed: ${err.message}`, key);
        }
      }
    }
  }

  monitorServices() {
    // 监控进程状态
    setInterval(() => {
      for (const [key, proc] of this.processes) {
        if (proc.exitCode !== null) {
          const config = SERVICES[key];
          this.log('error', `Service crashed, attempting restart...`, key);
          this.startService(key, config).catch((err) => {
            this.log('error', `Restart failed: ${err.message}`, key);
          });
        }
      }
    }, 10000);
  }

  printStatus() {
    console.log('\n📊 Service Status:');
    console.log('==================================');
    for (const [key, config] of Object.entries(SERVICES)) {
      const status = this.status.get(key) || 'not started';
      const icon = status === 'running' ? '✅' : status === 'failed' ? '❌' : '⏳';
      console.log(`${icon} ${config.name}: ${status}`);
    }
    console.log('==================================\n');
  }

  sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async shutdown() {
    this.log('info', 'Shutting down all services...');
    
    for (const [key, proc] of this.processes) {
      this.log('info', `Stopping ${key}...`);
      proc.kill('SIGTERM');
    }

    // 等待进程退出
    await this.sleep(5000);

    // 强制终止
    for (const [key, proc] of this.processes) {
      if (!proc.killed) {
        proc.kill('SIGKILL');
      }
    }

    this.log('info', 'All services stopped');
  }
}

// 主函数
async function main() {
  const manager = new ServiceManager();

  // 处理信号
  process.on('SIGTERM', () => manager.shutdown());
  process.on('SIGINT', () => manager.shutdown());

  try {
    await manager.start();
  } catch (err) {
    console.error('Failed to start services:', err);
    process.exit(1);
  }
}

main();
