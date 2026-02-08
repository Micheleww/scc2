# 客户端适配指南

## 概述

统一服务器将所有服务整合到单一端口（18788），路径前缀如下：
- `/mcp` - MCP总线服务
- `/api` - A2A Hub服务
- `/exchange` - Exchange Server服务

## 路径映射

### 原多端口模式 → 统一服务器

| 原服务 | 原端口 | 原路径 | 新路径 | 说明 |
|--------|--------|--------|--------|------|
| MCP总线 | 8001 | `/mcp` | `/mcp` | 保持不变 |
| A2A Hub | 5001 | `/api/*` | `/api/*` | 保持不变 |
| Exchange Server | 8080 | `/mcp` | `/exchange/mcp` | 路径前缀变化 |
| Exchange Server | 8080 | `/sse` | `/exchange/sse` | 路径前缀变化 |
| Exchange Server | 8080 | `/version` | `/exchange/version` | 路径前缀变化 |

## 客户端配置更新

### 1. TRAE MCP客户端

**配置文件**: `.trae/mcp.json`

**更新前**:
```json
{
  "mcpServers": {
    "qcc-bus-local": {
      "transport": {
        "type": "http",
        "url": "http://localhost:18788/mcp"
      }
    }
  }
}
```

**更新后**:
```json
{
  "mcpServers": {
    "qcc-bus-local": {
      "transport": {
        "type": "http",
        "url": "http://localhost:18788/mcp"
      },
      "auth": {
        "type": "none"
      },
      "description": "本地统一服务器 - MCP总线服务",
      "enabled": true
    }
  }
}
```

### 2. Python客户端

**更新前**:
```python
MCP_URL = "http://localhost:18788/mcp"
A2A_HUB_URL = "http://localhost:18788/api"
EXCHANGE_URL = "http://localhost:18788/"
```

**更新后**:
```python
UNIFIED_SERVER_URL = "http://localhost:18788"
MCP_URL = f"{UNIFIED_SERVER_URL}/mcp"
A2A_HUB_URL = f"{UNIFIED_SERVER_URL}/api"
EXCHANGE_URL = f"{UNIFIED_SERVER_URL}/exchange"
```

### 3. JavaScript客户端

**更新前**:
```javascript
const MCP_URL = 'http://localhost:18788/mcp';
const A2A_HUB_URL = 'http://localhost:18788/api';
const EXCHANGE_URL = 'http://localhost:18788/';
```

**更新后**:
```javascript
const UNIFIED_SERVER_URL = 'http://localhost:18788';
const MCP_URL = `${UNIFIED_SERVER_URL}/mcp`;
const A2A_HUB_URL = `${UNIFIED_SERVER_URL}/api`;
const EXCHANGE_URL = `${UNIFIED_SERVER_URL}/exchange`;
```

### 4. Exchange Server客户端

**更新前**:
```python
# JSON-RPC端点
EXCHANGE_MCP_URL = "http://localhost:18788/mcp"

# SSE端点
EXCHANGE_SSE_URL = "http://localhost:18788/sse"
```

**更新后**:
```python
# JSON-RPC端点
EXCHANGE_MCP_URL = "http://localhost:18788/exchange/mcp"

# SSE端点
EXCHANGE_SSE_URL = "http://localhost:18788/exchange/sse"
```

## 自动适配

统一服务器提供了自动适配功能：

### 1. 路径适配中间件

自动处理路径映射，确保向后兼容。

### 2. 请求ID传播

自动在所有服务间传播请求ID，便于追踪。

### 3. CORS适配

自动处理跨域请求，确保所有服务都能正确响应。

## 测试适配

### 测试MCP连接

```bash
# 测试MCP工具列表
curl -X POST http://localhost:18788/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tools/list"
  }'
```

### 测试A2A Hub

```bash
# 测试健康检查
curl http://localhost:18788/api/health

# 测试任务创建
curl -X POST http://localhost:18788/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_code": "TEST-001",
    "instructions": "Test task",
    "owner_role": "admin"
  }'
```

### 测试Exchange Server

```bash
# 测试版本端点
curl http://localhost:18788/exchange/version

# 测试JSON-RPC
curl -X POST http://localhost:18788/exchange/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tools/list"
  }'
```

## 常见问题

### Q1: 应用无法连接到服务器

**检查**:
1. 服务器是否运行: `curl http://localhost:18788/health`
2. 端口是否正确: 统一使用18788端口
3. 路径是否正确: 检查路径前缀

### Q2: 404错误

**原因**: 路径前缀不正确

**解决**: 使用正确的路径前缀：
- MCP: `/mcp`
- A2A Hub: `/api`
- Exchange Server: `/exchange`

### Q3: CORS错误

**解决**: 统一服务器已自动处理CORS，如果仍有问题，检查：
1. 请求头是否正确
2. 预检请求是否通过

### Q4: 请求ID丢失

**解决**: 统一服务器自动传播请求ID，确保：
1. 请求包含`X-Request-ID`或`X-Trace-ID`头
2. 响应会包含相同的请求ID

## 迁移检查清单

- [ ] 更新TRAE MCP配置 (`.trae/mcp.json`)
- [ ] 更新Python客户端配置
- [ ] 更新JavaScript客户端配置
- [ ] 更新Exchange Server客户端配置
- [ ] 测试所有端点连接
- [ ] 验证请求ID传播
- [ ] 验证CORS处理
- [ ] 更新文档中的URL引用

## 向后兼容

统一服务器支持向后兼容：

1. **路径自动适配** - 旧路径会自动映射到新路径
2. **请求头兼容** - 支持旧的请求头格式
3. **响应格式兼容** - 响应格式保持不变

## 配置生成工具

使用配置生成工具自动生成客户端配置：

```python
from core.client_config import generate_client_config_file

# 生成TRAE配置
generate_client_config_file("trae_mcp", ".trae/mcp.json")

# 生成Python客户端代码
generate_client_config_file("python_client", "client_example.py")
```
