---
oid: 01KGFSKM8XZ87HXS763TBZCAJZ
layer: DOCOPS
primary_unit: V.GUARD
tags: [S.NAV_UPDATE]
status: active
---

# QuantSys 宪法 V1.3

**Doc-ID**: QUANTSYS-CONSTITUTION-V1.3
**Category**: SPEC
**Version**: v1.3.0
**Status**: deprecated
**Last-Updated**: 2026-01-14
**Related-Task**: DOC-GOVERNANCE-001
**Replaced-By**: `docs/ssot/01_conventions/constitution/QUANTSYS_CONSTITUTION_V1.2.md`

---

## 0️⃣ 系统总目标（不变）
长期存活 + 稳定复利
任何提升短期收益但增加出局风险的设计，均视为违规。

## 1️⃣ 核心系统流水线（V1.3）
Data
→ Features
→ Market Belief (Raw → Calibrated → Scored)
→ State & Weight (w)
→ Strategy / Policy
→ Execution
→ Risk & Circuit Breaker
→ Observability

## 2️⃣ 各模块职责与工程接口

### M0 目标与优先级模块
职责：定义系统唯一目标函数与优先级（生存 > 复利 > 峰值）。

工程对应：
- docs/ssot/01_conventions/constitution/QUANTSYS_CONSTITUTION_V1.3.md（本宪法）
- docs/GOALS.md（一句话目标 + 不做清单）

不可违反：
- 任意改动若提高破产风险：拒绝合并

验收：
- PR/任务必须声明：对 MDD/爆仓风险影响为“降低/不变”

### M1 数据与可得性模块（Raw → Features 输入边界）
职责：原始数据的时间可得性与一致性；禁止未来函数。

