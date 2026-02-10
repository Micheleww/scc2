#!/usr/bin/env node
/**
 * SCC Unified Server
 * 
 * 融合版本：整合 OpenCode CLI Executor V2 + OLT CLI Bridge V2 + SCC Server with OLT CLI
 * 
 * 功能：
 * - 7个工具：read_file, write_file, edit_file, list_dir, search_files, grep_search, run_command
 * - 多轮对话：默认50轮
 * - HTTP API：OpenAI 兼容格式 + SCC 原生端点
 * 
 * 端口: 3458
 * 启动: node scc_server_unified.mjs
 */

import http from 'http';
import { spawn, execSync } from 'child_process';
import { randomUUID } from 'crypto';
import fs from 'fs';
import path from 'path';

const PORT = process.env.PORT || 3458;
const OPENCODE_CLI = 'C:\\scc\\plugin\\OpenCode\\opencode-cli.exe';
const DEFAULT_MODEL = 'opencode/kimi-k2.5-free';
const DEFAULT_MAX_ROUNDS = 50;
const DEFAULT_TIMEOUT = 300000; // 5 minutes

// ============================================================================
// 工具实现 (7个工具 - 来自 OpenCodeCLI Executor V2)
// ============================================================================

const TOOLS = {
  // 1. read_file - 读取文件
  async read_file(args) {
    try {
      const { file_path, offset, limit } = args;
      if (!fs.existsSync(file_path)) {
        return { error: `文件不存在: ${file_path}` };
      }
      let content = fs.readFileSync(file_path, 'utf-8');
      const lines = content.split('\n');
      if (offset !== undefined && limit !== undefined) {
        const start = Math.max(0, offset - 1);
        const end = Math.min(lines.length, start + limit);
        content = lines.slice(start, end).join('\n');
      } else if (limit !== undefined) {
        content = lines.slice(0, limit).join('\n');
      }
      return { 
        success: true,
        content, 
        totalLines: lines.length, 
        file_path 
      };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // 2. write_file - 写入文件
  async write_file(args) {
    try {
      const { file_path, content } = args;
      const dir = path.dirname(file_path);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(file_path, content, 'utf-8');
      return { 
        success: true, 
        file_path, 
        bytes: Buffer.byteLength(content, 'utf-8') 
      };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // 3. edit_file - 编辑文件（搜索替换）
  async edit_file(args) {
    try {
      const { file_path, old_string, new_string } = args;
      if (!fs.existsSync(file_path)) {
        return { error: `文件不存在: ${file_path}` };
      }
      const content = fs.readFileSync(file_path, 'utf-8');
      if (!content.includes(old_string)) {
        return { error: `找不到要替换的文本` };
      }
      const newContent = content.replace(old_string, new_string);
      fs.writeFileSync(file_path, newContent, 'utf-8');
      return { success: true, file_path };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // 4. list_dir - 列出目录
  async list_dir(args) {
    try {
      const { path: dirPath } = args;
      if (!fs.existsSync(dirPath)) {
        return { error: `目录不存在: ${dirPath}` };
      }
      const entries = fs.readdirSync(dirPath, { withFileTypes: true });
      const items = entries.map(entry => ({
        name: entry.name,
        type: entry.isDirectory() ? 'directory' : 'file',
        path: path.join(dirPath, entry.name)
      }));
      return { 
        success: true,
        path: dirPath, 
        items, 
        count: items.length 
      };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // 5. search_files - 使用 glob 搜索文件
  async search_files(args) {
    try {
      const { pattern, searchPath = '.' } = args;
      const { glob } = await import('glob');
      const matches = await glob(pattern, { cwd: searchPath });
      return { 
        success: true,
        pattern, 
        path: searchPath, 
        matches,
        count: matches.length 
      };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // 6. grep_search - 使用 ripgrep 搜索内容
  async grep_search(args) {
    try {
      const { pattern, searchPath = '.', glob: fileGlob } = args;
      const cmd = fileGlob 
        ? `rg "${pattern}" "${searchPath}" --glob "${fileGlob}" -l`
        : `rg "${pattern}" "${searchPath}" -l`;
      const result = execSync(cmd, { 
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024 
      });
      const matches = result.split('\n').filter(line => line.trim());
      return { 
        success: true,
        pattern, 
        path: searchPath, 
        matches,
        count: matches.length 
      };
    } catch (error) {
      // rg 返回非0退出码表示没找到，不是错误
      if (error.status === 1) {
        return { success: true, pattern, path: searchPath, matches: [], count: 0 };
      }
      return { success: false, error: error.message };
    }
  },

  // 7. run_command - 执行命令
  async run_command(args) {
    try {
      const { command, cwd, timeout = 60000 } = args;
      const result = execSync(command, {
        cwd: cwd || process.cwd(),
        timeout,
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024
      });
      return { 
        success: true, 
        output: result, 
        exitCode: 0 
      };
    } catch (error) {
      return { 
        success: false, 
        output: error.stdout?.toString() || '', 
        error: error.stderr?.toString() || error.message, 
        exitCode: error.status || 1 
      };
    }
  }
};

// ============================================================================
// OpenCode CLI 调用
// ============================================================================

function callOpenCode(model, prompt, useSummaryAgent = false) {
  return new Promise((resolve, reject) => {
    const args = useSummaryAgent 
      ? ['run', '--model', model, '--agent', 'summary', '--format', 'json']
      : ['run', '--model', model, '--format', 'json'];
    
    const child = spawn(OPENCODE_CLI, args, {
      shell: false,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe']
    });
    
    let output = '';
    let errorOutput = '';
    
    child.stdin.write(prompt);
    child.stdin.end();
    
    child.stdout.on('data', (data) => {
      output += data.toString();
    });
    
    child.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });
    
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`OpenCode CLI 退出码 ${code}: ${errorOutput}`));
        return;
      }
      
      try {
        const lines = output.split('\n').filter(line => line.trim());
        let textResponse = '';
        
        for (const line of lines) {
          try {
            const parsed = JSON.parse(line);
            if (parsed.type === 'text' && parsed.part?.text) {
              textResponse = parsed.part.text;
              break;
            }
          } catch {}
        }
        
        resolve(textResponse || output);
      } catch (error) {
        reject(error);
      }
    });
    
    setTimeout(() => {
      child.kill();
      reject(new Error('OpenCode CLI 调用超时'));
    }, DEFAULT_TIMEOUT);
  });
}

// ============================================================================
// 工具调用解析
// ============================================================================

function parseToolCall(text) {
  const match = text.match(/<tool_call>\s*({[\s\S]*?})\s*<\/tool_call>/);
  if (match) {
    try {
      return JSON.parse(match[1].trim());
    } catch {}
  }
  return null;
}

// ============================================================================
// HTTP 工具函数
// ============================================================================

function sendJSON(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
  });
  res.end(JSON.stringify(data));
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (e) {
        resolve({});
      }
    });
  });
}

