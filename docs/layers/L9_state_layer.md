# L9 状态与记忆层

> **对应SSOT分区**: `03_agent_playbook/`（Agent说明书）  
> **对应技术手册**: 第4章  
> **层定位**: 会话状态、工作记忆、上下文管理

---

## 9.1 层定位与职责

### 9.1.1 核心职责

L9是SCC架构的**状态管理层**，为全系统提供：

1. **会话状态** - 任务执行状态跟踪（SEARCH→HYPOTHESIS→FREEZE→ACT→VERIFY）
2. **工作记忆** - Agent工作记忆的持久化
3. **上下文管理** - 对话/执行上下文的维护
4. **记忆检索** - 历史记忆的向量检索
5. **状态机** - 任务状态转换管理

### 9.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L9 状态与记忆层                               │
│ ├─ 会话状态（执行状态跟踪）                   │
│ ├─ 工作记忆（Agent记忆持久化）                │
│ ├─ 上下文管理（对话/执行上下文）              │
│ └─ 记忆检索（向量检索）                       │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L4 提示词层                      │
└─────────────────────────────────────────────┘
```

---

## 9.2 来自03_agent_playbook/的核心内容

### 9.2.1 角色记忆

#### 核心文件

| 文件路径 | 说明 |
|----------|------|
| `ssot/03_agent_playbook/roles/index.md` | 角色包索引，包含记忆路径 |

#### 记忆路径规范

```yaml
角色记忆路径:
  router: docs/INPUTS/role_memory/router.md
  planner: docs/INPUTS/role_memory/planner.md
  executor: docs/INPUTS/role_memory/executor.md
  verifier: docs/INPUTS/role_memory/verifier.md
  auditor: docs/INPUTS/role_memory/auditor.md
  secretary: docs/INPUTS/role_memory/secretary.md
  factory_manager: docs/INPUTS/role_memory/factory_manager.md
```

### 9.2.2 执行状态机（状态跟踪）

> **完整执行状态机定义**: 详见 [L6 Agent层 - 5阶段执行流程](./L6_agent_layer.md#621-执行状态机)

L9关注状态的**持久化和检索**，而非状态机本身的流转逻辑。

### 9.2.3 上下文预算管理

#### Token预算

- `max_context_tokens`: 单次模型调用的输入上下文最大token数
- 组合上下文（目标 + 固定文件摘录 + 摘要 + 历史 + 系统支架）必须保持在此限制内

#### 上下文优先级

当预算不足时，按以下优先级顺序修剪上下文（最高优先级优先保留）：

1. **任务目标**（不得修剪）
2. **Pins内容**（按相关性修剪；保留最相关的固定内容）
3. **Map/上下文摘要**（可以缩短为更高级别的摘要）
4. **历史**（可以完全省略）

#### 预算分配策略

默认分配启发式（每个系统可调）：

- 目标: **~15%**
- 固定文件: **~50%**
- Map/上下文: **~25%**
- 为输出预留: **~10%**

预留输出预算可避免模型响应被强制截断。

#### 状态转换规则

```
SEARCH → HYPOTHESIS → FREEZE → ACT → VERIFY → DONE / FAIL

每个状态必须记录:
- 进入时间戳
- 产物/证据路径
- 退出原因
- 下一状态
```

---

## 9.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 状态管理 | 管理任务状态 | `state_manager.py` | `state_manager.py get --task-id TASK-001` |
| 记忆存储 | 存储工作记忆 | `memory_store.py` | `memory_store.py --agent executor --content "..."` |
| 记忆检索 | 检索历史记忆 | `memory_retrieve.py` | `memory_retrieve.py --query "auth pattern" --top-k 5` |
| 上下文管理 | 管理对话上下文 | `context_manager.py` | `context_manager.py compress --session SESSION-001` |
| 状态机运行 | 运行状态机 | `state_machine.py` | `state_machine.py --task-id TASK-001 --transition ACT` |

---

## 9.4 脚本使用示例

```bash
# 1. 获取任务当前状态
python tools/scc/ops/state_manager.py get \
  --task-id TASK-001 \
  --include-history

# 2. 存储Agent工作记忆
python tools/scc/ops/memory_store.py \
  --agent executor \
  --content "学会了新的CSS布局技巧" \
  --tags '["css", "frontend"]' \
  --task-id TASK-001

# 3. 检索相关记忆
python tools/scc/ops/memory_retrieve.py \
  --query "用户认证实现方式" \
  --top-k 5 \
  --agent executor

