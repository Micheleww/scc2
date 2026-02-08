# Docs Root Navigation（唯一入口 / SSOT）

本文件路径长期稳定：`docs/START_HERE.md`。

规则：任何人/任何 Agent 进入本仓库，**先读本页**；禁止创建第二个"主入口"来替代本页。

---

## 两层文档网络

```
┌─────────────────────────────────────────────┐
│ 导航层（本文档）← 你在这里                    │
│ ├── 17层架构速查                             │
│ ├── 快速导航                                 │
│ └── 指向17个详情文档的链接                   │
├─────────────────────────────────────────────┤
│ 详情层（17个独立文档）                        │
│ ├── layers/L1_code_layer.md                  │
│ ├── layers/L2_task_layer.md                  │
│ ├── ...                                      │
│ └── layers/L17_ontology_layer.md             │
└─────────────────────────────────────────────┘
```

---

## 17层架构速查

| 层 | 名称 | 核心职责 | 详情文档 |
|----|------|----------|----------|
| **L1** | 代码层 | 顶层治理、North Star、API端点 | [L1_code_layer.md](../../docs/layers/L1_code_layer.md) |
| **L2** | 任务层 | 任务模型、契约规范、Task Bundle | [L2_task_layer.md](../../docs/layers/L2_task_layer.md) |
| **L3** | 文档层 | 文档生命周期、SSOT治理、AI拼装上下文 | [L3_documentation_layer.md](../../docs/layers/L3_documentation_layer.md) |
| **L4** | 提示词层 | 角色定义、技能规范、Context Pack | [L4_prompt_layer.md](../../docs/layers/L4_prompt_layer.md) |
| **L5** | 模型层 | 模型配置、升级策略 | [L5_model_layer.md](../../docs/layers/L5_model_layer.md) |
| **L6** | Agent层 | Agent执行、5阶段状态机 | [L6_agent_layer.md](../../docs/layers/L6_agent_layer.md) |
| **L7** | 工具层 | Manager Tools、技能守卫、工具策略 | [L7_tool_layer.md](../../docs/layers/L7_tool_layer.md) |
| **L8** | 证据与裁决层 | 证据收集、裁决判定、失败代码 | [L8_evidence_layer.md](../../docs/layers/L8_evidence_layer.md) |
| **L9** | 状态与记忆层 | 会话状态、工作记忆、记忆治理 | [L9_state_layer.md](../../docs/layers/L9_state_layer.md) |
| **L10** | 工作空间层 | 工作空间、输入管理 | [L10_workspace_layer.md](../../docs/layers/L10_workspace_layer.md) |
| **L11** | 路由与调度层 | 任务路由、调度策略、工作流 | [L11_routing_layer.md](../../docs/layers/L11_routing_layer.md) |
| **L12** | 成本与预算层 | 成本追踪、预算管理 | [L12_cost_layer.md](../../docs/layers/L12_cost_layer.md) |
| **L13** | 安全与权限层 | 13道CI门、技能守卫 | [L13_security_layer.md](../../docs/layers/L13_security_layer.md) |
| **L14** | 质量与评测层 | 质量评估、缺陷分类 | [L14_quality_layer.md](../../docs/layers/L14_quality_layer.md) |
| **L15** | 变更与发布层 | 变更管理、版本控制 | [L15_change_layer.md](../../docs/layers/L15_change_layer.md) |
| **L16** | 观测与可观测性层 | 监控、日志、追踪 | [L16_observability_layer.md](../../docs/layers/L16_observability_layer.md) |
| **L17** | 知识与本体层 | OID/ULID、实体关系、术语表 | [L17_ontology_layer.md](../../docs/layers/L17_ontology_layer.md) |

---

## 快速导航