// ============================================================================
// 系统提示词
// ============================================================================

const SYSTEM_PROMPT_TOOLS = `你是 AI 助手。你可以使用以下工具：

1. read_file - 读取文件内容
   参数: { "file_path": "文件路径", "offset": 起始行(可选), "limit": 行数(可选) }

2. write_file - 写入文件
   参数: { "file_path": "文件路径", "content": "文件内容" }

3. edit_file - 编辑文件（搜索替换）
   参数: { "file_path": "文件路径", "old_string": "要替换的文本", "new_string": "新文本" }

4. list_dir - 列出目录内容
   参数: { "path": "目录路径" }

5. search_files - 使用 glob 搜索文件
   参数: { "pattern": "glob模式", "path": "搜索目录(可选)" }

6. grep_search - 使用 ripgrep 搜索内容
   参数: { "pattern": "搜索正则", "path": "搜索目录(可选)", "glob": "文件过滤(可选)" }

7. run_command - 执行命令
   参数: { "command": "命令", "cwd": "工作目录(可选)", "timeout": 超时毫秒(可选) }

当你需要使用工具时，请输出：
<tool_call>
{
  "tool": "工具名",
  "args": { ...参数 }
}
<\/tool_call>

我会执行工具并返回结果给你。当你完成任务时，请输出 <task_complete>。`;

// ============================================================================
// 路由处理
// ============================================================================

