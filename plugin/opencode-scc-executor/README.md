# OpenCode SCC Executor

OpenCode 执行器作为 SCC 系统的 AI 执行组件，提供任务执行、代码生成和验证功能。

## 目录结构

```
opencode-scc-executor/
├── config/
│   ├── opencode.config.json    # 执行器主配置
│   └── .opencode.json          # OpenCode CLI 配置
├── scripts/
│   └── test-opencode-executor.mjs  # 测试脚本
├── index.mjs                   # 模块导出
├── opencode_executor.mjs       # 原生执行器
├── opencode_wrapper.mjs        # Node.js 包装器
├── registry.mjs                # 执行器注册表
└── README.md                   # 本文档
```

## 快速开始

### 1. 测试执行器

```powershell
cd C:\scc\plugin\opencode-scc-executor
node scripts\test-opencode-executor.mjs
```

### 2. 在 SCC 中使用

```javascript
import { getRegistry } from 'C:/scc/plugin/opencode-scc-executor/index.mjs';

const registry = await getRegistry();
const executor = registry.getDefault();

const result = await executor.execute({
  id: 'task-001',
  role: 'engineer',
  prompt: 'Implement...'
});
```

## 配置

### 环境变量

```powershell
$env:ANTHROPIC_API_KEY = "your-key"
$env:OPENAI_API_KEY = "your-key"
$env:GEMINI_API_KEY = "your-key"
```

### 配置文件

- `config/opencode.config.json` - 执行器配置
- `config/.opencode.json` - OpenCode CLI 配置

## 依赖

- OpenCode 源码: `C:\scc\plugin\opencode`
- Node.js 18+
- (可选) Go 1.24+ 用于编译原生二进制

## 许可证

MIT
