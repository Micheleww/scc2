# REPORT: SCC 系统现状总览（供 gpt-5.2 审查）

Date: 2026-02-07  
Scope: `C:\scc` workspace (Windows), local control-plane + multi-executor routing

## 0. 文档目的（给审查模型的输入）

这是一份基于本工作区真实代码与配置的“现状总览”，目标是交给审查模型（`gpt-5.2`）做系统性审阅：
- What SCC provides (features, guarantees, constraints)
- What the core logic/flows are (task lifecycle, split/dispatch/execute/verify/replay)
- How model + executor routing works (paid/free pools, strong-to-weak ladder, backpressure)
- Where SCC is strong vs where to enhance (vs big-tech agent platforms and 2024-2026 multi-agent trends)

Primary entrypoint (local gateway):
- Unified gateway base: `http://127.0.0.1:18788` (see `docs/NAVIGATION.md`)

## 0.5 SCC 迭代总目标（总目标注入）

把 SCC 迭代成一个“自运行、自稳定、自迭代”的 Agent Factory OS：在最少人工介入下，将任意高层目标自动转化为**可验证**（gates）、**可回放**（replay）、**可解释**（trace + evidence）、**可控成本**（budget/WIP）的交付物，并在运行中持续提升成功率、吞吐与单位成本表现，同时保持 *fail-closed* 的安全与治理边界不被稀释。

后端总目标：
1) 控制平面成为“唯一事实源 + 可编排的自治系统”
- 以本地 Gateway 作为核心控制平面（taskboard/split/dispatch/scheduler/context shaping/策略与审计），把“系统怎么跑”从经验变成可配置、可追溯、可回归的工程对象。
- 目标态具备：
  - 确定性的任务生命周期：intake -> split -> dispatch -> execute -> verify -> verdict 全链路可追踪与可重放（而非依赖对话历史作为事实源）。
  - 统一的调度语义：WIP/背压/优先级/降级/断路器都由 factory policy 驱动，并能对外解释“为什么此刻这么调度”。
  - 严格的执行合约不退化：`atomic-only` + `SUBMIT`/verdict + evidence 的机器可验证闭环继续作为底座约束。

2) 数据平面成为“可替换执行器/模型的生产流水线”
- SCC 已具备多执行器与路由能力，目标态进一步抽象为“可插拔执行单元”，以任务约束与预算为主导：
  - 按任务类/能力/历史统计路由（而不是靠模型名启发式），并把预算变成硬边界。
  - 故障域隔离 + 有界重试 + 自动恢复：延续 bounded requeue + lanes（dlq/quarantine）的工厂化模式，把事故从“崩溃”变成“降级运行”。

3) 可观测性从“日志集合”进化为“系统事实”
- 将 jobs/failures/route_decisions/state_events 等提升为一等对象：
  - 每个 parent task 产出单文件 trace（plan -> pins -> dispatch -> execute -> gates -> verdict），并能回放定位到具体执行器/模型/版本配置。
  - 将路由决策、降级决策、断路器触发、预算消耗等纳入 trace 的“可解释字段”。

前端总目标（Console/Cockpit）：
- 不只是“展示任务列表”，而是自治工厂的操作台，满足三类用户：操作者（你）、系统管理员、审计者。
- 目标态能力：
  - 自运行可视化：实时展示任务树（parent -> children）、当前 lane/WIP、预算消耗、预计完成时间、阻塞原因（pins/依赖/CI）；一键查看某个 verdict 的证据链（`SUBMIT`、`REPORT`、`EVIDENCE`、gates 结果）。
  - 自稳定操作面板：工厂健康（断路器状态、降级矩阵、失败率突增、模型 throttle/auth 波动、执行器可用性）；提供“建议动作”和“已自动采取动作”的差异说明（避免人机互相打架）。
  - 自迭代工作台：把每次失败/回归变成 case -> 归因 -> 修复 PR/策略变更 -> 验证结果 -> 上线记录；将系统自动化复盘产物统一沉淀在“改进队列”，并一键触发离线评测/回归。

