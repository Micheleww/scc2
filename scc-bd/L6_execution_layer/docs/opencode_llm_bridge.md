# OpenCode LLM Bridge

## 功能名称
OpenCode LLM Bridge - OpenCode CLI 到 OpenAI API 的桥接服务器

## 所属层级
L6_execution_layer

## 功能描述
将 OpenCode CLI 的模型调用能力封装为标准 OpenAI-compatible API，使上层执行器可以通过 HTTP API 调用 OpenCode 的免费模型（Kimi K2.5-free）。

## 核心特性

### Bridge V1 (Port 3456)
- **自动工具执行**: OpenCode CLI 自动执行工具调用
- **适用场景**: 快速原型、简单任务
- **限制**: 无法控制工具调用流程

### Bridge V2 (Port 3457)
- **禁用自动工具**: 使用 `--agent summary` 禁用工具自动执行
- **工具调用控制**: 上层执行器自己解析和执行工具
- **适用场景**: 需要完全控制多轮对话的复杂任务

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Trae Executor V2                         │
│         解析工具调用 -> 执行工具 -> 返回结果                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenCode Bridge (Port 3457)                    │
│         OpenAI-compatible API /v1/chat/completions          │
└──────────────────────────┬──────────────────────────────────┘
                           │ stdin/stdout
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenCode CLI --agent summary                   │
│                    Kimi K2.5-free                           │
└─────────────────────────────────────────────────────────────┘
```

## API 接口

### POST /v1/chat/completions
OpenAI 标准的 Chat Completions API

**请求体:**
```json
{
  "model": "opencode/kimi-k2.5-free",
  "messages": [
    {"role": "system", "content": "系统提示"},
    {"role": "user", "content": "用户输入"}
  ]
}
```

**响应:**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "AI 响应"
    }
  }]
}
```

## 工具调用格式

Bridge V2 期望 AI 输出标准工具调用格式：

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

## 启动方式

```bash
# Bridge V1 (自动工具执行)
node L6_execution_layer/opencode_llm_bridge.mjs

# Bridge V2 (禁用自动工具)
node L6_execution_layer/opencode_llm_bridge_v2.mjs
```

## 配置

无需配置，直接使用 OpenCode CLI 的默认配置和免费模型。

## 依赖

- OpenCode CLI 已安装并配置
- Node.js 18+

## 使用示例

```javascript
const response = await fetch('http://localhost:3457/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer sk-test'
  },
  body: JSON.stringify({
    model: 'opencode/kimi-k2.5-free',
    messages: [
      { role: 'user', content: 'Hello' }
    ]
  })
});

const data = await response.json();
console.log(data.choices[0].message.content);
```

## 相关文件

- `opencode_llm_bridge.mjs` - Bridge V1 实现
- `opencode_llm_bridge_v2.mjs` - Bridge V2 实现
- `trae_executor_v2.mjs` - 使用 Bridge V2 的执行器

## 作者
SCC Team

## 更新日期
2026-02-10
