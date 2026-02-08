# oc-scc-local

本项目是 **本地使用** 的统一入口网关：在 `http://127.0.0.1:18788` 下同时提供：

- **SCC**：`/desktop`、`/scc`、`/dashboard`、`/viewer`、`/client-config`、`/mcp/*`（反代到 SCC：默认 `http://127.0.0.1:18789`）
- **OpenCode**：`/opencode/*`（反代到 OpenCode server：默认 `http://127.0.0.1:18790`）

目标：尽量不修改 OpenCode 源码，只通过独立网关项目实现“深度融合”的本地体验，并提供一个可并行的 CLI 执行器（codexcli + opencodecli）。

## 快速启动

```powershell
cd C:\scc\oc-scc-local
.\scripts\start-all.ps1
```

打开：
- `http://127.0.0.1:18788/`（网关首页 / 状态）
- `http://127.0.0.1:18788/desktop`（SCC）
- `http://127.0.0.1:18788/opencode/global/health`（OpenCode 健康检查）

停止：
```powershell
cd C:\scc\oc-scc-local
.\scripts\stop-all.ps1
```

## 并行执行器（队长一个日志）

网关暴露了执行器接口，用于“队长分发 -> 多 CLI 并行 -> 队长只看一个日志”：

- 健康检查：
  - `GET /executor/codex/health`
  - `GET /executor/opencodecli/health`
- 原子任务（推荐，强约束避免扫仓库 + 默认 10min/15min 超时）：
  - `POST /executor/jobs/atomic`
- 队长总览（最近 200 条）：
  - `GET /executor/leader`
  - `GET /executor/debug/summary`
  - `GET /executor/debug/failures`

日志落盘（JSONL）：
- `C:\scc\artifacts\executor_logs\leader.jsonl`（队长日志）
- `C:\scc\artifacts\executor_logs\jobs.jsonl`
- `C:\scc\artifacts\executor_logs\failures.jsonl`
- `C:\scc\artifacts\executor_logs\jobs_state.json`（断电/重启恢复）

## 端口与上游

- 网关：`18788`
- SCC（Docker 映射到宿主机）：`18789`（容器内 SCC 仍是 18788）
- OpenCode upstream：`18790`

可通过环境变量覆盖：
- `GATEWAY_PORT`（默认 `18788`）
- `SCC_UPSTREAM`（默认 `http://127.0.0.1:18789`）
- `OPENCODE_UPSTREAM`（默认 `http://127.0.0.1:18790`）
- `EXEC_CONCURRENCY_CODEX`（默认 `10`）
- `EXEC_CONCURRENCY_OPENCODE`（默认 `2`）

## 功能开关

复制 `config/features.sample.json` 为 `config/features.json`，按需开关：
- `exposeScc` / `exposeOpenCode`
- `exposeSccMcp`（SCC `/mcp`）
- `exposeOpenCodeUi` / `exposeOpenCodeApi`

