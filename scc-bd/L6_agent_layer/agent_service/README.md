# Agent Service - 统一 Agent 服务

> **功能分类**: Agent层 - 执行编排  
> **位置**: `L6_agent_layer/agent_service/`  
> **端口**: 18000

---

## 功能概述

Agent Service 是 SCC 的统一 Agent 服务，整合所有模块化组件：
- **Skills Registry** - Skills 注册表
- **Context Renderer** - 上下文渲染（7 Slots）
- **Role Registry** - Role 管理（规划中）
- **Task Management** - 任务管理（规划中）

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Service                        │
│                      (Port 18000)                       │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │   Skills    │  │   Context   │  │     Roles       │  │
│  │  Registry   │  │  Renderer   │  │   (planned)     │  │
│  │  /skills/*  │  │ /context/*  │  │   /roles/*      │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    Agent Core                           │
│              (使用 AgentServiceClient)                  │
└─────────────────────────────────────────────────────────┘
```

---

## API 端点

### Health
```
GET /health
```

### Skills API
```
GET  /skills/search?q=xxx&role=xxx&category=xxx
POST /skills/find-for-task          # 为任务查找相关 skills
GET  /skills/get?id=xxx
GET  /skills/list?category=xxx&role=xxx
GET  /skills/stats
```

### Context API
```
POST /context/render                # 渲染完整上下文（7 slots）
POST /context/render/slot           # 渲染单个 slot
```

---

## 7 Slots 上下文渲染

基于 `L2_task_layer/context_pack/context_pack_v1.mjs` 设计：

| Slot | 名称 | 说明 |
|------|------|------|
| 0 | LEGAL_PREFIX | 法律前缀/免责声明 |
| 1 | BINDING_REFS | 绑定引用（文件、Role、Mode） |
| 2 | ROLE_CAPSULE | Role 胶囊（system prompt、capabilities） |
| 3 | TASK_BUNDLE | 任务包（task 详情） |
| 4 | STATE | 状态（可持久化状态） |
| 5 | TOOLS | 工具（可用工具列表） |
| 6 | OPTIONAL_CONTEXT | 可选上下文（skills、额外信息） |

---

## 使用方法

### 启动服务
```bash
cd L6_agent_layer/agent_service
node server.mjs
```

### 使用客户端
```javascript
import { AgentServiceClient } from "../agent/core/agent-service-client.mjs"

const client = new AgentServiceClient("http://localhost:18000")

// 搜索 skills
const skills = await client.searchSkills("testing")

// 为任务查找 skills
const relevant = await client.findSkillsForTask(task, "executor")

// 渲染上下文
const context = await client.renderContext({
  role: "executor",
  task: { title: "...", goal: "..." },
  skills: relevant.skills
})
```

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `server.mjs` | 统一服务入口 |
| `../agent/core/agent-service-client.mjs` | 客户端 |

---

## 相关文档

- [Context Pack V1](../../L2_task_layer/context_pack/context_pack_v1.mjs) - 原始 7 slots 实现
- [Agent Core](../agent/agent_core.mjs) - Agent 核心
