# OpenCode 免费使用指南

## 概述

OpenCode 现在已配置为使用**多种免费模型**，包括 **Kimi K2.5** 等优秀的中文优化模型，无需付费 API 密钥即可使用。

## 🆓 免费模型列表

### 🌟 推荐免费模型 (默认)

| 模型 ID | 名称 | 上下文窗口 | 特点 |
|---------|------|-----------|------|
| **`kimi-k2.5`** | **Moonshot Kimi K2.5** | **256,000 tokens** | **默认模型**，超长上下文，中文优化，代码能力强 |

### OpenRouter 其他免费模型

| 模型 ID | 名称 | 上下文窗口 | 特点 |
|---------|------|-----------|------|
| `openrouter.deepseek-r1-free` | DeepSeek R1 Free | 163,840 tokens | 推理能力强，适合复杂任务 |
| `openrouter.gemini-2.5-flash` | Gemini 2.5 Flash | 动态 | Google 轻量级模型 |

### GROQ 免费模型

| 模型 ID | 名称 | 上下文窗口 | 特点 |
|---------|------|-----------|------|
| `llama-3.3-70b-versatile` | Llama 3.3 70B | 128,000 tokens | Meta 最新模型，通用能力强 |
| `meta-llama/llama-4-scout-17b-16e-instruct` | Llama 4 Scout | 128,000 tokens | Llama 4 系列，轻量级 |
| `meta-llama/llama-4-maverick-17b-128e-instruct` | Llama 4 Maverick | 128,000 tokens | Llama 4 系列，性能更强 |
| `qwen-qwq` | Qwen QwQ | 128,000 tokens | 阿里 Qwen 系列 |
| `deepseek-r1-distill-llama-70b` | DeepSeek R1 Distill Llama 70B | 128,000 tokens | 推理优化模型 |

## 🌟 Kimi K2.5 特点

**Kimi K2.5** 是目前配置的默认免费模型，具有以下优势：

- ✅ **超长上下文**: 256K tokens，可处理大量代码
- ✅ **中文优化**: 对中文理解和生成能力出色
- ✅ **代码能力**: 编程、代码审查、重构表现优秀
- ✅ **免费使用**: 通过 OpenRouter 免费访问
- ✅ **多语言支持**: 支持中英文混合编程场景

## 配置说明

### 1. OpenCode 配置文件

配置文件位置: `C:\scc\plugin\opencode-scc-executor\config\.opencode.json`

当前配置:
- ✅ 启用 **OpenRouter** 提供商 (Kimi K2.5 + 其他免费模型)
- ✅ 启用 **GROQ** 提供商 (Llama 系列等)
- ✅ 禁用付费提供商 (Anthropic, OpenAI, Google)
- ✅ **默认使用 `kimi-k2.5`**

### 2. SCC 执行器配置

配置文件位置: `C:\scc\plugin\opencode-scc-executor\config\opencode.config.json`

包含 8+ 个免费模型配置，支持自动切换。

## 使用方法

### 方式 1: 直接运行 OpenCode CLI

```powershell
cd C:\scc\plugin\opencode

# 使用默认免费模型 (kimi-k2.5)
.\opencode.exe -p "你的提示词" -f json

# 指定特定免费模型
.\opencode.exe -p "你的提示词" --model kimi-k2.5
.\opencode.exe -p "你的提示词" --model openrouter.deepseek-r1-free
.\opencode.exe -p "你的提示词" --model llama-3.3-70b-versatile
.\opencode.exe -p "你的提示词" --model qwen-qwq
```

### 方式 2: 通过 SCC Gateway 使用

Gateway 会自动使用配置的免费模型池，无需额外设置。

环境变量配置 (`.env` 文件):
```env
# 免费模型池 (逗号分隔)
MODEL_POOL_FREE=kimi-k2.5,openrouter.deepseek-r1-free,llama-3.3-70b-versatile,qwen-qwq

# 优先使用免费模型
PREFER_FREE_MODELS=true

# OpenCode 默认模型
OPENCODE_MODEL=kimi-k2.5
```

### 方式 3: 通过 SCC 执行器使用

```javascript
import { getRegistry } from './plugin/opencode-scc-executor/index.mjs';

const registry = await getRegistry();
const executor = registry.getDefault();

// 使用默认免费模型 (kimi-k2.5)
const result = await executor.execute({
  role: 'engineer',
  prompt: '分析当前代码库结构'
});

// 指定特定免费模型
const result2 = await executor.execute({
  role: 'engineer',
  prompt: '优化这段代码',
  model: 'openrouter.deepseek-r1-free'
});
```

## 获取 API Key

### OpenRouter (必需，用于 Kimi K2.5)

1. 访问 https://openrouter.ai/
2. 注册账号
3. 获取免费 API key
4. 设置环境变量:
   ```powershell
   $env:OPENROUTER_API_KEY="your-api-key-here"
   ```

### GROQ (可选)

1. 访问 https://groq.com/
2. 注册账号
3. 获取免费 API key
4. 设置环境变量:
   ```powershell
   $env:GROQ_API_KEY="your-api-key-here"
   ```

## 模型选择建议

| 使用场景 | 推荐模型 | 原因 |
|---------|---------|------|
| **中文编程/文档** | `kimi-k2.5` | 中文优化，代码理解好 |
| **长代码分析** | `kimi-k2.5` | 256K 超长上下文 |
| **复杂推理** | `openrouter.deepseek-r1-free` | 推理能力强 |
| **快速响应** | `llama-3.3-70b-versatile` | GROQ 速度快 |
| **轻量级任务** | `meta-llama/llama-4-scout` | 资源占用低 |
| **中文对话** | `qwen-qwq` | 阿里模型，中文优化 |

## 故障排除

### 如果遇到 403 错误

```
Error: 403 Forbidden {"message":"This model is not available in your region."}
```

解决方案:
- 检查网络连接
- 尝试切换到其他免费模型
- 确认 API key 已正确设置

### 如果遇到 401 错误

```
Error: 401 Unauthorized
```

解决方案:
- 设置对应的 API key 环境变量
- 确认 API key 有效且未过期

### 如果遇到 429 错误 (Rate Limit)

```
Error: 429 Too Many Requests
```

解决方案:
- 免费模型有速率限制，请稍后再试
- 切换到其他免费模型
- 减少并发请求数

## 切换到付费模型

如需使用付费模型，修改配置文件:

1. 编辑 `C:\scc\plugin\opencode-scc-executor\config\.opencode.json`
2. 启用相应提供商 (将 `disabled` 设为 `false`)
3. 设置对应的 API key 环境变量
4. 修改模型名称

## 支持

如有问题，请检查:
- OpenCode 二进制文件: `C:\scc\plugin\opencode\opencode.exe`
- 配置文件: `C:\scc\plugin\opencode-scc-executor\config\`
- Gateway 日志: `C:\scc\scc-bd\artifacts\logs\`

## 模型更新

OpenCode 会定期添加新的免费模型。要获取最新模型列表:

```powershell
cd C:\scc\plugin\opencode
.\opencode.exe --help
```

或在交互模式下按 `Ctrl+O` 查看可用模型。

---

**提示**: Kimi K2.5 是目前推荐的主力免费模型，特别适合中文编程场景和长代码分析任务。