# 4. 压缩对话上下文
python tools/scc/ops/context_manager.py compress \
  --session SESSION-001 \
  --max-tokens 4000 \
  --strategy summarization

# 5. 状态机状态转换
python tools/scc/ops/state_machine.py \
  --task-id TASK-001 \
  --transition ACT \
  --evidence artifacts/scc_tasks/TASK-001/evidence/
```

---

## 9.5 关键文件针脚

```yaml
L9_state_layer:
  ssot_partition: "03_agent_playbook"
  chapter: 4
  description: "状态与记忆层 - 提供会话状态、工作记忆、上下文管理"
  
  core_spec_files:
    - path: scc-top/docs/ssot/03_agent_playbook/roles/index.md
      description: "角色包索引，包含记忆路径"
    - path: scc-top/docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md
      description: "包含执行状态机定义"
  
  memory_files:
    - path: scc-top/docs/INPUTS/role_memory/router.md
    - path: scc-top/docs/INPUTS/role_memory/planner.md
    - path: scc-top/docs/INPUTS/role_memory/executor.md
    - path: scc-top/docs/INPUTS/role_memory/verifier.md
    - path: scc-top/docs/INPUTS/role_memory/auditor.md
    - path: scc-top/docs/INPUTS/role_memory/secretary.md
    - path: scc-top/docs/INPUTS/role_memory/factory_manager.md
  
  tools:
    - tools/scc/ops/state_manager.py
    - tools/scc/ops/memory_store.py
    - tools/scc/ops/memory_retrieve.py
    - tools/scc/ops/context_manager.py
    - tools/scc/ops/state_machine.py
  
  related_chapters:
    - technical_manual/chapter_04_state_layer.md
```

---

## 9.6 本章小结

### 9.6.1 记忆治理策略

#### 写入权限矩阵

| 角色 | 可写内容 | 禁止写入 | TTL |
|------|---------|---------|-----|
| **executor** | 执行日志、中间结果、临时变量 | 规范文档、策略 | 任务结束 |
| **designer** | 架构决策、设计文档、规范更新 | 执行日志、审计记录 | 长期 |
| **ssot_curator** | SSOT更新、术语表、最佳实践 | 临时结果、执行日志 | 永久 |
| **lessons_miner** | 经验模式、失败案例、改进建议 | 规范原文、策略 | 长期 |
| **auditor** | 审计记录、合规检查 | 其他所有内容 | 永久 |
| **factory_manager** | 工厂配置、策略调整 | 任务具体内容 | 长期 |

#### 记忆类型与TTL

**热记忆 (Hot Memory)**
```yaml
tier: hot
location: memory
ttl: session  # 当前任务会话
content:
  - 当前对话历史
  - 临时计算结果
  - 活跃状态缓存
access_latency: <10ms
```

**温记忆 (Warm Memory)**
```yaml
tier: warm
location: local_storage  # SQLite/JSON
ttl: 24h
content:
  - 今日任务列表
  - 近期事件(24h)
  - 缓存的Pins
  - 常用知识片段
