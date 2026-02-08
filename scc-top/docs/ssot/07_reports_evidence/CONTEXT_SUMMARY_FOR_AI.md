---
oid: 01KGEJFVG597Y2CYYT9PD8K26R
layer: REPORT
primary_unit: P.REPORT
tags: [V.VERDICT]
status: active
---

# ATA 自迭代项目完整上下文总结

**生成时间**：2025-01-16  
**项目路径**：`<ABS_PATH>`（本地工作区）

---

## 一、Cursor CLI 延迟测试结论

### 测试发现
- **主要问题**：延迟主要来自**网络或 API 层面**，而非模型选择问题
- **模型表现**：除 `gemini-3-flash` 明显较慢外，其他主要模型的响应时间相对一致
- **对比结果**：iFlow CLI 表现出**显著更低的延迟**
- **建议**：根据实际需求选择合适的工具和模型

### Cursor CLI 信息
- **状态**：已安装并登录成功
- **文档**：https://cursor.com/cn/docs/cli/overview
- **关键命令**：
  - `agent`：交互式会话
  - `agent "prompt"`：非交互式执行
  - `--mode=plan/ask/agent`：模式选择
  - `--model`：模型选择
  - `agent ls`：列出会话
  - `agent resume`：恢复会话

### iFlow CLI 信息
- **安装位置**：
  - 核心代码：`C:/Users/Nwe-1/AppData/Roaming/npm/node_modules/@iflow-ai/iflow-cli/`
  - 可执行文件：`C:/Users/Nwe-1/AppData/Roaming/npm/iflow.cmd`
- **配置**：
  - API Key：通过 `IFLOW_API_KEY` 环境变量
  - 配置文件：`C:/Users/Nwe-1/.iflow/settings.json`（不应直接编辑）
- **关键命令**：
  - `iflow "prompt"`：非交互式执行
  - `iflow`：交互式会话
  - `--model qwen3-coder-plus`：模型选择（默认）
  - `--debug`：调试模式
  - `--continue`：继续上次会话
  - `--resume <session-id>`：恢复指定会话

---

## 二、项目核心目标：ATA 自迭代自动化

### 2.1 核心目标
实现 ATA (Automated Task Agent) 流程的**自迭代自动化**，让系统能够：
- 自动发现系统不足
- 自动生成改进任务
- 自动验证和回滚
- 无需人工"产品经理"持续介入

### 2.2 8 步自迭代闭环
1. **Collect**：采集事件与指标（行为、性能、错误、任务执行结果）
2. **Detect**：自动检测异常/不足（规则 + 统计 + 对比基线）
3. **Explain**：归因与定位候选（日志聚类、堆栈聚合、相关性）
4. **Propose**：生成修复/优化子任务（带成功标准、回滚、风险）
5. **Execute**：交给执行AI产 patch（严格走现有 CI/硬门）
6. **Verify**：自测+回归（smoke/e2e/性能基线对比）
7. **Rollout**：特性开关灰度（可回滚、可禁用）
8. **Measure**：上线后指标回归到基线/变好，否则自动回滚并降权策略

### 2.3 机器可验证信号（SLO + 负样本）

**A. 可靠性（必须自动化）**
- crash-free session %
- task 成功率 / 失败率（按失败码分桶）
- 重试次数分布（mean_retries、p95 retries）
- DLQ 堆积长度、重复 message_id 比例

**B. 体验摩擦（最像"产品经理"的部分，但可量化）**
- "发送任务→看到ACK"延迟（p50/p95）
- "任务创建→首个进度事件"延迟
- 用户手动介入次数
- 抢占焦点：foreground steal 次数/分钟

**C. 性能**
- 启动 T0-T5、主线程卡顿、渲染首屏时间
- 内存/CPU 基线漂移
- I/O 热点（加载、索引、日志写入）

**D. 安全与可控**
- 任何自动执行必须有 verdict/证据链
- 配置泄露扫描、token/密钥落盘检测
- 版本回滚耗时、回滚成功率

---

## 三、三个核心计划文件

### 3.1 ATA 自迭代计划 (`ata-auto-iteration_5b2cd437.plan.md`)

