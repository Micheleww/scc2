# SCC Docker 部署指南

## 概述

本文档介绍如何使用 Docker 部署完整的 SCC 系统，包括：
- **SCC OLT CLI** - OpenCode LLM Tool CLI 服务 (Port 3458)
- **SCC Backend** - SCC 后端网关 (Port 18788)
- **SCC Daemon** - 后台任务处理器 (可选)

## 为什么使用 Docker？

| 优势 | 说明 |
|------|------|
| **环境一致性** | 开发/测试/生产环境完全一致 |
| **依赖隔离** | 所有依赖打包在镜像内，不受宿主机影响 |
| **快速部署** | 一条命令启动所有服务 |
| **易于维护** | 版本化管理，可快速回滚 |
| **资源控制** | 可限制 CPU/内存使用 |
| **自动恢复** | 服务崩溃后自动重启 |

## 前置要求

- Docker Desktop 或 Docker Engine 20.10+
- Docker Compose 2.0+
- 至少 4GB 可用内存
- 10GB 可用磁盘空间

## 快速开始

### 1. 构建镜像

```bash
# 构建所有镜像
docker-compose -f docker-compose.full.yml build

# 或者使用启动脚本
cd docker
start-docker.bat
# 然后选择 [1] 基础服务
```

### 2. 启动服务

```bash
# 启动基础服务 (OLT CLI + SCC Backend)
docker-compose -f docker-compose.full.yml up -d

# 启动完整服务 (包含 Daemon)
docker-compose -f docker-compose.full.yml --profile with-daemon up -d

# 仅启动 OLT CLI
docker-compose -f docker-compose.full.yml up -d scc-olt-cli
```

### 3. 验证服务

```bash
# 查看运行状态
docker-compose -f docker-compose.full.yml ps

# 测试 OLT CLI
curl http://localhost:3458/api/health

# 测试 SCC Backend
curl http://localhost:18788/health
```

## 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                          │
│                    (scc-network)                            │
│                                                             │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │   scc-olt-cli    │        │     scc-bd       │          │
│  │   (Port 3458)    │◄──────►│  (Port 18788)    │          │
│  │                  │        │                  │          │
│  │ - OLT CLI API    │        │ - Gateway        │          │
│  │ - Chat Completion│        │ - Router         │          │
│  │ - Tool Execution │        │ - Plugins        │          │
│  └──────────────────┘        └──────────────────┘          │
│           ▲                           ▲                     │
│           │                           │                     │
│           └──────────┬────────────────┘                     │
│                      │                                      │
│                 ┌────┴────┐                                 │
│                 │  Host   │                                 │
│                 │ Machine │                                 │
│                 └─────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCC_OLT_CLI_PORT` | 3458 | OLT CLI 服务端口 |
| `SCC_BD_PORT` | 18788 | SCC Backend 端口 |
| `LOG_LEVEL` | info | 日志级别 |
| `NODE_ENV` | production | 运行环境 |

### 数据卷

| 卷名 | 用途 | 挂载点 |
|------|------|--------|
| `scc_olt_logs` | OLT CLI 日志 | /app/logs |
| `scc_olt_data` | OLT CLI 数据 | /app/data |
| `scc_artifacts` | SCC 构建产物 | /app/artifacts |
| `scc_data` | SCC 数据 | /app/data |
| `scc_logs` | SCC 日志 | /app/logs |
| `scc_state` | SCC 状态 | /app/state |

## 常用命令

```bash
# 查看日志
docker-compose -f docker-compose.full.yml logs -f

# 查看特定服务日志
docker-compose -f docker-compose.full.yml logs -f scc-olt-cli

# 重启服务
docker-compose -f docker-compose.full.yml restart

# 停止服务
docker-compose -f docker-compose.full.yml down

# 停止并删除数据卷
docker-compose -f docker-compose.full.yml down -v

# 进入容器
docker exec -it scc-olt-cli sh
docker exec -it scc-bd sh

# 更新镜像
docker-compose -f docker-compose.full.yml pull
docker-compose -f docker-compose.full.yml up -d
```

## API 端点

### OLT CLI (Port 3458)

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/olt-cli/models` | 模型列表 |
| POST | `/api/olt-cli/chat/completions` | 聊天完成 |
| POST | `/api/olt-cli/execute` | 执行带工具的对话 |

### SCC Backend (Port 18788)

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/status` | 系统状态 |

## 故障排除

### 服务无法启动

```bash
# 检查日志
docker-compose -f docker-compose.full.yml logs

# 检查端口占用
netstat -ano | findstr :3458
netstat -ano | findstr :18788
```

### 容器崩溃重启

```bash
# 查看重启次数
docker-compose -f docker-compose.full.yml ps

# 查看崩溃日志
docker-compose -f docker-compose.full.yml logs --tail=100 scc-olt-cli
```

### 网络问题

```bash
# 检查网络
docker network ls
docker network inspect scc-bd_scc-network

# 测试容器间通信
docker exec scc-bd ping scc-olt-cli
```

## 性能优化

### 资源限制

在 `docker-compose.full.yml` 中添加资源限制：

```yaml
services:
  scc-olt-cli:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 日志轮转

已配置自动日志轮转，保留 5 个文件，每个最大 10MB。

## 安全建议

1. **不要在生产环境使用默认端口映射**
2. **启用防火墙限制访问**
3. **定期更新基础镜像**
4. **使用 Docker Secrets 管理敏感信息**

## 更新日志

- **2026-02-10** - 初始版本，包含 OLT CLI 和 SCC Backend

## 相关文档

- [OLT CLI 文档](../L6_execution_layer/docs/olt_cli.md)
- [Trae Executor 文档](../L6_execution_layer/docs/trae_executor_v2.md)
- [SCC Backend README](../L1_code_layer/README.md)