```

### 9.6.2 记忆写入策略

### 9.6.3 任务状态字段

# Task State Fields

This document enumerates common task object fields used by PromptOS/SCC, their meaning, and mutability expectations.

## Field Table

| Field | Type | Description | Mutable |
|------|------|-------------|---------|
| `id` | `uuid` | Task unique identifier. | No |
| `parent_id` | `uuid \| null` | Parent task id if this is a child task. | No |
| `status` | `enum` | `backlog/ready/in_progress/done/failed`. | Yes |
| `kind` | `enum` | Task kind: `parent/atomic`. | No |
| `role` | `string` | Execution role (e.g., executor, curator). | No |
| `lane` | `enum` | `fastlane/mainlane/batchlane/quarantine/dlq`. | Yes |
| `priority` | `number` | Scheduling priority (higher runs sooner). | Yes |
| `title` | `string` | Human-friendly task title. | No |
| `goal` | `string` | Task goal/instructions. | No |
| `created_at` | `datetime` | Creation timestamp. | No |
| `updated_at` | `datetime` | Last update timestamp. | Yes |
| `started_at` | `datetime \| null` | When execution started. | Yes |
| `finished_at` | `datetime \| null` | When execution finished. | Yes |
| `attempt` | `number` | Current attempt index. | Yes |
| `max_attempts` | `number` | Maximum attempts before terminal failure. | No |
| `inputs` | `object` | Structured inputs (pins, constraints, pointers). | No |
| `pins` | `object` | Pins declaration (`allowed_paths`, `forbidden_paths`). | No |
| `constraints` | `object` | Execution constraints (must/forbid/unknown_policy). | No |
| `acceptance` | `array<string>` | Acceptance criteria for completion. | No |
| `execution_plan` | `object` | Stop conditions, fallback policies, retries. | No |
| `required_artifacts` | `object` | Artifact paths required by the runner. | No |
| `submit_contract` | `object` | Schema expectations for final submission. | No |
| `error_snippets` | `array<object>` | Recent error snippets and metadata. | Yes |
| `assigned_to` | `string \| null` | Assigned worker/agent identifier. | Yes |
| `tags` | `array<string>` | Labels (area/type). | Yes |
| `notes` | `string \| null` | Free-form notes / rationale. | Yes |
| `progress` | `number` | Normalized progress (`0.0`–`1.0`). | Yes |
| `result` | `object \| null` | Structured final result metadata. | Yes |
| `timeout_ms` | `number \| null` | Optional task timeout budget. | Yes |

## Example Task Object (Simplified)

```json
{
  "id": "254587b3-c219-4af2-b8f1-3cebe2a9771e",
  "parent_id": "d7baa8d0-5124-403a-a16a-0e2770698a76",
  "title": "PromptOS T05: Context Layer — Pins, Budget, Memory, State",
  "kind": "atomic",
  "role": "executor",
  "lane": "batchlane",
  "priority": 5,
  "status": "in_progress",
  "attempt": 1,
  "max_attempts": 2,
  "created_at": "2026-02-08T00:00:00Z",
  "updated_at": "2026-02-08T00:10:00Z",
  "started_at": "2026-02-08T00:10:00Z",
  "finished_at": null,
  "pins": {
    "allowed_paths": ["docs/prompt_os/context/**"],
    "forbidden_paths": ["**/secrets/**"]
  },
  "constraints": {
    "must": ["patch-only", "minimal-diff"],
    "forbid": ["reading outside pins allowlist"],
    "unknown_policy": "NEED_INPUT"
  },
  "tags": ["docs", "prompt_os"],
  "progress": 0.5,
  "notes": "Drafting context layer documentation"
}
```


---



#### 短期记忆

**短期记忆**是用于完成当前任务的任务内工作状态。

- **范围**: 在单个任务执行内
- **内容**: 中间笔记、草稿、部分摘要、临时决策
- **生命周期**: 任务结束时必须清除
- **持久化**: 默认不写入长期文档位置

典型短期记忆项目：
- 临时解析结果
- 未解决的假设
- 候选补丁计划

#### 长期记忆

**长期记忆**是用于跨任务重用的持久知识。

- **范围**: 跨任务
- **存储位置**: 通常是 `docs/` 和/或 `map/`（项目定义的知识库）
- **质量标准**: 连贯、有来源支持、冲突感知

**写入权限**:
- 只有指定的curator角色（例如 `ssot_curator`）可以写入长期记忆
- 其他角色可以提议更改，但不得直接持久化

#### 记忆冲突解决

当新记忆与现有记忆冲突时，显式解决冲突而不是静默覆盖。

**冲突检测**:
- 矛盾定义（相同术语，不同含义）
- 不兼容默认值（相同字段，不同默认值）
- 重叠的权威来源（两个"SSOT"声明不一致）

**解决规则**:
1. **优先当前SSOT**: 如果项目指定了单一事实来源，该来源获胜
2. **需要来源**: 每个长期记忆更改必须引用其来源
3. **弃用而非删除**: 当存在不确定性时，将旧声明标记为已弃用，添加带有生效日期和理由的新声明
4. **升级未解决冲突**: 升级到curator角色进行审查

### 9.6.4 核心概念

| 概念 | 说明 |
|------|------|
| 会话状态 | 任务执行的当前状态（SEARCH/HYPOTHESIS等） |
| 工作记忆 | Agent的学习和经验存储 |
| 上下文管理 | 对话/执行上下文的压缩和维护 |
| 记忆检索 | 基于语义的向量检索 |
| 记忆治理 | 写入权限、TTL、分层存储管理 |
| 记忆写入策略 | 短期/长期记忆管理、冲突解决 |

### 9.6.5 依赖关系

```
L9 状态与记忆层
    │
    ├─ 依赖 → L17本体层（OID用于状态标识）
    │
    ├─ 提供状态给 → L6 Agent层
    └─ 提供记忆给 → L4 提示词层
```

---

**导航**: [← L8](./L8_evidence_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L10](./L10_workspace_layer.md)