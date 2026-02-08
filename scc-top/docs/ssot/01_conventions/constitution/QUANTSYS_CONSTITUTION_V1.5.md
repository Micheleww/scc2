---
oid: 01KGFSKMP58CWP613MK90HSKE6
layer: DOCOPS
primary_unit: V.GUARD
tags: [S.NAV_UPDATE]
status: active
---

# QuantSys 宪法 V1.5

## 0️⃣ 系统总目标（不变）
长期存活 + 稳定复利
任何提升短期收益但增加出局风险的设计，均视为违规。

## 1️⃣ 核心系统流水线（V1.5）
Data
→ Features
→ Market Belief (Raw → Calibrated → Scored)
→ State & Weight (w)
→ Risk Budget (base_risk → effective_risk)
→ Position Sizing (effective_risk → position_size)
→ Strategy / Policy
→ Execution
→ Risk & Circuit Breaker
→ Observability

## 2️⃣ 各模块职责与工程接口

### M0 目标与优先级模块
职责：定义系统唯一目标函数与优先级（生存 > 复利 > 峰值）。

工程对应：
- docs/ssot/01_conventions/constitution/QUANTSYS_CONSTITUTION_V1.5.md（本宪法）
- docs/GOALS.md（一句话目标 + 不做清单）

不可违反：
- 任意改动若提高破产风险：拒绝合并

验收：
- PR/任务必须声明：对 MDD/爆仓风险影响为“降低/不变”

### M1 风险哲学（新增章节）

#### 1.1 根本风险承认
系统明确承认三类可能导致出局的根本风险：
- **连续亏损出局（Path Dependence）**：多次小亏损累积导致破产
- **单次爆亏出局（Tail / Black Swan）**：极端尾部事件导致的毁灭性损失
- **模型错误出局（Probability / Regime Error）**：模型在新环境下失效导致的持续亏损

#### 1.2 系统目标重述
系统的首要目标不是最大化期望收益，而是：
- 在不出局的前提下参与正期望机会
- 明确“空仓”是主动决策，而非失败状态
- 保持系统的鲁棒性和适应性

### M2 数据与可得性模块（Raw → Features 输入边界）
职责：原始数据的时间可得性与一致性；禁止未来函数。

