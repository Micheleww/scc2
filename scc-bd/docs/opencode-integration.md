# OpenCode 执行器集成文档

## 概述

OpenCode 已配置为 SCC 系统的主要执行器，提供 AI 驱动的任务执行、代码生成和验证功能。

## 架构

```
SCC System
├── L6_agent_layer/
│   └── executors/
│       ├── index.mjs              # 执行器模块导出
│       ├── registry.mjs           # 执行器注册表
│       ├── opencode_executor.mjs  # OpenCode 原生执行器
│       ├── opencode_wrapper.mjs   # OpenCode Node.js 包装器
│       └── ...
├── config/
│   ├── opencode.config.json       # OpenCode 执行器配置
│   └── .opencode.json            # OpenCode CLI 配置
└── scripts/
    ├── start-opencode.ps1        # 启动脚本
    └── test-opencode-executor.mjs # 测试脚本
```

## 配置

### 1. 执行器配置 (`config/opencode.config.json`)

```json
{
  "executor": {
    "name": "opencode",
    "type": "cli",
    "enabled": true,
    "concurrency": 6,
    "timeout": { "default": 300000, "max": 600000 }
  },
  "models": {
    "default": "claude-3.7-sonnet",
    "available": [...]
  },
  "agents": {
    "coder": { "model": "claude-3.7-sonnet", ... },
    "task": { "model": "claude-3.7-sonnet", ... },
    "verifier": { "model": "claude-3.5-sonnet", ... }
  }
}
```

### 2. OpenCode CLI 配置 (`config/.opencode.json`)

```json
{
  "providers": {
    "anthropic": { "apiKey": "${ANTHROPIC_API_KEY}" },
    "openai": { "apiKey": "${OPENAI_API_KEY}" },
    "google": { "apiKey": "${GEMINI_API_KEY}" }
  },
  "agents": { ... },
  "shell": { "path": "powershell.exe", ... }
}
```

## 环境变量

在使用前需要设置以下环境变量：

```powershell
# Anthropic Claude
$env:ANTHROPIC_API_KEY = "your-anthropic-api-key"

# OpenAI
$env:OPENAI_API_KEY = "your-openai-api-key"

# Google Gemini
$env:GEMINI_API_KEY = "your-gemini-api-key"
```

## 使用方法

### 1. 基本使用

```javascript
import { getRegistry } from './L6_agent_layer/executors/index.mjs';

// 获取注册表
const registry = await getRegistry();

// 获取默认执行器
const executor = registry.getDefault();

// 执行任务
const result = await executor.execute({
  id: 'task-001',
  role: 'engineer',
  skills: ['implementation'],
  prompt: 'Implement a function to...'
}, {
  contextPack: '...'
});
```

### 2. 角色映射

| SCC 角色 | OpenCode Agent | 模型 |
|---------|---------------|------|
| engineer | coder | claude-3.7-sonnet |
| integrator | task | claude-3.7-sonnet |
| designer | task | claude-3.7-sonnet |
| auditor | verifier | claude-3.5-sonnet |
| verifier_judge | verifier | claude-3.5-sonnet |

### 3. 测试

```powershell
# 运行测试
node scripts\test-opencode-executor.mjs
```

## 支持的模型

### 标准模型
- **Claude 3.7 Sonnet** - 主要编码模型
- **Claude 3.5 Sonnet** - 验证和轻量级任务
- **GPT-4o** - OpenAI 替代方案

### 免费模型
- **Gemini 2.5 Pro** - Google 免费模型
- **Gemini 2.0 Flash** - 快速响应

## 工具支持

OpenCode 执行器支持以下工具：

- `bash` - 执行 shell 命令
- `glob` - 文件模式匹配
- `grep` - 文件内容搜索
- `ls` - 目录列表
- `view` - 查看文件内容
- `write` - 写入文件
- `edit` - 编辑文件
- `patch` - 应用补丁
- `diagnostics` - 获取诊断信息

## 安全限制

### 允许的命令
- git, npm, node, python
- cat, ls, grep, find
- mkdir, cp, mv, rm
- 其他常用命令

### 阻止的模式
- `rm -rf /` 或 `rm -rf ~`
- 设备直接操作
- 管道到 shell 的 curl/wget

## 日志

执行日志保存在：
```
artifacts/executor_logs/opencode/
```

## 故障排除

### 1. 执行器未找到
```
[ExecutorRegistry] OpenCode binary not found, using wrapper
```
这是正常行为，系统会自动使用 Node.js 包装器。

### 2. API 密钥未设置
```
Environment variable not set: ANTHROPIC_API_KEY
```
需要设置相应的 API 密钥环境变量。

### 3. 任务执行失败
检查：
- API 密钥是否有效
- 网络连接是否正常
- 任务提示词是否正确

## 未来改进

1. **编译原生二进制** - 安装 Go 后编译 OpenCode 以获得完整功能
2. **添加更多模型** - 支持更多 AI 提供商
3. **缓存机制** - 添加响应缓存以提高性能
4. **监控** - 添加执行器性能监控

## 参考

- [OpenCode GitHub](https://github.com/opencode-ai/opencode)
- [SCC 架构文档](./architecture.md)
- [角色系统文档](./roles.md)
