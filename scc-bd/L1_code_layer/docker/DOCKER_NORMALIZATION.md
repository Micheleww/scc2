# Docker 归一化文档

> 所属层级: L1 代码层 (L1_code_layer)  
> 功能分类: Docker 部署配置  
> 创建日期: 2026-02-10  
> 版本: 1.0.0

---

## 1. 概述

本文档记录 SCC 项目的 Docker 配置归一化过程，确保 Docker 配置的唯一性和标准化。

---

## 2. 归一化原则

### 2.1 单一真相源 (Single Source of Truth)

- **唯一的 Dockerfile**: `docker/Dockerfile`
- **唯一的 docker-compose.yml**: `docker/docker-compose.yml`
- **唯一的构建脚本**: `scripts/build-docker.bat`

### 2.2 禁止行为

- ❌ 禁止在其他位置创建 Dockerfile
- ❌ 禁止在其他位置创建 docker-compose.yml
- ❌ 禁止手动运行 `docker build` 命令
- ❌ 禁止使用非标准镜像名称

---

## 3. 镜像命名规范

### 3.1 标准格式

```
scc:<version>
```

### 3.2 版本标签规则

| 标签类型 | 格式示例 | 使用场景 |
|---------|---------|---------|
| **latest** | `scc:latest` | 开发/测试环境 |
| **语义版本** | `scc:1.0.0` | 生产环境 |
| **日期版本** | `scc:20260210` | 特殊构建 |

---

## 4. 目录结构

```
c:\scc\
├── docker\
│   ├── Dockerfile              # 唯一的 Dockerfile
│   ├── docker-compose.yml      # 唯一的编排文件
│   ├── VERSION_POLICY.md       # 版本管理规范
│   ├── BUILD_GUIDE.md          # 构建指南
│   └── entrypoint.sh           # 入口脚本
├── scripts\
│   └── build-docker.bat        # 统一构建脚本
└── backups\
    └── scc_backup.tar.gz       # 数据备份
```

---

## 5. 基础镜像选择

### 5.1 当前使用

- **镜像**: `mcr.microsoft.com/mirror/docker/library/node:18-alpine`
- **原因**: 国内网络环境下可稳定访问
- **替代方案**: 网络恢复后可切换回 `node:18-alpine`

### 5.2 镜像特性

- 基于 Alpine Linux（轻量级）
- 包含 Node.js 18.x
- 已安装 Python 3.12
- 包含 curl、git、bash 等常用工具

---

## 6. 构建流程

### 6.1 标准构建命令

```batch
:: 构建 latest 版本
scripts\build-docker.bat

:: 构建指定版本
scripts\build-docker.bat 1.0.0

:: 构建并同时标记为 latest
scripts\build-docker.bat 1.0.0 latest
```

### 6.2 构建步骤

1. 安装系统依赖 (apk add)
2. 验证 Node.js 和 Python 版本
3. 复制 package.json 并安装 Node 依赖
4. 安装 Python 依赖 (pyyaml, jsonschema, requests)
5. 复制 17 层分层代码
6. 创建必要目录
7. 配置运行时环境变量

---

## 7. 部署流程

### 7.1 开发环境

```batch
cd c:\scc\docker
docker-compose up -d
```

### 7.2 生产环境

```batch
:: 1. 构建指定版本
scripts\build-docker.bat 1.0.0 latest

:: 2. 部署
cd c:\scc\docker
docker-compose down
docker-compose up -d
```

---

## 8. 容器配置

### 8.1 服务配置

```yaml
container_name: scc-server
image: scc:latest
ports:
  - "18788:18788"
restart: unless-stopped
```

### 8.2 数据卷

- `scc_artifacts` - 构建产物
- `scc_data` - 应用数据
- `scc_logs` - 日志文件
- `scc_state` - 状态数据

### 8.3 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `GATEWAY_PORT` | 18788 | 网关端口 |
| `LOG_LEVEL` | info | 日志级别 |
| `OPENCODE_UPSTREAM` | http://host.docker.internal:18790 | OpenCode 上游 |
| `CLAWDBOT_UPSTREAM` | http://host.docker.internal:19001 | Clawdbot 上游 |

---

## 9. 健康检查

```dockerfile
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=30s \
    CMD curl -f http://127.0.0.1:18788/health || exit 1
```

---

## 10. 故障排除

### 10.1 容器无法启动

```batch
:: 查看日志
docker logs scc-server

:: 检查配置
docker-compose config

:: 重新构建
docker-compose down
docker-compose up -d --build
```

### 10.2 网络连接问题

如果无法拉取基础镜像：

1. 检查网络连接
2. 配置 Docker 使用国内镜像源
3. 使用 Microsoft Container Registry 镜像

---

## 11. 相关文档

- [VERSION_POLICY.md](./VERSION_POLICY.md) - 版本管理规范
- [BUILD_GUIDE.md](./BUILD_GUIDE.md) - 构建指南
- [LAYER_MAPPING.md](../../LAYER_MAPPING.md) - 分层映射文档

---

## 12. 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-02-10 | 1.0.0 | 初始版本，完成 Docker 归一化 |
