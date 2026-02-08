# 冲突优先级规则 (Conflict Order)

> **层级**: L3 文档层 / L4 提示词层  
> **版本**: v1.0.0  
> **更新日期**: 2026-02-08  
> **状态**: P0 - 核心组件  
> **依赖**: `docs/prompt_os/constitution.md`

## 概述

本文档定义 SCC 系统中各类规范、策略、合同之间的冲突解决优先级。当不同来源的规则发生冲突时，按照本文档定义的优先级顺序解决。

## 优先级层级（从高到低）

### L0: Constitution（最高原则）
```
来源: docs/prompt_os/constitution.md
优先级: 绝对最高
冲突处理: 不可违反，违反即系统故障
示例: Pins-First原则、Fail-Closed原则
```

### L1: Hard Policies（硬策略）
```
来源: docs/prompt_os/policies/hard.md
优先级: 极高
冲突处理: 违反即失败，任务终止
示例: "禁止直接修改SSOT"
```

### L2: Role Constraints（角色约束）
```
来源: roles/{role}.json
优先级: 高
冲突处理: 超出角色权限即拒绝
示例: executor禁止读取SSOT
```

### L3: Task Contracts（任务合同）
```
来源: task_bundle/task_contract.json
优先级: 中高
冲突处理: 违反即重试或升级
示例: 验收标准、完成定义
```

### L4: Factory Policies（工厂策略）
```
来源: factory_policy.json
优先级: 中
冲突处理: 违反触发熔断或降级
示例: WIP限制、泳道规则
```

### L5: Soft Policies（软策略）
```
来源: docs/prompt_os/policies/soft.md
优先级: 低
冲突处理: 偏好，不阻断，仅记录
示例: "优先使用TypeScript"
```

### L6: Best Practices（最佳实践）
```
来源: docs/prompt_os/knowledge/best_practices.md
优先级: 最低
冲突处理: 建议性，仅供参考
示例: 代码风格建议
```

## 冲突解决流程

```
检测到冲突
    ↓
识别冲突双方层级
    ↓
层级不同？
    ├── 是 → 高优先级胜出
    ↓
层级相同？
    ├── 是 → 应用同层级规则
    ↓
记录冲突与决议
    ↓
执行胜出规则
```

## 同层级冲突规则

当冲突双方处于同一优先级层级时：

### 时间优先（Time Priority）
- **规则**: 后发布的规则覆盖先发布的规则
- **适用**: L3-L6 层级
- **示例**: 新版本的合同覆盖旧版本

### 特定优先（Specificity Priority）
- **规则**: 特定规则覆盖一般规则
- **适用**: 所有层级
- **示例**: "禁止修改此文件" > "禁止修改代码"

### 范围优先（Scope Priority）
- **规则**: 小范围规则覆盖大范围规则
- **适用**: L2-L4 层级
- **示例**: 任务级配置 > 项目级配置 > 全局配置

## 常见冲突场景

### 场景1: Constitution vs Hard Policy
```
冲突:
- Constitution: "Fail-Closed原则"
- Hard Policy: "允许紧急情况下绕过门禁"

解决:
- Constitution胜出
- 不允许任何绕过，即使紧急情况
```

### 场景2: Role Constraint vs Task Contract
```
冲突:
- Role: executor禁止读取SSOT
- Contract: 任务要求executor读取架构文档

解决:
- Role Constraint胜出（L2 > L3）
- 任务必须重新分配角色或修改合同
```

### 场景3: Factory Policy vs Soft Policy
```
冲突:
- Factory: WIP限制为16
- Soft Policy: 建议并行处理更多任务

解决:
- Factory Policy胜出（L4 > L5）
- 忽略Soft Policy的建议
```

### 场景4: 同层级 - 新旧合同
```
冲突:
- Contract v1.0: 验收标准A
- Contract v1.1: 验收标准B

解决:
- 时间优先，v1.1胜出
- 使用新的验收标准
```

## 冲突裁决机制

当自动规则无法解决冲突时：

### 1. Judge角色裁决
```
触发条件:
- 同层级冲突无法通过时间/特定/范围规则解决
- 涉及Constitution解释争议

裁决流程:
1. Judge接收冲突报告
2. 分析双方依据
3. 参考历史案例
4. 发布裁决（verdict）
5. 更新Conflict Order文档
```

### 2. 升级路径
```
Level 1: 自动规则解决
    ↓ 无法解决
Level 2: Judge角色裁决
    ↓ 仍有争议
Level 3: factory_manager + architect 联合决策
    ↓ 涉及Constitution
Level 4: 人工介入
```

## 冲突记录格式

所有冲突必须记录：

```json
{
  "conflict_id": "oid:L11:Conflict:01ARZ...",
  "timestamp": "2026-02-08T14:30:00Z",
  "parties": [
    {
      "source": "docs/prompt_os/constitution.md",
      "level": "L0",
      "rule": "Pins-First原则"
    },
    {
      "source": "task_contract.json",
      "level": "L3",
      "rule": "允许自由探索"
    }
  ],
  "resolution": {
    "winner": "L0",
    "reason": "Constitution绝对优先",
    "action": "任务失败，路由到pinser"
  },
  "judge_id": "oid:L6:Role:01ARZ...",
  "verdict_id": "oid:L8:Verdict:01ARZ..."
}
```

## 更新流程

### 何时更新本文档
- 新增优先级层级
- 同层级规则变更
- 常见冲突场景变化

### 更新审批
1. 由 factory_manager 提议
2. 经 architect 审核
3. 经 auditor 合规检查
4. 全量回归测试通过
5. 更新版本号

## 相关文件

- [constitution.md](./constitution.md) - 最高原则
- [policies/hard.md](./policies/hard.md) - 硬策略
- [policies/soft.md](./policies/soft.md) - 软策略
- [../L8_evidence/layer_index.md](../L8_evidence/layer_index.md) - 裁决层

## 变更记录

| 版本 | 日期 | 变更内容 | 审批人 |
|------|------|---------|--------|
| v1.0.0 | 2026-02-08 | 初始版本，定义L0-L6优先级 | factory_manager |

---

**维护者**: factory_manager  
**审核者**: architect + auditor  
**下次评审**: 2026-05-08
