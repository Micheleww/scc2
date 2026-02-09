# L12 成本与预算层

> **对应SSOT分区**: `05_runbooks/`（操作手册）  
> **对应技术手册**: 第5章  
> **层定位**: 成本追踪、预算管理、资源配额

---

## 12.1 层定位与职责

### 12.1.1 核心职责

L12是SCC架构的**成本管理层**，为全系统提供：

1. **成本追踪** - 实时成本监控（token使用量）
2. **预算管理** - 预算分配和告警
3. **资源配额** - 模型调用配额管理
4. **成本报告** - 定期成本分析和报告
5. **效率指标** - 系统效率度量

### 12.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L12 成本与预算层                              │
│ ├─ 成本追踪（token使用量）                    │
│ ├─ 预算管理（预算/告警）                      │
│ ├─ 资源配额（调用配额）                       │
│ └─ 成本报告（定期报告）                       │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L5 模型层, L11 调度层, L14 质量层            │
└─────────────────────────────────────────────┘
```

---

## 12.2 来自05_runbooks/的核心内容

### 12.2.1 最小指标（来自metrics_spec.md）

| 指标 | 说明 | 目标 |
|------|------|------|
| pass_rate | 无需人工干预通过的任务% | > 80% |
| mean_retries | 每任务平均重试次数 | < 1.5 |
| time_to_green | queued→passed持续时间(p50/p95) | p50 < 5min |
| top_fail_codes | 失败分类分布 | 可追踪 |
| oid_coverage | 强制树中嵌入oid+注册表项的对象% | 100% |
| ingestion_lag | 原始捕获→任务派生延迟 | < 1min |

### 12.2.2 成本追踪规范

```yaml
cost_tracking:
  per_task:
    - model_name
    - prompt_tokens
    - completion_tokens
    - total_tokens
    - estimated_cost_usd
  aggregation:
    - by_project
    - by_capability
    - by_time_period
```

### 12.2.3 预算审批流程

#### 预算申请与审批

```
1. 预算申请
   - 项目负责人提交预算申请
   - 说明用途、预期成本、时间范围
   - 状态: PENDING

2. 预算审批
   - 成本管理员审查申请
   - 评估合理性和必要性
   - 批准或拒绝（附理由）
   - 状态: APPROVED / REJECTED

3. 预算分配
   - 分配预算配额
   - 设置告警阈值（默认80%）
   - 启用成本追踪
   - 状态: ACTIVE

4. 预算监控
   - 实时成本追踪
   - 接近阈值时告警
   - 超支时自动限制
   - 状态: ALERT / EXHAUSTED
```

#### 预算层级

| 层级 | 预算范围 | 审批人 | 告警阈值 |
|------|----------|--------|----------|
| 项目级 | $100-$1000 | 项目经理 | 80% |
| 部门级 | $1000-$10000 | 部门主管 | 85% |
| 公司级 | >$10000 | 财务总监 | 90% |

### 12.2.4 成本优化策略

#### 模型选择优化

| 策略 | 说明 | 预期节省 |
|------|------|----------|
| **免费模型优先** | 优先使用MODEL_POOL_FREE | 100% |
| **阶梯降级** | 失败后降级到更便宜模型 | 30-50% |
| **上下文压缩** | 压缩历史上下文减少tokens | 20-40% |
| **缓存复用** | 复用之前的推理结果 | 50-80% |

#### 任务批处理

```yaml
batch_optimization:
  enabled: true
  batch_size: 10
  max_wait_time: 30s
  
  benefits:
    - 减少API调用次数
    - 提高吞吐量
    - 降低单位成本
```

#### 智能重试策略

| 失败类型 | 重试策略 | 成本影响 |
|----------|----------|----------|
| 超时 | 指数退避，最多3次 | 最小化 |
| 限流 | 切换到备用模型 | 可控 |
| 内容错误 | 不自动重试 | 避免浪费 |

#### 成本监控告警

```yaml
alert_rules:
  - name: "预算80%告警"
    condition: "spend > budget * 0.8"
    action: "notify_manager"
    
  - name: "预算100%告警"
    condition: "spend >= budget"
    action: "block_new_tasks"
    
  - name: "异常成本告警"
    condition: "hourly_cost > avg_hourly * 3"
    action: "notify_admin"
```

---

## 12.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| Token追踪 | 追踪token使用 | `token_tracker.py` | `token_tracker.py log --model kimi-k2.5 --tokens 1500` |
| 成本报告 | 生成成本报告 | `cost_report.py` | `cost_report.py --daily --project quantsys` |
| 预算检查 | 检查预算 | `budget_checker.py` | `budget_checker.py --project quantsys --limit 1000` |
| 效率指标 | 计算效率指标 | `efficiency_metrics.py` | `efficiency_metrics.py --report` |
| 告警管理 | 成本告警 | `cost_alert.py` | `cost_alert.py check --threshold 0.8` |

---

## 12.4 脚本使用示例

```bash
# 1. 记录token使用
python tools/scc/ops/token_tracker.py log \
  --model kimi-k2.5 \
  --prompt-tokens 2000 \
  --completion-tokens 500 \
  --task-id TASK-001 \
  --project quantsys

# 2. 生成每日成本报告
python tools/scc/ops/cost_report.py \
  --daily \
  --project quantsys \
  --format html \
  --output reports/cost_2026-02-09.html

# 3. 检查项目预算
python tools/scc/ops/budget_checker.py \
  --project quantsys \
  --limit 1000 \
  --current-spend 850 \
  --alert-threshold 0.9

# 4. 计算效率指标
python tools/scc/ops/efficiency_metrics.py \
  --report \
  --include-pass-rate \
  --include-mean-retries \
  --include-time-to-green

# 5. 检查成本告警
python tools/scc/ops/cost_alert.py check \
  --threshold 0.8 \
  --project quantsys \
  --notify
```

---

## 12.5 关键文件针脚

```yaml
L12_cost_layer:
  ssot_partition: "05_runbooks"
  chapter: 5
  description: "成本与预算层 - 提供成本追踪、预算管理、效率指标"
  
  core_spec_files:
    - path: scc-top/docs/ssot/05_runbooks/metrics_spec.md
      description: "指标规范，定义最小指标集"
  
  tools:
    - tools/scc/ops/token_tracker.py
    - tools/scc/ops/cost_report.py
    - tools/scc/ops/budget_checker.py
    - tools/scc/ops/efficiency_metrics.py
    - tools/scc/ops/cost_alert.py
  
  related_chapters:
    - technical_manual/chapter_05_cost_layer.md
```

---

## 12.6 本章小结

### 12.6.1 核心概念

| 概念 | 说明 |
|------|------|
| Token追踪 | 记录模型的token使用量 |
| 成本报告 | 按项目/能力/时间聚合成本 |
| 效率指标 | pass_rate, mean_retries, time_to_green等 |
| 预算告警 | 成本接近预算阈值时告警 |

### 12.6.2 关键规则

1. **成本追踪**: 每个任务必须记录token使用量
2. **预算告警**: 达到预算80%时触发告警
3. **效率目标**: pass_rate > 80%, mean_retries < 1.5
4. **定期报告**: 每日/每周生成成本报告

### 12.6.3 依赖关系

```
L12 成本与预算层
    │
    ├─ 依赖 → L5模型层（token数据）
    ├─ 依赖 → L11调度层（任务数据）
    │
    ├─ 提供成本给 → L14 质量层
    └─ 提供指标给 → L16 观测层
```

---


---

**导航**: [← L11](./L11_routing_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L13](./L13_security_layer.md)