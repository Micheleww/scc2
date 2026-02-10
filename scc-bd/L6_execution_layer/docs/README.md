# L6_execution_layer 文档

## 功能名称
执行层 - 任务执行器和工具调用

## 所属层级
L6_execution_layer

## 目录结构

```
L6_execution_layer/
├── docs/                           # 文档目录
│   ├── README.md                   # 本文件
│   ├── olt_cli.md                 # OLT CLI 文档
│   └── trae_executor_v2.md        # Trae Executor V2 文档
├── executors/                      # 执行器实现
│   ├── opencodecli_executor.mjs   # OpenCode CLI 执行器 V1
│   ├── opencodecli_executor_v2.mjs # OpenCode CLI 执行器 V2
│   ├── trae_level_executor.mjs    # Trae 级别执行器
│   └── trae_executor_v2.mjs       # Trae Executor V2 (推荐)
├── mcp_server/                     # MCP 服务器
│   └── scc_mcp_server.mjs         # SCC MCP 实现
├── olt_cli_bridge.mjs             # OLT CLI Bridge V1 (Port 3456)
└── olt_cli_bridge_v2.mjs          # OLT CLI Bridge V2 (Port 3457)
```

## 执行器对比

我们提供两种执行器，分别基于不同的后端：

### 1. OpenCode CLI 执行器
直接调用 OpenCode CLI，工具由 OpenCode 自动执行。

| 执行器 | 工具控制 | 适用场景 | 状态 |
|-------|---------|---------|------|
| `opencodecli_executor.mjs` | 自动 | 简单任务 | 稳定 |
| `opencodecli_executor_v2.mjs` | 自动 | 简单任务 | 稳定 |

**启动方式**: 无需启动额外服务，直接调用 OpenCode CLI

### 2. OLT CLI 执行器 (推荐)
通过 OLT CLI Bridge 调用模型，工具由执行器自己控制。

| 执行器 | 工具控制 | 适用场景 | 状态 |
|-------|---------|---------|------|
| `trae_executor_v2.mjs` | 手动 | 复杂多轮对话 | **推荐** |

**启动方式**:
```bash
# 1. 启动 OLT CLI Bridge V2
node L6_execution_layer/olt_cli_bridge_v2.mjs

# 2. 使用执行器
node L6_execution_layer/executors/trae_executor_v2.mjs
```

**使用示例**:
```javascript
import { execute } from './L6_execution_layer/executors/trae_executor_v2.mjs';
const result = await execute('你的任务描述');
console.log(result.result);
```

## 核心组件

### OpenCode CLI 执行器
直接调用 OpenCode CLI 的执行器，工具由 OpenCode 自动执行。

**文件**:
- `opencodecli_executor.mjs` - 基础执行器
- `opencodecli_executor_v2.mjs` - 增强版执行器

### OLT CLI (OpenCode LLM Tool CLI)
将 OpenCode CLI 封装为 OpenAI-compatible API 的桥接服务器，支持免费使用 Kimi K2.5 模型。

- **V1** (`olt_cli_bridge.mjs`): 自动工具执行，适合快速原型
- **V2** (`olt_cli_bridge_v2.mjs`): 禁用自动工具，适合复杂任务

**特点**:
- 提供标准 OpenAI API 接口
- 支持多轮对话上下文
- 工具调用完全可控

详见：[olt_cli.md](./olt_cli.md)

### Trae Executor V2
基于 OLT CLI 的执行器，实现 Trae 级别的多轮对话能力：
- 多轮对话上下文记忆
- 工具调用意图检测
- 完全可控的执行流程

详见：[trae_executor_v2.md](./trae_executor_v2.md)

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      上层应用                                │
│              (Agent / Task Manager / UI)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              L6_execution_layer                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Trae Executor V2                        │   │
│  │   多轮对话管理 -> 工具解析 -> 工具执行 -> 结果反馈    │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │ HTTP API                      │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │           OpenCode Bridge V2 (Port 3457)             │   │
│  │         OpenAI-compatible API 封装                   │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │ stdin/stdout                  │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │              OpenCode CLI                            │   │
│  │            Kimi K2.5-free 模型                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 工具系统

### 内置工具

| 工具名 | 功能 | 参数 |
|-------|------|------|
| list_dir | 列出目录 | path |
| read_file | 读取文件 | file_path, limit |

### 工具调用格式

```xml
<tool_call>
{
  "tool": "list_dir",
  "args": {
    "path": "C:\\scc\\scc-bd\\L1_code_layer"
  }
}
</tool_call>
```

## 配置

无需额外配置，直接使用 OpenCode CLI 的默认配置。

## 依赖

- Node.js 18+
- OpenCode CLI 已安装
- OpenCode Bridge 运行中

## 测试

```bash
# 测试 Bridge
node test_bridge.mjs

# 测试完整流程
node test_full_flow.mjs

# 测试执行器
node L6_execution_layer/executors/trae_executor_v2.mjs
```

## 作者
SCC Team

## 更新日期
2026-02-10
