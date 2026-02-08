# SCC/Unified Server Docker 部署（本地）

目标：把服务器运行形态收敛到 Docker Compose，实现“企业级”可维护性：
- `restart: unless-stopped`（崩溃自动拉起）
- `healthcheck`（ready 可观测）
- `logging` 轮转（不爆磁盘）
- `volumes` 持久化（`artifacts/` 不丢）

## 启动

1) 确保 Docker Desktop 已启动（Windows 托盘里 Docker 图标为运行状态）
2) 在仓库根目录执行：

```powershell
docker compose -f docker-compose.scc.yml up -d --build
```

说明：
- 默认暴露端口 `18788`。如果你想匹配 legacy navigation 里写的 `:8000`，用 `SCC_HOST_PORT=8000`：
  - `SCC_HOST_PORT=8000 docker compose -f docker-compose.scc.yml up -d --build`
- 离线安装依赖依赖 `_docker_ctx_scc/_wheelhouse`（通常用 `tools\\unified_server\\docker\\stage_context.cmd` 生成/更新构建上下文）。

## 查看状态

```powershell
docker compose -f docker-compose.scc.yml ps
docker compose -f docker-compose.scc.yml logs -f --tail 200 scc-server
docker compose -f docker-compose.scc.yml logs -f --tail 200 scc-daemon
```

## 停止

```powershell
docker compose -f docker-compose.scc.yml down
```

## 数据持久化（全部）

Docker 运行形态下，所有运行时写盘点统一落到 volumes：
- `/app/artifacts`（SCC state/tasks/runs 及各类运行产物）

## 与本地代码同步（镜像重建策略）

说明：当前 compose 形态默认 **不 bind-mount 源码**（以保证容器运行稳定、避免宿主机污染），因此本地对 `scc-top` 的代码改动不会自动进入容器；需要按策略重建镜像。

已落地的量化策略：
- 策略文件（可调）：`tools/unified_server/docker/build_stamp.json`
- 一键重建（按阈值判断是否需要重建）：`powershell -File tools/unified_server/docker/rebuild_if_needed.ps1`

默认阈值（可在 `build_stamp.json` 里调整）：
- commitsAhead ≥ 20
- filesChanged ≥ 120
- linesChanged ≥ 8000

重建发生后会写回：
- `lastBuiltCommit`：镜像对应的 git commit
- `lastBuiltAt`：UTC 时间戳
- `/app/data`（本地数据与轻量 DB；例如 chart configs）
- `/app/logs`（本地日志目录，stdout 之外的文件日志落点）
- `/app/tools/unified_server/state`（统一服务器状态/端口分配等）
- `/app/tools/unified_server/logs`（统一服务器文件日志落点）
- `/app/tools/mcp_bus/_state`（MCP/触发器等本地状态）

## 备份（推荐）

从 volumes 打包出一个 `tar.gz` + `manifest.json` 到宿主机目录 `./_backups/`：

```powershell
docker compose -f docker-compose.scc.yml run --rm --profile ops scc-backup
```

## 恢复（谨慎）

恢复前请先停掉服务：

```powershell
docker compose -f docker-compose.scc.yml down
```

然后设置要恢复的文件名（位于 `./_backups/`），执行恢复：

```powershell
$env:SCC_RESTORE_FILE = "scc_backup_YYYYMMDD_HHMMSS.tar.gz"
docker compose -f docker-compose.scc.yml run --rm --profile ops scc-restore
```

## 端口

- Host: `http://127.0.0.1:18788/`
- 健康检查：`/health/ready`
- SCC：`/scc`
