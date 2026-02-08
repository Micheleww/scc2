# 队长并行执行器

## 目标

- 单个 CLI 子任务尽量在 **10 分钟内完成**
- 任务失败必须有明确 `reason` 并落盘
- 队长只看一个入口与一个日志就能掌握全局
- Executor **禁止自由读仓**：默认使用 Pins JSON + 最小切片（降低读文件成本）

## 执行者硬约束（必须）
- 只能访问 pins 中列出的路径/符号/行窗
- 不允许读取未列出的文件；pins 不足直接失败并返回错误码
- 不复述需求、不重新设计、不输出建议
- 输出必须固定结构（见下方）

## API（网关：18788）

### 任务提交（推荐：原子任务）

`POST http://127.0.0.1:18788/executor/jobs/atomic`

Body：
```json
{
  "goal": "一句话+清晰交付物",
  "files": ["packages/opencode/src/server/server.ts"],
  "pins": {
    "allowed_paths": ["packages/opencode/src/server/server.ts"],
    "line_windows": { "packages/opencode/src/server/server.ts": [[120, 180]] }
  },
  "executor": "codex",
  "model": "gpt-5.1-codex-max",
  "timeoutMs": 600000,
  "taskType": "mcp_dedup"
}
```

## 输出结构（固定）

```
REPORT: <one-line outcome>
SELFTEST.LOG: <commands run or 'none'>
EVIDENCE: <paths or 'none'>
SUBMIT: {"status":"pass|fail","reason_code":"...","touched_files":[...],"tests_run":[...]}
```

约束（服务端会拒绝）：
- `goal` 太短/太长会被拒绝
- codex 任务默认必须带 `files`（避免扫仓库）；确需无上下文时显式传 `allowNoContext=true`
- `files` 数量最多 16；`maxBytes` 最多 400k

### 队长总览（一个日志）

- `GET /executor/leader`：最近 200 条队长事件（started/finished/long_running/failure_burst/contextpack_created…）
- `GET /executor/debug/summary`：失败原因按 reason / executor 聚合
- `GET /executor/debug/failures`：最近失败明细（200 条）

## 自动推进（减少“等待 running”）
队长不需要在聊天窗口里一直轮询 job 状态。推荐开一个后台 pump：

- `powershell -NoProfile -ExecutionPolicy Bypass -File C:\scc\oc-scc-local\scripts\pump-board.ps1`

它会：
- 父任务 split job done 后自动 `POST /board/tasks/:id/split/apply` 生成子任务
- 自动 `POST /board/tasks/:id/dispatch` 派发 ready/backlog 原子任务（每 tick 最多派发 6 个，默认 20s tick）

## 自动补充 worker（不监控也能跑满）
如果你不想盯着“running < 4”，可以后台运行自动补充脚本：

- `powershell -NoProfile -ExecutionPolicy Bypass -File C:\scc\oc-scc-local\scripts\ensure-workers.ps1`

默认目标：codex=4、occli=6，且当 running job 数 < 4 会优先补 codex worker。

（当前实验配置：codex=4、occli=6，用于对比不同免费模型的成功率；可在脚本顶部或用环境变量覆盖。）

## 无窗口后台运行（完全无感）

如果你希望 **无任务栏窗口、无托盘角标**，用隐藏窗口的 VBS 启动脚本（不需要安装服务/不需要计划任务）：

- 启动：`C:\scc\oc-scc-local\scripts\daemon-start.vbs`
- 停止：`C:\scc\oc-scc-local\scripts\daemon-stop.vbs`

查看是否正常运行：
- `http://127.0.0.1:18788/pools`
- `http://127.0.0.1:18788/board`

### 任务列表与详情

- `GET /executor/jobs`
- `GET /executor/jobs/:id`
- `GET /executor/jobs/:id/patch`：从 stdout 抽取 `*** Begin Patch`，并尝试把 `\\n` 反转义成真实换行

### 队长干预（取消 / 重新排队）
用于“明显卡壳/跑偏/重复逻辑/超出能力范围”等情况（不建议按超时一刀切）。
- `POST /executor/jobs/:id/cancel`：取消一个 external job
  - Body：`{ "reason": "string (optional)" }`
- `POST /executor/jobs/:id/requeue`：把 external job 重新排队（清空 stdout/stderr 并重置长跑提醒）
  - Body：`{ "reason": "string (optional)" }`

## Worker 模式（外部 CLI 自动认领）

用途：让多个 CLI 作为“工人”自动从队列认领任务，完成后回传结果，队长无需手动派发。

### 注册 / 列表

- `POST /executor/workers/register`：`{ name, executors: ["codex"|"opencodecli"] }`
- `GET /executor/workers`

### 认领（长轮询）

- `GET /executor/workers/:id/claim?executor=codex&waitMs=25000`

返回 200 时会带上 `prompt/model/taskType`；无任务时返回 204。

### 回传完成

- `POST /executor/jobs/:id/complete`：`{ workerId, exit_code, stdout, stderr }`

### 任务投递到 worker 队列

创建任务时把 `runner` 设为 `external`：
- `POST /executor/jobs` 或 `POST /executor/jobs/atomic` 增加 `runner: "external"`

## 角色（Role）约定

执行器/任务板支持 `role` 字段（主要用于把“同一目标”下的输出风格和交付物强约束成一致）。

当前内置 6 类角色：
- `designer`：只做拆解/接口/任务规格，要求输出结构化 JSON（便于队长导入子任务）
- `architect`：模块边界与迁移策略
- `integrator`：系统粘合与最小改动接入
- `engineer`：具体实现（patch/命令）
- `qa`：验收/冒烟/失败归因
- `doc`：文档/导航/手册

强约束：
- `designer` 的拆解（`/board/tasks/:id/split`）必须使用模型 `gpt-5.2`（由服务端校验）。

## Worker 预握手（避免领到不属于自己的任务）

Worker 注册时可上报可用模型列表（可选）：
- `POST /executor/workers/register`：`{ name, executors, models: ["gpt-5.1-codex-max","gpt-5.2"] }`

网关在 `claim` 时会按 `job.model` 过滤，未声明 `models` 则视为“都能跑”（不推荐）。

## 日志与持久化

日志目录：`C:\scc\artifacts\executor_logs`

- `leader.jsonl`：队长单日志
- `jobs.jsonl`：每个任务结束都会写一条（成功/失败）
- `failures.jsonl`：失败任务专用
- `jobs_state.json`：任务状态（重启后 running 会回到 queued 继续跑）
- `contextpacks/`：上下文包（markdown）
- `threads/`：线程历史（用于轻量“上下文重新注入”）

## 并行与超时建议

- 默认并行（网关 internal runner）：codex=10、occli=2（可通过环境变量覆盖）
- 默认超时：codex=20min、occli=20min（仅 internal runner 强制；external worker 由队长监控 + 人工 cancel/requeue）
- 外部 worker 全局并发上限（避免本机被打满）：`EXTERNAL_MAX_CODEX=7`、`EXTERNAL_MAX_OPENCODECLI=3`
- 推荐 worker 比例：codex:occli = **7:3**（仍建议用 `EXTERNAL_MAX_*` 保 CPU 不被打满）
- 队长提醒：
  - `job_long_running`：超过阈值只提醒一次
  - `failure_burst`：10 分钟内失败数 >= 3（可配置）