const routes = {
  // 根路径
  'GET /': async (req, res) => {
    sendJSON(res, 200, {
      name: 'SCC Unified Server',
      version: '2.0.0',
      description: '融合 OpenCode CLI Executor + OLT CLI Bridge + SCC Server',
      features: [
        '7个工具 (read_file, write_file, edit_file, list_dir, search_files, grep_search, run_command)',
        '多轮对话 (默认50轮)',
        'OpenAI 兼容 API',
        'SCC 原生 API'
      ],
      endpoints: {
        health: '/api/health',
        oltCli: '/api/olt-cli/*',
        openai: '/v1/*'
      }
    });
  },

  // 健康检查
  'GET /api/health': async (req, res) => {
    sendJSON(res, 200, {
      status: 'ok',
      timestamp: new Date().toISOString(),
      services: { 
        'olt-cli': 'available',
        'unified-executor': 'available'
      }
    });
  },

  // OLT CLI 健康检查
  'GET /api/olt-cli/health': async (req, res) => {
    sendJSON(res, 200, { 
      status: 'ok', 
      service: 'olt-cli',
      tools: Object.keys(TOOLS),
      maxRounds: DEFAULT_MAX_ROUNDS
    });
  },

  // 模型列表 (SCC 格式)
  'GET /api/olt-cli/models': async (req, res) => {
    sendJSON(res, 200, {
      object: 'list',
      data: [
        { id: DEFAULT_MODEL, object: 'model', description: 'Kimi K2.5 免费版' }
      ]
    });
  },

  // 聊天完成 (SCC 格式)
  'POST /api/olt-cli/chat/completions': async (req, res) => {
    try {
      const body = await parseBody(req);
      const { messages, model = DEFAULT_MODEL } = body;

      const prompt = messages.map(m => {
        if (m.role === 'system') return `System: ${m.content}`;
        if (m.role === 'user') return `User: ${m.content}`;
        if (m.role === 'assistant') return `Assistant: ${m.content}`;
        return m.content;
      }).join('\n\n');

      const response = await callOpenCode(model, prompt, false);

      sendJSON(res, 200, {
        id: `chatcmpl-${randomUUID()}`,
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: model,
        choices: [{
          index: 0,
          message: { role: 'assistant', content: response },
          finish_reason: 'stop'
        }],
        usage: {
          prompt_tokens: prompt.length / 4,
          completion_tokens: response.length / 4,
          total_tokens: (prompt.length + response.length) / 4
        }
      });
    } catch (error) {
      sendJSON(res, 500, { error: { message: error.message, type: 'internal_error' } });
    }
  },

  // 执行带工具的对话 (SCC 格式)
  'POST /api/olt-cli/execute': async (req, res) => {
    try {
      const body = await parseBody(req);
      const { task, maxRounds = DEFAULT_MAX_ROUNDS, model = DEFAULT_MODEL } = body;

      if (!task) {
        return sendJSON(res, 400, { error: '缺少 task 参数' });
      }

      const messages = [
        { role: 'system', content: SYSTEM_PROMPT_TOOLS },
        { role: 'user', content: task }
      ];

      const conversation = [];

      for (let round = 1; round <= maxRounds; round++) {
        const prompt = messages.map(m => {
          if (m.role === 'system') return `System: ${m.content}`;
          if (m.role === 'user') return `User: ${m.content}`;
          if (m.role === 'assistant') return `Assistant: ${m.content}`;
          return m.content;
        }).join('\n\n');

        const aiResponse = await callOpenCode(model, prompt, true);

        conversation.push({ role: 'assistant', content: aiResponse, round });
        messages.push({ role: 'assistant', content: aiResponse });

        if (aiResponse.includes('<task_complete>') || aiResponse.includes('任务完成')) {
          break;
        }

        const toolCall = parseToolCall(aiResponse);
        if (!toolCall) break;

        const toolFn = TOOLS[toolCall.tool];
        if (!toolFn) {
          const errorMsg = `未知工具: ${toolCall.tool}`;
          conversation.push({ role: 'user', content: errorMsg, round });
          messages.push({ role: 'user', content: errorMsg });
          continue;
        }

        const result = await toolFn(toolCall.args);
        const resultMsg = `工具执行结果：\n\n${JSON.stringify(result, null, 2)}`;

        conversation.push({ role: 'user', content: resultMsg, round });
        messages.push({ role: 'user', content: resultMsg });
      }

      sendJSON(res, 200, {
        ok: true,
        rounds: conversation.filter(m => m.role === 'assistant').length,
        conversation,
        result: conversation.filter(m => m.role === 'assistant').pop()?.content || ''
      });
    } catch (error) {
      sendJSON(res, 500, { error: { message: error.message, type: 'internal_error' } });
    }
  },

  // ==========================================================================
  // OpenAI 兼容 API (来自 OLT CLI Bridge V2)
  // ==========================================================================

  // 模型列表 (OpenAI 格式)
  'GET /v1/models': async (req, res) => {
    sendJSON(res, 200, {
      object: 'list',
      data: [
        { id: 'gpt-4o-mini', object: 'model' },
        { id: DEFAULT_MODEL, object: 'model' }
      ]
    });
  },

  // 聊天完成 (OpenAI 格式)
  'POST /v1/chat/completions': async (req, res) => {
    try {
      const body = await parseBody(req);
      const { messages, model = DEFAULT_MODEL } = body;

      console.log('[Unified] OpenAI API 请求:', { model, messageCount: messages.length });

      const prompt = messages.map(m => {
        if (m.role === 'system') return `System: ${m.content}`;
        if (m.role === 'user') return `User: ${m.content}`;
        if (m.role === 'assistant') return `Assistant: ${m.content}`;
        return m.content;
      }).join('\n\n');

      const response = await callOpenCode(model, prompt, false);

      const openaiResponse = {
        id: `chatcmpl-${randomUUID()}`,
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: model,
        choices: [{
          index: 0,
          message: {
            role: 'assistant',
            content: response
          },
          finish_reason: 'stop'
        }],
        usage: {
          prompt_tokens: prompt.length / 4,
          completion_tokens: response.length / 4,
          total_tokens: (prompt.length + response.length) / 4
        }
      };

      sendJSON(res, 200, openaiResponse);
    } catch (error) {
      console.error('[Unified] OpenAI API 错误:', error);
      sendJSON(res, 500, { 
        error: {
          message: error.message,
          type: 'internal_error'
        }
      });
    }
  }
};

