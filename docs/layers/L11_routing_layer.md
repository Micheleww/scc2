# L11 路由与调度层

> **对应SSOT分区**: `02_architecture/`, `03_agent_playbook/`  
> **对应技术手册**: 第12章  
> **层定位**: 任务路由、调度策略、负载均衡

---

## 11.1 层定位与职责

### 11.1.1 核心职责

L11是SCC架构的**路由调度层**，为全系统提供：

1. **任务路由** - 确定性任务到角色的分配
2. **调度策略** - 任务优先级和队列管理
3. **负载均衡** - 多执行器之间的负载分配
4. **重试机制** - 失败任务的重试策略
5. **DLQ管理** - 死信队列管理

### 11.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L11 路由与调度层                              │
│ ├─ 任务路由（确定性分配）                     │
│ ├─ 调度策略（优先级/队列）                    │
│ ├─ 负载均衡（多执行器）                       │
│ └─ 重试/DLQ管理                               │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L12 成本层                       │
└─────────────────────────────────────────────┘
```

---

## 11.2 来自02_architecture/和03_agent_playbook/的核心内容

### 11.2.1 路由契约

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/03_agent_playbook/ROLE_SPEC__v0.1.0.md` | 角色规范 | 路由契约定义 |
| `ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md` | 运行手册 | 调度策略、重试规则 |

#### 路由契约（规范）

```yaml
Routing Contract (normative):
  Input:
    - 任务描述（目标文本）
    - 可选元数据（类型、受影响路径、风险标志）
  Output:
    - 一个role_id
    - reason
    - 可选required_skills[]
  Rule: 给定相同输入和RoleSpec，路由必须是确定性的
```

### 11.2.2 调度策略

#### 优先级规则

```
1. 人类目标（Web chat）> 系统生成的任务
2. 阻塞性失败 > 警告性失败
3. 高价值能力（CAPABILITY）> 低价值任务
```

#### 重试策略

```
- 最大重试次数: 3次
- 重试条件: 必须有新的假设/验证方式/冻结范围
- 必须增加新证据（新日志、新diff、新指标）
```

#### DLQ规则

```
进入DLQ条件（满足任一）:
- 3次重试后仍失败
- 需要外部依赖（硬件到货/管理员权限/备份后才能做）
- 风控/登录/第三方不可控导致无法稳定复现

DLQ落盘内容:
- fail_code（结构化）
- 阻塞条件
- 继续执行的最小触发条件
```

### 11.2.4 工作流模板（Flows）

#### Feature Patch v1（功能补丁）

**适用**: 小功能/小修复，目标是"改动小、验证最小、快速合并"。

**输入**:
- `goal`: 一句话目标 + 明确验收标准（DoD）
- `files`: 预计触碰的文件列表（尽量 1-3 个）
- `allowedTests`: 允许运行的最小测试命令

**约束**:
- Executor 只读 pins/切片范围；不扫仓库
- 成功即结束，不自动扩展范围；失败就 fail

**最小闭环步骤**:
1. Designer 生成 pins + assumptions + allowedTests
2. Executor patch-only 完成改动
3. CI gate（exit code=0）通过才算 done
4. 审计/回放：能从日志看出"改了哪里、测了什么、证据在哪"

#### CI Fixup v1（CI修复）

**适用**: 任务执行完成但 CI gate 失败/跳过，需要补齐证据或修复测试/实现。

**触发条件**:
- `ci_gate_result.ok=false`
- 或 `ci_gate_skipped.required=true`

**约束**:
- 最多补救 2 次（超过则保持 failed）
- 修复任务必须把"失败根因 → 修复动作 → 可复现命令 → 证据路径"写清楚

**最小闭环步骤**:
1. 系统自动创建 `ci_fixup_v1`（角色默认 `qa`）
2. Fixup 执行后：CI gate 再次运行
3. 通过：源任务可重新进入 ready 并重跑；不通过：继续失败（最多 2 次）

### 11.2.5 降级策略（Degradation Strategy）

#### 模型降级

按层级降级，从高能力/成本到低能力/成本：

```
Tier 1 (Premium): claude-opus, gpt-4o
Tier 2 (Standard): claude-sonnet, gpt-4o-mini
Tier 3 (Free): glm-4.7, kimi-k2.5, deepseek
```

**规则**:
- 从配置的层级中的主模型开始
- 失败时，尝试同一层级中的下一个模型（如果有）
- 如果该层级已耗尽，降级到下一个层级
- 保留安全策略：不要切换到缺乏所需防护措施的模型/提供商

#### 功能降级

- Map不可用 → 回退到文件列表导航
- Instinct不可用 → 跳过聚类并运行确定性步骤
- Playbook不可用 → 执行单步模式

**附加指导**:
- 降级时优先保证正确性而非完整性
- 发出用户可见的说明，描述降级内容和原因

#### 熔断器规则

- **连续失败阈值**: 在**N**次连续失败后，触发该模型/执行器的熔断器
- **触发时**:
  - 停止向该目标路由请求
  - 进入固定持续时间的冷却期
- **冷却期后**:
  - 半开：允许少量试验请求
  - 如果试验成功，关闭熔断器；否则再次触发

### 11.2.6 升级策略（Escalation Policy）

