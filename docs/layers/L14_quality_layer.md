# L14 质量与评测层

> **对应SSOT分区**: `07_reports_evidence/`, `05_runbooks/`  
> **对应技术手册**: 第7章  
> **层定位**: 质量评估、评测框架、质量报告

---

## 14.1 层定位与职责

### 14.1.1 核心职责

L14是SCC架构的**质量管理层**，为全系统提供：

1. **质量评估** - 基于acceptance的自动化质量检查
2. **评测框架** - 标准化评测流程
3. **质量报告** - 定期质量指标报告
4. **缺陷分类** - 失败任务的分类和追踪
5. **持续改进** - 质量趋势分析和改进建议

### 14.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L14 质量与评测层                              │
│ ├─ 质量评估（acceptance检查）                 │
│ ├─ 评测框架（标准化流程）                     │
│ ├─ 质量报告（定期报告）                       │
│ └─ 缺陷分类（结构化分类）                     │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L8 证据层, L12 成本层, L15 变更层            │
└─────────────────────────────────────────────┘
```

---

## 14.2 来自07_reports_evidence/和05_runbooks/的核心内容

### 14.2.1 质量评估规范

#### 基于Acceptance的质量判定

```
质量判定规则:
- 验证器必须仅根据acceptance结果进行裁决
- 禁止不带检查的"looks good"裁决
- 故障关闭（fail-closed）
- 每个失败必须有结构化的fail_code
```

#### 质量指标

| 指标 | 说明 | 计算方式 |
|------|------|----------|
| pass_rate | 通过率 | pass任务数 / 总任务数 |
| mean_retries | 平均重试次数 | 总重试次数 / 总任务数 |
| time_to_green | 任务完成时间 | queued → passed 的持续时间 |
| defect_density | 缺陷密度 | 失败任务数 / 代码变更量 |

### 14.2.2 缺陷分类

#### fail_code标准分类

| fail_code | 说明 | 示例 |
|-----------|------|------|
| timeout | 超时 | 执行时间超过限制 |
| test_failure | 测试失败 | 单元测试/集成测试失败 |
| lint_error | 代码风格错误 | ESLint/Prettier错误 |
| type_error | 类型错误 | TypeScript类型检查失败 |
| security_violation | 安全违规 | 密钥泄露、注入风险 |
| scope_violation | 范围违规 | 修改了允许范围外的文件 |
| external_dependency | 外部依赖 | 需要外部资源才能继续 |

---

## 14.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 质量评估 | 评估任务质量 | `quality_eval.py` | `quality_eval.py --task-id TASK-001` |
| 质量报告 | 生成质量报告 | `quality_report.py` | `quality_report.py --weekly` |
| 缺陷分析 | 分析缺陷趋势 | `defect_analyzer.py` | `defect_analyzer.py --trend` |
| 评测运行 | 运行评测 | `eval_runner.py` | `eval_runner.py --suite full` |
| 质量门 | 质量门禁 | `quality_gate.py` | `quality_gate.py --check` |

---

## 14.4 脚本使用示例

```bash
# 1. 评估任务质量
python tools/scc/ops/quality_eval.py \
  --task-id TASK-001 \
  --include-code-quality \
  --include-test-coverage \
  --output quality_eval.json

# 2. 生成每周质量报告
python tools/scc/ops/quality_report.py \
  --weekly \
  --project quantsys \
  --format html \
  --include-trends \
  --output reports/quality_week_06.html

# 3. 分析缺陷趋势
python tools/scc/ops/defect_analyzer.py \
  --trend \
  --time-range 30d \
  --group-by fail_code \
  --output defect_trend.json

# 4. 运行完整评测套件
python tools/scc/ops/eval_runner.py \
  --suite full \
  --project quantsys \
  --parallel 4 \
  --output eval_results.json

# 5. 质量门检查
python tools/scc/ops/quality_gate.py \
  --check \
  --min-pass-rate 0.8 \
  --max-mean-retries 1.5 \
  --fail-closed
