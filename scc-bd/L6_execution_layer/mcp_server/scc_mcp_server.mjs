#!/usr/bin/env node
/**
 * SCC MCP Server
 * 
 * 为 OpenCode CLI 提供扩展工具支持
 * 同步 Trae 的工具功能
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import glob from "glob";

const globAsync = promisify(glob);

/**
 * 工具定义
 */
const TOOLS = [
  // 文件操作工具
  {
    name: "read_file",
    description: "读取文件内容，支持行范围选择和自动截断",
    inputSchema: {
      type: "object",
      properties: {
        file_path: { type: "string", description: "文件绝对路径" },
        offset: { type: "number", description: "起始行号（可选）" },
        limit: { type: "number", description: "读取行数（可选）" }
      },
      required: ["file_path"]
    }
  },
  {
    name: "write_file",
    description: "写入文件内容（覆盖模式）",
    inputSchema: {
      type: "object",
      properties: {
        file_path: { type: "string", description: "文件绝对路径" },
        content: { type: "string", description: "文件内容" }
      },
      required: ["file_path", "content"]
    }
  },
  {
    name: "edit_file",
    description: "编辑文件内容（搜索替换模式）",
    inputSchema: {
      type: "object",
      properties: {
        file_path: { type: "string", description: "文件绝对路径" },
        old_string: { type: "string", description: "要替换的文本" },
        new_string: { type: "string", description: "新文本" }
      },
      required: ["file_path", "old_string", "new_string"]
    }
  },
  {
    name: "list_dir",
    description: "列出目录内容",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string", description: "目录绝对路径" },
        ignore: { type: "array", items: { type: "string" }, description: "忽略模式（可选）" }
      },
      required: ["path"]
    }
  },
  
  // 搜索工具
  {
    name: "search_files",
    description: "使用 glob 模式搜索文件",
    inputSchema: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "glob 模式，如 **/*.js" },
        path: { type: "string", description: "搜索目录（可选，默认当前目录）" }
      },
      required: ["pattern"]
    }
  },
  {
    name: "grep_search",
    description: "使用 ripgrep 搜索文件内容",
    inputSchema: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "搜索正则表达式" },
        path: { type: "string", description: "搜索目录（可选）" },
        glob: { type: "string", description: "文件过滤模式（可选）" },
        output_mode: { type: "string", enum: ["content", "files"], description: "输出模式" }
      },
      required: ["pattern"]
    }
  },
  
  // 终端工具
  {
    name: "run_command",
    description: "执行命令并返回结果",
    inputSchema: {
      type: "object",
      properties: {
        command: { type: "string", description: "要执行的命令" },
        cwd: { type: "string", description: "工作目录（可选）" },
        timeout: { type: "number", description: "超时时间（毫秒，默认60000）" }
      },
      required: ["command"]
    }
  },
  
  // 代码分析工具
  {
    name: "get_diagnostics",
    description: "获取文件的诊断信息（需要 VS Code 语言服务器）",
    inputSchema: {
      type: "object",
      properties: {
        file_path: { type: "string", description: "文件绝对路径" }
      },
      required: ["file_path"]
    }
  }
];

/**
 * 工具实现
 */