自运行目标（自运行的定义与闭环）：
- 定义：“没有人盯着也能持续产出合格 verdict”。
- 目标态自运行需要三种自治闭环（都在控制平面发生，而不是靠某个 executor 临时发挥）：
  - 任务自治闭环：自动拆解（split）、自动派发（dispatch）、自动修复链（pins_fixup/ci_fixup/timeout/tooling fallback），直到进入 done/failed 终态，并把 `NEED_INPUT` 明确沉入 dlq 列出缺失项。
  - 资源自治闭环：以 factory policy 为唯一控制项（WIP、lane、budget、degradation、circuit breaker 自动调节），目标是“稳态吞吐最大化 + 不雪崩”。
  - 质量自治闭环：gates 作为质量闸门，任何不满足合约/证据/安全策略的结果都不会被当作完成（fail-closed）。

自稳定目标（波动下不雪崩，最多降级，并可自动恢复）：
- 定义：“面对模型/网络/执行器/负载波动不崩溃，最多降级；并能自动恢复到稳态”。
- 衡量指标（建议作为系统 SLO）：
  - Task success rate（按 task_class 分桶）
  - p50/p90 time-to-verdict
  - “需要人工介入”的比例（`NEED_INPUT` + 人工 override）
  - meltdown 指标：断路器触发次数、quarantine/dlq 堆积、重试风暴次数
- 稳定机制（应当强制由控制平面执行）：
  - bounded requeue + cooldown（防止抖动）
  - lane 迁移（fastlane/main/batch/dlq/quarantine）
  - circuit breakers + degradation matrix（止血）

自迭代目标（把运行数据转化为可验证改进，并门禁安全上线）：
- 定义：“系统能把运行数据转化为可验证的改进，并通过评测 + 门禁安全上线”。
- 完整变更流水线（类似 CI/CD，但针对 agent factory）：
  - 发现（Detect）：failures、state_events、route_decisions、token 浪费、越权倾向、复盘报告、playbooks 草案等运行信号。
  - 归因（Diagnose）：归因到合约问题、pins/上下文问题、路由问题、执行器问题、策略问题、测试问题，产出可执行的改动提案（prompt/role/connector/路由参数/预算策略/测试策略等）。
  - 验证（Validate）：离线 eval suite + 回归对比，证明改动提升核心指标且不引入倒退；对会影响安全/成本/成功率的改动设硬门槛 gate 化。
  - 上线（Rollout）：分 lane/分 task_class 灰度；可回滚；所有上线写入 trace 的 config snapshot 以便复盘。
  - 固化（Codify）：把有效改动固化为 factory policy 规则、路由模型统计、playbooks、skills/roles 约束、connector 权限模板。

一句话“完成态定义”（Definition of Done）：
- 输入一个高层目标，系统能自动拆解并调度执行，最终输出可审计 verdict，且任何人可在 Console 中用 trace + replay 在分钟级复现全过程。
- 在模型/执行器波动时不崩溃，只会按 policy 降级并自动恢复稳态吞吐。
- 系统能把失败模式与浪费自动转成改进提案，并经评测/门禁后自动灰度上线，持续提升单位成本与成功率（自迭代闭环）。

## 2026-02-07 现状补丁：统一 Workbench + Control Plane（/cp）

当前你实际在用的融合形态（以代码与容器运行态为准）是：
- 单端口单服务器：Docker 容器内 `scc-top/tools/unified_server` 暴露 `18788`。
- 单 UI：Workbench 由 unified_server 直接从 `/` 提供（VS Code 风格 token + codicon）。
- `/api` 专用于 legacy A2A Hub（WSGI mount），避免与 control plane 冲突。
- unified_server 自己的控制面 API 使用 `/cp/*`。
- 兼容性：中间件将部分历史 `/api/*` control plane 路径重写到 `/cp/*`（如 `/api/executor/*`、`/api/jobs/*`）。

Workbench 的融合操作页（同一个 UI 内）：
- Tasks：总任务/父任务/子任务列表
- Routing：模型路由（持久化到 `tools/unified_server/state/model_routing.json`，executor 实时读取）
- Waterfall：executor/automation 瀑布流（暂时内嵌 legacy 页面）
- Logs：可选日志/JSONL 流 + tail
- Agents：切换 agent/查看状态（本地 executor + OpenClaw 远程 executors + OpenCode/OpenClaw health）
- Flow：任务分配与执行流（curated streams + `/cp/flow/combined` 合并时间线）

