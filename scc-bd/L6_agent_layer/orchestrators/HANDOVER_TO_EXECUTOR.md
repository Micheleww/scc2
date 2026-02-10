# 工作交接文档：Parent Inbox → Executor Role

> **交接人**: Parent Inbox Watcher  
> **接收人**: Executor Role  
> **日期**: 2026-02-10  
> **状态**: ✅ Parent Inbox 链路已完成，等待 Executor 实现

---

## 📋 已完成的工作

### 1. Parent Inbox Watcher (`parent_inbox_watcher.mjs`)

**位置**: `L6_agent_layer/orchestrators/parent_inbox_watcher.mjs`

**功能**:
- ✅ 监听 `parent_inbox.jsonl` 文件
- ✅ 自动分解父任务为子任务
- ✅ 将子任务提交到 Jobs Store
- ✅ 更新父任务状态 (pending → decomposing → completed)

**验证结果**:
```
父任务 (pending) 
    ↓
Parent Inbox Watcher
    ↓
子任务已创建
    ↓
Jobs Store (exec_state.json) ✅
```

### 2. Job Executor Bridge (`job_executor_bridge.mjs`)

**位置**: `L6_agent_layer/orchestrators/job_executor_bridge.mjs`

**功能**:
- 轮询 Jobs Store 中的 pending 任务
- 根据任务类型选择合适的 Role
- 将任务写入 Role Inbox (`/app/artifacts/role_inbox/{role}_inbox.jsonl`)
- 更新 Job 状态为 assigned

---

## 🔄 当前数据流

```
┌─────────────────────────────────────────────────────────────┐
│  Parent Inbox                                               │
│  /app/artifacts/scc_state/parent_inbox.jsonl               │
│                                                             │
│  {"type":"parent_task","status":"completed",...}            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Parent Inbox Watcher                                       │
│  (已部署并运行)                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Jobs Store                                                 │
│  /app/artifacts/executor_logs/exec_state.json              │
│                                                             │
│  {                                                          │
│    "jobs": {                                                │
│      "subtask_xxx": {                                       │
│        "id": "subtask_xxx",                                 │
│        "title": "测试任务",                                  │
│        "goal": "测试父任务自动分解",                          │
│        "status": "pending",  ← 等待执行                     │
│        "executor": "opencodecli",                           │
│        "model": "opencode/kimi-k2.5-free",                  │
│        "prompt": "Task: 测试任务\nGoal: ..."                 │
│      }                                                      │
│    }                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Job Executor Bridge                                        │
│  (已创建，需要部署)                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Role Inbox                                                 │
│  /app/artifacts/role_inbox/executor_inbox.jsonl            │
│                                                             │
│  {"type":"role_task","role":"executor",...}                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    ❓ 需要实现
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Executor Role                                              │
│  - 读取 Role Inbox                                          │
│  - 执行实际任务                                             │
│  - 更新执行结果                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 下一步工作（交给 Executor Role）

### 1. 部署 Job Executor Bridge

```bash
# 在 Docker 容器中启动
docker exec scc-server node /app/scc-bd/L6_agent_layer/orchestrators/job_executor_bridge.mjs &
```

### 2. 实现 Executor Role Worker

需要创建一个新的组件：`L6_agent_layer/executors/role_executor_worker.mjs`

**职责**:
- 监听 `/app/artifacts/role_inbox/executor_inbox.jsonl`
- 读取分配给 executor role 的任务
- 调用实际的执行器（opencodecli/codex/trae）
- 更新任务状态和结果

**参考实现**:
```javascript
// 伪代码
function processRoleTask(roleTask) {
  // 1. 准备执行环境
  const context = prepareContext(roleTask)
  
  // 2. 调用执行器
  const result = await executeWithOpenCode({
    prompt: roleTask.prompt,
    systemPrompt: roleTask.systemPrompt,
    model: roleTask.model
  })
  
  // 3. 更新 Jobs Store
  await updateJobStatus(roleTask.jobId, "completed", result)
  
  // 4. 生成 artifacts
  await generateArtifacts(roleTask.jobId, result)
}
```

### 3. 集成到 Service Manager

修改 `L1_code_layer/service-manager.mjs`，添加 Job Executor Bridge 和 Role Executor Worker 到自动启动服务列表。

---

## 📁 相关文件

| 文件 | 路径 | 说明 |
|-----|------|------|
| Parent Inbox Watcher | `L6_agent_layer/orchestrators/parent_inbox_watcher.mjs` | 已完成 ✅ |
| Job Executor Bridge | `L6_agent_layer/orchestrators/job_executor_bridge.mjs` | 已创建，待部署 |
| Role Executor Worker | `L6_agent_layer/executors/role_executor_worker.mjs` | 需要实现 ❓ |
| Jobs Store | `/app/artifacts/executor_logs/exec_state.json` | 数据存储 |
| Role Inbox | `/app/artifacts/role_inbox/` | Role 任务队列 |
| Gateway | `L1_code_layer/gateway/gateway.mjs` | API 网关 |
| Router Executor | `L11_routing_layer/routing/router_executor.mjs` | Job API 路由 |

---

## 🔍 测试方法

### 1. 验证 Parent Inbox Watcher

```bash
# 添加一个测试父任务
echo '{"type":"parent_task","description":"测试任务","status":"pending","title":"测试","role":"workspace_janitor","files":["docs/INDEX.md"]}' >> /app/artifacts/scc_state/parent_inbox.jsonl

# 等待 5 秒
# 检查 Jobs Store
cat /app/artifacts/executor_logs/exec_state.json
```

### 2. 验证 Job Executor Bridge

```bash
# 启动 Bridge
node L6_agent_layer/orchestrators/job_executor_bridge.mjs &

# 检查 Role Inbox 是否生成
cat /app/artifacts/role_inbox/executor_inbox.jsonl
```

---

## 📞 问题联系

如有问题，请查看：
1. `L6_agent_layer/orchestrators/parent_inbox_watcher.mjs` 的实现
2. `L6_agent_layer/orchestrators/job_executor_bridge.mjs` 的实现
3. `L4_prompt_layer/roles/executor.json` Role 策略定义

---

**交接完成时间**: 2026-02-10  
**交接状态**: ✅ 完成  
**下一步负责人**: Executor Role 开发者
