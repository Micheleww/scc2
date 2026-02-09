# L16 观测与可观测性层

> **对应SSOT分区**: `07_reports_evidence/`, `05_runbooks/`  
> **对应技术手册**: 第3章  
> **层定位**: 监控、日志、追踪、告警

---

## 16.1 层定位与职责

### 16.1.1 核心职责

L16是SCC架构的**可观测性层**，为全系统提供：

1. **监控** - 系统健康状态监控
2. **日志聚合** - 分布式日志收集
3. **追踪** - 分布式追踪分析
4. **告警** - 异常事件的告警通知
5. **审计** - 操作审计和合规检查

### 16.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L16 观测与可观测性层                          │
│ ├─ 监控（系统健康）                           │
│ ├─ 日志聚合（分布式日志）                     │
│ ├─ 追踪（分布式追踪）                         │
│ └─ 告警（异常通知）                           │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L8 证据层, L12 成本层, L14 质量层, L15 变更层│
└─────────────────────────────────────────────┘
```

---

## 16.2 来自07_reports_evidence/和05_runbooks/的核心内容

### 16.2.1 可观测性规范

#### 事件落盘规则

```
- 每次动作都要落盘事件（task/event/evidence）
- 确保可追溯、可重放、可回滚
- 审计记录：evidence/（append-only）
```

### 16.2.2 Changelog（入口结构变化记录）

#### 变更日志规范

```
Changelog只记录入口结构变化：
- 2026-02-01：建立 docs/ssot/ 主干结构；将 Runbook/Observability/Docflow 收敛到 SSOT Trunk
- 2026-02-01：建立 SCC 顶层宪法 docs/ssot/02_architecture/SCC_TOP.md 与 DocOps 治理文档
```

#### 变更记录规则

1. **只记录结构变化**: 不记录内容修改，只记录文档结构/入口变化
2. **时间戳**: 使用ISO 8601格式
3. **描述清晰**: 说明变化内容和影响范围

### 16.2.3 Dedup Map（文档去重映射）

#### 去重记录

| 原始文件 | 目标位置 | 说明 |
|----------|----------|------|
| architecture.md | docs/ssot/02_architecture/architecture.md | 架构文档归位 |
| aws_connection_guide.md | docs/ssot/05_runbooks/aws_connection_guide.md | 运行手册归位 |
| core_assets.md | docs/ssot/01_conventions/core_assets.md | 约定规范归位 |
| data_source_of_truth.md | docs/ssot/01_conventions/data_source_of_truth.md | 约定规范归位 |
| entrypoints_checklist.md | docs/ssot/07_reports_evidence/entrypoints_checklist.md | 报告证据归位 |
| execution_engineering_design.md | docs/ssot/02_architecture/execution_engineering_design.md | 架构文档归位 |
| factor_library_ranking.md | docs/ssot/07_reports_evidence/factor_library_ranking.md | 报告证据归位 |
| quantsys_repo_archaeology_report.md | docs/ssot/07_reports_evidence/quantsys_repo_archaeology_report.md | 报告证据归位 |
| replay_consistency.md | docs/ssot/02_architecture/replay_consistency.md | 架构文档归位 |
| taskhub_system_manifest.md | docs/ssot/02_architecture/taskhub_system_manifest.md | 架构文档归位 |
| taskhub_system_overview.md | docs/ssot/02_architecture/taskhub_system_overview.md | 架构文档归位 |
| unified_market_data_downloader_README.md | docs/ssot/05_runbooks/unified_market_data_downloader_README.md | 运行手册归位 |

#### Content Dedup（内容去重）

| 原始文件 | 目标位置 | 说明 |
|----------|----------|------|
| INPUTS/quant_finance/project_navigation.md | docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md | 项目导航更新 |
| INPUTS/quant_finance/PROJECT_NAVIGATION__legacy.md | docs/ssot/02_architecture/legacy/PROJECT_NAVIGATION__v0.1.0__20260115.md | 遗留版本归档 |
| REPORT/control_plane/LEADER_BOARD__LATEST.md | docs/REPORT/control_plane/LEADER_BOARD__20260202-071930Z.md | 队长板更新 |
| oc-scc-local/MISSION.md | docs/oc-scc-local/archive/MISSION.md | 归档 |
| oc-scc-local/RUNBOOK.md | docs/oc-scc-local/archive/RUNBOOK.md | 归档 |

#### 归档位置

- 原始文件归档: `docs/arch/dedup_20260204/`
- 内容去重归档: `docs/arch/dedup_content_20260204/oc-scc-local/`
- 去重报告: `docs/REPORT/dedup_report_20260204.md`

#### 日志规范

```yaml
日志必须包含:
  timestamp: ISO 8601格式
  level: DEBUG/INFO/WARN/ERROR/FATAL
  component: 产生日志的组件
  task_id: 关联的任务ID（若适用）
  message: 日志消息
  context: 上下文信息（JSON）