```

---

## 14.5 关键文件针脚

```yaml
L14_quality_layer:
  ssot_partition: "07_reports_evidence, 05_runbooks"
  chapter: 7
  description: "质量与评测层 - 提供质量评估、评测框架、质量报告"
  
  core_spec_files:
    - path: scc-top/docs/ssot/04_contracts/contract_min_spec.md
      description: "契约规范，定义acceptance和fail_code"
    - path: scc-top/docs/ssot/05_runbooks/metrics_spec.md
      description: "指标规范，定义质量指标"
  
  tools:
    - tools/scc/ops/quality_eval.py
    - tools/scc/ops/quality_report.py
    - tools/scc/ops/defect_analyzer.py
    - tools/scc/ops/eval_runner.py
    - tools/scc/ops/quality_gate.py
  
  related_chapters:
    - technical_manual/chapter_07_quality_layer.md
```

---

## 14.6 本章小结

### 14.2.4 评估指标（Metrics）

#### 任务成功率（Task Success Rate）
- **公式**: `done_count / total_count`
- **目标**: `> 85%`
- **计算**: 汇总选定时期内所有已评估任务，统计submit状态为`DONE`的任务数
- **频率**: 每日/每周
- **告警**: 每日`< 80%`警告，每周`< 75%`严重

#### 首次通过成功率（First-Attempt Pass Rate）
- **公式**: `first_attempt_done / total_count`
- **目标**: `> 60%`
- **计算**: 统计在第1次尝试就达到`DONE`的任务数，除以总任务数
- **频率**: 每日/每周
- **告警**: `< 55%`警告，`< 45%`严重

#### 升级率（Escalation Rate）
- **公式**: `escalated_count / total_count`
- **目标**: `< 10%`
- **计算**: 统计需要升级的任务数（例如模型/角色升级、人工交接），除以总任务数
- **频率**: 每日/每周
- **告警**: `> 12%`警告，`> 20%`严重

#### 平均尝试次数（Average Attempts）
- **公式**: `sum(attempts) / total_count`
- **目标**: `< 1.5`
- **计算**: 记录每个任务直到终止状态的尝试次数，然后计算平均值
- **频率**: 每日/每周
- **告警**: `> 1.6`警告，`> 2.0`严重

#### 策略违规率（Policy Violation Rate）
- **公式**: `violation_count / total_count`
- **目标**: `< 2%`
- **计算**: 统计被标记为策略违规的任务数（安全、隐私、许可、固定范围违规），除以总任务数
- **频率**: 每日/每周
- **告警**: `> 2%`警告，`> 5%`严重

#### Token效率（Token Efficiency）
- **公式**: `tokens_used / task_complexity_score`
- **目标**: 持续降低（基于趋势）
- **计算**: 按任务复杂度分数（例如1=简单，2=中等，3=困难）归一化每个任务使用的总token数，跟踪中位数+p95
- **频率**: 每周
- **告警**: 2周移动平均增加`> 10%`警告

#### 测试覆盖率（Test Coverage）
- **公式**: `tasks_with_tests / total_tasks`
- **目标**: `100%`
- **计算**: 统计至少有一个可运行测试或可验证检查（单元/集成/网关检查）的任务数，除以总任务数
- **频率**: 每周
- **告警**: `< 95%`警告，`< 90%`严重

#### 证据完整性（Evidence Completeness）
- **公式**: `tasks_with_full_evidence / total_tasks`
- **目标**: `> 95%`
- **计算**: 如果任务包含所需工件（例如补丁差异、自测日志、报告、提交JSON）且内部一致，则该任务具有完整证据
- **频率**: 每日/每周
- **告警**: `< 95%`警告，`< 90%`严重

### 14.6.1 核心概念

| 概念 | 说明 |
|------|------|
| Acceptance | 验收标准，质量判定的唯一依据 |
| fail_code | 结构化的失败分类 |
| 质量指标 | pass_rate, mean_retries, time_to_green等 |
| 质量门 | 合并前的质量检查 |
| 评估指标 | 8个核心质量指标（成功率、升级率等） |

### 14.6.2 关键规则

1. **基于Acceptance**: 质量判定必须基于acceptance结果
2. **结构化失败**: 每个失败必须有fail_code
3. **质量目标**: pass_rate > 80%, mean_retries < 1.5
4. **定期报告**: 每周生成质量报告

### 14.6.3 依赖关系

```
L14 质量与评测层
    │
    ├─ 依赖 → L8证据层（裁决结果）
    ├─ 依赖 → L12成本层（效率指标）
    │
    ├─ 提供质量给 → L15 变更层
    └─ 提供报告给 → L16 观测层
```

---


---

**导航**: [← L13](./L13_security_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L15](./L15_change_layer.md)