**目标**：让 CI 失败和 nightly 回归自动生成 A2A 任务

**关键修改点**：
- `tools/ci/mvm-verdict.py`：对齐字段（task_code、area、fail_codes、status_normalized）
- `tools/mcp_bus/server/verdict_handler.py`：兼容大小写状态判断
- `tools/ci/run_phase4_checks.py`：新增 secrets-scan check
- `.github/workflows/nightly-regression.yml`：直接运行 nightly_regression.py
- 新增 `tools/ci/controlplane/ata_reliability_metrics.py`：收集可靠性指标
- 新增 `configs/ata/auto_pm_slo.yaml`：SLO 阈值配置
- 新增 `tools/ci/controlplane/auto_pm_detect.py`：检测 SLO 违规

**状态**：所有 todos 标记为 completed

### 3.2 Agent Harness 硬门计划 (`ata-harness-hardgate_84a03a6d.plan.md`)

**目标**：将"Effective harnesses for long-running agents"方法论落地为可持续运行的生产级系统

**核心概念**：
- **两段式会话**：Initializer（一次性）+ Coding（多回合增量）
- **两工件**：
  - `docs/FEATURES/features.json`：只允许改 passes
  - `docs/PROGRESS/agent_progress.md`：append-only 接班说明书
- **强制增量**：每轮只完成 1 个 feature
- **先测后标 pass**：无 smoke/selftest/e2e 证据则禁止 passes=true

**关键文件**：
- `tools/agent_harness/harness_hardgate.py`：本地硬门检查
- `tools/ci/run_phase4_checks.py`：接入 harness-hardgate check
- `docs/PROGRESS/harness_baseline.json`：baseline marker
- `tools/e2e.ps1`：最小 e2e harness

**状态**：所有 todos 标记为 completed

### 3.3 P0 任务链回归计划 (`p0-taskchain-regression_77c033e4.plan.md`)

**目标**：确保任务链路的正确性、幂等性、可恢复性和可审计性

**核心设计**：
- **三者职责固定**：
  - `task_id`：任务身份（贯穿全链路）
  - `message_id`：投递幂等（重试保持不变；去重主键）
  - `task_code`：展示标签（不参与幂等）
- **双模式执行器**：
  - CI：SimWorker（确定性、可复跑）
  - Local：RealExecutor（可选 Trae/Codex/Cursor/iFlow CLI）

**关键修改**：
- `tools/a2a_hub/main.py`：tasks 表新增 message_id + unique index
- `/api/task/create`：按 message_id 幂等
- `/api/task/next`：ACK 丢失/重复恢复
- 指数退避≤3 + DLQ 规则
- `tools/gatekeeper/reason_codes.py`：env/test/business 三元分类
- 新增 P0 端到端回归脚本
- `tools/ci/run_phase4_checks.py`：接入 a2a-taskchain-e2e check
- Kill switch 机制：读取 `configs/ata/auto_pm_controls.yaml`

**状态**：所有 todos 标记为 completed

---

## 四、项目关键文件与架构

### 4.1 核心入口
- **项目导航**：`docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md`
- **Agent 契约**：`corefiles/AGENT_CONTRACT.txt.md`
- **启动脚本**：`tools/run_dev.ps1`
- **冒烟测试**：`tools/smoke.ps1`

### 4.2 A2A 系统
- **A2A Hub**：`tools/a2a_hub/main.py`（任务管理、API、重试/DLQ）
- **A2A Worker**：`tools/a2a_worker/main.py`（任务执行、产物签名）
- **MCP Bus**：`tools/mcp_bus/server/`（事件发布、消息队列、工具执行）

### 4.3 CI 系统
- **Phase4 Checks**：`tools/ci/run_phase4_checks.py`（统一检查框架）
- **Verdict**：`tools/ci/mvm-verdict.py`（生成 verdict.json）
- **Nightly Regression**：`tools/ci/controlplane/nightly_regression.py`
- **Gatekeeper**：`tools/gatekeeper/`（验证、原因码、模式）