注：本文档后续章节里对 Node gateway（`oc-scc-local/src/gateway.mjs`）的描述属于历史/并行实现；在当前“统一服务器 Docker 模式”下，不建议它继续占用 `18788`。

## 2026-02-07 补充：程序员 Dev 调试端（Electron）

为“点开即可用”的程序员 Dev 调试端补了一个 Electron 客户端（可直接双击运行，不依赖 node/electron 全局安装）：
- 源码目录：`scc-top/tools/scc_dev_electron/`
- 成品目录（已打包）：`scc-top/tools/scc_dev_electron/dist/SCC Workbench-win32-x64/SCC Workbench.exe`
- Electron 本体：`scc-top/tools/scc_dev_electron/dist/SCC Workbench-win32-x64/SCC Workbench (Electron).exe`
- 行为：启动时探测 `GET /health/ready`；未就绪则自动执行 `docker compose -f docker-compose.scc.yml up -d` 拉起统一服务器；就绪后加载 `http://127.0.0.1:18788/`。
- 唯一快捷键：`Ctrl+Alt+D`（App 内注册：切换到 Flow 视图并打开/关闭 DevTools。）

注意：当前环境存在全局环境变量 `ELECTRON_RUN_AS_NODE=1`，会导致 Electron 直接以 Node 模式启动并退出。
因此我们把 `SCC Workbench.exe` 做成 Launcher：启动时清空该变量后再拉起 `SCC Workbench (Electron).exe`，保证“一次成功、点开可用”。

## 1. 一句话理解 SCC

SCC 是一个 *fail-closed*、可审计、可回放的多 agent 控制平面：把目标拆成 *atomic executor tasks*，用 *pins-first* 约束最小上下文，按 factory policy 做 WIP/背压/降级并在多执行器与多模型间路由，最后用 CI gates 产出可证据化的 verdict。

## 2. 系统地图（组件与职责）

### 2.1 本地 Gateway（控制平面 + 路由 + 调度）
Code:
- `oc-scc-local/src/gateway.mjs` (primary control-plane implementation)

职责（以代码行为为准）：
- Taskboard: create/update/list tasks (“board”)
- Split orchestration: create “needs_split” planner tasks; apply split result to generate atomic children
- Dispatch: choose executor + model for each atomic task (constraints + pool policy)
- Scheduler: job queue, leases, internal/external concurrency, WIP limits
- Context shaping: pins/map/preflight building, context packs, pins-v2 support
- Fail-closed enforcement: role policy checks, pins constraints, submit contract requirements
- Observability: events, route decisions, failure logs, debug endpoints

Key user-facing endpoints are summarized in `docs/NAVIGATION.md`.

### 2.2 Upstreams（OpenCode + SCC Console）
Gateway proxies/coordinates with:
- SCC upstream (default): `http://127.0.0.1:18789`
- OpenCode upstream (default): `http://127.0.0.1:18790`

The “single port” UX is: users hit `18788`, gateway forwards to upstreams where appropriate.

### 2.3 Unified Server（容器/单端口聚合 + 服务注册）
Code:
- `scc-top/tools/unified_server/main.py`
- `scc-top/tools/unified_server/services/executor_service.py`
- `scc-top/tools/unified_server/services/opencode_proxy_service.py`
- `scc-top/tools/unified_server/services/clawdbot_service.py`

Purpose:
- Provide a “unified server process” that can expose `/executor`, `/opencode`, `/clawdbot` etc from a single port (useful when SCC runs inside Docker and Windows-only executables need proxying).

备注：
- In this workspace, the **Node gateway** is the primary control-plane at `18788`; the unified server is an additional integration layer (especially for container setups).

### 2.4 Role System（角色权限 + 技能矩阵）
关键文件：
- `oc-scc-local/config/roles.json`
- `oc-scc-local/src/role_system.mjs`