// ============================================================================
// 创建服务器
// ============================================================================

const server = http.createServer(async (req, res) => {
  console.log(`[SCC-Unified] ${req.method} ${req.url}`);

  // CORS 预检
  if (req.method === 'OPTIONS') {
    res.writeHead(200, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    });
    res.end();
    return;
  }

  // 查找路由
  const routeKey = `${req.method} ${req.url}`;
  const handler = routes[routeKey];

  if (handler) {
    await handler(req, res);
  } else {
    sendJSON(res, 404, { error: 'Not found' });
  }
});

// ============================================================================
// 启动服务器
// ============================================================================

server.listen(PORT, () => {
  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║           SCC Unified Server v2.0.0                          ║');
  console.log('║  融合: OpenCode CLI Executor + OLT CLI Bridge + SCC Server   ║');
  console.log('╚══════════════════════════════════════════════════════════════╝');
  console.log(`\n服务器运行在: http://localhost:${PORT}`);
  console.log('\n📋 OpenAI 兼容端点:');
  console.log(`  GET  http://localhost:${PORT}/v1/models`);
  console.log(`  POST http://localhost:${PORT}/v1/chat/completions`);
  console.log('\n📋 SCC 原生端点:');
  console.log(`  GET  http://localhost:${PORT}/api/health`);
  console.log(`  GET  http://localhost:${PORT}/api/olt-cli/health`);
  console.log(`  GET  http://localhost:${PORT}/api/olt-cli/models`);
  console.log(`  POST http://localhost:${PORT}/api/olt-cli/chat/completions`);
  console.log(`  POST http://localhost:${PORT}/api/olt-cli/execute  (多轮+工具)`);
  console.log('\n🔧 可用工具 (7个):');
  console.log('  read_file, write_file, edit_file, list_dir,');
  console.log('  search_files, grep_search, run_command');
  console.log(`\n⚙️  默认最大轮数: ${DEFAULT_MAX_ROUNDS}`);
  console.log('\n按 Ctrl+C 停止服务器\n');
});