const toolHandlers = {
  // 读取文件
  async read_file(args) {
    const { file_path, offset, limit } = args;
    
    if (!fs.existsSync(file_path)) {
      return { error: `文件不存在: ${file_path}` };
    }
    
    const stats = fs.statSync(file_path);
    if (stats.isDirectory()) {
      return { error: `${file_path} 是目录，不是文件` };
    }
    
    let content = fs.readFileSync(file_path, 'utf-8');
    const lines = content.split('\n');
    const totalLines = lines.length;
    
    // 如果指定了范围
    if (offset !== undefined && limit !== undefined) {
      const start = Math.max(0, offset - 1);
      const end = Math.min(totalLines, start + limit);
      content = lines.slice(start, end).join('\n');
    }
    
    // 截断长内容
    const MAX_LENGTH = 100000;
    const truncated = content.length > MAX_LENGTH;
    if (truncated) {
      content = content.substring(0, MAX_LENGTH) + '\n... (内容已截断)';
    }
    
    return {
      content,
      totalLines,
      truncated,
      file_path
    };
  },

  // 写入文件
  async write_file(args) {
    const { file_path, content } = args;
    
    try {
      // 确保目录存在
      const dir = path.dirname(file_path);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      
      fs.writeFileSync(file_path, content, 'utf-8');
      return { success: true, file_path, bytes: Buffer.byteLength(content, 'utf-8') };
    } catch (error) {
      return { error: `写入失败: ${error.message}` };
    }
  },

  // 编辑文件
  async edit_file(args) {
    const { file_path, old_string, new_string } = args;
    
    if (!fs.existsSync(file_path)) {
      return { error: `文件不存在: ${file_path}` };
    }
    
    const content = fs.readFileSync(file_path, 'utf-8');
    
    if (!content.includes(old_string)) {
      return { error: `找不到要替换的文本` };
    }
    
    // 只替换第一次出现
    const newContent = content.replace(old_string, new_string);
    fs.writeFileSync(file_path, newContent, 'utf-8');
    
    return { 
      success: true, 
      file_path,
      replaced: content !== newContent
    };
  },

  // 列出目录
  async list_dir(args) {
    const { path: dirPath, ignore = [] } = args;
    
    if (!fs.existsSync(dirPath)) {
      return { error: `目录不存在: ${dirPath}` };
    }
    
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    const items = entries
      .filter(entry => !ignore.some(pattern => entry.name.match(pattern)))
      .map(entry => ({
        name: entry.name,
        type: entry.isDirectory() ? 'directory' : 'file',
        path: path.join(dirPath, entry.name)
      }));
    
    return {
      path: dirPath,
      items,
      count: items.length
    };
  },

  // 搜索文件
  async search_files(args) {
    const { pattern, path: searchPath = '.' } = args;
    
    try {
      const files = await globAsync(pattern, {
        cwd: searchPath,
        absolute: true,
        nodir: true
      });
      
      return {
        pattern,
        path: searchPath,
        files: files.slice(0, 100), // 限制结果数量
        total: files.length
      };
    } catch (error) {
      return { error: `搜索失败: ${error.message}` };
    }
  },

  // Grep 搜索
  async grep_search(args) {
    const { pattern, path: searchPath, glob: fileGlob, output_mode = "content" } = args;
    
    try {
      let cmd = `rg -n`;
      if (fileGlob) cmd += ` --glob "${fileGlob}"`;
      if (output_mode === "files") cmd += ` -l`;
      cmd += ` "${pattern}"`;
      if (searchPath) cmd += ` "${searchPath}"`;
      
      const result = execSync(cmd, { encoding: 'utf-8', timeout: 30000 });
      
      return {
        pattern,
        results: result.split('\n').filter(Boolean).slice(0, 50),
        count: result.split('\n').filter(Boolean).length
      };
    } catch (error) {
      if (error.status === 1) {
        // ripgrep 返回 1 表示没有找到匹配
        return { pattern, results: [], count: 0 };
      }
      return { error: `搜索失败: ${error.message}` };
    }
  },

  // 运行命令
  async run_command(args) {
    const { command, cwd, timeout = 60000 } = args;
    
    try {
      const result = execSync(command, {
        cwd: cwd || process.cwd(),
        timeout,
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024 // 10MB
      });
      
      return {
        success: true,
        command,
        output: result,
        exitCode: 0
      };
    } catch (error) {
      return {
        success: false,
        command,
        output: error.stdout?.toString() || '',
        error: error.stderr?.toString() || error.message,
        exitCode: error.status || 1
      };
    }
  },

  // 获取诊断信息（简化版）
  async get_diagnostics(args) {
    const { file_path } = args;
    
    // 这里可以集成 VS Code 语言服务器
    // 简化版本只返回文件基本信息
    if (!fs.existsSync(file_path)) {
      return { error: `文件不存在: ${file_path}` };
    }
    
    const stats = fs.statSync(file_path);
    const ext = path.extname(file_path);
    
    return {
      file_path,
      size: stats.size,
      modified: stats.mtime,
      extension: ext,
      note: "完整诊断需要语言服务器支持"
    };
  }
};

/**
 * 创建 MCP 服务器
 */
const server = new Server(
  {
    name: "scc-mcp-server",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

/**
 * 处理工具列表请求
 */
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: TOOLS,
  };
});

/**
 * 处理工具调用请求
 */
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  console.error(`[SCC MCP] 调用工具: ${name}`);
  
  const handler = toolHandlers[name];
  if (!handler) {
    throw new Error(`未知工具: ${name}`);
  }
  
  try {
    const result = await handler(args);
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ error: error.message }, null, 2),
        },
      ],
      isError: true,
    };
  }
});

/**
 * 启动服务器
 */
async function main() {
  const transport = new StdioServerTransport();
  console.error("[SCC MCP] 服务器启动中...");
  await server.connect(transport);
  console.error("[SCC MCP] 服务器已就绪");
}

main().catch((error) => {
  console.error("[SCC MCP] 错误:", error);
  process.exit(1);
});
