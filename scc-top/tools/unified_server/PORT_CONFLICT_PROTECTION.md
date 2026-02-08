# 端口冲突保护说明

## 问题说明

统一服务器整合了以下服务：
- **Exchange Server** (原端口: 8080)
- **A2A Hub** (原端口: 5001)  
- **MCP Bus** (原端口: 8001)
- **LangGraph** (原端口: 无独立端口)
- **Clawdbot** (代理到Gateway: 19001)

如果这些原始服务文件被直接执行（如 `python tools/exchange_server/main.py`），它们会启动独立的服务器，占用8080、5001等端口，与统一服务器冲突。

## 保护机制

### 1. 统一服务器使用模块导入

统一服务器通过 `importlib.util.spec_from_file_location` 导入服务模块，**不会触发** `if __name__ == "__main__":` 代码块，因此不会启动独立服务器。

### 2. 环境变量保护

在统一服务器启动时，设置环境变量 `UNIFIED_SERVER_MODE=true`，原始服务可以检查此变量，避免在统一服务器环境中启动。

### 3. 端口检查

统一服务器启动时会检查端口是否被占用，如果发现冲突会报错退出。

## 建议

1. **不要同时运行独立服务和统一服务器**
   - 如果使用统一服务器，不要单独运行 `tools/exchange_server/main.py` 或 `tools/a2a_hub/main.py`
   - 统一服务器已经整合了所有服务

2. **使用统一服务器（推荐）**
   ```bash
   cd tools/unified_server
   python start_unified_server.py
   ```

3. **如果必须使用独立服务**
   - 确保统一服务器未运行
   - 或者修改独立服务的端口配置，避免冲突

## 端口使用情况

| 服务 | 原独立端口 | 统一服务器路径 | 说明 |
|------|-----------|---------------|------|
| Exchange Server | 8080 | `/exchange` | 已整合，不再使用8080 |
| A2A Hub | 5001 | `/api` | 已整合，不再使用5001 |
| MCP Bus | 8001 | `/mcp` | 已整合，不再使用8001 |
| LangGraph | 无 | `/langgraph` | 已整合 |
| Clawdbot | 19001 (Gateway) | `/clawdbot` | 代理模式，Gateway仍使用19001 |
| **统一服务器** | **18788** | `/` | **主端口** |

## 检查端口占用

```bash
# Windows
netstat -ano | findstr :8080
netstat -ano | findstr :5001
netstat -ano | findstr :8001
netstat -ano | findstr :18788

# Linux/Mac
lsof -i :8080
lsof -i :5001
lsof -i :8001
lsof -i :18788
```

## 故障排除

如果遇到端口冲突：

1. **检查是否有独立服务在运行**
   ```bash
   # 查找占用端口的进程
   netstat -ano | findstr :8080
   ```

2. **停止独立服务**
   - 找到进程ID (PID)
   - 终止进程：`taskkill /PID <pid> /F` (Windows) 或 `kill <pid>` (Linux/Mac)

3. **确保统一服务器未重复启动**
   - 检查是否有多个统一服务器实例在运行

4. **使用统一服务器（推荐）**
   - 统一服务器已经整合所有服务，无需单独启动
