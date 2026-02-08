# 统一服务器 - 企业级架构

## 🏗️ 架构概述

统一服务器采用业界最佳实践的企业级架构，参考了FastAPI、Flask、Django等成熟框架的设计模式。

## ✨ 核心特性

### 1. 应用工厂模式
- 通过`create_app()`工厂函数创建应用
- 支持配置管理和环境隔离
- 便于测试和部署

### 2. 生命周期管理
- 使用FastAPI的`lifespan` context manager
- 统一的启动和关闭流程
- 资源自动清理

### 3. 服务注册表
- 统一管理所有服务
- 服务自动发现和初始化
- 服务健康状态监控

### 4. 中间件系统
- 可重用的中间件类
- 请求ID追踪
- 结构化日志
- 统一错误处理

### 5. 健康检查
- `/health` - 基本健康检查
- `/health/ready` - 就绪检查（Kubernetes兼容）
- `/health/live` - 存活检查（Kubernetes兼容）

### 6. 配置管理
- 基于Pydantic的配置验证
- 环境变量支持
- 类型安全

### 7. 优雅关闭
- 信号处理（SIGTERM, SIGINT）
- 等待请求完成
- 资源清理

## 📁 项目结构

```
unified_server/
├── core/                    # 核心模块
│   ├── __init__.py
│   ├── app_factory.py      # 应用工厂
│   ├── config.py            # 配置管理
│   ├── lifecycle.py         # 生命周期管理
│   ├── middleware.py         # 中间件
│   ├── service_registry.py   # 服务注册表
│   └── health.py            # 健康检查
├── services/                # 服务集成
│   ├── __init__.py
│   └── service_wrappers.py  # 服务包装器
├── main.py                  # 入口文件
├── requirements.txt         # 依赖
└── README.md               # 文档
```

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务器

```bash
python main.py
```

## 🧰 Windows Service（推荐：无需登录常驻）

以管理员 PowerShell 运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\unified_server\install_windows_service_watchdog.ps1
```

卸载：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\unified_server\uninstall_windows_service_watchdog.ps1
```

说明：该服务运行 `tools\unified_server\run_watchdog.cmd`，watchdog 负责健康检查并在异常时拉起/重启 unified_server（默认端口 `127.0.0.1:18788`）。

### 配置环境变量

```bash
# 服务器配置
export UNIFIED_SERVER_HOST=0.0.0.0
export UNIFIED_SERVER_PORT=18788
export LOG_LEVEL=info

# 服务配置
export MCP_BUS_ENABLED=true
export A2A_HUB_ENABLED=true
export EXCHANGE_SERVER_ENABLED=true
```

## 📊 健康检查

### 基本健康检查

```bash
curl http://localhost:18788/health
```

响应：
```json
{
  "status": "healthy",
  "service": "unified_server"
}
```

### 就绪检查

```bash
curl http://localhost:18788/health/ready
```

响应：
```json
{
  "status": "ready",
  "services": {
    "mcp_bus": {
      "status": "ready",
      "enabled": true,
      "ready": true,
      "healthy": true
    },
    ...
  }
}
```

### 存活检查

```bash
curl http://localhost:18788/health/live
```

## 🔧 扩展开发

### 添加新服务

1. 在`services/service_wrappers.py`中创建服务类
2. 在`services/__init__.py`中注册服务
3. 服务会自动初始化和挂载

### 添加新中间件

1. 在`core/middleware.py`中创建中间件类
2. 在`core/app_factory.py`中注册中间件

### 添加启动/关闭任务

使用装饰器注册任务：

```python
@lifecycle.register_startup
async def my_startup_task():
    # 启动逻辑
    pass

@lifecycle.register_shutdown
async def my_shutdown_task():
    # 关闭逻辑
    pass
```

## 📚 参考文档

- [架构设计文档](ARCHITECTURE_DESIGN.md)
- [实现指南](IMPLEMENTATION_GUIDE.md)
- [架构总结](ARCHITECTURE_SUMMARY.md)

## 🎯 业界最佳实践对照

| 最佳实践 | 实现 |
|---------|------|
| 应用工厂模式 | ✅ `core/app_factory.py` |
| 生命周期管理 | ✅ `core/lifecycle.py` |
| 服务注册表 | ✅ `core/service_registry.py` |
| 中间件系统 | ✅ `core/middleware.py` |
| 健康检查 | ✅ `core/health.py` |
| 配置管理 | ✅ `core/config.py` |
| 优雅关闭 | ✅ 信号处理 |
| 依赖注入 | ✅ FastAPI内置 |
| 错误处理 | ✅ 统一错误处理 |
| 日志记录 | ✅ 结构化日志 |

## 🔄 与简单实现的对比

### 之前（简单实现）
- 直接创建应用
- 手动挂载服务
- 简单的启动逻辑
- 无生命周期管理
- 无健康检查

### 现在（企业级架构）
- 应用工厂模式
- 服务自动注册和初始化
- 完整的生命周期管理
- 健康检查系统
- 中间件系统
- 配置管理
- 优雅关闭

## 📈 优势

1. **可扩展性** - 易于添加新服务和新功能
2. **可维护性** - 清晰的架构和职责分离
3. **可测试性** - 支持依赖注入和配置隔离
4. **可观测性** - 完整的日志和健康检查
5. **可靠性** - 优雅关闭和错误处理
6. **符合标准** - 遵循业界最佳实践
