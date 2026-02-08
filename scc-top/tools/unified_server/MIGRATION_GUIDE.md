# 统一服务器迁移指南

## 概述

统一服务器将原本分散在多个端口的服务整合到一个服务器内，提高了稳定性和管理效率。

## 迁移前准备

### 1. 备份当前配置

在迁移前，请备份以下配置文件：

- `tools/mcp_bus/.env`
- `tools/a2a_hub/` 目录下的配置文件
- `tools/exchange_server/` 目录下的配置文件

### 2. 停止现有服务

确保所有独立运行的服务都已停止：

```bash
# Windows PowerShell
Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Stop-Process -Force

# 或手动停止各个服务
# 停止MCP总线（如果正在运行）
# 停止A2A Hub（如果正在运行）
# 停止Exchange Server（如果正在运行）
```

## 迁移步骤

### 步骤1：安装依赖

确保已安装必要的Python包：

```bash
pip install fastapi uvicorn
```

### 步骤2：启动统一服务器

#### Windows (PowerShell)

```powershell
cd <REPO_ROOT>/tools/unified_server
.\start_unified_server.ps1
```

#### Linux/Mac

```bash
cd tools/unified_server
python start_unified_server.py
```

### 步骤3：验证服务

打开浏览器访问以下地址验证服务是否正常：

- 统一服务器根路径: http://localhost:18788/
- 健康检查: http://localhost:18788/health
- MCP总线: http://localhost:18788/mcp
- A2A Hub: http://localhost:18788/api
- Exchange Server: http://localhost:18788/exchange

### 步骤4：更新客户端配置

#### MCP客户端

将MCP客户端配置从：
```
http://localhost:18788/mcp
```

更新为：
```
http://localhost:18788/mcp
```

#### A2A客户端

将A2A客户端配置从：
```
http://localhost:18788/api
```

更新为：
```
http://localhost:18788/api
```

#### Exchange客户端

将Exchange客户端配置从：
```
http://localhost:18788/mcp
```

更新为：
```
http://localhost:18788/exchange/mcp
```

## 端口映射

| 原服务 | 原端口 | 新路径 | 说明 |
|--------|--------|--------|------|
| MCP总线 | 8001 | /mcp | 保持不变 |
| A2A Hub | 5001 | /api | 保持不变 |
| Exchange Server | 8080 | /exchange | 路径前缀变化 |

## 环境变量

统一服务器支持以下环境变量：

### 统一服务器配置

- `UNIFIED_SERVER_HOST`: 服务器监听地址（默认：127.0.0.1）
- `UNIFIED_SERVER_PORT`: 服务器监听端口（默认：18788）
- `LOG_LEVEL`: 日志级别（默认：info）

### 各服务原有环境变量

各服务仍然支持原有的环境变量配置，例如：

- **MCP总线**：
  - `MCP_BUS_HOST`
  - `MCP_BUS_PORT`
  - `AUTH_MODE`
  - `AUTO_START_FREQTRADE`

- **A2A Hub**：
  - `A2A_HUB_SECRET_KEY`

- **Exchange Server**：
  - `EXCHANGE_JSONRPC_AUTH_TYPE`
  - `EXCHANGE_SSE_AUTH_MODE`
  - `EXCHANGE_BEARER_TOKEN`

## 常见问题

### Q1: 端口18788已被占用怎么办？

A: 可以更改统一服务器的端口：

```bash
export UNIFIED_SERVER_PORT=18788
python start_unified_server.py
```

### Q2: 如何查看服务日志？

A: 统一服务器的日志会直接输出到控制台。如果需要保存日志，可以使用重定向：

```bash
python start_unified_server.py > unified_server.log 2>&1
```

### Q3: 如何停止统一服务器？

A: 在运行服务器的终端中按 `Ctrl+C`，或使用以下命令（Windows）：

```powershell
Get-Process | Where-Object {$_.CommandLine -like "*start_unified_server*"} | Stop-Process
```

### Q4: 统一服务器启动失败怎么办？

A: 检查以下几点：

1. 确保所有依赖已安装
2. 检查端口是否被占用
3. 查看错误日志，定位具体问题
4. 确保各服务的配置文件正确

### Q5: 可以同时运行统一服务器和独立服务吗？

A: 不建议同时运行，因为：

1. 端口可能冲突
2. 资源可能重复使用
3. 可能导致数据不一致

建议完全迁移到统一服务器后，停止所有独立服务。

## 回滚方案

如果需要回滚到多端口模式：

1. 停止统一服务器
2. 按照原来的方式启动各个独立服务
3. 恢复客户端配置到原来的端口

## 性能优化建议

1. **调整工作进程数**：根据服务器性能调整uvicorn的workers数量
2. **启用Gzip压缩**：统一服务器默认启用Gzip压缩
3. **配置反向代理**：在生产环境中，建议使用nginx等反向代理

## 技术支持

如遇到问题，请：

1. 查看日志文件
2. 检查配置文件
3. 参考README.md文档
4. 提交Issue到项目仓库
