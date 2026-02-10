# SCC Docker 构建指南

> 版本: 1.0.0  
> 最后更新: 2026-02-10

---

## 当前状态

由于网络连接问题，无法从 Docker Hub 拉取基础镜像。以下是解决方案：

---

## 方案 1: 使用已有镜像（推荐）

如果您之前已经构建过 SCC 镜像，可以使用以下命令查看：

```bash
# 查看所有镜像
docker images

# 如果有 scc-unified:local 或其他镜像，可以直接使用
docker tag scc-unified:local scc:latest
```

---

## 方案 2: 从其他机器导出/导入镜像

### 在有网络的机器上

```bash
# 拉取基础镜像
docker pull node:18-bookworm

# 保存为 tar 文件
docker save -o node-18-bookworm.tar node:18-bookworm

# 如果有已构建的 scc 镜像，也一并导出
docker save -o scc-latest.tar scc:latest
```

### 复制到当前机器

```bash
# 复制 tar 文件到 c:\scc\images\ 目录

# 导入镜像
docker load -i node-18-bookworm.tar
docker load -i scc-latest.tar
```

---

## 方案 3: 使用 Docker Desktop 内置镜像

检查 Docker Desktop 是否缓存了基础镜像：

```bash
# 查看所有镜像（包括中间层）
docker images -a

# 搜索 node 相关镜像
docker images | grep node
```

---

## 方案 4: 配置代理（如果有代理服务器）

编辑 `C:\Users\<用户名>\.docker\config.json`：

```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://proxy.example.com:8080",
      "httpsProxy": "http://proxy.example.com:8080",
      "noProxy": "localhost,127.0.0.1"
    }
  }
}
```

---

## 方案 5: 使用替代基础镜像

如果无法获取 `node:18-bookworm`，可以尝试修改 Dockerfile 使用其他基础镜像：

### 修改 `docker/Dockerfile`

```dockerfile
# 原配置
# FROM node:18-bookworm

# 替代方案 1: 使用更小的 alpine 版本
FROM node:18-alpine

# 替代方案 2: 使用国内镜像源构建的镜像
# FROM registry.cn-hangzhou.aliyuncs.com/node:18-bookworm

# 替代方案 3: 使用 Ubuntu 基础镜像自行安装 Node
# FROM ubuntu:22.04
# RUN apt-get update && apt-get install -y nodejs npm
```

---

## 构建步骤（网络恢复后）

### 步骤 1: 验证网络连接

```bash
# 测试 Docker Hub 连接
docker pull hello-world

# 如果成功，继续下一步
```

### 步骤 2: 拉取基础镜像

```bash
docker pull node:18-bookworm
```

### 步骤 3: 构建 SCC 镜像

```bash
# 使用构建脚本
cd c:\scc
scripts\build-docker.bat 1.0.0 latest
```

### 步骤 4: 启动服务

```bash
cd c:\scc\docker
docker-compose up -d
```

### 步骤 5: 验证运行状态

```bash
# 查看容器状态
docker ps

# 查看日志
docker logs -f scc-server

# 测试健康检查
curl http://localhost:18788/health
```

---

## 故障排除

### 问题 1: 网络连接超时

**症状**: `dial tcp: connectex: A connection attempt failed`

**解决**:
1. 检查网络连接
2. 配置 Docker 使用国内镜像源（已完成）
3. 重启 Docker Desktop
4. 使用离线镜像导入方案

### 问题 2: 镜像构建失败

**症状**: `failed to solve: failed to fetch`

**解决**:
```bash
# 清理构建缓存
docker builder prune -f

# 重新构建
docker-compose up -d --build --no-cache
```

### 问题 3: 容器无法启动

**症状**: 容器启动后立即退出

**解决**:
```bash
# 查看详细日志
docker logs scc-server

# 进入容器调试
docker run -it --rm scc:latest /bin/bash

# 检查配置文件
docker-compose config
```

---

## 快速检查清单

构建前请确认：

- [ ] Docker Desktop 正在运行
- [ ] 网络连接正常（能访问 Docker Hub 或镜像源）
- [ ] 磁盘空间充足（至少 5GB）
- [ ] 已备份重要数据
- [ ] 已阅读 `VERSION_POLICY.md`

---

## 联系支持

- 维护者: SCC Team
- 问题反馈: 提交 Issue 到项目仓库
