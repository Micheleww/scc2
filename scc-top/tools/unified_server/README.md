# 统一服务器

## 概述

统一服务器将原本分散在多个端口的服务整合到一个服务器内，采用企业级架构，提高了稳定性和管理效率。

**⚠️ 重要提示：端口配置**

统一服务器默认使用 **18788** 端口（非业界常用端口），以避免与其他AI工具或服务冲突。如需修改端口，可通过环境变量 `UNIFIED_SERVER_PORT` 进行配置。

**⚠️ 端口冲突保护**

统一服务器启动时会自动检查以下端口是否被占用：
- 8080 (Exchange Server 独立运行)
- 5001 (A2A Hub 独立运行)  
- 8001 (MCP Bus 独立运行)
- 8002 (主应用服务器 独立运行)

如果检测到这些端口被占用，会显示警告。**建议停止独立服务，使用统一服务器整合所有服务**，避免冲突。

详细说明请参见：[端口冲突保护文档](PORT_CONFLICT_PROTECTION.md)

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务器

```bash
# 基本启动
python main.py

# 或使用启动脚本
python start_unified_server.py
```

### 后台运行和开机自启动

```powershell
# 后台运行
.\run_as_background_service.ps1

# 创建开机自启动（需要管理员权限）
powershell -ExecutionPolicy Bypass -File create_startup_task.ps1
```

详细部署指南请参见：[部署指南](DEPLOYMENT_GUIDE.md)

## 功能特性

### 整合的服务

1. **MCP总线服务** - 挂载到 `/mcp`
2. **A2A Hub服务** - 挂载到 `/api`
3. **Exchange Server服务** - 挂载到 `/exchange`
4. **LangGraph服务** - 挂载到 `/langgraph`
5. **Clawdbot服务** - 挂载到 `/clawdbot`

### 智能端口分配系统 ⭐ **NEW**

统一服务器内置智能端口分配系统，自动为新服务分配不常用端口（18000-19999），避免端口冲突：

- ✅ 自动分配：新服务注册时自动分配端口
- ✅ 避免冲突：自动排除常用端口（80, 443, 8080等）
- ✅ 持久化：端口分配保存到文件
- ✅ 管理工具：提供命令行工具管理端口分配

**查看端口分配：**
```bash
python manage_ports.py list
```

**通过API查看：**
```bash
curl http://localhost:18788/health/ports
```

详细说明请参见：[端口分配系统使用指南](PORT_ALLOCATION_GUIDE.md)

### 企业级架构

- ✅ 应用工厂模式
- ✅ 生命周期管理
- ✅ 服务注册表
- ✅ 中间件系统
- ✅ 健康检查系统
- ✅ 配置管理
- ✅ 优雅关闭

## 访问地址

- **统一服务器**: http://localhost:18788/
- **健康检查**: http://localhost:18788/health
- **就绪检查**: http://localhost:18788/health/ready
- **存活检查**: http://localhost:18788/health/live
- **MCP总线**: http://localhost:18788/mcp
- **A2A Hub**: http://localhost:18788/api
- **Exchange Server**: http://localhost:18788/exchange

## 测试

### 全面测试

```bash
python test_comprehensive.py
```

### 简单测试

```bash
python test_unified_server.py
```

## 文档

- [架构设计](ARCHITECTURE_DESIGN.md) - 架构设计文档
- [实现指南](IMPLEMENTATION_GUIDE.md) - 使用和扩展指南
- [架构总结](ARCHITECTURE_SUMMARY.md) - 架构总结
- [部署指南](DEPLOYMENT_GUIDE.md) - 部署和运行指南
- [企业级架构说明](README_ENTERPRISE.md) - 企业级架构详细说明
- [迁移指南](MIGRATION_GUIDE.md) - 从多端口模式迁移

## 配置

### 环境变量

```bash
# 服务器配置
export UNIFIED_SERVER_HOST=127.0.0.1
export UNIFIED_SERVER_PORT=18788
export LOG_LEVEL=info

# 服务配置
export MCP_BUS_ENABLED=true
export A2A_HUB_ENABLED=true
export EXCHANGE_SERVER_ENABLED=true
```

## 优势

1. **单一端口** - 所有服务运行在同一个端口
2. **统一管理** - 一个进程管理所有服务
3. **更高稳定性** - 避免异步启动问题
4. **资源共享** - 服务之间可以共享资源
5. **简化部署** - 只需部署一个服务器实例
6. **企业级架构** - 符合业界最佳实践

## 支持

如遇到问题，请：

1. 查看日志文件
2. 检查配置文件
3. 运行测试脚本
4. 参考文档