要点：
- Gateway 在“创建任务”与“派发任务”两个阶段都做 role policy 校验（fail-closed）。
- Policy 以 read/write allowlist/denylist 为中心，叠加 skills 约束与“必须跑真实测试”的规则（避免只跑 `task_selftest` 走过场）。

### 2.4 Contracts (Machine-Verifiable Outputs)
Location:
- `contracts/**`

Key ideas:
- Executor output must include a strict JSON `SUBMIT` line plus report/evidence pointers (see `docs/EXECUTOR.md`).
- Gates verify artifact presence + schema validity + hygiene (see below).

### 2.5 Gates (Verification / Policy Enforcement)
Entry:
- `tools/scc/gates/run_ci_gates.py`

Notable gates:
- Contracts gate: required artifacts exist + match schema (`tools/scc/gates/contracts_gate.py`)
- Event gate: each task has `events.jsonl` with success/fail (`tools/scc/gates/event_gate.py`)
- Secrets gate: blocks plaintext secrets/tokens (`tools/scc/gates/secrets_gate.py`, see `docs/SECURITY_SECRETS.md`)
- SSOT / SSOT-map gates: governance checks around SSOT registry and map linkage
- Map/schema/doclink/release gates: repo hygiene + documentation integrity

Artifacts:
- Verdict output: `artifacts/<task_id>/verdict.json` (schema in `contracts/verdict/*`)

### 2.6 Factory Policy (Backpressure / Degradation / Circuit Breakers)
Policy file:
- `factory_policy.json`

Controls:
- WIP limits (exec/batch, internal/external)
- Lanes + priorities (fastlane/mainlane/batchlane/dlq/quarantine)
- Budgets (max children, max depth, token budget, verify minutes)
- Event routing (e.g. `CI_FAILED` -> fastlane -> fixup roles)
- Circuit breakers + degradation matrix (stop-the-bleeding modes)

## 3. Core Design Principles (What SCC Optimizes For)

### 3.1 “Atomic Only” Execution Contract (Fail-Closed)
Doc:
- `docs/EXECUTOR.md`

Executor tasks are treated as pure-ish functions:
- Inputs: pins JSON + minimal context pack + explicit tests/acceptance
- Outputs: machine-parsable report + strict `SUBMIT` JSON + evidence paths
- Forbidden: repo-wide scanning, reading SSOT directly, inventing context when pins are missing

### 3.2 Pins-First Minimal Context (Token/Latency Control)
Doc:
- `docs/AI_CONTEXT.md`

Constraints:
- Prefer 3-10 key files
- Never dump directories or huge logs into context packs
- If pins are missing/insufficient: fail with `PINS_INSUFFICIENT` (no guessing)

### 3.3 Evidence-First + Replayability
Mechanisms:
- Append-only-ish logs (`artifacts/executor_logs/*.jsonl`)
- Per-task artifacts: `artifacts/<task_id>/*`
- Replay endpoint: `/replay/task?task_id=...` (see `docs/NAVIGATION.md`)

Goal:
- Any “verdict” should be explainable from artifacts and gates, not from chat history.

## 4. End-to-End Flow (From Parent Goal To Verified Outcome)

### 4.1 Task Intake (Board)
Typical lifecycle:
1. Create a parent task (often broad scope)
2. Parent enters `needs_split`
3. A split/planner job runs, producing a JSON array of child tasks
4. Gateway applies split output, creating many atomic child tasks

Gateway endpoints:
- `POST /board/tasks`
- `POST /board/tasks/:id/split`
- `POST /board/tasks/:id/dispatch`

### 4.2 Split Output Contract (Planner -> Atomic Children)
Implementation:
- `oc-scc-local/src/gateway.mjs` `applySplitFromJob(...)`

Child task minimum schema (practically enforced):
- `title`, `goal`
- `files[]` (explicit touch set)
- `allowedTests[]` (must include at least one “real” test, not only `task_selftest`)
- `pins.allowed_paths[]` (must be non-empty)
- Optional: `allowedExecutors[]`, `allowedModels[]`, `skills[]`, `pointers`, `task_class_*`, `contract`, `runner`, `lane`