```

#### 追踪规范

```yaml
追踪必须包含:
  trace_id: 全局追踪ID
  span_id: 当前跨度ID
  parent_span_id: 父跨度ID（若有）
  operation: 操作名称
  start_time: 开始时间
  end_time: 结束时间
  status: OK/ERROR
```

### 16.2.2 监控指标

| 指标类别 | 指标 | 说明 |
|----------|------|------|
| 系统健康 | uptime | 系统运行时间 |
| 系统健康 | error_rate | 错误率 |
| 性能 | latency_p50/p95/p99 | 响应延迟 |
| 性能 | throughput | 吞吐量 |
| 资源 | cpu_usage | CPU使用率 |
| 资源 | memory_usage | 内存使用率 |
| 业务 | task_queue_depth | 任务队列深度 |
| 业务 | active_executors | 活跃执行器数 |

---

## 16.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 日志收集 | 收集日志 | `log_collector.py` | `log_collector.py --service "*" --time-range 1h` |
| 指标收集 | 收集指标 | `metrics_collector.py` | `metrics_collector.py --metric latency` |
| 追踪分析 | 分析追踪 | `trace_analyzer.py` | `trace_analyzer.py --trace-id TRACE-001` |
| 告警管理 | 管理告警 | `alert_manager.py` | `alert_manager.py status` |
| 仪表板 | 生成仪表板 | `dashboard_generator.py` | `dashboard_generator.py --generate` |

---

## 16.4 脚本使用示例

```bash
# 1. 收集所有服务的日志
python tools/scc/ops/log_collector.py \
  --service "*" \
  --time-range 1h \
  --level INFO \
  --output logs/2026-02-09/

# 2. 收集延迟指标
python tools/scc/ops/metrics_collector.py \
  --metric latency \
  --service gateway \
  --aggregation p50,p95,p99 \
  --time-range 5m

# 3. 分析追踪
python tools/scc/ops/trace_analyzer.py \
  --trace-id TRACE-ABC123 \
  --include-spans \
  --format tree

# 4. 查看告警状态
python tools/scc/ops/alert_manager.py status \
  --format table \
  --include-history

# 5. 确认告警
python tools/scc/ops/alert_manager.py ack \
  --alert-id ALERT-001 \
  --by "ops-team"

# 6. 生成监控仪表板
python tools/scc/ops/dashboard_generator.py \
  --generate \
  --include-system \
  --include-business \
  --output dashboard.html
```

---

## 16.5 关键文件针脚

```yaml
L16_observability_layer:
  ssot_partition: "07_reports_evidence, 05_runbooks"
  chapter: 3
  description: "观测与可观测性层 - 提供监控、日志、追踪、告警"
  
  core_spec_files:
    - path: scc-top/docs/ssot/05_runbooks/SCC_OBSERVABILITY_SPEC__v0.1.0.md
      oid: 01KGDT0H7TXA8XY6TDRXAZ9N1J
      layer: CANON
      primary_unit: V.GUARD
      description: "可观测性规范，定义事件落盘、日志、追踪规则"
  
  tools:
    - path: tools/scc/ops/log_collector.py
      oid: 01CDB895D0833E4315A6098E55EB
    - path: tools/scc/ops/metrics_collector.py
      oid: 01B3EAEA0808454E3A89D5E3728F
    - path: tools/scc/ops/trace_analyzer.py
      oid: 014AD6E5F3C0F745CCBFE523B042
    - path: tools/scc/ops/alert_manager.py
      oid: 01BA96C0739B6C49E6824BB975F0
    - path: tools/scc/ops/dashboard_generator.py
      oid: 01CA2A65B0180042578CEB786C82
  
  related_chapters:
    - chapter: technical_manual/chapter_03_observability_layer.md
      oid: 011BE5AF5D6C2748C8BFA601FFBB
```

---

## 16.6 本章小结

### 16.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 事件落盘 | 每次动作必须记录事件 |
| 日志聚合 | 分布式日志收集 |
| 分布式追踪 | 跨服务的请求追踪 |
| 告警管理 | 异常事件的告警通知 |

### 16.6.2 关键规则

1. **事件落盘**: 每次动作必须落盘事件
2. **可追溯**: 所有操作必须可追溯
3. **可重放**: 基于事件可以重放操作
4. **审计记录**: evidence/目录append-only

### 16.6.3 依赖关系

```
L16 观测与可观测性层
    │
    ├─ 依赖 → L8证据层（证据数据）
    ├─ 依赖 → L12成本层（成本指标）
    ├─ 依赖 → L14质量层（质量指标）
    ├─ 依赖 → L15变更层（变更事件）
    │
    └─ 提供观测给 → 所有其他层
