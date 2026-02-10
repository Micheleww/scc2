# SCC Backend (scc-bd)

SCC 后端服务器 - 包含完整的本地功能和插件接口支持。

## 架构

```
scc-bd/
├── src/
│   ├── core/           ← 本地核心功能
│   │   ├── gateway.mjs           # 主网关入口
│   │   ├── router*.mjs           # 路由系统
│   │   ├── role_system.mjs       # 角色系统
│   │   ├── map_v1.mjs            # Map 系统
│   │   ├── pins_builder_v1.mjs   # Pins 构建器
│   │   ├── preflight_v1.mjs      # 预检系统
│   │   ├── factory_policy_v1.mjs # 工厂策略
│   │   └── verifier_judge_v1.mjs # 验证裁决
│   ├── plugins/        ← 插件接口（外部服务代理）
│   │   ├── opencode_proxy.mjs    # OpenCode 代理
│   │   ├── clawdbot_proxy.mjs    # Clawdbot 代理
│   │   ├── webgpt_proxy.mjs      # WebGPT 代理
│   │   ├── mcp_proxy.mjs         # MCP Bus 代理
│   │   ├── a2a_proxy.mjs         # A2A Hub 代理
│   │   ├── exchange_proxy.mjs    # Exchange 代理
│   │   └── langgraph_proxy.mjs   # LangGraph 代理
│   ├── executors/      ← 执行器
│   ├── lib/            ← 工具库
│   └── config/         ← 配置
├── scripts/            ← 脚本工具
├── ui/                 ← Web 界面
├── prompts/            ← 提示词
├── docker/             ← Docker 配置
└── config/             ← 运行时配置
```

## 功能分类

### 本地功能（Core）
- **Gateway** - HTTP 代理和路由
- **Role System** - 角色权限系统
- **Board Management** - 任务看板
- **Map System** - 代码地图构建和查询
- **Pins Builder** - 上下文构建
- **Preflight** - 预检系统
- **Factory Policy** - 工厂策略（熔断器、健康检查）
- **Verifier Judge** - 验证裁决
- **Context Pack** - 上下文打包
- **Self-check** - 自检系统

### 插件接口（Plugins）
| 服务 | 路径 | 说明 |
|-----|------|------|
| **OpenCode** | `/opencode/*` | AI 模型服务代理 |
| **Clawdbot/OpenClaw** | `/clawdbot/*` | 外部工具代理 |
| **WebGPT** | `/webgpt/*` | ChatGPT 个性化记忆 |
| **MCP Bus** | `/mcp/*` | Model Context Protocol |
| **A2A Hub** | `/api/*` | Agent-to-Agent 通信 |
| **Exchange** | `/exchange/*` | 交换服务器 |
| **LangGraph** | `/langgraph/*` | 工作流引擎 |
| **Executor** | `/executor/*` | 任务执行器 |

## 快速开始

### 本地开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev
# 或
npm start

# 运行自检
npm run smoke
```

### Docker 部署

```bash
# 构建镜像
cd docker
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f scc-bd

# 停止服务
docker-compose down
```

### 带 Daemon 的部署

```bash
# 启动主服务 + 后台任务处理器
docker-compose --profile with-daemon up -d
```

## 环境变量

### 核心配置
| 变量 | 默认值 | 说明 |
|-----|--------|------|
| `GATEWAY_PORT` | 18788 | 网关监听端口 |
| `LOG_LEVEL` | info | 日志级别 |
| `NODE_ENV` | production | 运行环境 |

### 插件上游配置
| 变量 | 默认值 | 说明 |
|-----|--------|------|
| `OPENCODE_UPSTREAM` | http://host.docker.internal:18790 | OpenCode 服务地址 |
| `CLAWDBOT_UPSTREAM` | http://host.docker.internal:19001 | Clawdbot 服务地址 |
| `SCC_UPSTREAM` | http://127.0.0.1:18789 | SCC 上游服务地址 |

### 执行器配置
| 变量 | 默认值 | 说明 |
|-----|--------|------|
| `EXEC_CONCURRENCY_CODEX` | 4 | Codex 最大并发数 |
| `EXEC_CONCURRENCY_OPENCODE` | 6 | OpenCodeCLI 最大并发数 |
| `MODEL_POOL_FREE` | opencode/kimi-k2.5-free | 免费模型池 |
| `PREFER_FREE_MODELS` | true | 优先使用免费模型 |

### 自动化配置
| 变量 | 默认值 | 说明 |
|-----|--------|------|
| `SCC_AUTOMATION_MAX_OUTSTANDING` | 3 | 最大并发任务数 |
| `AUTO_SPLIT_ON_PARENT_CREATE` | true | 父任务自动拆分 |
| `CIRCUIT_BREAKERS_ENABLED` | true | 启用熔断器 |

## API 端点

### 健康检查
- `GET /health` - 健康状态
- `GET /healthz` - 详细健康检查
- `GET /status` - 服务状态

### 核心功能
- `GET /metrics` - Prometheus 指标
- `GET /debug/state` - 调试状态
- `GET /` - 首页仪表盘

### 插件代理
- `/opencode/*` → OpenCode 服务
- `/clawdbot/*` → Clawdbot 服务
- `/webgpt/*` → WebGPT 服务
- `/mcp/*` → MCP Bus
- `/api/*` → A2A Hub
- `/exchange/*` → Exchange Server
- `/langgraph/*` → LangGraph

## 脚本工具

```bash
# Map 操作
npm run map:build          # 构建代码地图
npm run map:query          # 查询地图
npm run map:sqlite         # 构建 SQLite 地图

# Pins 操作
npm run pins:build         # 构建 Pins

# 预检
npm run preflight:check    # 运行预检

# 自检
npm run selfcheck:role-system
npm run selfcheck:map-v1
npm run selfcheck:factory-policy-v1
# ... 更多自检脚本
```

## 从 oc-scc-local 迁移

`scc-bd` 是 `oc-scc-local` 的重构版本，主要变化：

1. **目录结构调整**
   - `src/` → `src/core/` (核心功能)
   - 新增 `src/plugins/` (插件接口)

2. **名称变更**
   - 包名从 `oc-scc-local` 改为 `scc-bd`
   - 描述更新为包含插件接口支持

3. **Docker 支持**
   - 新增完整的 Docker 配置
   - 支持 Node.js + Python 混合运行时

## License

UNLICENSED
