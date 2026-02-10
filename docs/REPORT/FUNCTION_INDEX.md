# SCC 功能索引

> **说明**: 本文档根据17层分层架构整理，将功能名称映射到对应层级

---

## L1 代码层 - 顶层治理

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Gateway | `scc-bd/L1_code_layer/gateway/` | API网关，统一入口 |
| Factory Policy | `scc-bd/L1_code_layer/factory_policy/` | 工厂策略控制 |
| Config | `scc-bd/L1_code_layer/config/` | 配置管理 |
| Smoke Test | `scc-bd/L1_code_layer/gateway/smoke.mjs` | 冒烟测试 |

---

## L2 任务层 - 任务模型

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Context Pack | `scc-bd/L2_task_layer/context_pack/` | 任务包管理 |
| Contracts | `scc-bd/L2_task_layer/contracts/` | 契约规范 |
| Patterns | `scc-bd/L2_task_layer/patterns/` | 模式库 |
| Pins | `scc-bd/L2_task_layer/pins/` | Pins构建器 |

---

## L3 文档层 - SSOT治理

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Docs Governance | `scc-bd/L3_documentation_layer/docs_governance/` | 文档治理 |

---

## L4 提示词层 - 角色与技能

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Skills | `scc-bd/L4_prompt_layer/skills/` | 51个技能定义 |
| Skills Drafts | `scc-bd/L4_prompt_layer/skills_drafts/` | 技能草稿 |
| Roles | `scc-bd/L4_prompt_layer/roles/` | 29个角色定义 |
| Role System | `scc-bd/L4_prompt_layer/role_system/` | 角色系统核心 |
| Prompt Registry | `scc-bd/L4_prompt_layer/prompt_registry/` | 提示词注册表 |

---

## L5 模型层 - 模型配置

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Models | `scc-bd/L5_model_layer/models/` | 模型适配器与配置 |

---

## L6 Agent层 - 编排与执行

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Orchestrators | `scc-bd/L6_agent_layer/orchestrators/` | 编排器（状态机） |
| Runtime | `scc-bd/L6_agent_layer/runtime/` | 运行时环境 |

---

## L7 工具层 - 能力模块

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Capabilities | `scc-bd/L7_tool_layer/capabilities/` | 能力模块 |
| Ops | `scc-bd/L7_tool_layer/ops/` | 运维工具 |
| Lib | `scc-bd/L7_tool_layer/lib/` | 工具库 |

---

## L8 证据层 - 裁决与验证

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Verifier Judge | `scc-bd/L8_evidence_layer/verdict/` | 裁决判定 |

---

## L9 状态层 - 状态管理

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| State Stores | `scc-bd/L9_state_layer/state_stores/` | 状态存储（Board, Jobs等） |

---

## L10 工作空间层

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| （预留） | `scc-bd/L10_workspace_layer/` | 工作空间管理 |

---

## L11 路由层 - 任务路由

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Router | `scc-bd/L11_routing_layer/routing/` | 路由核心 |

---

## L12 成本层

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| （预留） | `scc-bd/L12_cost_layer/` | 成本追踪 |

---

## L13 安全层 - CI门控

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Gates | `scc-bd/L13_security_layer/gates/` | 13道CI门 |
| Gatekeeper | `scc-bd/L13_security_layer/gatekeeper/` | 门禁工具 |
| Preflight | `scc-bd/L13_security_layer/preflight/` | 预检门控 |
| Circuit Breaker | `scc-bd/L13_security_layer/circuit_breaker/` | 熔断器 |

---

## L14 质量层 - 验证与评测

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Validators | `scc-bd/L14_quality_layer/validators/` | 验证器 |
| Selftest | `scc-bd/L14_quality_layer/selftest/` | 自检工具 |
| Eval | `scc-bd/L14_quality_layer/eval/` | 评测框架 |

---

## L15 变更层 - 发布管理

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Playbooks | `scc-bd/L15_change_layer/playbooks/` | 剧本管理 |

---

## L16 观测层 - 日志与监控

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Logging | `scc-bd/L16_observability_layer/logging/` | 日志系统 |

---

## L17 本体层 - 知识管理

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Map | `scc-bd/L17_ontology_layer/map/` | 代码地图 |
| Map V1 | `scc-bd/L17_ontology_layer/map_v1/` | Map核心 |
| OID | `scc-bd/L17_ontology_layer/oid/` | OID/ULID生成 |

---

## 插件层

| 功能名称 | 路径 | 说明 |
|---------|------|------|
| Connectors | `plugin/connectors/` | 连接器 |
| A2A Hub | `plugin/projects/quantsys/services/a2a_hub/` | A2A Hub服务 |
| MCP Bus | `plugin/projects/quantsys/services/mcp_bus/` | MCP总线服务 |
| Exchange Server | `plugin/projects/quantsys/services/exchange_server/` | 交换服务 |

---

## 文档说明

- **17层分层文档**: `docs/layers/L1-L17_*.md`
- **架构决策记录**: `docs/adr/`
- **审计报告**: `docs/REPORT/`

---

*生成时间: 2026-02-09*
*版本: v1.0*
