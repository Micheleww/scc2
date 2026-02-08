# 统一服务器实现指南

## 架构概述

统一服务器采用业界最佳实践的企业级架构，包括：

### 核心组件

1. **应用工厂** (`core/app_factory.py`)
   - 使用工厂模式创建应用实例
   - 支持配置管理和环境隔离
   - 统一的生命周期管理

2. **生命周期管理** (`core/lifecycle.py`)
   - 启动和关闭任务注册
   - 后台任务管理
   - 资源管理

3. **服务注册表** (`core/service_registry.py`)
   - 服务注册和发现
   - 服务状态管理
   - 服务健康检查

4. **中间件系统** (`core/middleware.py`)
   - 请求ID追踪
   - 日志记录
   - 错误处理

5. **健康检查** (`core/health.py`)
   - 基本健康检查
   - 就绪检查
   - 存活检查

6. **配置管理** (`core/config.py`)
   - 基于Pydantic的配置
   - 环境变量支持
   - 配置验证

## 使用方式

### 基本启动

```bash
python main.py
```

### 环境变量配置

```bash
# 服务器配置
export UNIFIED_SERVER_HOST=0.0.0.0
export UNIFIED_SERVER_PORT=18788
export LOG_LEVEL=info
export DEBUG=false

# 服务配置
export MCP_BUS_ENABLED=true
export A2A_HUB_ENABLED=true
export EXCHANGE_SERVER_ENABLED=true
export A2A_HUB_SECRET_KEY=your_secret_key
```

### 健康检查

```bash
# 基本健康检查
curl http://localhost:18788/health

# 就绪检查（检查所有服务是否就绪）
curl http://localhost:18788/health/ready

# 存活检查
curl http://localhost:18788/health/live
```

## 扩展开发

### 添加新服务

1. 创建服务包装器类（继承`Service`基类）
2. 在`services/service_wrappers.py`中实现
3. 在`services/__init__.py`中注册

示例：

```python
class MyNewService(Service):
    def __init__(self, name: str, path: str, enabled: bool, repo_root: Path):
        super().__init__(name, enabled)
        self.path = path
        self.repo_root = repo_root
        self._app = None
    
    async def initialize(self) -> None:
        # 初始化逻辑
        self._app = create_my_service_app()
    
    async def shutdown(self) -> None:
        # 清理逻辑
        pass
    
    def get_app(self) -> Any:
        return self._app
```

### 添加新中间件

在`core/middleware.py`中创建新的中间件类：

```python
class MyCustomMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 中间件逻辑
        response = await call_next(request)
        return response
```

然后在`core/app_factory.py`中注册：

```python
app.add_middleware(MyCustomMiddleware)
```

### 添加启动/关闭任务

在`core/app_factory.py`中使用装饰器：

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

## 最佳实践

1. **配置管理**
   - 使用环境变量覆盖默认配置
   - 使用Pydantic进行配置验证
   - 敏感信息使用环境变量

2. **错误处理**
   - 使用统一的错误响应格式
   - 记录详细的错误日志
   - 不要在错误中暴露敏感信息

3. **日志记录**
   - 使用结构化日志
   - 包含请求ID追踪
   - 记录关键操作和错误

4. **性能优化**
   - 使用异步操作
   - 合理使用缓存
   - 监控性能指标

5. **安全性**
   - 使用HTTPS（生产环境）
   - 实施认证和授权
   - 限制CORS来源
   - 实施速率限制

## 监控和调试

### 日志

日志格式为结构化JSON，包含：
- 时间戳
- 日志级别
- 请求ID
- 消息内容
- 额外上下文

### 指标

可以通过`/health/ready`端点获取服务状态：
- 服务状态
- 服务健康状态
- 错误信息

### 调试

设置`DEBUG=true`启用调试模式：
- 详细的错误信息
- 请求/响应日志
- 性能分析

## 部署建议

### 开发环境

```bash
export DEBUG=true
export RELOAD=true
export LOG_LEVEL=debug
python main.py
```

### 生产环境

```bash
export DEBUG=false
export RELOAD=false
export LOG_LEVEL=info
export UNIFIED_SERVER_WORKERS=4
python main.py
```

### Docker部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

### Kubernetes部署

使用健康检查端点配置liveness和readiness probes：

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 18788
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 18788
  initialDelaySeconds: 5
  periodSeconds: 5
```