Routing default (important):
- If the planner doesn’t specify `allowedExecutors`, SCC defaults split children to `["opencodecli","codex"]` so strong models (e.g. `kimi-k2.5`) can implement first, with fallback to Codex.

### 4.3 Dispatch (Executor + Model Choice)
Dispatch decision uses:
- Role policy: allowed paths/tools/skills constraints (fail-closed)
- Pins/preflight readiness: if missing pins, task blocks/fails instead of guessing
- WIP/backpressure: factory policy + degradation action
- Executor availability: internal/external concurrency, fuses
- Model pools: free/vision pools + preferred order

Key logic:
- `pickExecutorForTask(...)`
- `pickOccliModelForTask(...)` / `pickCodexModelForTask(...)`

### 4.4 Execution (Atomic Job)
Executors:
- `opencodecli` (OpenCode CLI, often wired to OpenRouter free/paid models)
- `codex` (Codex CLI models)

Executor contract outputs (must appear in stdout):
- `REPORT: ...`
- `SELFTEST.LOG: ...`
- `EVIDENCE: ...`
- `SUBMIT: { ... strict JSON ... }`

If occli task finishes without `SUBMIT` and `OCCLI_REQUIRE_SUBMIT=true`, SCC fails it (fail-closed).

### 4.5 Verification + Verdict
Gates:
- `python tools/scc/gates/run_ci_gates.py ...`

Output:
- `artifacts/<task_id>/verdict.json`
- plus supporting audit artifacts (e.g. backfills in non-strict mode)

### 4.6 Requeue/Recovery Loops
There are multiple controlled requeue paths:
- Timeout requeue (bounded)
- Tooling fallback (occli instability -> retry via codex) (bounded)
- Pins fixup loop (pins failures -> pins_fixup task -> requeue source)
- CI fixup loop (CI failures -> ci_fixup task -> requeue source)
- Model ladder requeue (throttle/auth -> advance model ladder) (bounded)

DLQ behavior:
- `NEED_INPUT` failures go directly to `dlq` with a missing-inputs list.

### 4.7 状态机速览（Taskboard/Job）
Task（board task）常见字段（概念层面）：
- 身份与结构：`id`, `parentId`, `kind`(atomic/...), `task_class_id`
- 执行约束：`role`, `skills`, `allowedExecutors`, `allowedModels`, `files`, `pins`, `allowedTests`, `contract`
- 调度属性：`lane`, `priority`, `runner`(internal/external), `timeoutMs`, `cooldownUntil`
- 过程记录：`status`, `lastJobId`, `lastJobReason`, `dispatch_attempts`, 以及各类 bounded retry 计数（timeout/tooling/pins/ci/...）

Task 状态（高频）：
- `ready` -> 可派发
- `in_progress` -> 已派发且有 active job
- `blocked` -> pins 两阶段生成中或缺关键前置
- `needs_split` -> 需要拆分
- `done` / `failed` -> 终态（`failed` 可能进入 `dlq` 或 `quarantine` lanes）

Job（执行作业）常见字段（概念层面）：
- `executor`(codex/opencodecli), `model`, `runner`(internal/external), `status`(queued/running/done/failed), `reason`
- 产物：stdout/stderr + `submit` 解析结果（SUBMIT JSON）

## 5. Routing: Strong-to-Weak Model Ladder (Paid + Free Pools)

### 5.1 Model Sources You’ve Integrated
You collected model availability from:
- Codex CLI (paid models via your GPT Pro login)
- OpenCode CLI local cache (`~/.cache/opencode/models.json`)
- OpenRouter (free and paid models; OpenClaw gateway can proxy it via `clawdbot`)

Normalized registry outputs are in:
- `artifacts/model_registry/*.json` (see `docs/MODEL_REGISTRY.md`)

### 5.2 Runtime Model Pools (Gateway)
Configured in:
- `oc-scc-local/config/runtime.env`

Important keys:
- `MODEL_POOL_FREE` / `MODEL_POOL_VISION` (opencode model ids)
- `CODEX_MODEL_PREFERRED` + `MODEL_POOL_PAID`
- `AUTO_ASSIGN_OPENCODE_MODELS=true`