工程对应：
- data/feeds/*（行情/订单簿/资金费率等）
- data/schema.py（字段语义与时间戳规则）
- tests/test_no_lookahead.py

不可违反：
- 特征只能使用 t 时刻之前可得的数据

验收：
- 单元测试：随机截断数据后，特征输出不依赖未来

### M3 因子/特征模块（信息压缩层）
职责：把原始数据压缩成稳定特征；不包含任何仓位/交易结果。

工程对应：
- features/*（算子、滚动、rank/log等）
- features/registry.py（特征注册表）

不可违反：
- 特征层不得读取：持仓、PnL、成交结果

验收：
- 静态检查/测试：特征模块无 portfolio/ execution/ pnl 依赖

### M4 市场维度概率层（Market Belief）

#### M4.1 核心职责
表达对市场演化方式的概率判断，包含三个正交维度：
- 方向：Up / Down / Flat
- 幅度：|ΔP| ∈ bins
- 时间：事件在不同时间窗 H 内发生的概率

#### M4.2 Belief Calibration & Scoring 治理子层

##### 4.2.1 Belief 类型定义
- **Raw Belief**：模型直接输出的概率
- **Calibrated Belief**：经慢变量校准后的概率，包含 calibration_meta 和 health_score

##### 4.2.2 校准与评分目标
- **校准**：解决“概率是否说实话”问题
- **评分**：解决“概率是否仍值得信任”问题

##### 4.2.3 治理原则
- 校准与评分不产生交易信号，仅影响风险尺度

#### M4.3 工程接口

##### 4.3.1 数据结构
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

##### 4.3.2 校准接口
- `BeliefCalibrator.fit()`   # 仅慢频调用，更新校准模型
- `BeliefCalibrator.calibrate(raw_belief)`  # 在线轻量调用，返回校准后的 belief

##### 4.3.3 评分接口
- `BeliefScorer.score(calibrated_belief) -> direction / magnitude / time / overall_health`

##### 4.3.4 与风险系统的连接
- `overall_health` → 仅影响 w_cap / risk_budget
- 不得绕过 Risk & Circuit 模块

#### M4.4 不可违反原则

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

### M5 状态评估与权重压缩层（State & w）

#### M5.1 w 的正式定义（冻结）

##### 5.1.1 w 的本质
- w 表示：当前市场环境下，系统“愿意承担风险的强度”
- w 不代表仓位比例，不代表胜率，不代表确定性
- w ∈ [0, 1]，其中 0 表示完全不愿意承担风险，1 表示最大愿意承担风险

##### 5.1.2 w 的作用范围（严格限制）
- 决定是否参与：w < w_min → 不参与
- 决定风险预算的放大或压缩
- 不允许 w 直接决定仓位大小

##### 5.1.3 风险强度映射规则（沿用并冻结）
- effective_risk = base_risk × w²
- w² 用于惩罚概率误差与过度自信

#### M5.2 工程对应
- state/estimator.py（compute_w(features)->w）
- state/labels.py（label_from_w(w)->state + 迟滞规则）
- tests/test_state_smoothness.py

#### M5.3 不可违反
- 状态不是开关：交易决策必须基于 w（标签仅解释）
- 必须包含：平滑（EMA）+ 迟滞（进入/退出阈值不同）

#### M5.4 验收
- 回放测试：w 不能在边界频繁抖动（设定最大切换频率）

### M6 权重器与风险预算模块（Weighting / Risk Budget）

#### M6.1 从 w 到 Risk Budget 的链路（新增冻结）

##### 6.1.1 base_risk 定义
- base_risk 是账户层面可承受的单笔最大损失上限
- 受日/周/总回撤断路器约束
- base_risk 必须是保守估计，不得超过账户净值的安全比例

##### 6.1.2 effective_risk 定义
- effective_risk 表示：在当前 belief 健康度与市场状态下，本次交易允许消耗的最大现金损失
- effective_risk = base_risk × w²
- belief health 仅允许降低 effective_risk，不得放大 base_risk

#### M6.2 工程对应
- risk/budget.py（effective_risk = base_risk * f(w)，V1默认 w^2）
- risk/alloc.py（多策略时 alloc_i(w)）
- tests/test_budget_monotonic.py

#### M6.3 不可违反
- w 越低，风险预算不能上升（单调性）
- w < w_min 必须进入“保护带”（限仓/禁交易）
- belief health score 可进一步限制 w 上限和风险预算

#### M6.4 验收
- 单测：f(w) 单调、上下限正确、保护带生效
- 单测：health_score 降低时风险预算相应降低

### M7 仓位计算模块（Position Sizing）

#### M7.1 从 Risk Budget 到仓位的计算方法（新增冻结）

##### 7.1.1 仓位计算的唯一合法形式
- position_size = effective_risk / per_unit_risk

##### 7.1.2 per_unit_risk 的制度性定义
- per_unit_risk = 止损损失 + 滑点缓冲 + 手续费 + 尾部/跳空缓冲
- per_unit_risk 必须是“保守估计”，不是期望值
- per_unit_risk 必须包含对极端情况的缓冲

##### 7.1.3 禁止项（硬约束）
- 禁止使用期望收益、胜率、Kelly 比例直接计算仓位
- 禁止概率直接映射到账户仓位比例
- 禁止不考虑单位风险的仓位计算

#### M7.2 三维 Market Belief 在仓位中的合法作用

##### 7.2.1 Direction 维度
- 决定是否参与
- 决定多/空方向
- 不决定仓位大小

##### 7.2.2 Magnitude 维度
- 影响止损距离与尾部缓冲
- 间接影响 per_unit_risk

##### 7.2.3 Time 维度
- 影响持有期、资金成本、尾部暴露
- 间接影响 per_unit_risk

#### M7.3 工程对应
- risk/position_sizing.py（calculate_position_size(effective_risk, per_unit_risk)->position_size）
- tests/test_position_sizing.py

#### M7.4 不可违反
- 仓位计算必须严格遵循 position_size = effective_risk / per_unit_risk
- per_unit_risk 必须包含所有风险成分
- 仓位不得超过交易所或系统设定的上限

#### M7.5 验收
- 单测：仓位随 effective_risk 增加而增加，随 per_unit_risk 增加而减少
- 单测：极端情况下仓位不会导致爆仓

### M8 防出局制度（新增章节）

#### M8.1 防连续亏损
- 单笔风险上限：effective_risk 严格限制
- 日/周亏损限额：累计亏损达到阈值时降档或暂停
- 连错降档：连续错误决策后下调 w_cap
- 最大回撤 HALT：达到预设最大回撤时强制暂停

#### M8.2 防单次爆亏
- per_unit_risk 必须包含 tail buffer
- 不允许满仓或极限暴露
- 承认并支付“保险成本”：接受保守的风险估计
- 严格的止损执行：不允许随意扩大止损

#### M8.3 防模型错误
- belief calibration & health 机制
- health 下降只允许降低风险
- 模型不可信 → 优先空仓
- 定期模型重校准与验证

### M9 策略模块（Strategy Layer）
职责：只负责“怎么做”（入场/出场/加仓），不决定“何时值得做”（那是状态+权重器）。

工程对应：
- strategies/trend.py
- strategies/range.py（若启用震荡策略）
- strategies/mix.py（signal = w*trend + (1-w)*range 或资金分配）

不可违反：
- 策略不得绕过 risk/budget 直接下单
- 策略必须提供：propose_orders(context)->orders
- 策略不得修改仓位大小，只能接受 position_size 作为输入

验收：
- 集成测试：不提供 w / effective_risk 时策略不能产生可执行订单
- 集成测试：策略严格按照 position_size 下单

### M10 执行模块（Execution）

#### M10.1 Execution 的系统定位
1.1 Execution 是风险控制模块，不是收益优化模块  
1.2 Execution 的职责是：
- 降低不可控摩擦
- 识别执行不可行的交易
- 防止执行层放大账户风险

1.3 Execution 不允许：
- 改变 w
- 放大仓位
- 以“执行优化”为理由突破风险预算

#### M10.2 Execution 与风险系统的关系
2.1 Execution 只能接收：
- 已冻结的 position_size
- 已计算的 per_unit_risk
- 已通过的风险预算审批

2.2 Execution 允许做的事情只有：
- 缩小实际下单量
- 延迟执行
- 拆分执行
- 拒绝执行（返回拒单原因）

2.3 Execution 不得做的事情：
- 不得增加下单规模
- 不得绕过 risk / circuit breaker
- 不得隐式承担未计入 per_unit_risk 的风险

#### M10.3 执行失败的制度定义
3.1 以下情况被视为“执行风险事件”：
- 大幅偏离预期滑点
- 成交失败或长期未成交
- 流动性快速枯竭
- 交易成本异常放大

3.2 执行风险事件的后果：
- 必须回传至风险系统
- 可触发：
  - 降低 w_cap
  - 降低 effective_risk
  - 暂停相关品种或时间段交易

#### M10.4 Execution 在 per_unit_risk 中的地位
4.1 Execution 相关风险必须：
- 事前进入 per_unit_risk 的估计
- 而不是事后解释亏损

4.2 禁止：
- 将执行损失视为“偶然噪声”
- 将执行失败归因为“运气”

#### M10.5 Observability 要求
每一笔执行必须可追溯：
- 计划下单量 vs 实际成交量
- 预期滑点 vs 实际滑点
- 拒单原因（如有）
- 执行结果对 risk / w 的反馈

#### M10.6 工程对应
- execution/router.py
- execution/slippage_guard.py
- execution/order_state.py

#### M10.7 不可违反
- 任何下单必须带：最大滑点/最大点差/深度检查（门禁）

#### M10.8 验收
- 冒烟回放：异常点差/深度不足时订单被拒绝并记录原因

### M11 风控与断路器模块（Risk Control / Circuit Breakers）
职责：独立于策略的“刹车系统”；任何时候可压制策略。

工程对应：
- risk/guards.py（点差、波动、资金费率、连续亏损、系统异常）
- risk/circuit.py（状态：NORMAL / DEGRADED / HALT）

不可违反：
- 刹车优先级最高：风控可将 effective_risk 直接降为 0

验收：
- 压力测试：触发条件时必停手，且不会被策略覆盖

### M12 评估与实验模块（Research / Backtest）
职责：验证“优势是否存在且成本后为正”；必须做基线对照与鲁棒性。

工程对应：
- research/backtest.py
- research/baselines.py（随机入场、买入持有、简单突破）
- research/metrics.py（CAGR/MDD/成本占比/参与度）

不可违反：
- 必须对比基线；必须成本翻倍敏感性测试；必须时间切片

验收：
- 报告产物：reports/edge_eval.md（含基线与三把刀）

### M13 观测与审计模块（Observability / Evidence）
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
  - w / effective_risk
  - per_unit_risk 的各组成项
  - 最终 position_size
  - 是否因风险规则被限制或拒绝

验收：
- 给任意一笔交易能回答：当时的 w/状态/风控/成本门禁/信念健康度/仓位计算依据 是什么

## 3️⃣ 模块关系说明

### 3.1 从 belief 到仓位的完整链路
```
Raw Belief → Calibration → Scored Belief → w (风险强度) → effective_risk (风险预算) → per_unit_risk (单位风险) → position_size (仓位)
```

### 3.2 详细模块关系表

| 模块/层级 | 输入 | 输出 | 职责 | 更新频率 |
|-----------|------|------|------|----------|
| Raw Belief | Features | MarketBeliefRaw | 模型直接输出概率 | 快变量 |
| Calibration | MarketBeliefRaw | MarketBeliefCalibrated | 校准概率，解决“是否说实话” | 慢变量 |
| Scoring | MarketBeliefCalibrated | health_score | 评估可信度，解决“是否值得信任” | 更慢的健康评估变量 |
| State & w | MarketBeliefCalibrated | w | 压缩为风险强度旋钮 | 与 belief 同频，但受慢变量影响 |
| Risk Budget | w, base_risk, health_score | effective_risk | 计算本次交易允许的最大损失 | 与 w 同频 |
| Position Sizing | effective_risk, per_unit_risk | position_size | 计算最终仓位大小 | 与 effective_risk 同频 |

## 4️⃣ 与既有模块的关系说明
- 校准与评分属于 M4（Market Belief）的治理子层
- 仓位计算（M7）是新增模块，位于风险预算与策略之间
- 不修改 M2（Features）的职责
- 不替代 M5（State & w），只作为其下游扩展
- 不削弱断路器的最高优先级
- Execution（M10）正式纳入风险控制体系，作为风险系统的延伸

## 5️⃣ V1.4 → V1.5 变更摘要
1. 正式将 Execution 模块写入宪法，明确其风险控制定位
2. 规定 Execution 只能进行风险降低操作，禁止任何风险放大行为
3. 定义执行风险事件类型及后果处理机制
4. 明确 Execution 与风险系统的上下游关系和数据边界
5. 要求执行风险必须事前纳入 per_unit_risk 估计
6. 强化执行层面的可观测性要求，确保每笔执行可追溯
7. 明确 Execution 不得改变 w、放大仓位或突破风险预算
8. 确立执行失败是风险事件，需回传风险系统并可触发风控措施

## 🔒 V1.5 冻结声明
在 V1.5 中：
- 不推翻 V1.4 的核心架构
- 不新增交易策略理念
- 不引入复杂数学或模型细节
- 不改变系统目标函数（长期存活 + 复利）
- 不弱化 w²、断路器、空仓制度
- 所有升级必须符合本宪法规定的风险链路
- 仓位计算必须严格遵循 position_size = effective_risk / per_unit_risk
- 禁止使用 Kelly、胜率、期望收益作为仓位输入
- Execution 必须严格遵守风险控制定位，不得作为收益优化模块

## 验收提示词
**TaskCode: QUANTSYS_CONSTITUTION_V1_5_UPDATE_001**

**提交**
- 最终回复以 SUBMIT 盖章
- ≤8 行总结：Execution 在系统中的职责与边界
