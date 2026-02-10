# MCP Bus 软件集成使用指南

本文档介绍如何使用已集成的软件功能。

---

## 1. Browser-Tools-MCP（浏览器审计）

### 前置条件

1. **启动Browser-Tools-Server:**
   ```bash
   cd tools/browser-tools-mcp/browser-tools-server
   npm install
   npm start
   ```
   服务器默认运行在 `http://127.0.0.1:3025`

2. **安装Chrome扩展（可选）:**
   - 从 [BrowserTools MCP Releases](https://github.com/AgentDeskAI/browser-tools-mcp/releases) 下载扩展
   - 在Chrome中加载扩展

### 使用方式

#### 方式1: 网页界面

1. 访问 `http://localhost:18788/browser-tools`
2. 输入要审计的URL（如 `http://localhost:18788/`）
3. 选择审计类型：
   - **可访问性审计** - WCAG合规性检查
   - **性能审计** - Lighthouse性能分析
   - **SEO审计** - 搜索引擎优化检查
   - **最佳实践** - Web开发最佳实践
   - **全部审计** - 运行所有审计类型
4. 查看审计结果

#### 方式2: API调用

```bash
# 可访问性审计
curl -X POST http://localhost:18788/api/browser-tools/audit/accessibility \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:18788/"}'

# 性能审计
curl -X POST http://localhost:18788/api/browser-tools/audit/performance \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:18788/"}'

# 完整审计
curl -X POST http://localhost:18788/api/browser-tools/audit/all \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:18788/"}'

# 检查服务器状态
curl http://localhost:18788/api/browser-tools/status
```

### API端点

- `GET /api/browser-tools/status` - 检查服务器状态
- `POST /api/browser-tools/audit/accessibility` - 可访问性审计
- `POST /api/browser-tools/audit/performance` - 性能审计
- `POST /api/browser-tools/audit/seo` - SEO审计
- `POST /api/browser-tools/audit/best-practices` - 最佳实践审计
- `POST /api/browser-tools/audit/all` - 完整审计
- `POST /api/browser-tools/screenshot` - 截图捕获
- `GET /api/browser-tools/logs/console` - 控制台日志
- `GET /api/browser-tools/logs/network` - 网络日志

---

## 2. Desktop Tray App（系统托盘应用）

### 前置条件

1. **安装依赖:**
   ```bash
   pip install pystray pillow PyQt5 httpx
   ```

2. **确保MCP Bus服务器运行:**
   - MCP Bus应运行在 `http://127.0.0.1:18788/`

### 使用方式

1. **启动应用:**
   ```bash
   python tools/desktop/ata_tray_app.py
   ```

2. **使用托盘图标:**
   - 系统托盘会出现ATA图标（紫色圆圈，白色"A"）
   - 右键点击图标，选择"打开对话窗口"

3. **发送消息:**
   - 选择接收者（自动路由或指定代理）
   - 选择通知方式（ATA消息、桌面通知、企业微信、全部）
   - 输入消息并点击"发送"或按Enter

4. **查看响应:**
   - 消息发送结果会显示在对话区域
   - 可以清空历史记录

### 功能特性

- ✅ 系统托盘图标，随时可访问
- ✅ 通过ATA系统发送消息
- ✅ 自动加载代理列表
- ✅ 支持多种通知方式
- ✅ 对话历史记录

---

## 3. Cursor10x（记忆系统）

### 前置条件

1. **配置Turso数据库:**
   ```bash
   # 安装Turso CLI
   curl -sSfL https://get.turso.tech/install.sh | bash
   
   # 登录
   turso auth login
   
   # 创建数据库
   turso db create cursor10x-mcp
   
   # 获取URL和Token
   turso db show cursor10x-mcp --url
   turso db tokens create cursor10x-mcp
   ```

2. **设置环境变量:**
   ```bash
   export TURSO_DATABASE_URL="your-turso-url"
   export TURSO_AUTH_TOKEN="your-turso-token"
   export CURSOR10X_ENABLED="true"
   ```

3. **安装cursor10x-mcp:**
   ```bash
   npm install -g cursor10x-mcp
   ```

### 使用方式

#### 方式1: API调用

```bash
# 检查状态
curl http://localhost:18788/api/cursor10x/status

# 存储记忆
curl -X POST http://localhost:18788/api/cursor10x/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "content": "项目使用FastAPI框架",
    "memory_type": "long_term",
    "importance": 8
  }'

# 检索记忆
curl -X POST http://localhost:18788/api/cursor10x/memory/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "FastAPI",
    "limit": 10
  }'

# 获取统计
curl http://localhost:18788/api/cursor10x/memory/stats

# 健康检查
curl http://localhost:18788/api/cursor10x/health
```

#### 方式2: 在代码中使用

```python
from tools.mcp_bus.server.cursor10x_integration import get_cursor10x_integration

integration = get_cursor10x_integration()

# 存储记忆
result = await integration.store_memory(
    content="项目使用FastAPI框架",
    memory_type="long_term",
    importance=8
)

# 检索记忆
result = await integration.retrieve_memory(
    query="FastAPI",
    limit=10
)
```

### API端点

- `GET /api/cursor10x/status` - 检查状态
- `POST /api/cursor10x/memory/store` - 存储记忆
- `POST /api/cursor10x/memory/retrieve` - 检索记忆
- `GET /api/cursor10x/memory/stats` - 获取统计
- `GET /api/cursor10x/health` - 健康检查

### 注意事项

- Cursor10x需要通过MCP协议调用cursor10x-mcp
- 确保cursor10x-mcp已正确安装并可用
- 如果遇到问题，检查环境变量和Turso数据库连接

---

## 4. 配置管理

### 使用方式

1. **访问配置管理页面:**
   ```
   http://localhost:18788/configs
   ```

2. **或使用API:**
   ```bash
   # 列出配置
   curl http://localhost:18788/api/configs/list
   
   # 获取配置
   curl http://localhost:18788/api/configs/config.json
   
   # 保存配置
   curl -X POST http://localhost:18788/api/configs/config.json \
     -H "Content-Type: application/json" \
     -d '{"config": {...}}'
   ```

---

## 5. 故障排除

### Browser-Tools-MCP

**问题:** 服务器不可用
- 检查browser-tools-server是否运行
- 检查端口3025是否被占用
- 查看服务器日志

**问题:** 审计失败
- 确保URL可访问
- 检查Chrome扩展是否安装（如果需要）

### Desktop Tray App

**问题:** 应用无法启动
- 检查依赖是否安装: `pip install pystray pillow PyQt5 httpx`
- 检查MCP Bus服务器是否运行

**问题:** 消息发送失败
- 检查MCP Bus服务器地址是否正确
- 检查网络连接

### Cursor10x

**问题:** 未启用
- 检查环境变量: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `CURSOR10X_ENABLED`
- 确保cursor10x-mcp已安装

**问题:** MCP调用失败
- 检查cursor10x-mcp是否正确安装: `npx cursor10x-mcp --version`
- 检查Turso数据库连接
- 查看日志获取详细错误信息

---

## 6. 快速开始

### 完整启动流程

1. **启动MCP Bus服务器:**
   ```bash
   cd tools/mcp_bus
   python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
   ```

2. **启动Browser-Tools-Server（可选）:**
   ```bash
   cd tools/browser-tools-mcp/browser-tools-server
   npm start
   ```

3. **启动Desktop Tray App（可选）:**
   ```bash
   python tools/desktop/ata_tray_app.py
   ```

4. **访问网页界面:**
   - 消息查看器: `http://localhost:18788/viewer`
   - 配置管理: `http://localhost:18788/configs`
   - 浏览器审计: `http://localhost:18788/browser-tools`
   - 对话系统: `http://localhost:18788/chat`

---

**最后更新:** 2026-01-21