### 5.3 Strong-to-Weak Routing Behavior (occli)
Implementation:
- `oc-scc-local/src/gateway.mjs`

Features:
- Pools are auto-sorted strong -> weak using a heuristic “strength score”
  - Hard preference for `kimi-k2.5` when present
  - Tie-break using estimated parameter count tokens like `70B`, `27B` when present in model ids
- `MODEL_ROUTING_MODE`:
  - `rr`: round-robin within the chosen pool
  - `strong_first`: always select the strongest model in the pool
  - `ladder`: per-task ladder; uses `task.modelAttempt` to step strong -> weaker on requeues
- Auto requeue on model throttle/auth failures:
  - `AUTO_REQUEUE_MODEL_FAILURES=true`
  - `AUTO_REQUEUE_MODEL_FAIL_MAX` bounds how many “ladder advances” a task can perform
  - `AUTO_REQUEUE_MODEL_FAIL_COOLDOWN_MS` adds a cooldown to avoid immediate hammering

This matches your intent: “subtasks should be implemented by better models first; degrade only when needed; try to spend token budget wisely.”

## 6. Observability + Operability (What You Can Inspect Today)

### 6.1 Primary Logs/Artifacts
- `artifacts/executor_logs/jobs.jsonl` (job timeline)
- `artifacts/executor_logs/failures.jsonl` (failures)
- `artifacts/executor_logs/route_decisions.jsonl` (routing evidence)
- `artifacts/executor_logs/state_events.jsonl` (structured SCC events)
- `artifacts/<task_id>/...` (task-local artifacts: submit/verdict/preflight/pins/replay bundle, etc.)

### 6.2 Debug/Control Endpoints
See `docs/NAVIGATION.md`, especially:
- `/executor/debug/*`
- `/routes/decisions`
- `/events`
- `/verdict?task_id=...`
- `/replay/task?task_id=...`
- `/factory/*` (policy/WIP/degradation/health)

### 6.3 自动化 Hook（“工厂化”闭环的雏形）
从 `oc-scc-local/config/runtime.env` 与 gateway 行为可见，系统已经具备一批“自触发”的控制平面任务（多为 rate-limited）：
- `LEARNED_PATTERNS_*`: 汇总失败模式并产出 patterns summary，触发 `factory_manager` 类任务做治理
- `TOKEN_CFO_*`: 检测上下文浪费（included vs used）并触发优化建议
- `FIVE_WHYS_*`: 失败增量达到阈值时自动生成复盘报告并建议对策
- `RADIUS_AUDIT_*`: 检测 scope 扩张/越权倾向并触发审计
- `INSTINCT_*`: 从历史失败与 state events 生成 playbooks/skills drafts（可作为“系统自我改进素材”）

这些 Hook 目前更接近“可观测 + 建议生成”；若要向大厂 agent 平台靠拢，下一步通常是把它们纳入更严格的 ledger 与评测体系（见第 9 节）。

## 7. Governance + Security Posture

### 7.1 Secrets
Doc:
- `docs/SECURITY_SECRETS.md`

Policy:
- plaintext secrets are forbidden in repo
- encrypted containers allowed under `.scc_secrets/*.secrets.enc.json`
- gates block common secret patterns

### 7.2 SSOT / “Single Entry” Docs Discipline
Docs:
- `docs/INDEX.md`
- `scc-top/docs/START_HERE.md` (SSOT trunk conventions)

Rule of thumb:
- Executors do not read SSOT directly; SSOT is for control-plane roles and deterministic tooling.

## 8. Comparison Against Big-Tech Agent Platforms (Strengths / Gaps)

This section maps SCC to the shared 2024-2026 direction you summarized:
multi-agent orchestration, ledger/state machines, MCP/A2A standardization, context/tool explosion mitigation, observability/evals.

### 8.1 Where SCC Is Already Strong
- Fail-closed execution contract with machine-verifiable `SUBMIT` and gate-driven verdicts
- Pins-first minimal context discipline (token control + safety via allowlists)
- Clear control-plane endpoints: routing decisions + replay + policy introspection
- Factory policy as a first-class artifact: WIP limits, lanes, budgets, circuit breakers, degradation
- Evidence artifacts stored on disk (debuggable without “trust me” chat history)
- Multi-executor architecture (codex + opencodecli) plus proxies (unified server for Docker)