工程对应：
- data/feeds/*（行情/订单簿/资金费率等）
- data/schema.py（字段语义与时间戳规则）
- tests/test_no_lookahead.py

不可违反：
- 特征只能使用 t 时刻之前可得的数据

验收：
- 单元测试：随机截断数据后，特征输出不依赖未来

### M2 因子/特征模块（信息压缩层）
职责：把原始数据压缩成稳定特征；不包含任何仓位/交易结果。

工程对应：
- features/*（算子、滚动、rank/log等）
- features/registry.py（特征注册表）

不可违反：
- 特征层不得读取：持仓、PnL、成交结果

验收：
- 静态检查/测试：特征模块无 portfolio/ execution/ pnl 依赖

### M3 市场维度概率层（Market Belief）

#### M3.1 核心职责
表达对市场演化方式的概率判断，包含三个正交维度：
- 方向：Up / Down / Flat
- 幅度：|ΔP| ∈ bins
- 时间：事件在不同时间窗 H 内发生的概率

#### M3.2 新增：Belief Calibration & Scoring 治理子层

##### 3.2.1 Belief 类型定义
- **Raw Belief**：模型直接输出的概率
- **Calibrated Belief**：经慢变量校准后的概率，包含 calibration_meta 和 health_score

##### 3.2.2 校准与评分目标
- **校准**：解决“概率是否说实话”问题
- **评分**：解决“概率是否仍值得信任”问题

##### 3.2.3 治理原则
- 校准与评分不产生交易信号，仅影响风险尺度

#### M3.3 工程接口

##### 3.3.1 数据结构
```
MarketBeliefRaw = {
    "direction": P(up, down, flat),
    "magnitude": P(|ΔP| ∈ bins),
    "time": P(event within H_i)
}

MarketBeliefCalibrated = {
    "belief": MarketBeliefRaw,
    "calibration_meta": {
        "calibrator_id": str,
        "calibration_window": int,
        "timestamp": datetime
    },
    "health_score": {
        "direction": float,
        "magnitude": float,
        "time": float,
        "overall_health": float
    }
}
```

##### 3.3.2 校准接口
- `BeliefCalibrator.fit()`   # 仅慢频调用，更新校准模型
- `BeliefCalibrator.calibrate(raw_belief)`  # 在线轻量调用，返回校准后的 belief

##### 3.3.3 评分接口
- `BeliefScorer.score(calibrated_belief) -> direction / magnitude / time / overall_health`

##### 3.3.4 与风险系统的连接
- `overall_health` → 仅影响 w_cap / risk_budget
- 不得绕过 Risk & Circuit 模块

#### M3.4 不可违反原则

##### 概率治理原则
- 系统不允许未经校准的概率直接驱动仓位或风险预算
- 所有 belief 必须通过 Calibration 层后，才允许进入 w / RiskBudget

##### 时间纪律原则
- Belief 是快变量
- Calibration 是慢变量
- Scoring 是更慢的健康评估变量
- 三者更新频率必须显式声明，不得混用

##### 风险优先原则
- belief 不可信 ≠ 系统失效
- 但 belief 不可信 ⇒ 风险必须先下降
- health score 只能影响：
  - w 上限
  - risk budget
  - 系统状态（NORMAL / DEGRADED）
- health score 不得直接触发交易

### M4 状态评估与权重压缩层（State & w）
职责：把高维概率压缩为可执行的风险旋钮。

工程对应：
- state/estimator.py（compute_w(features)->w）
- state/labels.py（label_from_w(w)->state + 迟滞规则）
- tests/test_state_smoothness.py

不可违反：
- 状态不是开关：交易决策必须基于 w（标签仅解释）
- 必须包含：平滑（EMA）+ 迟滞（进入/退出阈值不同）

验收：
- 回放测试：w 不能在边界频繁抖动（设定最大切换频率）

### M5 权重器与风险预算模块（Weighting / Risk Budget）
职责：把 w 映射成风险预算与策略权重（旋钮），并受 belief health score 约束。

工程对应：
- risk/budget.py（effective_risk = base_risk * f(w)，V1默认 w^2）
- risk/alloc.py（多策略时 alloc_i(w)）
- tests/test_budget_monotonic.py

不可违反：
- w 越低，风险预算不能上升（单调性）
- w < w_min 必须进入“保护带”（限仓/禁交易）
- belief health score 可进一步限制 w 上限和风险预算

验收：
- 单测：f(w) 单调、上下限正确、保护带生效
- 单测：health_score 降低时风险预算相应降低

### M6 策略模块（Strategy Layer）
职责：只负责“怎么做”（入场/出场/加仓），不决定“何时值得做”（那是状态+权重器）。

工程对应：
- strategies/trend.py
- strategies/range.py（若启用震荡策略）
- strategies/mix.py（signal = w*trend + (1-w)*range 或资金分配）

不可违反：
- 策略不得绕过 risk/budget 直接下单
- 策略必须提供：propose_orders(context)->orders

验收：
- 集成测试：不提供 w / effective_risk 时策略不能产生可执行订单

### M7 执行模块（Execution）
职责：把订单安全地送到交易所/撮合模拟；处理滑点保护、限价/市价规则、重试、幂等。

工程对应：
- execution/router.py
- execution/slippage_guard.py
- execution/order_state.py

不可违反：
- 任何下单必须带：最大滑点/最大点差/深度检查（门禁）

验收：
- 冒烟回放：异常点差/深度不足时订单被拒绝并记录原因

### M8 风控与断路器模块（Risk Control / Circuit Breakers）
职责：独立于策略的“刹车系统”；任何时候可压制策略。

工程对应：
- risk/guards.py（点差、波动、资金费率、连续亏损、系统异常）
- risk/circuit.py（状态：NORMAL / DEGRADED / HALT）

不可违反：
- 刹车优先级最高：风控可将 effective_risk 直接降为 0

验收：
- 压力测试：触发条件时必停手，且不会被策略覆盖

### M9 评估与实验模块（Research / Backtest）
职责：验证“优势是否存在且成本后为正”；必须做基线对照与鲁棒性。

工程对应：
- research/backtest.py
- research/baselines.py（随机入场、买入持有、简单突破）
- research/metrics.py（CAGR/MDD/成本占比/参与度）

不可违反：
- 必须对比基线；必须成本翻倍敏感性测试；必须时间切片

验收：
- 报告产物：reports/edge_eval.md（含基线与三把刀）

### M10 观测与审计模块（Observability / Evidence）
职责：任何结论都能复盘；关键状态可见；不靠“感觉”。

工程对应：
- reports/（每次运行生成摘要）
- logs/（轮转）
- dash/（可选：展示 w、状态、风险档位、是否被风控压制）

不可违反：
- 每次运行必须落盘：w、状态、effective_risk、被拦截原因
- 每次决策至少可追溯：
  - raw belief
  - calibrated belief
  - health score
  - 校准窗口信息
  - 是否因 health 限制了 w 或 risk

验收：
- 给任意一笔交易能回答：当时的 w/状态/风控/成本门禁/信念健康度 是什么

## 3️⃣ 模块关系说明

| 模块/层级 | 输入 | 输出 | 职责 | 更新频率 |
|-----------|------|------|------|----------|
| Raw Belief | Features | MarketBeliefRaw | 模型直接输出概率 | 快变量 |
| Calibration | MarketBeliefRaw | MarketBeliefCalibrated | 校准概率，解决“是否说实话” | 慢变量 |
| Scoring | MarketBeliefCalibrated | health_score | 评估可信度，解决“是否值得信任” | 更慢的健康评估变量 |
| w / RiskBudget | MarketBeliefCalibrated | w, effective_risk | 压缩为风险旋钮，受 health_score 约束 | 与 belief 同频，但受慢变量影响 |

## 4️⃣ 与既有模块的关系说明
- 校准与评分属于 M3（Market Belief）的治理子层
- 不修改 M2（Features）的职责
- 不替代 M4（State & w），只作为其上游约束
- 不削弱断路器的最高优先级

## 5️⃣ V1.2 → V1.3 变更摘要
1. 新增 Market Belief 治理子层：Belief Calibration & Scoring
2. 明确 Raw Belief 和 Calibrated Belief 定义与转换关系
3. 建立概率治理、时间纪律、风险优先三大原则
4. 冻结校准与评分的工程接口
5. 强化观测性要求，增加 belief 相关追溯字段
6. 明确校准与评分不产生交易信号，仅影响风险尺度
7. 规定 belief 健康评分只能影响 w 上限、风险预算和系统状态

## 🔒 V1.3 冻结声明
在 V1.3 中：
- 不推翻 V1.2 的核心架构
- 不新增交易策略理念
- 不引入复杂数学或模型细节
- 不改变系统目标函数（长期存活 + 复利）
- 不弱化 w、w² 风险预算、断路器优先级
- 所有升级必须符合本宪法规定的校准与评分机制

## 验收提示词
**TaskCode: QUANTSYS_CONSTITUTION_V1_3_UPDATE_001**

**提交**
- 最终回复以 SUBMIT 盖章
- ≤8 行总结：本次宪法新增了什么、冻结了什么、下一步工程应做什么
