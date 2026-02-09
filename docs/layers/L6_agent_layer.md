# L6 Agent层

> **对应SSOT分区**: `03_agent_playbook/`（Agent说明书）  
> **对应技术手册**: 第13章  
> **层定位**: Agent执行、Agent路由、Agent协作

---

## 6.1 层定位与职责

### 6.1.1 核心职责

L6是SCC架构的**Agent执行层**，为全系统提供：

1. **Agent路由** - 确定性任务到角色的分配
2. **Agent执行** - 在契约范围内执行更改（SEARCH→HYPOTHESIS→FREEZE→ACT→VERIFY）
3. **证据生成** - 执行过程中产生证据
4. **Agent协作** - 多Agent之间的任务交接
5. **执行状态机** - 标准化的执行流程

### 6.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L6 Agent层                                   │
│ ├─ Agent路由（确定性分配）                    │
│ ├─ Agent执行（5阶段状态机）                   │
│ ├─ 证据生成（执行证据）                       │
│ └─ Agent协作（任务交接）                      │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L7 工具层, L8 证据层, L11 调度层             │
└─────────────────────────────────────────────┘
```

---

## 6.2 来自03_agent_playbook/的核心内容

### 6.2.1 执行状态机

#### 5阶段执行流程

```
SEARCH → HYPOTHESIS → FREEZE → ACT → VERIFY → DONE / FAIL

SEARCH（定位）:
- 目标：找到可验证的失败点/缺口（日志/报错/缺文件/接口差异）
- 产物：证据路径（log/evidence/artifact），以及最小复现步骤或触发条件

HYPOTHESIS（假设）:
- 目标：提出1-3个可证伪假设，给出验证方法与预期输出
- 禁止：直接改代码"碰运气"

FREEZE（冻结范围）:
- 目标：冻结要改的范围与可接受的副作用（文件白名单、接口影响、回滚点）
- 产物：acceptance_tests（最少1条）+ rollback_plan（最少1条）

ACT（执行）:
- 目标：在冻结范围内最小改动，落盘diff + 证据
- 产物：patch（diff）、执行日志、产物路径、退出码

VERIFY（验证）:
- 目标：只认测试/验证器输出（exit_code、golden、回归用例），通过才算DONE
- 失败：进入FAIL（并写失败分类），生成下一条"可执行修复任务"或进入DLQ
```

#### 重试/DLQ/升级策略

**重试（≤3次）**:
- 每次重试必须满足：
  - 修改了假设/验证方式/冻结范围之一（不能重复同一动作）
  - 增加了新的证据（新日志、新diff、新指标）

**DLQ（Dead Letter Queue）**:
- 进入DLQ的条件（满足任一）：
  - 3次重试后仍失败
  - 需要外部依赖（硬件到货/管理员权限/备份后才能做）
  - 风控/登录/第三方不可控导致无法稳定复现
- DLQ要落盘：
  - fail_code（结构化）
  - 阻塞条件
  - 继续执行的最小触发条件

---

## 6.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| Agent路由 | 任务到Agent分配 | `agent_router.py` | `agent_router.py --task "fix bug" --complexity medium` |
| 执行状态机 | 运行5阶段执行 | `execution_engine.py` | `execution_engine.py --contract contract.json --stage ACT` |
| 证据收集 | 收集执行证据 | `evidence_collector.py` | `evidence_collector.py --task-id TASK-001` |
| DLQ管理 | 管理死信队列 | `dlq_manager.py` | `dlq_manager.py list` |
| Agent协作 | 多Agent任务交接 | `agent_handoff.py` | `agent_handoff.py --from executor --to verifier --task TASK-001` |

---

## 6.4 脚本使用示例

```bash
# 1. 路由任务到Agent
python tools/scc/ops/agent_router.py \
  --task "修复登录页面的CSS样式问题" \
  --complexity medium \
  --risk low

# 2. 运行执行状态机（从SEARCH到VERIFY）
python tools/scc/ops/execution_engine.py \
  --contract contracts/task_001.json \
  --start-stage SEARCH \
  --auto-progress \
  --evidence-dir artifacts/scc_tasks/TASK-001/

# 3. 收集执行证据
python tools/scc/ops/evidence_collector.py \
  --task-id TASK-001 \
  --include-logs \
  --include-diff \
  --output artifacts/scc_tasks/TASK-001/evidence/

# 4. 查看DLQ
python tools/scc/ops/dlq_manager.py list \
  --format table \
  --include-blockers

# 5. Agent间任务交接
python tools/scc/ops/agent_handoff.py \
  --from executor \
  --to verifier \
  --task TASK-001 \
  --handoff-template TASK_CONTRACT
```

---

## 6.5 关键文件针脚

```yaml
L6_agent_layer:
  ssot_partition: "03_agent_playbook"
  chapter: 13
  description: "Agent层 - 提供Agent路由、执行状态机、证据生成、Agent协作"
  
  core_spec_files:
    - path: scc-top/docs/ssot/03_agent_playbook/ROLE_SPEC__v0.1.0.md
      description: "角色规范，定义9个Agent角色"
    - path: scc-top/docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md
      description: "SCC运行手册，包含执行状态机定义"
  
  tools:
    - tools/scc/ops/agent_router.py
    - tools/scc/ops/execution_engine.py
    - tools/scc/ops/evidence_collector.py
    - tools/scc/ops/dlq_manager.py
    - tools/scc/ops/agent_handoff.py
  
  related_chapters:
    - technical_manual/chapter_13_agent_layer.md
```

---

## 6.6 本章小结

### 6.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 5阶段执行 | SEARCH→HYPOTHESIS→FREEZE→ACT→VERIFY |
| DLQ | 死信队列，存放无法自动处理的任务 |
| 重试策略 | ≤3次，每次必须有新证据 |
| Agent协作 | 通过标准化交接模板进行 |
| Executor Atomic | Executor必须pins-first，缺pins直接失败 |

### 6.6.2 Executor硬约束

- **Executor MUST be pins-first**: 只能读取 pins allowlist 内的路径
- **缺少 pins 必须失败**: 任务必须以 `PINS_INSUFFICIENT` 失败
- **禁止自由扫描**: 不允许仓库级扫描
- **禁止直接读取 SSOT**: SSOT 仅供控制平面角色使用
- **保持工作空间整洁**: 不得在 `artifacts/<task_id>/` 外遗留文件

#### Executor必需输出

```text
REPORT: <one-line outcome>
SELFTEST.LOG: <commands run or 'none'>
EVIDENCE: <paths or 'none'>
SUBMIT: {"status":"DONE|NEED_INPUT|FAILED","reason_code":"...","touched_files":[...],"tests_run":[...]}
```

- `SUBMIT` 必须是严格的 JSON
- `touched_files` 必须包含补丁/diff 更改的所有文件
- `tests_run` 必须包含至少一条非 `task_selftest` 的命令
- 入口点: `POST /executor/jobs/atomic`

### 6.6.3 依赖关系

```
L6 Agent层
    │
    ├─ 依赖 → L4提示词层（角色定义）
    ├─ 依赖 → L5模型层（模型选择）
    │
    ├─ 提供执行给 → L7 工具层
    ├─ 提供证据给 → L8 证据层
    └─ 提供状态给 → L11 调度层
```

---

**导航**: [← L5](./L5_model_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L7](./L7_tool_layer.md)