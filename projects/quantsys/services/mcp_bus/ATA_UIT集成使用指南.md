# ATA与UI-TARS集成使用指南

## 🎯 功能说明

当ATA系统中的**user_ai**收到消息时，自动触发UI-TARS发送提醒，实现一一对应通知。

### 核心特性

- ✅ **自动检测**：定期检查所有user_ai的未读ATA消息
- ✅ **自动提醒**：通过UI-TARS底层代码层发送提醒
- ✅ **一一对应**：每个user_ai收到消息都有对应的UIT提醒
- ✅ **避免重复**：已处理的消息不会重复提醒

## 🚀 快速开始

### 方式1: 使用启动脚本（推荐）

**Windows (批处理)**:
```bash
cd tools/mcp_bus
启动ATA_UIT集成服务.bat
```

**Windows (PowerShell)**:
```powershell
cd tools/mcp_bus
.\启动ATA_UIT集成服务.ps1
```

### 方式2: 直接运行Python

**持续运行**:
```bash
cd tools/mcp_bus
python ata_uit_integration.py --repo-root ../../ --check-interval 30
```

**单次检查**:
```bash
cd tools/mcp_bus
python ata_uit_integration.py --repo-root ../../ --once
```

## 📋 使用场景

### 场景1: 2号交易模块收到消息

1. **另一个AI发送消息**给 `numeric_code=2` 的agent
2. **集成服务检测**到新消息（如果该agent是user_ai）
3. **自动发送UI-TARS提醒**："请查看ATA收件箱。您有 X 条新消息。"
4. **用户在Cursor对话框**中看到提醒

### 场景2: 多个user_ai同时收到消息

- 每个user_ai独立检查
- 每个user_ai独立发送提醒
- 一一对应，互不干扰

## 🔧 配置说明

### Agent识别规则

- **user_ai**: 
  - `category == "user_ai"` 
  - 或 `numeric_code > 10`（如果没有category字段）
- **system_ai**: 
  - `category == "system_ai"` 
  - 或 `1 <= numeric_code <= 10`（如果没有category字段）

**只有user_ai会收到UI-TARS提醒**

### 消息检测规则

- 从 `mvm/ata/messages/` 目录读取消息文件
- 按 `to_agent` 过滤（只检查发送给该agent的消息）
- 按 `status` 过滤未读消息（`pending` 或 `delivered`）

### UI-TARS消息发送

- 使用底层IPC文件机制
- 触发文件位置：`%TEMP%/ui-tars-ipc/send_message_*.json`
- UI-TARS会自动监听并处理这些文件

## 📊 工作流程

```
┌─────────────────────────────────────────┐
│  1. 加载Agent注册表                      │
│     .cursor/agent_registry.json          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  2. 筛选所有user_ai类型的agent           │
│     (category == "user_ai" 或            │
│      numeric_code > 10)                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  3. 对每个user_ai:                      │
│     a. 调用ata_receive检查未读消息       │
│     b. 过滤已处理的消息                  │
│     c. 如果有新消息 → 发送UI-TARS提醒    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  4. 等待指定间隔后重复                   │
│     (默认30秒)                           │
└─────────────────────────────────────────┘
```

## 📝 提醒消息格式

默认提醒消息：
```
请查看ATA收件箱。您有 X 条新消息。
```

可以根据需要修改 `ata_uit_integration.py` 中的消息格式。

## 🔍 日志和监控

### 日志文件

位置：`tools/mcp_bus/ata_uit_integration.log`

日志级别：
- `INFO`: 正常运行信息
- `WARNING`: 警告信息（如文件不存在）
- `ERROR`: 错误信息

### 示例日志

```
2026-01-22 15:10:27 [INFO] 初始化ATA-UI-TARS集成服务
2026-01-22 15:10:27 [INFO] 找到 2 个user_ai agent
2026-01-22 15:10:27 [INFO] ✅ 已为 agent_id 发送UI-TARS提醒 (新消息: 1条)
```

## ⚙️ 参数说明

### 命令行参数

- `--repo-root`: 项目根目录（默认: 当前目录）
- `--check-interval`: 检查间隔（秒，默认: 30）
- `--once`: 只检查一次，不持续运行

### 环境要求

- Python 3.7+
- UI-TARS Desktop 正在运行
- Agent已注册（`.cursor/agent_registry.json`）
- ATA消息目录存在（`mvm/ata/messages/`）

## 🐛 故障排查

### 问题1: 没有发送提醒

**检查清单**:
1. ✅ Agent是否注册为user_ai（`category == "user_ai"`）
2. ✅ 是否有未读消息（`status` 为 `pending` 或 `delivered`）
3. ✅ UI-TARS是否正在运行
4. ✅ IPC目录是否可写（`%TEMP%/ui-tars-ipc`）
5. ✅ 查看日志文件：`ata_uit_integration.log`

### 问题2: 重复提醒

**检查清单**:
1. ✅ `processed_message_ids` 是否正确维护
2. ✅ `msg_id` 是否唯一（使用 `taskcode/filename` 格式）

### 问题3: 日志文件过大

**解决方案**:
- 定期清理日志文件
- 或配置日志轮转（修改代码中的logging配置）

## 📚 相关文档

- **详细技术文档**: `ATA_UIT集成说明.md`
- **UI-TARS底层通信**: `../ui-tars-desktop/主进程代码层通信实现.md`
- **ATA消息系统**: `server/tools.py` (ata_receive方法)
- **Agent注册**: `server/coordinator.py`

## 🔄 与现有系统集成

### 与MCP Bus集成

可以扩展为MCP工具，通过MCP协议调用（未来功能）。

### 与UI-TARS集成

- 使用现有的IPC文件监听机制
- 无需修改UI-TARS代码
- 完全解耦，独立运行

## 💡 最佳实践

1. **检查间隔**：建议30秒以上，避免过于频繁
2. **后台运行**：可以使用 `nohup` 或 Windows服务方式后台运行
3. **监控日志**：定期查看日志，确保服务正常运行
4. **错误处理**：单个agent出错不影响其他agent

## 🎯 下一步

1. **测试场景**：发送一条测试消息给某个user_ai，验证提醒是否正常
2. **监控运行**：启动服务后，观察日志输出
3. **自定义消息**：根据需要修改提醒消息格式