### 4.4 数据存储
- **Features**：`docs/FEATURES/features.json`
- **Progress**：`docs/PROGRESS/agent_progress.md`
- **Reports**：`docs/REPORT/`（按 area 组织）
- **Artifacts**：`docs/REPORT/{area}/artifacts/{TASK_CODE}/`
- **Message Queue**：`docs/REPORT/ata/message_queue.db`
- **Events**：`docs/REPORT/ata/events/*.json`

### 4.5 配置文件
- **SLO 配置**：`configs/ata/auto_pm_slo.yaml`
- **控制开关**：`configs/ata/auto_pm_controls.yaml`
- **Kill Switch**：`data/kill_switch_status.json`

---

## 五、技术决策记录

### 5.1 执行器模式
- **选择**：双模式执行器（CI 模拟 + Local 真实）
- **理由**：保证 CI 可复跑，同时本地可真实执行

### 5.2 幂等键
- **选择**：`message_id` 作为幂等主键
- **理由**：同一消息重放只执行一次，task_code 仅作展示

### 5.3 失败分类
- **选择**：env/test/business 三元分类
- **理由**：便于 Auto-PM 归因和统计，避免空泛任务

### 5.4 CLI 工具选择
- **Cursor CLI**：已安装，延迟主要来自网络/API
- **iFlow CLI**：延迟更低，建议根据需求选择

---

## 六、当前状态

### 6.1 已完成
- ✅ ATA 自迭代 MVP（verdict→事件→自动派单）
- ✅ Agent Harness 硬门系统
- ✅ P0 任务链回归（幂等、重试、DLQ、失败分类）
- ✅ Cursor CLI 延迟测试

### 6.2 待完成
- ⏳ **Cursor CLI 集成**：实现作为 RealExecutor 的调用接口
- ⏳ **iFlow CLI 集成**：实现作为 RealExecutor 的调用接口
- ⏳ **性能优化**：根据延迟测试结果选择合适工具和模型
- ⏳ **端到端测试**：验证集成后的完整流程

---

## 七、关键路径与证据

### 7.1 关键路径
- **Verdict**：`mvm/verdict/verdict.json`
- **Baseline**：`docs/PROGRESS/harness_baseline.json`
- **Features**：`docs/FEATURES/features.json`
- **Progress**：`docs/PROGRESS/agent_progress.md`

### 7.2 证据路径
- **Phase4 结果**：`docs/REPORT/{area}/artifacts/{TASK_CODE}/*_result.json`
- **ATA Context**：`docs/REPORT/{area}/artifacts/{TASK_CODE}/ata/context.json`
- **Self-test**：`docs/REPORT/{area}/artifacts/{TASK_CODE}/selftest.log`
- **E2E**：`docs/REPORT/{area}/artifacts/{TASK_CODE}/e2e_output.log`

---

## 八、重要原则

1. **Fail-closed 原则**：所有检查必须生成证据，缺证据必须失败
2. **幂等性**：message_id 必须唯一，重放只执行一次
3. **增量开发**：每轮只完成 1 个 feature，先测后标 pass
4. **可审计性**：所有变更必须有证据链和 commit
5. **网络延迟**：Cursor CLI 延迟主要来自网络/API，非模型选择问题
6. **工具选择**：iFlow CLI 延迟更低，建议优先考虑

---

## 九、下一步行动建议

1. **实现 Cursor CLI 集成**：
   - 创建调用接口（封装 `agent` 命令）
   - 实现结果解析和错误处理
   - 集成到 A2A Worker 的 RealExecutor

2. **实现 iFlow CLI 集成**：
   - 创建调用接口（封装 `iflow` 命令）
   - 实现结果解析和错误处理
   - 集成到 A2A Worker 的 RealExecutor

3. **性能优化**：
   - 根据延迟测试结果，在配置中推荐使用 iFlow CLI（延迟更低）
   - 为 Cursor CLI 提供模型选择建议（避免 gemini-3-flash）

4. **端到端验证**：
   - 使用真实 CLI 执行器运行 P0 回归测试
   - 验证完整任务链路（create → ACK → progress → artifacts → verdict → DONE）

---

**文档用途**：供另一个 AI 快速了解项目全貌和上下文  
**更新建议**：随着项目进展持续更新此文档
