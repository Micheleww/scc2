---
oid: <MINT_WITH_SCC_OID_GENERATOR>
layer: RUNBOOK
primary_unit: S.NAV_UPDATE
tags: [V.GUARD]
status: active
---

# Docker 本地运行（SCC / Unified Server）

目标：只在本机访问，**对外只暴露 18788**，所有运行时数据通过 Docker volumes 持久化，并提供一键备份/恢复闭环。

## 启动

推荐入口（用户级）：一键启动 + 自动打开桌面入口页：

```powershell
cd <REPO_ROOT>
tools\scc\sccctl.cmd desktop
```

Dev（一键，3 秒内出页面）：先打开本地 `dev.html`，后台自动维护 Docker 并拉起服务，然后页面会自动变绿：

```powershell
cd <REPO_ROOT>
tools\scc\dev.cmd
```

构建上下文（离线 wheelhouse + 最小运行树）：

```powershell
cd <REPO_ROOT>
tools\unified_server\docker\stage_context.cmd
```

启动服务：

```powershell
docker compose -f docker-compose.scc.yml up -d --build
```

## 访问

- 入口：`http://127.0.0.1:18788/`
- 桌面入口页：`http://127.0.0.1:18788/desktop`
- 就绪：`http://127.0.0.1:18788/health/ready`
- MCP：`http://127.0.0.1:18788/mcp`
- SCC：`http://127.0.0.1:18788/scc`

## 数据持久化（全部）

Docker volumes 覆盖以下写盘点（容器可重建、数据不丢）：
- `/app/artifacts`
- `/app/data`
- `/app/logs`
- `/app/tools/unified_server/state`
- `/app/tools/unified_server/logs`
- `/app/tools/mcp_bus/_state`

## 备份

将 volumes 打包输出到宿主机目录 `./_backups/`：

```powershell
docker compose -f docker-compose.scc.yml run --rm --profile ops scc-backup
```

输出包含：
- `scc_backup_YYYYMMDD_HHMMSS.tar.gz`
- `scc_backup_YYYYMMDD_HHMMSS.manifest.json`

## 恢复

恢复前先停止服务：

```powershell
docker compose -f docker-compose.scc.yml down
```

指定要恢复的备份文件名（位于 `./_backups/`）并执行：

```powershell
$env:SCC_RESTORE_FILE = "scc_backup_YYYYMMDD_HHMMSS.tar.gz"
docker compose -f docker-compose.scc.yml run --rm --profile ops scc-restore
```

## 排障

查看容器状态与日志：

```powershell
docker compose -f docker-compose.scc.yml ps
docker compose -f docker-compose.scc.yml logs -f --tail 200 scc-server
docker compose -f docker-compose.scc.yml logs -f --tail 200 scc-daemon
```

如果 `/health/ready` 返回 503：
- 先看返回体里的 `services`（服务 readiness）
- 再看 `persistence.checks` 与 `persistence.disk`（持久化目录是否可写 / 磁盘空间是否足够）

## 全链路冒烟测试（桌面入口）

```powershell
cd <REPO_ROOT>
powershell -NoProfile -ExecutionPolicy Bypass -File tools\scc\ops\desktop_e2e_smoke.ps1
```
