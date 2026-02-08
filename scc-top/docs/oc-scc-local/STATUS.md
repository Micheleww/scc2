# 当前状态（2026-02-04）

## 统一入口与端口

- 统一入口网关：`http://127.0.0.1:18788`
- SCC（Docker 映射宿主机）：`http://127.0.0.1:18789`（容器内 SCC 仍为 18788）
- OpenCode upstream：`http://127.0.0.1:18790`（通过网关挂载到 `/opencode/*`）

## 并行（建议配置）
- worker 比例（当前实验）：codex:occli = 4:6（更多任务交给免费模型）
- 外部 worker 全局并发上限：`EXTERNAL_MAX_CODEX=4`、`EXTERNAL_MAX_OPENCODECLI=6`
- 无需人工监控：可运行 `C:\scc\oc-scc-local\scripts\ensure-workers.ps1` 自动补 worker
- 配置入口：`GET http://127.0.0.1:18788/config`、`POST http://127.0.0.1:18788/config/set`（写入 `C:\scc\oc-scc-local\config\runtime.env`；重启 daemon 生效）
- 超时自动再入队（默认开启）：`AUTO_REQUEUE_TIMEOUT=true`、`AUTO_REQUEUE_TIMEOUT_MAX=3`、`AUTO_REQUEUE_TIMEOUT_COOLDOWN_MS=60000`

## 无窗口后台运行（完全无感）

如果你希望 **无任务栏窗口、无托盘角标**，用隐藏窗口的 VBS 启动脚本（不需要安装服务/不需要计划任务）：

- 启动：`C:\scc\oc-scc-local\scripts\daemon-start.vbs`
- 停止：`C:\scc\oc-scc-local\scripts\daemon-stop.vbs`

日志与 PID 文件落盘在：
- `C:\scc\artifacts\executor_logs\gateway.out.log`
- `C:\scc\artifacts\executor_logs\gateway.err.log`
- `C:\scc\artifacts\executor_logs\ensure-workers.out.log`
- `C:\scc\artifacts\executor_logs\ensure-workers.err.log`
- `C:\scc\artifacts\executor_logs\gateway.pid`
- `C:\scc\artifacts\executor_logs\ensure-workers.pid`

## 队长并行执行器（已落地）

网关（`C:\scc\oc-scc-local`）提供执行器 API + 队长单日志：

- 任务提交：
  - 推荐：`POST /executor/jobs/atomic`（自动打包上下文、限制扫仓库、默认 20min/20min 超时；卡壳用 cancel/requeue）
  - 兼容：`POST /executor/jobs`（手动指定 prompt + contextPackId/threadId）
- 任务查询：
  - `GET /executor/jobs`
  - `GET /executor/jobs/:id`
  - `GET /executor/jobs/:id/patch`（从 stdout 提取 `*** Begin Patch`，并尝试反转义 `\\n`）
  - `POST /executor/jobs/:id/cancel`（队长人工取消 external job）
  - `POST /executor/jobs/:id/requeue`（队长人工重排 external job）
- 队长日志：
  - `GET /executor/leader`（最近 200 条）
  - `GET /executor/debug/summary`
  - `GET /executor/debug/failures`

落盘位置：
- `C:\scc\artifacts\executor_logs\leader.jsonl`
- `C:\scc\artifacts\executor_logs\jobs.jsonl`
- `C:\scc\artifacts\executor_logs\failures.jsonl`
- `C:\scc\artifacts\executor_logs\jobs_state.json`（重启恢复）

## 已知失败原因（已纳入队长日志）

1) **timeout**
   - 根因：CLI 任务过大/扫描仓库/读大量文件导致超过默认超时。
   - 处理：引入原子任务 `/executor/jobs/atomic` + 限制读取文件数量；默认超时提高到 20min；明显卡壳时用 cancel/requeue。

2) **occli BunInstallFailedError / plugin 404**
   - 根因：`C:\scc\opencode.json` 中存在插件 `opencode-workspace`，npm 404 会触发 bun 安装失败。
   - 处理：执行器运行 occli 时禁用项目配置（`OPENCODE_DISABLE_PROJECT_CONFIG=true` + 注入空 plugin 配置）。

3) **PowerShell 命令拼接**
   - 根因：某些环境 PowerShell 不支持 `&&` 作为连接符。
   - 处理：统一用 `;` 或 `cmd /c` 链接命令。

## 当前融合推进（进行中）

- 已提交的 B 批子任务：`C:\scc\submit_jobs_B.ps1`
- 结果以 `GET /executor/leader` 与 `C:\scc\artifacts\executor_logs\jobs.jsonl` 为准。

注意：部分 CLI 返回的是“摘要/文件变更意图”而非可直接应用的 diff。
队长侧策略：强制要求输出 `*** Begin Patch ...`（或统一 diff），否则判定为未完成并重跑。

## 约束：父任务拆解模型（强制）

- 父任务（role=`designer`）执行“拆解(split)”时，模型必须为 `gpt-5.2`（强约束）。
- 若本机 CLI 不支持该模型，会直接失败并记录到队长日志；需要在 CLI 侧补齐模型可用性后再继续。
