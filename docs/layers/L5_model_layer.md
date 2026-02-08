# L5 模型层

> **对应SSOT分区**: `02_architecture/`（架构文档）  
> **对应技术手册**: 第14章  
> **层定位**: 模型配置、模型选择策略、模型能力映射

---

## 5.1 层定位与职责

### 5.1.1 核心职责

L5是SCC架构的**模型管理层**，为全系统提供：

1. **模型配置** - 多模型配置管理（kimi-k2.5, claude-3.5等）
2. **模型选择** - 任务到模型的路由策略
3. **能力映射** - 模型能力与任务需求匹配
4. **升级策略** - 模型失败时的升级路径（4级升级）
5. **成本追踪** - 模型调用的token成本追踪

### 5.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L5 模型层                                     │
│ ├─ 模型配置（多模型管理）                     │
│ ├─ 模型选择（任务-模型路由）                  │
│ ├─ 能力映射（能力-需求匹配）                  │
│ └─ 升级策略（4级升级路径）                    │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L4 提示词层, L12 成本层          │
└─────────────────────────────────────────────┘
```

---

## 5.2 来自02_architecture/的核心内容

### 5.2.1 模型升级策略

#### 升级路径（从低到高）

```
Level 1: 扩验证与证据（更细粒度日志/更窄复现）
    ↓
Level 2: 扩执行范围（但仍patch-only）
    ↓
Level 3: 升模型（先coder/medium，再thinking/强模型）
    ↓
Level 4: 升权限（管理员/系统级）——需要显式记录原因与回滚
```

#### 模型选择规则

| 任务类型 | 推荐模型 | 原因 |
|----------|----------|------|
| 代码生成 | kimi-k2.5, claude-3.5-sonnet | 代码能力强 |
| 架构设计 | claude-3.5-opus, kimi-k2.5 | 长上下文理解 |
| 文档编写 | kimi-k2.5 | 中文能力强 |
| 测试生成 | kimi-k2.5, gpt-4 | 测试覆盖率高 |
| 审查验证 | claude-3.5-sonnet | 细致严谨 |

---

## 5.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 模型配置 | 配置模型参数 | `model_config.py` | `model_config.py set --model kimi-k2.5 --priority high` |
| 模型选择 | 为任务选择模型 | `model_selector.py` | `model_selector.py --task "code review" --complexity high` |
| 成本追踪 | 追踪token成本 | `token_tracker.py` | `token_tracker.py --model kimi-k2.5 --tokens 1500` |
| 升级决策 | 决定升级路径 | `escalation_decider.py` | `escalation_decider.py --fail-code timeout --attempt 2` |

---

## 5.4 脚本使用示例

```bash
# 1. 设置模型优先级
python tools/scc/ops/model_config.py set \
  --model kimi-k2.5 \
  --priority high \
  --max-tokens 8000 \
  --temperature 0.7

# 2. 为任务选择最佳模型
python tools/scc/ops/model_selector.py \
  --task "实现用户认证模块" \
  --complexity high \
  --context-size large \
  --format json

# 3. 追踪token成本
python tools/scc/ops/token_tracker.py log \
  --model kimi-k2.5 \
  --prompt-tokens 2000 \
  --completion-tokens 500 \
  --task-id TASK-001

# 4. 决定升级路径
python tools/scc/ops/escalation_decider.py \
  --fail-code timeout \
  --attempt 2 \
  --current-model kimi-k2.5 \
  --suggest-next
```

---

## 5.5 关键文件针脚

```yaml
L5_model_layer:
  ssot_partition: "02_architecture"
  chapter: 14
  description: "模型层 - 提供模型配置、选择策略、能力映射、升级策略"
  
  core_spec_files:
    - path: scc-top/docs/ssot/02_architecture/SCC_TOP.md
      description: "包含模型升级策略（4级升级路径）"
  
  tools:
    - tools/scc/ops/model_config.py
    - tools/scc/ops/model_selector.py
    - tools/scc/ops/token_tracker.py
    - tools/scc/ops/escalation_decider.py
  
  related_chapters:
    - technical_manual/chapter_14_model_layer.md
```

---

## 5.6 本章小结

### 5.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 4级升级 | 扩验证→扩范围→升模型→升权限 |
| 模型选择 | 基于任务类型、复杂度、上下文大小选择模型 |
| Token追踪 | 记录prompt和completion的token使用量 |

### 5.6.2 依赖关系

```
L5 模型层
    │
    ├─ 提供模型选择给 → L6 Agent层
    ├─ 提供升级策略给 → L4 提示词层
    └─ 提供成本数据给 → L12 成本层
```

---


---

**导航**: [← L4](./L4_prompt_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L6](./L6_agent_layer.md)