Relative advantage vs “agent chat frameworks” (e.g. early AutoGen-like groupchat):
- SCC is more production-leaning: explicit contracts, gates, fail-closed, replay, and backpressure.

### 8.2 Where SCC Is Behind Or Has Clear Enhancement Room
- Ledger depth: SCC now emits a minimal `task_ledger.json` + `progress_ledger.json` (+ `progress_events.jsonl`) per parent task (MVP stall counter + usage/budgets), but does not yet drive full re-planning off the ledger.
- Evaluation harness: gates exist and `eval_replay.py` provides offline shape + replay-smoke for playbook drafts, but systematic offline evals for router/model/prompt changes are not yet first-class.
- Connector governance: SCC now has a typed `connectors/registry.json` plus CI gate validation, but dispatch-time enforcement (connector selection constraints per role) is still shallow.
- Shared context/memory: SCC now has a read-only `semantic_context/` layer plus CI gate validation, but it is not yet integrated into context assembly as a governed first-class input.
- Model capability tagging: model routing uses heuristics; it does not yet route by explicit capabilities with measured success rates per task class.
- Budget-based routing: factory_policy budgets are now enforced as hard stops at dispatch time (root-parent budget exhaustion blocks new child dispatch), but CFO-grade accounting and per-task-class budgeting are still incomplete.

## 9. Concrete Enhancement Backlog (Prioritized)

### 9.1 Reliability / “Don’t Get Stuck”
1. Add an explicit progress ledger per parent task: states, next action, stall detection, retry reasons.
2. Standardize requeue reasons into a taxonomy (already partially present) and drive routing from it deterministically.
3. Add idempotent “handoff bundles” per atomic task: inputs + pins + context hash + tool versions, enabling deterministic replay.

### 9.2 Cost / Token Efficiency
1. Per-task and per-tree token budgets enforced at dispatch time (hard stops + degrade lanes).
2. Route by “task class difficulty” and model capability tags, not only by pool order/heuristics.
3. Add automatic context-pack minimization metrics into gate/verdict (unused context ratio -> fail or warn).

### 9.3 Observability / Evals
1. First-class traces: timeline of (plan -> pins -> preflight -> dispatch -> execute -> gates -> verdict), exportable as a single JSON trace.
2. Offline eval suite: fixed tasks + golden verdicts; run on model/router changes; track success rate/time/token.
3. Decision explanation artifacts: why a task got a given executor/model, with the exact config snapshot and pool ordering.

### 9.4 Standardization / Ecosystem Fit
1. Align tool definitions toward MCP-style interfaces where feasible, so connectors don’t become one-off glue.
2. Optional A2A-style agent-to-agent protocol support for cross-runtime collaboration (if SCC wants to interop with other agent stacks).

## 10. Reviewer Prompt (Give This To gpt-5.2)

Use the following reviewer instructions when auditing SCC:

1. Identify the top 10 failure modes this system is most exposed to (stalls, loops, silent policy bypass, missing evidence, unsafe writes).
2. For each failure mode, cite which component should own mitigation (gateway, executor, gates, policy, docs/SSOT).
3. Evaluate whether the current contracts (pins/preflight/SUBMIT/verdict) are sufficient to make outcomes replayable and auditable.
4. Evaluate the routing strategy (executor selection + strong-to-weak ladder) for:
   - correctness (no accidental downgrade/upgrade)
   - cost control
   - fairness under throttling
   - loop prevention
5. Propose a minimal “ledger + stall detection” design that fits SCC’s current artifacts/logs.
6. Propose an eval plan: what to measure, where to log it, and what the CI gates should enforce.

Appendix: key entry docs
- `docs/INDEX.md`
- `docs/NAVIGATION.md`
- `docs/AI_CONTEXT.md`
- `docs/EXECUTOR.md`
- `docs/MODEL_REGISTRY.md`
- `factory_policy.json`