```

---

# 附录：17层与SSOT分区映射总表

| 层 | 名称 | SSOT分区 | 核心文件 |
|----|------|----------|----------|
| L1 | 代码层 | 02_architecture/ | SCC_TOP.md, PROJECT_GROUP__v0.1.0.md |
| L2 | 任务层 | 04_contracts/ | task_model.md, contract_min_spec.md |
| L3 | 文档层 | 01_conventions/ | DOCFLOW_SSOT__v0.1.0.md, DOC_REGISTRY__v0.1.0.md |
| L4 | 提示词层 | 03_agent_playbook/ | ROLE_SPEC__v0.1.0.md, SKILL_SPEC__v0.1.0.md |
| L5 | 模型层 | 02_architecture/ | SCC_TOP.md（升级策略） |
| L6 | Agent层 | 03_agent_playbook/, 05_runbooks/ | ROLE_SPEC__v0.1.0.md, SCC_RUNBOOK__v0.1.0.md |
| L7 | 工具层 | 05_runbooks/, 03_agent_playbook/ | execution_verification_interfaces.md, SKILL_SPEC__v0.1.0.md |
| L8 | 证据与裁决层 | 07_reports_evidence/, 04_contracts/ | contract_min_spec.md, execution_verification_interfaces.md |
| L9 | 状态与记忆层 | 03_agent_playbook/, 05_runbooks/ | roles/index.md, SCC_RUNBOOK__v0.1.0.md |
| L10 | 工作空间层 | 06_inputs/, 02_architecture/ | index.md, PROJECT_GROUP__v0.1.0.md |
| L11 | 路由与调度层 | 02_architecture/, 03_agent_playbook/, 05_runbooks/ | ROLE_SPEC__v0.1.0.md, SCC_RUNBOOK__v0.1.0.md |
| L12 | 成本与预算层 | 05_runbooks/ | metrics_spec.md |
| L13 | 安全与权限层 | 04_contracts/, 03_agent_playbook/ | contract_min_spec.md, SKILL_SPEC__v0.1.0.md |
| L14 | 质量与评测层 | 07_reports_evidence/, 05_runbooks/ | contract_min_spec.md, metrics_spec.md |
| L15 | 变更与发布层 | 05_runbooks/, 02_architecture/ | SCC_RUNBOOK__v0.1.0.md, SCC_TOP.md |
| L16 | 观测与可观测性层 | 07_reports_evidence/, 05_runbooks/ | SCC_OBSERVABILITY_SPEC__v0.1.0.md |
| L17 | 知识与本体层 | 01_conventions/ | OID_SPEC__v0.1.0.md, UNIT_REGISTRY__v0.1.0.md |

### 16.2.4 SCC Observability Spec

> **来源**: `ssot/05_runbooks/SCC_OBSERVABILITY_SPEC__v0.1.0.md`

**目标**: 把SCC的关键指标"口径统一 + 采集点明确 + 阈值可告警"固化成单页SSOT

**核心指标（SCC任务执行）**:

| 指标 | 定义 | 阈值 |
|------|------|------|
| `pass_rate` | `DONE` / (`DONE` + `FAIL`) | ≥ 0.90（本地压测）；≥ 0.97（稳定运行） |
| `mean_retries` | 每个task的平均重试次数 | ≤ 0.6（健康）；> 1.0触发"混乱度治理"检查 |
| `time_to_green` | 从task创建到首次`DONE`的耗时 | P50 < 10min（本地）；P95 < 45min |
| `dlq_rate` | 进入DLQ的task / 总task | ≤ 0.03（连续3天） |

**上下文与成本指标**:
- `tokens_per_task`: 每个task的总tokens（prompt+completion）
- `context_hit_rate`: 注入context/pins时命中"稳定前缀/缓存"的比例（目标 ≥ 0.70）

**WebGPT采集指标**:
- `webgpt_intake_ok_rate`: `/scc/webgpt/intake`请求成功率（≥ 0.98）
- `webgpt_backfill_fail_rate`: Backfill的fail/total（≤ 0.05）
- `webgpt_memory_capture_ok_rate`: `/scc/webgpt/memory/intake`成功率（≥ 0.95）

**指标落点**:
- 原始事件/证据: `artifacts/` 与 `evidence/`（append-only）
- 共享阅读入口: `docs/START_HERE.md` → `docs/arch/00_index.md`

---

**导航**: [← L15](./L15_change_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L17](./L17_ontology_layer.md)