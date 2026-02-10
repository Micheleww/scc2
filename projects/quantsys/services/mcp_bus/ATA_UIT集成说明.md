
# ATA与UI-TARS集成服务说明

## 📋 功能概述

当ATA系统中的user_ai收到消息时，自动触发UI-TARS发送提醒，实现一一对应通知。

## 🎯 核心功能

1. **自动检测新消息**：定期检查所有user_ai的未读ATA消息
2. **自动发送提醒**：通过UI-TARS底层代码层发送提醒消息
3. **一一对应**：每个user_ai收到消息都会收到对应的UIT提醒
4. **避免重复**：已处理的消息不会重复提醒

## 🚀 使用方法

### 方式1: 持续运行（推荐）

```bash
cd tools/mcp_bus
python ata_uit_integration.py --repo-root ../../ --check-interval 30
```

参数说明：
- `--repo-root`: 项目根目录（默认: 当前目录）
- `--check-interval`: 检查间隔（秒，默认: 30）
- 按 `Ctrl+C` 停止

### 方式2: 单次检查

```bash
cd tools/mcp_bus
python ata_uit_integration.py --repo-root ../../ --once
```

## 📊 工作流程

```
1. 加载Agent注册表
   ↓
2. 筛选所有user_ai类型的agent
   ↓
3. 对每个user_ai:
   a. 调用ata_receive检查未读消息
   b. 过滤已处理的消息
   c. 如果有新消息 → 发送UI-TARS提醒
   ↓
4. 等待指定间隔后重复
```

## 🔧 技术实现

### 1. Agent识别

- **user_ai**: `category == "user_ai"` 或 `numeric_code > 10`
- **system_ai**: `category == "system_ai"` 或 `1 <= numeric_code <= 10`

### 2. 消息检测

- 从 `mvm/ata/messages/` 目录读取消息文件
- 按 `to_agent` 过滤
- 按 `status` 过滤未读消息（`pending` 或 `delivered`）

### 3. UI-TARS消息发送

- 使用底层IPC文件机制
- 触发文件位置：`%TEMP%/ui-tars-ipc/send_message_*.json`
- 文件格式：
  ```json
  {
    "action": "sendMessage",
    "message": "请查看ATA收件箱。您有 X 条新消息。",
    "timestamp": 1234567890
  }
  ```

## 📝 提醒消息格式

默认提醒消息：
```
请查看ATA收件箱。您有 X 条新消息。
```

可以根据需要自定义消息格式。

## 🔍 日志

日志文件：`ata_uit_integration.log`

日志级别：
- `INFO`: 正常运行信息
- `WARNING`: 警告信息（如文件不存在）
- `ERROR`: 错误信息

## ⚙️ 配置

### Agent注册表

位置：`.cursor/agent_registry.json`

格式：
```json
{
  "agents": {
    "agent_id": {
      "agent_id": "agent_id",
      "numeric_code": 99,
      "category": "user_ai",
      ...
    }
  }
}
```

### ATA消息目录

位置：`mvm/ata/messages/<taskcode>/<msg_id>.json`

## 🎯 使用场景

### 场景1: 2号交易模块收到消息

1. 另一个AI发送消息给 `numeric_code=2` 的agent
2. 集成服务检测到新消息
3. 如果该agent是user_ai，发送UI-TARS提醒
4. 用户在Cursor对话框中看到："请查看ATA收件箱"

### 场景2: 多个user_ai同时收到消息

- 每个user_ai独立检查
- 每个user_ai独立发送提醒
- 一一对应，互不干扰

## 🔄 与现有系统集成

### 与MCP Bus集成

可以扩展为MCP工具，通过MCP协议调用：

```python
# 未来可以添加为MCP工具
{
  "name": "ata_uit_check",
  "description": "检查并发送UI-TARS提醒"
}
```

### 与UI-TARS集成

- 使用现有的IPC文件监听机制
- 无需修改UI-TARS代码
- 完全解耦，独立运行

## 📋 注意事项

1. **消息去重**：使用 `msg_id` 避免重复提醒
2. **性能考虑**：检查间隔建议30秒以上
3. **错误处理**：单个agent出错不影响其他agent
4. **日志记录**：所有操作都有日志记录

## 🐛 故障排查

### 问题1: 没有发送提醒

检查：
1. Agent是否注册为user_ai
2. 是否有未读消息
3. UI-TARS是否运行
4. IPC目录是否可写

### 问题2: 重复提醒

检查：
1. `processed_message_ids` 是否正确维护
2. `msg_id` 是否唯一

### 问题3: 日志文件过大

定期清理或配置日志轮转。

## 📚 相关文档

- UI-TARS底层代码层通信：`tools/ui-tars-desktop/主进程代码层通信实现.md`
- ATA消息系统：`tools/mcp_bus/server/tools.py` (ata_receive)
- Agent注册：`tools/mcp_bus/server/coordinator.py`
