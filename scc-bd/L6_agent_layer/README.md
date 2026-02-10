# L6 Agent Layer - 执行编排层

> **层职责**: Agent 执行、任务编排、运行时管理

---

## 功能分类

| 功能 | 路径 | 说明 |
|------|------|------|
| **Agent Service** | `agent_service/` | 统一 Agent 服务（Skills、Context、Roles） |
| **Agent Core** | `agent/` | Agent 核心实现 |
| **执行器** | `executors/` | 各种执行器实现 |
| **编排器** | `orchestrators/` | 任务编排组件 |
| **运行时** | `runtime/` | 运行时环境 |

---

## 核心组件

### Agent Service (Port 18000)
统一服务入口，整合所有模块化组件：
- Skills Registry (`/skills/*`)
- Context Renderer (`/context/*`) - 7 Slots
- Role Registry (`/roles/*`) - 规划中

[查看详情 →](agent_service/README.md)

### Agent Core
Agent 核心实现，包含：
- TaskBox 任务管理
- HookSystem 钩子系统
- 可插拔执行器

[查看详情 →](agent/README.md)

---

## 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Service                        │
│                      (Port 18000)                       │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │   Skills    │  │   Context   │  │     Roles       │  │
│  │  Registry   │  │  Renderer   │  │   Registry      │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    Agent Core                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐  │
│  │ TaskBox │  │  Hooks  │  │ Context │  │ Executors │  │
│  └─────────┘  └─────────┘  └─────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    Executors                            │
│              (oltcli, codexcli, ...)                    │
└─────────────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# 启动 Agent Service
cd agent_service
node server.mjs

# 启动 Agent Core
cd ../agent
node agent_core.mjs
```

---

## 相关层

- [L4 Prompt Layer](../L4_prompt_layer/) - Roles 和 Skills 定义
- [L5 Model Layer](../L5_model_layer/) - 模型适配
- [L9 State Layer](../L9_state_layer/) - 状态存储
