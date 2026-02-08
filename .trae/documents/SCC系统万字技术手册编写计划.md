# Phase 1: 创建核心基础组件（20个P0组件）

## 实施计划

### Week 1-2 目标
建立最小可运行的17层架构，补齐最核心的20个P0组件。

### 执行顺序（按依赖关系）

#### 第1批：元层基础（3个组件）
1. `docs/ARCHITECTURE_INDEX.md` - 架构总索引
2. `docs/L17_ontology/id_system.md` - ID体系规范
3. `docs/L17_ontology/entity_relations.json` - 实体关系图

#### 第2批：观测与状态（3个组件）
4. `docs/L16_observability/log_schema.json` - 结构化日志Schema
5. `docs/L9_state/task_state.schema.json` - 任务状态Schema
6. `docs/L9_state/memory_governance.md` - 记忆治理策略

#### 第3批：成本与安全（3个组件）
7. `docs/L12_cost/cost_ledger.jsonl` - 成本账本（初始）
8. `docs/L12_cost/per_task_budget.json` - 每任务预算
9. `docs/L13_security/rbac_policy.json` - RBAC策略

#### 第4批：定义层核心（4个组件）
10. `docs/prompt_os/constitution.md` - 最高原则
11. `docs/prompt_os/conflict_order.md` - 冲突优先级
12. `docs/L3_documentation/policies/hard.md` - 硬策略
13. `docs/L3_documentation/policies/soft.md` - 软策略

#### 第5批：提示词编译层（3个组件）
14. `docs/prompt_os/compiler/legal_prefix_v1.txt` - 效力声明
15. `docs/prompt_os/compiler/refs_index_v1.json` - 引用索引
16. `oc-scc-local/scripts/compile_prompts.mjs` - 编译脚本

#### 第6批：契约层（3个组件）
17. `docs/L2_task/task_bundle/bundle_spec.md` - Task Bundle规范
18. `docs/roles/task_compiler.json` - Task Compiler角色
19. `docs/roles/judge.json` - Judge角色

#### 第7批：工具与执行（1个组件）
20. `docs/L7_tool/catalog.md` - 工具目录

### 每批交付物
- 组件文件本身
- 组件的layer_index.md更新
- 依赖关系更新到COMPONENT_REGISTRY.json

### 验收标准
- 每个组件都有完整的schema/规范
- 组件间引用关系清晰
- 机器可读（JSON/Schema验证通过）
- 人工可读（Markdown文档完整）

请确认此计划后，我将开始创建第1批组件。