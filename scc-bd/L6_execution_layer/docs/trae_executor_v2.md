# Trae Executor V2

## 功能名称
Trae Executor V2 - Trae 级别的多轮对话和工具调用执行器

## 所属层级
L6_execution_layer

## 功能描述
实现类似 Trae IDE 的多轮对话能力，支持：
- 多轮对话上下文记忆
- 工具调用意图检测
- 工具执行和结果反馈
- 完全可控的对话流程

## 核心特性

### 多轮对话管理
- 维护完整的对话历史
- 支持系统提示词
- 最大轮数限制（默认 10 轮）

### 工具系统
- **list_dir**: 列出目录内容
- **read_file**: 读取文件内容
- 支持自定义工具扩展

### 工具调用格式
```xml
<tool_call>
{
  "tool": "工具名",
  "args": {
    "参数名": "参数值"
  }
}
</tool_call>
```

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Trae Executor V2                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  对话管理    │    │  工具解析    │    │  工具执行    │     │
│  │  - 历史记录  │ -> │  - 格式匹配  │ -> │  - 本地实现  │     │
│  │  - 上下文   │    │  - 意图识别  │    │  - 结果返回  │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenCode Bridge V2 (Port 3457)                 │
└─────────────────────────────────────────────────────────────┘
```

## 工作流程

1. **初始化**: 构建系统提示词，包含工具定义
2. **用户输入**: 接收任务描述
3. **AI 调用**: 发送对话历史到 Bridge
4. **响应解析**: 检查是否包含工具调用
5. **工具执行**: 解析并执行工具
6. **结果反馈**: 将工具结果返回给 AI
7. **循环**: 重复步骤 3-6 直到任务完成

## API

### execute(task, options)

**参数:**
- `task` (string): 任务描述
- `options.maxRounds` (number): 最大对话轮数，默认 10

**返回:**
```javascript
{
  ok: true,
  conversation: [...],  // 完整对话记录
  result: "最终回复"     // AI 的最后回复
}
```

## 使用示例

```javascript
import { execute } from './trae_executor_v2.mjs';

const result = await execute(
  '请查看 C:\\scc\\scc-bd\\L1_code_layer 目录，然后读取 README.md 前10行，总结项目。',
  { maxRounds: 5 }
);

console.log(result.result);
```

## 示例对话流程

**Round 1:**
- 用户: "请查看 C:\scc\scc-bd\L1_code_layer 目录"
- AI: `<tool_call>{"tool": "list_dir", "args": {"path": "..."}}</tool_call>`

**Round 2:**
- 系统: [工具执行结果]
- AI: "目录包含 config, docker, gateway..."

## 系统提示词模板

```
你是 AI 助手。你可以使用以下工具：

1. list_dir - 列出目录内容
   参数: { "path": "目录路径" }

2. read_file - 读取文件
   参数: { "file_path": "文件路径", "limit": 行数 }

当你需要使用工具时，请输出：
<tool_call>
{
  "tool": "工具名",
  "args": { ...参数 }
}
</tool_call>

我会执行工具并返回结果给你。
```

## 工具实现

### list_dir
```javascript
async function list_dir(args) {
  const entries = await fs.readdir(args.path, { withFileTypes: true });
  return {
    success: true,
    directories: entries.filter(e => e.isDirectory()).map(e => e.name),
    files: entries.filter(e => e.isFile()).map(e => e.name)
  };
}
```

### read_file
```javascript
async function read_file(args) {
  const content = await fs.readFile(args.file_path, 'utf-8');
  const lines = content.split('\n');
  return {
    success: true,
    content: lines.slice(0, args.limit || 50).join('\n'),
    total_lines: lines.length
  };
}
```

## 扩展工具

要添加新工具，在 `TOOLS` 对象中添加实现：

```javascript
const TOOLS = {
  async my_tool(args) {
    // 工具实现
    return { success: true, data: ... };
  }
};
```

并在系统提示词中添加工具定义。

## 依赖

- OpenCode Bridge V2 运行中
- Node.js 18+ (fetch API)

## 相关文件

- `trae_executor_v2.mjs` - 执行器实现
- `opencode_llm_bridge_v2.mjs` - 桥接服务器
- `docs/opencode_llm_bridge.md` - 桥接服务器文档

## 作者
SCC Team

## 更新日期
2026-02-10