| 目标 | 文档 |
|------|------|
| **了解某层详情** | 点击上表中的层链接 |
| **API详情** | [L1代码层 - API端点列表](../../docs/layers/L1_code_layer.md) |
| **核心原则** | [constitution.md](../../docs/prompt_os/constitution.md) |
| **工作流** | [L11路由层 - 工作流模板](../../docs/layers/L11_routing_layer.md) |
| **Context Pack** | [L4提示词层 - Context Pack规范](../../docs/layers/L4_prompt_layer.md) |
| **失败代码** | [L8证据层 - 失败代码目录](../../docs/layers/L8_evidence_layer.md) |
| **SCC Observability Spec** | [L16可观测性层 - Observability Spec](../../docs/layers/L16_observability_layer.md) |
| **术语表** | [L17本体层 - 术语表](../../docs/layers/L17_ontology_layer.md) |
| **Task Bundle** | [L2任务层 - Task Bundle规范](../../docs/layers/L2_task_layer.md) |
| **Task Model** | [L2任务层 - Task Model与Codes](../../docs/layers/L2_task_layer.md) |
| **WorkspaceSpec** | [L10工作空间层 - WorkspaceSpec](../../docs/layers/L10_workspace_layer.md) |
| **记忆治理** | [L9状态层 - 记忆治理](../../docs/layers/L9_state_layer.md) |
| **记忆写入策略** | [L9状态层 - 记忆写入策略](../../docs/layers/L9_state_layer.md) |
| **ID体系** | [L17本体层 - ID体系规范](../../docs/layers/L17_ontology_layer.md) |
| **工具策略** | [L7工具层 - 工具使用策略](../../docs/layers/L7_tool_layer.md) |
| **API规则** | [L7工具层 - API规则](../../docs/layers/L7_tool_layer.md) |
| **数据规则** | [L7工具层 - 数据规则](../../docs/layers/L7_tool_layer.md) |
| **证据规范** | [L8证据层 - 证据规范](../../docs/layers/L8_evidence_layer.md) |
| **评估指标** | [L14质量层 - 8个核心指标](../../docs/layers/L14_quality_layer.md) |
| **降级策略** | [L11路由层 - 降级策略](../../docs/layers/L11_routing_layer.md) |
| **升级策略** | [L11路由层 - 升级策略](../../docs/layers/L11_routing_layer.md) |
| **Dispatch Runbook** | [L11路由层 - Dispatch Runbook](../../docs/layers/L11_routing_layer.md) |
| **清洁策略** | [L3文档层 - Hygiene Policy](../../docs/layers/L3_documentation_layer.md) |
| **最佳实践** | [L17本体层 - Best Practices](../../docs/layers/L17_ontology_layer.md) |
| **领域知识库** | [L17本体层 - Domain KB](../../docs/layers/L17_ontology_layer.md) |
| **IO模式** | [L8证据层 - Schemas](../../docs/layers/L8_evidence_layer.md) |
| **任务状态字段** | [L9状态层 - Task State Fields](../../docs/layers/L9_state_layer.md) |
| **AI拼装上下文** | [L3文档层 - AI拼装上下文](../../docs/layers/L3_documentation_layer.md) |
| **SSOT Trunk** | [L3文档层 - SSOT Trunk结构](../../docs/layers/L3_documentation_layer.md) |
| **Docflow SSOT** | [L3文档层 - Docflow规范](../../docs/layers/L3_documentation_layer.md) |
| **Canonical Truth** | [L3文档层 - 权威文档集](../../docs/layers/L3_documentation_layer.md) |
| **Constitution** | [L1代码层 - 最高原则](../../docs/layers/L1_code_layer.md) |
| **SCC_TOP宪法** | [L1代码层 - SCC_TOP](../../docs/layers/L1_code_layer.md) |
| **冲突优先级** | [L3文档层 - 冲突优先级规则](../../docs/layers/L3_documentation_layer.md) |
| **角色规范** | [L6Agent层 - RoleSpec](../../docs/layers/L6_agent_layer.md) |
| **Capability Catalog** | [L6Agent层 - Capability Catalog](../../docs/layers/L6_agent_layer.md) |
| **技能规范** | [L4提示词层 - SkillSpec](../../docs/layers/L4_prompt_layer.md) |
| **OID规范** | [L17本体层 - OID/ULID规范](../../docs/layers/L17_ontology_layer.md) |
| **Pins规范** | [L2任务层 - Pins规范](../../docs/layers/L2_task_layer.md) |
| **Task Contract** | [L2任务层 - Task Contract规范](../../docs/layers/L2_task_layer.md) |

---

## Changelog（入口结构变化）

- **2026-02-09**: 将START_HERE.md内容分拆到17层对应层
- **2026-02-09**: 将四层结构压缩为**两层结构**（导航层→详情层）
- **2026-02-09**: 将LAYER_DETAILS.md拆分为17个独立文档
- **2026-02-09**: 合并入口层和导航层为单一START_HERE.md
- **2026-02-01**: 建立 `docs/ssot/` 主干结构
- **2026-02-01**: 建立 SCC 顶层宪法 `SCC_TOP.md`

---

**文档导航**: 点击上表中的任意层链接查看详细文档