#### 升级级别

| 级别 | 名称 | 描述 | 典型输出 |
|------|------|------|----------|
| Level 0 | 自重试 | 在同一模型和角色内重试，在 `max_attempts` 范围内 | 继续为 `Active` |
| Level 1 | 模型升级 | 切换到更强的模型以提高推理、工具使用或速度 | 继续为 `Active` |
| Level 2 | 角色升级 | 切换到更高权限的角色（或更广泛的工具访问），同时仍遵守策略 | 继续为 `Active` |
| Level 3 | 人工干预 | 明确请求人工输入；没有它任务无法安全继续 | `NEED_INPUT` |
| Level 4 | 任务中止 | 停止尝试；将任务标记为中止并路由到DLQ供以后分类 | `DLQ` |

#### 升级触发器

| 触发器 | 信号 | 默认操作 |
|--------|------|----------|
| 重复错误 | 相同错误签名连续发生N次 | 升级一级（0→1, 1→2等） |
| `PINS_INSUFFICIENT` | 当前pins下无法获得所需上下文 | 升级到Level 3请求pins/上下文更新 |
| `SCOPE_CONFLICT` | 任务需要更改固定范围外的内容 | 升级到Level 3请求扩展范围或任务拆分 |
| `CI_FAILED` | 质量门对 `allowed_tests` 失败 | 如果还有尝试次数则Level 0自重试；然后如果重复则Level 1 |
| `TIMEOUT_EXCEEDED` | 执行达到合同超时 | 根据根本原因选择Level 1或Level 2；考虑任务拆分 |
| `POLICY_VIOLATION` | 策略不允许请求的操作或内容 | 直接Level 3（需要人工决策） |
| `BUDGET_EXCEEDED` | 预算或配额已超出 | 直接Level 4（中止到DLQ） |

---

## 11.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 任务路由 | 路由任务到角色 | `task_router.py` | `task_router.py --task "fix bug" --meta '{"risk": "high"}'` |
| 调度器 | 管理任务队列 | `scheduler.py` | `scheduler.py status` |
| 负载均衡 | 分配执行器 | `load_balancer.py` | `load_balancer.py --assign TASK-001` |
| 重试管理 | 管理重试 | `retry_manager.py` | `retry_manager.py --task TASK-001 --attempt 2` |
| DLQ管理 | 管理死信队列 | `dlq_manager.py` | `dlq_manager.py list` |

---

## 11.4 脚本使用示例

```bash
# 1. 路由任务到角色
python tools/scc/ops/task_router.py \
  --task "修复登录页面的CSS样式问题" \
  --meta '{"type": "frontend", "risk": "low", "paths": ["src/css/login.css"]}' \
  --format json

# 2. 查看调度器状态
python tools/scc/ops/scheduler.py status \
  --queue all \
  --format table

# 3. 分配任务到执行器
python tools/scc/ops/load_balancer.py assign \
  --task TASK-001 \
  --executor-pool "executor-pool-1" \
  --strategy least-loaded

# 4. 管理重试
python tools/scc/ops/retry_manager.py \
  --task TASK-001 \
  --attempt 2 \
  --new-hypothesis "可能是CSS选择器冲突" \
  --new-evidence artifacts/scc_tasks/TASK-001/logs/v2/

# 5. 查看DLQ
python tools/scc/ops/dlq_manager.py list \
  --format table \
  --include-blockers \
  --include-resume-conditions
```

---

## 11.5 关键文件针脚

```yaml
L11_routing_layer:
  ssot_partition: "02_architecture, 03_agent_playbook"
  chapter: 12
  description: "路由与调度层 - 提供任务路由、调度策略、负载均衡"
  
  core_spec_files:
    - path: scc-top/docs/ssot/03_agent_playbook/ROLE_SPEC__v0.1.0.md
      description: "角色规范，定义路由契约"
    - path: scc-top/docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md
      description: "运行手册，定义调度策略和重试规则"
  
  tools:
    - tools/scc/ops/task_router.py
    - tools/scc/ops/scheduler.py
    - tools/scc/ops/load_balancer.py
    - tools/scc/ops/retry_manager.py
    - tools/scc/ops/dlq_manager.py
  
  related_chapters:
    - technical_manual/chapter_12_routing_layer.md
```

---

## 11.6 本章小结

### 11.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 路由契约 | 任务到角色的确定性分配 |
| 调度策略 | 优先级队列管理 |
| 负载均衡 | 多执行器间的任务分配 |
| DLQ | 死信队列，存放无法处理的任务 |

### 11.6.2 关键规则

1. **确定性路由**: 相同输入必须产生相同输出
2. **重试限制**: 最多3次重试，每次必须有新证据
3. **DLQ条件**: 3次失败、外部依赖、不可控因素
4. **优先级**: 人类目标 > 系统任务

### 11.6.3 依赖关系

```
L11 路由与调度层
    │
    ├─ 依赖 → L4提示词层（角色定义）
    ├─ 依赖 → L10工作空间层（项目范围）
    │
    ├─ 提供路由给 → L6 Agent层
    └─ 提供调度给 → L12 成本层
```

---

**导航**: [← L10](./L10_workspace_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L12](./L12_cost_layer.md)